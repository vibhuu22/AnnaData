"""
Farmer profiles and conversation history.

Two kinds of memory live here, and they deliberately have different lifetimes:

  profile facts  - location, crops, language. Persist indefinitely; a farmer in
                   Vidarbha growing cotton is still there next month.
  session context - the last few messages, so follow-ups make sense. Expires
                   after CONTEXT_TTL_HOURS so a conversation from three weeks
                   ago cannot bleed into today's question.

Every function degrades to a no-op when the database is unavailable, so the
agent keeps working exactly as it did before profiles existed.
"""
import json
from datetime import datetime, timedelta, timezone

import db
from config import CONTEXT_MESSAGES, CONTEXT_TTL_HOURS, LOCATION_ASK_COOLDOWN_HOURS


# A crop is one thing however it is written. Storing what the parser happened
# to return left 'wheat' and 'Wheat' as separate crops, and 'Kharif rice'
# alongside 'rice' - a season is not part of a crop's name.
SEASON_WORDS = ("kharif", "rabi", "zaid", "summer", "winter", "monsoon")


# Whether a name is a crop at all is a question the dose register can answer:
# it lists 314 of them. Without this check the profile accumulated whatever the
# parser returned, and one farmer ended up recorded as growing "small plant",
# "flower", "indoor potted plant" and "indoor potted plants" - the last two the
# same non-crop stored twice. The greeting then offered help with their
# "watermelons and plants", and an acknowledgement described five acres of
# indoor potted plants.
_KNOWN_CROPS: set[str] | None = None


def _known_crops() -> set[str]:
    """Every crop name the system recognises, loaded once."""
    global _KNOWN_CROPS
    if _KNOWN_CROPS is not None:
        return _KNOWN_CROPS

    import knowledge
    names = set(knowledge.CROP_SYNONYMS) | set(knowledge.CROP_SYNONYMS.values())
    try:
        with db.connection() as conn:
            names |= {r[0].strip().lower()
                      for r in conn.execute("SELECT DISTINCT crop FROM pesticide_uses").fetchall()
                      if r[0]}
    except Exception as e:
        # The synonym list alone still covers the common crops.
        print(f"Could not load crop names from the dose table: {e}")
    _KNOWN_CROPS = names
    return names


def _clean_crop(value: str | None) -> str | None:
    """Normalise a crop name, and reject anything that is not a crop."""
    crop = _clean(value)
    if not crop:
        return None
    words = [w for w in crop.lower().split() if w not in SEASON_WORDS]
    crop = " ".join(words).strip()
    if not crop:
        return None

    known = _known_crops()
    if crop in known:
        return crop
    # "tomatoes" and "indoor potted plants" both arrive plural; only one of them
    # is a crop, and the singular decides which.
    for plural, singular in (("ies", "y"), ("es", ""), ("s", "")):
        if crop.endswith(plural):
            candidate = crop[: -len(plural)] + singular
            if candidate in known:
                return candidate
    print(f"Not storing {crop!r} as a crop: not a name the system recognises")
    return None


def _clean(value: str | None) -> str | None:
    """Normalise the parser's 'unknown' sentinel to a real absence."""
    if not value:
        return None
    value = value.strip()
    if not value or value.lower() == "unknown":
        return None
    return value


def forget_location(user_id: str) -> None:
    """Drop a stored place the farmer has said is wrong ("i am not in shimla").

    The whole location group goes, state included: a state inferred from the
    wrong place is wrong too. The next place they name - or the location ask -
    fills it again.
    """
    if not db.is_available():
        return
    try:
        with db.connection() as conn:
            conn.execute(PRECISION_COLUMNS)
            conn.execute(
                """UPDATE farmers SET location_text = NULL, latitude = NULL, longitude = NULL,
                          state = NULL, district = NULL, location_kind = NULL,
                          location_rank = NULL, updated_at = now()
                    WHERE user_id = %s""", (user_id,))
    except Exception as e:
        print(f"Forgetting location failed for {user_id}: {e}")


def ask_about_farm(user_id: str, key: str, pending: dict) -> None:
    """Record that "Is your farm near X?" was asked, and what a yes would save."""
    if not user_id or not db.is_available():
        return
    try:
        from psycopg.types.json import Jsonb
        with db.connection() as conn:
            conn.execute(
                """INSERT INTO farmers (user_id, farm_asked, farm_pending)
                   VALUES (%s, ARRAY[%s], %s)
                   ON CONFLICT (user_id) DO UPDATE SET
                       farm_asked = CASE WHEN %s = ANY(farmers.farm_asked) THEN farmers.farm_asked
                                         ELSE array_append(farmers.farm_asked, %s) END,
                       farm_pending = EXCLUDED.farm_pending, updated_at = now()""",
                (user_id, key, Jsonb(pending), key, key))
    except Exception as e:
        print(f"Recording the farm question failed for {user_id}: {e}")


