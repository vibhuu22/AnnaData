"""
Fill in how specific each farmer's stored location is, and their district.

Two jobs, both one-off.

The first is a repair. Before precision was recorded, any place name overwrote
any other, so a farmer who mentioned their own state had their farm replaced by
the state's centroid. One farmer is known to have been moved this way - the
message history shows three days of answers from Kharagpur, then a question
about "rice varieties in west bengal", then a profile reading West Bengal. The
location cannot be recovered by geocoding what is stored, because what is
stored is the wrong place; it is restored here from the record of what they
actually said.

The second is a backfill. Existing rows have no location_kind, so the new rule
has nothing to compare against and would let the next coarse mention through.
Re-geocoding each stored place supplies the kind, and the district that was
never captured.

    python -m tools.backfill_location_precision --dry-run
    python -m tools.backfill_location_precision
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import profile_store  # noqa: E402
from Address_Convertor import locate, precision  # noqa: E402

# Farmers whose stored location is known to be wrong, with what they said.
# Keyed by user, valued by the place to restore and the evidence for it.
REPAIRS = {
    "+917388535376": (
        "Kharagpur",
        'said "currently in kharagpur" on 30 Aug and was answered from it for '
        'three days, including a price from Medinipur(West) APMC on 2 Sep',
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report, change nothing")
    args = ap.parse_args()

    if not db.init():
        print("Database unavailable")
        return 1

    try:
        with db.connection() as conn:
            conn.execute(profile_store.PRECISION_COLUMNS)
            rows = conn.execute(
                "SELECT user_id, location_text, location_kind FROM farmers"
                " WHERE location_text IS NOT NULL ORDER BY user_id"
            ).fetchall()

        print(f"{len(rows)} profile(s) with a location\n")
        changed = 0
        for user_id, stored, kind in rows:
            wanted, why = REPAIRS.get(user_id, (stored, None))
            if why:
                print(f"{user_id}: REPAIR {stored!r} -> {wanted!r}\n    ({why})")
            elif kind:
                print(f"{user_id}: {stored!r} already ranked as {kind}, skipped")
                continue

            place = locate(wanted)
            if place.latitude is None:
                print(f"{user_id}: {wanted!r} did not geocode, left alone")
                continue

            rank = precision(place.kind)
            print(f"{user_id}: {wanted!r} -> {place.kind} (rank {rank})"
                  f"  district={place.district}  ({place.latitude}, {place.longitude})")
            if args.dry_run:
                continue

            with db.connection() as conn:
                conn.execute(
                    """UPDATE farmers
                          SET location_text = %s, latitude = %s, longitude = %s,
                              location_kind = %s, location_rank = %s,
                              district = COALESCE(%s, district),
                              state    = COALESCE(state, %s),
                              updated_at = now()
                        WHERE user_id = %s""",
                    (wanted, place.latitude, place.longitude, place.kind, rank,
                     place.district, place.state, user_id),
                )
            changed += 1

        print(f"\n{'would update' if args.dry_run else 'updated'} {changed} profile(s)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
