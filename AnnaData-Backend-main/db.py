"""
Postgres access for farmer profiles and message history.

Entirely optional, in keeping with the rest of the service: with no DATABASE_URL
the pool is never created, is_available() reports False, and every caller falls
back to the stateless behaviour the agent had before. Nothing here should ever
be the reason a farmer does not get an answer, so all failures are caught and
logged rather than raised.
"""
import threading

from config import DATABASE_URL, DB_POOL_MAX

_pool = None
_init_error: str | None = None
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS farmers (
    user_id           TEXT PRIMARY KEY,
    channel           TEXT NOT NULL DEFAULT 'sms',
    location_text     TEXT,
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    state             TEXT,
    district          TEXT,
    language          TEXT,
    crops             TEXT[] NOT NULL DEFAULT '{}',
    location_asked_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id                 BIGSERIAL PRIMARY KEY,
    user_id            TEXT NOT NULL,
    direction          TEXT NOT NULL,
    body               TEXT NOT NULL,
    gateway_message_id TEXT UNIQUE,
    meta               JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_user_time
    ON messages (user_id, created_at DESC);
"""


# Everything added after the first farmers who were already in the table.
#
# Kept apart from SCHEMA and written as ADD COLUMN IF NOT EXISTS so it can run on
# every boot against a live database without a migration tool. The service is one
# person's, deployed by pushing; a framework that needs its own state table is
# more machinery than the problem deserves at this size.
MIGRATIONS = """
-- Identity. user_id has always been the farmer's phone number on SMS, so a web
-- signup deliberately produces the SAME key rather than a second identity: a
-- farmer who signs up in the browser and later texts the gateway is one farmer.
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS name         TEXT;
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS verified_at  TIMESTAMPTZ;
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS onboarded_at TIMESTAMPTZ;
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS consent_sms  BOOLEAN NOT NULL DEFAULT TRUE;

-- Bumped to invalidate every token a farmer holds. Cheap logout-everywhere,
-- and the only revocation a stateless JWT can have.
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

-- Finer than district, and the level a KVK referral actually names.
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS village TEXT;
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS block   TEXT;
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS tehsil  TEXT;

-- The unit this farmer thinks in - 'acre', 'bigha', 'guntha'. Areas are stored
-- in hectares everywhere else; this is only so answers can speak back in the
-- unit the farmer used. See units.py for why a bigha needs the state too.
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS area_unit TEXT;

-- The collective a farmer belongs to: 'fpo', 'cooperative', 'shg' or 'none'.
-- AnnaData is paid for by institutions on behalf of their members, so this is
-- what ties a farmer's usage to the organisation buying the coverage.
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS farmer_group      TEXT;
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS farmer_group_name TEXT;

-- "Is your farm near Kharagpur?" - asked at most once a place (farm_asked
-- holds whereabouts.asked_key of each), and the one currently awaiting a yes
-- or no (farm_pending: name, coordinates, district, state, language).
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS farm_asked   TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS farm_pending JSONB;

-- A plot of land. Separate from farmers because a smallholding is usually
-- several fragmented parcels with different water, not one field.
CREATE TABLE IF NOT EXISTS plots (
    id           BIGSERIAL PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES farmers(user_id) ON DELETE CASCADE,
    label        TEXT,
    -- CANONICAL. Every calculation reads this one and no other.
    area_ha      NUMERIC(10, 4),
    -- What the farmer actually said, kept so the answer can repeat it back.
    -- "0.27 hectares" is not a quantity a farmer who said "2 bigha" recognises.
    area_said    NUMERIC(10, 3),
    area_unit    TEXT,
    irrigation   TEXT,    -- rainfed | canal | borewell | tubewell | tank | other
    soil_texture TEXT,    -- farmer-reported; beats the Earth Engine guess locally
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS plots_user ON plots (user_id);

-- What is growing, and since when.
--
-- sown_on is the highest-value column here. CROP_CALENDAR in Agent.py is
-- month-based for the whole country; days-after-sowing is what actually decides
-- growth stage and which pest window is open, and it is the difference between
-- "spray for bollworm" and "you are at 45 days, this is the window".
CREATE TABLE IF NOT EXISTS plantings (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES farmers(user_id) ON DELETE CASCADE,
    plot_id    BIGINT REFERENCES plots(id) ON DELETE SET NULL,
    crop       TEXT NOT NULL,
    variety    TEXT,
    season     TEXT,      -- kharif | rabi | zaid
    sown_on    DATE,
    area_ha    NUMERIC(10, 4),
    status     TEXT NOT NULL DEFAULT 'standing',   -- standing | harvested
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS plantings_user ON plantings (user_id, status);

-- One-time codes for sign-in.
--
-- The code itself is never stored, only a keyed hash of it - the same reason a
-- password is not stored. A dump of this table must not let anyone sign in as a
-- farmer between the code being sent and it expiring.
CREATE TABLE IF NOT EXISTS login_codes (
    phone       TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    -- Wrong guesses. A six-digit code is 10^6, which is only out of reach if a
    -- limited number of guesses is allowed.
    attempts    SMALLINT NOT NULL DEFAULT 0,
    -- When a code was last SENT, so a farmer cannot be spammed and the gateway
    -- SIM cannot be drained by someone hammering the endpoint.
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_count  SMALLINT NOT NULL DEFAULT 1
);
"""


def init() -> bool:
    """Create the pool and ensure the schema exists. Safe to call repeatedly."""
    global _pool, _init_error

    if _pool is not None:
        return True
    if _init_error is not None:
        return False

    with _lock:
        if _pool is not None:
            return True
        if not DATABASE_URL:
            _init_error = "DATABASE_URL not set; farmer profiles and history disabled"
            print(f"Database: {_init_error}")
            return False

        try:
            from psycopg_pool import ConnectionPool

            # Neon scales to zero, so the first connection after an idle period
            # has to wait for the compute to spin up.
            pool = ConnectionPool(
                DATABASE_URL,
                min_size=0,
                max_size=DB_POOL_MAX,
                timeout=30,
                max_idle=120,
                open=True,
            )
            pool.wait(timeout=30)

            with pool.connection() as conn:
                conn.execute(SCHEMA)
                # Separately, and tolerantly: a failure to add a later column
                # must not take down a service whose original tables are fine.
                # The features that need those columns check for themselves.
                try:
                    conn.execute(MIGRATIONS)
                except Exception as e:
                    print(f"Schema migrations failed, continuing without them: {e}")

            _pool = pool
            print("Database ready (farmer profiles and history enabled)")
            return True

        except Exception as e:
            _init_error = str(e)
            print(f"Database unavailable, continuing stateless: {e}")
            return False


def is_available() -> bool:
    return _pool is not None


def status() -> str:
    if _pool is not None:
        return "connected"
    return _init_error or "not initialized"


def connection():
    """Context manager yielding a pooled connection. Caller must check is_available()."""
    return _pool.connection()


def close():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