def clear_farm_pending(user_id: str) -> None:
    """The farm question is answerable by the very next message only."""
    if not user_id or not db.is_available():
        return
    try:
        with db.connection() as conn:
            conn.execute("UPDATE farmers SET farm_pending = NULL WHERE user_id = %s", (user_id,))
    except Exception as e:
        print(f"Clearing the farm question failed for {user_id}: {e}")


def save_farm(user_id: str, pending: dict) -> None:
    """The farmer said yes: the phone's place becomes their farm.

    The stored place is cleared first. They have confirmed this one, so the
    rule that refuses a coarser place (a town over a village) must not keep a
    village they have just said is not theirs.
    """
    forget_location(user_id)
    remember(user_id, location_text=pending.get("name"), latitude=pending.get("latitude"),
             longitude=pending.get("longitude"), state=pending.get("state"),
             district=pending.get("district"), location_kind=pending.get("kind"),
             channel=pending.get("channel") or "web")


def get_profile(user_id: str) -> dict | None:
    """Stored facts for a farmer, or None if unknown / no database."""
    if not user_id or not db.is_available():
        return None
    try:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT user_id, location_text, latitude, longitude, state,
                       district, language, crops, location_asked_at
                  FROM farmers WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
            farm = None
            if row:
                try:
                    farm = conn.execute(
                        "SELECT farm_asked, farm_pending FROM farmers WHERE user_id = %s",
                        (user_id,)).fetchone()
                except Exception:
                    farm = None     # columns not migrated yet: nothing asked
        if not row:
            return None
        return {
            "farm_asked": list((farm or [None])[0] or []),
            "farm_pending": (farm or [None, None])[1],
            "user_id": row[0],
            "location_text": row[1],
            "latitude": row[2],
            "longitude": row[3],
            "state": row[4],
            "district": row[5],
            "language": row[6],
            "crops": list(row[7] or []),
            "location_asked_at": row[8],
        }
    except Exception as e:
        print(f"Profile lookup failed for {user_id}: {e}")
        return None


PRECISION_COLUMNS = """
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS location_kind TEXT;
ALTER TABLE farmers ADD COLUMN IF NOT EXISTS location_rank INTEGER;
"""

# When an incoming place may replace the stored one. Both a name and coordinates
# must be present, and the new place must not be known to be coarser.
_REPLACE_LOCATION = """(
    EXCLUDED.location_text IS NOT NULL
    AND EXCLUDED.latitude IS NOT NULL
    AND EXCLUDED.longitude IS NOT NULL
    AND (farmers.location_rank IS NULL
         OR EXCLUDED.location_rank IS NULL
         OR EXCLUDED.location_rank >= farmers.location_rank)
)"""


