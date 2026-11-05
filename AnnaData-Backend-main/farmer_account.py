"""
The farmer's account: who they are, what they farm, what they have asked before.

Kept apart from profile_store.py on purpose. That module is the AGENT's memory -
facts it picked up mid-conversation and will use to answer better. This one is
the FARMER's account: things they told us deliberately, on a form, and expect to
see again and be able to correct.

They share the `farmers` table because they are the same farmer, and separating
them into two tables would mean deciding which one owns `district` - a question
with no good answer, since the agent learns it from a question and the farmer
also types it during sign-up.
"""
from __future__ import annotations

from datetime import datetime, timezone

import db
import units


def ensure(user_id: str, *, channel: str = "web") -> int:
    """Make sure a row exists for this farmer, and return their token version.

    Called the moment a phone number is proved, so a farmer exists before they
    have told us anything at all. ON CONFLICT rather than a check-then-insert
    because the SMS bridge may have created the same row a second earlier.
    """
    if not db.is_available():
        return 0
    now = datetime.now(timezone.utc)
    try:
        with db.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO farmers (user_id, channel, verified_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                    SET verified_at = COALESCE(farmers.verified_at, EXCLUDED.verified_at),
                        updated_at  = now()
                RETURNING token_version
                """,
                (user_id, channel, now),
            ).fetchone()
            return int(row[0] or 0) if row else 0
    except Exception as e:
        print(f"Could not ensure a farmer row for {user_id}: {e}")
        return 0


def token_version(user_id: str) -> int:
    if not db.is_available():
        return 0
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT token_version FROM farmers WHERE user_id = %s", (user_id,)
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def sign_out_everywhere(user_id: str) -> bool:
    """Invalidate every token this farmer holds."""
    if not db.is_available():
        return False
    try:
        with db.connection() as conn:
            conn.execute(
                "UPDATE farmers SET token_version = token_version + 1, updated_at = now()"
                " WHERE user_id = %s",
                (user_id,),
            )
        return True
    except Exception as e:
        print(f"Could not sign out {user_id}: {e}")
        return False


def account(user_id: str) -> dict | None:
    """Everything the farmer told us about themselves, for their own screen."""
    if not user_id or not db.is_available():
        return None
    try:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT user_id, name, state, district, village, block, tehsil,
                       latitude, longitude, language, area_unit, crops,
                       onboarded_at, verified_at, consent_sms,
                       farmer_group, farmer_group_name
                  FROM farmers WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
            if not row:
                return None

            plots = conn.execute(
                """
                SELECT id, label, area_ha, area_said, area_unit, irrigation, soil_texture
                  FROM plots WHERE user_id = %s ORDER BY id
                """,
                (user_id,),
            ).fetchall()

            plantings = conn.execute(
                """
                SELECT id, crop, variety, season, sown_on, area_ha, status
                  FROM plantings WHERE user_id = %s AND status = 'standing'
                 ORDER BY sown_on DESC NULLS LAST, id
                """,
                (user_id,),
            ).fetchall()

        state, area_unit = row[2], row[10]
        total_ha = sum(float(p[2]) for p in plots if p[2] is not None) or None

        return {
            "user_id": row[0],
            "phone": row[0],
            "name": row[1],
            "state": state,
            "district": row[3],
            "village": row[4],
            "block": row[5],
            "tehsil": row[6],
            "latitude": row[7],
            "longitude": row[8],
            "language": row[9],
            "area_unit": area_unit,
            "crops": list(row[11] or []),
            "onboarded_at": row[12].isoformat() if row[12] else None,
            "verified_at": row[13].isoformat() if row[13] else None,
            "consent_sms": row[14],
            "farmer_group": row[15],
            "farmer_group_name": row[16],
            "total_area_ha": total_ha,
            # Said in the farmer's own unit as well as hectares, because "0.27
            # hectares" is not a quantity a farmer who said "2 bigha" recognises.
            "total_area_text": units.describe(total_ha, area_unit, state),
            "plots": [
                {
                    "id": p[0], "label": p[1],
                    "area_ha": float(p[2]) if p[2] is not None else None,
                    "area_said": float(p[3]) if p[3] is not None else None,
                    "area_unit": p[4], "irrigation": p[5], "soil_texture": p[6],
                }
                for p in plots
            ],
            "plantings": [
                {
                    "id": q[0], "crop": q[1], "variety": q[2], "season": q[3],
                    "sown_on": q[4].isoformat() if q[4] else None,
                    "area_ha": float(q[5]) if q[5] is not None else None,
                    "status": q[6],
                }
                for q in plantings
            ],
        }
    except Exception as e:
        print(f"Could not read the account for {user_id}: {e}")
        return None


def save_onboarding(user_id: str, data: dict) -> tuple[bool, str | None]:
    """Write what the sign-up form collected. Every field is optional.

    Onboarding is allowed to be abandoned halfway. A farmer who gave a district
    and nothing else is more useful than one who gave up on a required field, and
    the agent already knows how to ask for what is missing mid-conversation.

    Returns (ok, note) where note carries any assumption made converting the
    area - a bigha depends on the state, and that has to be sayable out loud.
    """
    if not db.is_available():
        return False, None

    name = (data.get("name") or "").strip() or None
    state = (data.get("state") or "").strip() or None
    district = (data.get("district") or "").strip() or None
    village = (data.get("village") or "").strip() or None
    language = (data.get("language") or "").strip() or None
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    crops = [c.strip().lower() for c in (data.get("crops") or []) if c and c.strip()]
    group = (data.get("farmer_group") or "").strip().lower() or None
    if group not in (None, "fpo", "cooperative", "shg", "none"):
        group = None
    group_name = (data.get("farmer_group_name") or "").strip()[:120] or None

    area_said = data.get("area")
    area_unit = units.normalise_unit(data.get("area_unit"))
    converted = units.convert(area_said, area_unit, state)
    note = converted.note if converted else None

    try:
        with db.connection() as conn:
            conn.execute(
                """
                UPDATE farmers SET
                    name       = COALESCE(%s, name),
                    state      = COALESCE(%s, state),
                    district   = COALESCE(%s, district),
                    village    = COALESCE(%s, village),
                    language   = COALESCE(%s, language),
                    latitude   = COALESCE(%s, latitude),
                    longitude  = COALESCE(%s, longitude),
                    area_unit  = COALESCE(%s, area_unit),
                    crops      = CASE WHEN %s::text[] IS NULL THEN crops ELSE %s::text[] END,
                    farmer_group      = COALESCE(%s, farmer_group),
                    farmer_group_name = COALESCE(%s, farmer_group_name),
                    onboarded_at = COALESCE(farmers.onboarded_at, now()),
                    updated_at = now()
                 WHERE user_id = %s
                """,
                (name, state, district, village, language, latitude, longitude,
                 area_unit, crops or None, crops or None, group, group_name, user_id),
            )

            # One plot at sign-up. A farmer with three fragmented parcels can add
            # the others later; asking for them on the way in would cost more
            # farmers than it would gain detail.
            if converted is not None:
                existing = conn.execute(
                    "SELECT id FROM plots WHERE user_id = %s ORDER BY id LIMIT 1",
                    (user_id,),
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE plots SET area_ha = %s, area_said = %s,
                                  area_unit = %s, updated_at = now() WHERE id = %s""",
                        (converted.hectares, converted.said, converted.unit, existing[0]),
                    )
                else:
                    conn.execute(
                        """INSERT INTO plots (user_id, area_ha, area_said, area_unit)
                           VALUES (%s, %s, %s, %s)""",
                        (user_id, converted.hectares, converted.said, converted.unit),
                    )

            for crop in crops:
                conn.execute(
                    """
                    INSERT INTO plantings (user_id, crop, sown_on, status)
                    SELECT %s, %s, %s, 'standing'
                     WHERE NOT EXISTS (
                        SELECT 1 FROM plantings
                         WHERE user_id = %s AND crop = %s AND status = 'standing'
                     )
                    """,
                    (user_id, crop, data.get("sown_on"), user_id, crop),
                )
        return True, note
    except Exception as e:
        print(f"Could not save onboarding for {user_id}: {e}")
        return False, None


def history(user_id: str, limit: int = 50) -> list[dict]:
    """Past turns, oldest first, so the browser can render a conversation.

    recent_history() in profile_store answers a different question - the last few
    messages for the AGENT's context window, capped and expiring. This is the
    farmer's own record and does not expire.
    """
    if not user_id or not db.is_available():
        return []
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """
                SELECT direction, body, meta, created_at, session_id
                  FROM messages WHERE user_id = %s
                 ORDER BY created_at DESC, id DESC LIMIT %s
                """,
                (user_id, max(1, min(limit, 200))),
            ).fetchall()
        return [
            {
                "direction": r[0],
                "body": r[1],
                "meta": r[2] or {},
                "at": r[3].isoformat() if r[3] else None,
                # Groups SMS messages, which carry no chat id, into chats.
                "session": r[4],
            }
            for r in reversed(rows)
        ]
    except Exception as e:
        print(f"Could not read history for {user_id}: {e}")
        return []