def remember(
    user_id: str,
    channel: str = "sms",
    location_text: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    state: str | None = None,
    district: str | None = None,
    location_kind: str | None = None,
    crop: str | None = None,
    language: str | None = None,
) -> None:
    """Merge newly learned facts into a farmer's profile.

    Only non-empty values overwrite; a message that mentions no location must
    not erase the location we learned last week. Crops accumulate rather than
    replace, since a farmer grows more than one thing.

    A location must also not be *coarsened*. That guard used to protect only
    against absence, and absence was not what arrived: a farmer in Kharagpur
    asked about "rice varieties in west bengal", their own state geocoded
    perfectly well, and COALESCE - which skips NULL and knows nothing of
    specificity - wrote the state's centroid over their farm. It moved them
    83 km, and because weather and soil are sampled at those coordinates the
    damage was silent. Three hours earlier the same farmer had been quoted a
    price from Medinipur(West) APMC; afterwards they were asked which mandi
    they meant.

    So a place replaces the stored one only when it is at least as specific,
    and text and coordinates move together or not at all - a name written
    without the coordinates that belong to it is how the two came to disagree.
    """
    if not user_id or not db.is_available():
        return

    from Address_Convertor import precision

    location_text = _clean(location_text)
    state = _clean(state)
    district = _clean(district)
    location_kind = _clean(location_kind)
    crop = _clean_crop(crop)
    language = _clean(language)
    location_rank = precision(location_kind)

    try:
        with db.connection() as conn:
            conn.execute(PRECISION_COLUMNS)
            # The location group moves as one, and only upward in precision.
            # An unknown rank on either side does not block the update: the
            # rule refuses a *proven* downgrade, it does not demand proof of an
            # upgrade, so an unfamiliar place type still gets stored.
            conn.execute(
                """
                INSERT INTO farmers (user_id, channel, location_text, latitude,
                                     longitude, state, district, language,
                                     location_kind, location_rank)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    location_text = CASE WHEN {repl} THEN EXCLUDED.location_text
                                         ELSE farmers.location_text END,
                    latitude      = CASE WHEN {repl} THEN EXCLUDED.latitude
                                         ELSE farmers.latitude END,
                    longitude     = CASE WHEN {repl} THEN EXCLUDED.longitude
                                         ELSE farmers.longitude END,
                    location_kind = CASE WHEN {repl} THEN EXCLUDED.location_kind
                                         ELSE farmers.location_kind END,
                    location_rank = CASE WHEN {repl} THEN EXCLUDED.location_rank
                                         ELSE farmers.location_rank END,
                    state         = COALESCE(EXCLUDED.state,    farmers.state),
                    district      = COALESCE(EXCLUDED.district, farmers.district),
                    language      = COALESCE(EXCLUDED.language, farmers.language),
                    updated_at    = now()
                """.format(repl=_REPLACE_LOCATION),
                (user_id, channel, location_text, latitude, longitude, state,
                 district, language, location_kind, location_rank),
            )

            # Crops accumulate. Kept as its own statement because inferring the
            # parameter type inside a CASE on the upsert is more trouble than
            # it is worth, and this reads far better.
            if crop:
                conn.execute(
                    """
                    UPDATE farmers
                       SET crops = array_append(crops, %s), updated_at = now()
                     WHERE user_id = %s
                       AND NOT (lower(%s) = ANY(SELECT lower(unnest(crops))))
                    """,
                    (crop, user_id, crop),
                )
    except Exception as e:
        print(f"Profile update failed for {user_id}: {e}")


def recent_history(user_id: str) -> list[dict]:
    """Recent turns as [{'role': ..., 'content': ...}], oldest first.

    Bounded by both count and age: an old thread should not be treated as
    context for a question asked weeks later.
    """
    if not user_id or not db.is_available():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=CONTEXT_TTL_HOURS)
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """
                SELECT direction, body FROM messages
                 WHERE user_id = %s AND created_at >= %s
              ORDER BY created_at DESC, id DESC
                 LIMIT %s
                """,
                (user_id, cutoff, CONTEXT_MESSAGES),
            ).fetchall()
    except Exception as e:
        print(f"History lookup failed for {user_id}: {e}")
        return []

    rows.reverse()
    return [
        {"role": "user" if d == "inbound" else "assistant", "content": b}
        for d, b in rows
    ]


def log_message(
    user_id: str,
    direction: str,
    body: str,
    gateway_message_id: str | None = None,
    meta: dict | None = None,
    session_id: int | None = None,
) -> None:
    """Record one message. Duplicate gateway ids are ignored, not an error."""
    if not user_id or not db.is_available() or not body:
        return
    try:
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (user_id, direction, body, gateway_message_id,
                                      meta, session_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (gateway_message_id) DO NOTHING
                """,
                (user_id, direction, body, gateway_message_id,
                 json.dumps(meta) if meta else None, session_id),
            )
    except Exception as e:
        print(f"Message log failed for {user_id}: {e}")


def should_ask_location(profile: dict | None) -> bool:
    """Whether to append the location invitation to this reply.

    Only when we genuinely have no coordinates, and not more than once a day -
    a farmer who ignores the question should not be nagged on every message.
    """
    if not db.is_available():
        return False
    if profile is None:
        return True
    if profile.get("latitude") is not None and profile.get("longitude") is not None:
        return False

    asked = profile.get("location_asked_at")
    if asked is None:
        return True
    if asked.tzinfo is None:
        asked = asked.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - asked > timedelta(hours=LOCATION_ASK_COOLDOWN_HOURS)


def mark_location_asked(user_id: str) -> None:
    if not user_id or not db.is_available():
        return
    try:
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO farmers (user_id, location_asked_at)
                VALUES (%s, now())
                ON CONFLICT (user_id) DO UPDATE
                    SET location_asked_at = now(), updated_at = now()
                """,
                (user_id,),
            )
    except Exception as e:
        print(f"Could not record location prompt for {user_id}: {e}")


def claim_guest(guest_user_id: str, phone: str) -> int:
    """Move a guest's conversation and learned facts onto a verified number.

    A farmer asks before signing in, is shown their answer, and is then told
    that confirming their number keeps their questions saved. That promise is
    kept here. Without it the history screen would be empty the moment after it
    said it would not be.

    The guest row's facts fill gaps only - a district or crop the farmer told us
    weeks ago over SMS outranks one inferred from a single anonymous question.
    Crops are the exception and are merged, because a farmer grows more than one
    thing. Coordinates move with their location text or not at all, the same
    rule remember() keeps, so the two cannot come to disagree.

    Returns how many messages moved. All in one transaction, so a failure leaves
    the guest's conversation where it was rather than half-moved.
    """
    if not guest_user_id or not phone or not db.is_available():
        return 0
    if not guest_user_id.startswith("guest:") or guest_user_id == phone:
        return 0
    try:
        with db.connection() as conn:
            # Added lazily by remember(); a database that has never stored a
            # location precision would otherwise fail this whole move.
            conn.execute(PRECISION_COLUMNS)
            moved = conn.execute(
                "UPDATE messages SET user_id = %s WHERE user_id = %s",
                (phone, guest_user_id),
            ).rowcount or 0
            conn.execute(
                """
                UPDATE farmers f SET
                    location_text = CASE WHEN f.latitude IS NULL THEN g.location_text ELSE f.location_text END,
                    latitude      = CASE WHEN f.latitude IS NULL THEN g.latitude      ELSE f.latitude      END,
                    longitude     = CASE WHEN f.latitude IS NULL THEN g.longitude     ELSE f.longitude     END,
                    location_kind = CASE WHEN f.latitude IS NULL THEN g.location_kind ELSE f.location_kind END,
                    location_rank = CASE WHEN f.latitude IS NULL THEN g.location_rank ELSE f.location_rank END,
                    state    = COALESCE(f.state, g.state),
                    district = COALESCE(f.district, g.district),
                    language = COALESCE(f.language, g.language),
                    crops    = ARRAY(SELECT DISTINCT c FROM unnest(f.crops || g.crops) AS c),
                    updated_at = now()
                  FROM farmers g
                 WHERE f.user_id = %s AND g.user_id = %s
                """,
                (phone, guest_user_id),
            )
            # Thumbs up and down given before signing in are theirs too.
            conn.execute("UPDATE feedback SET user_id = %s WHERE user_id = %s",
                         (phone, guest_user_id))
            conn.execute("DELETE FROM farmers WHERE user_id = %s", (guest_user_id,))
        if moved:
            print(f"Moved {moved} guest message(s) onto a verified number")
        return moved
    except Exception as e:
        print(f"Could not claim guest conversation: {e}")
        return 0


def forget(user_id: str) -> bool:
    """Delete a farmer's profile and messages. Backs the STOP keyword."""
    if not user_id or not db.is_available():
        return False
    try:
        with db.connection() as conn:
            conn.execute("DELETE FROM messages WHERE user_id = %s", (user_id,))
            conn.execute("DELETE FROM farmers  WHERE user_id = %s", (user_id,))
            from metrics_store import normal_user, participant_id
            # A verified account can own pre-sign-in events through its guest alias.
            if conn.execute('SELECT to_regclass(%s)', ('web_analytics_events',)).fetchone()[0]:
                conn.execute('DELETE FROM web_analytics_events WHERE participant_id=%s OR guest_id=%s',
                             (participant_id(user_id), participant_id(user_id)))
                if conn.execute('SELECT to_regclass(%s)', ('web_analytics_identity',)).fetchone()[0]:
                    conn.execute('DELETE FROM web_analytics_events WHERE guest_id IN (SELECT guest_id FROM web_analytics_identity WHERE participant_id=%s)', (participant_id(user_id),))
                    conn.execute('DELETE FROM web_analytics_identity WHERE participant_id=%s OR guest_id=%s', (participant_id(user_id), participant_id(user_id)))
            # Analytics tables may not exist yet during a rolling deployment.
            for table, column, value in (
                ('analytics_requests', 'user_id', normal_user(user_id)),
                ('analytics_reviews', 'participant_id', participant_id(user_id)),
                ('analytics_audience', 'participant_id', participant_id(user_id)),
            ):
                if conn.execute('SELECT to_regclass(%s)', (table,)).fetchone()[0]:
                    conn.execute(f'DELETE FROM {table} WHERE {column} = %s', (value,))
        print(f"Erased profile and history for {user_id}")
        return True
    except Exception as e:
        print(f"Erase failed for {user_id}: {e}")
        return False
