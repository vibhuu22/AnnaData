"""Export recent conversations for review, without phone numbers.

    python tools/export_conversations.py              # the last 14 days
    python tools/export_conversations.py --days 30

Reads DATABASE_URL from .env, opens a READ ONLY transaction and writes
conversations_export.json next to this repo's backend folder. Nothing in the
database is changed.

What leaves the database, and what does not:
- Each farmer is a participant id - the same keyed pseudonym the admin
  dashboard uses (ANALYTICS_PSEUDONYM_KEY), so a conversation in the file can
  be found on the dashboard. Phone numbers are not in the file.
- Message text is kept, because the text is what is being reviewed, but any
  run of 10 or more digits in it (a phone number typed into a question) is
  replaced with [number].
- From the profile: state, district, crops and language. No coordinates, no
  village, no name.
- Ratings (SMS 1-5 and web thumbs) and the analytics row for each answer
  (tools, intent, dose status, time taken).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.admin")
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
import metrics_store  # noqa: E402

DIGITS = re.compile(r"\+?\d[\d\s-]{8,}\d")


def scrub(text):
    return DIGITS.sub(lambda m: "[number]" if len(re.sub(r"\D", "", m.group())) >= 10 else m.group(),
                      text or "")


def kind(user_id):
    if user_id.startswith("guest:"):
        return "guest"
    return "signed_in" if metrics_store.normal_user(user_id).startswith("+91") else "other"


def when(value):
    return value.astimezone(timezone.utc).isoformat() if value else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--out", default=str(ROOT / "conversations_export.json"))
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is missing from the backend .env")

    with psycopg.connect(url, connect_timeout=20, row_factory=dict_row) as conn:
        conn.read_only = True
        cur = conn.cursor()
        cur.execute("SET statement_timeout = 60000")
        cur.execute(
            """SELECT id, user_id, direction, body, meta, session_id, created_at
                 FROM messages
                WHERE created_at > now() - make_interval(days => %s)
                ORDER BY user_id, created_at""", (args.days,))
        messages = cur.fetchall()
        users = sorted({m["user_id"] for m in messages})

        cur.execute("SELECT user_id, state, district, crops, language FROM farmers WHERE user_id = ANY(%s)",
                    (users,))
        farmers = {f["user_id"]: f for f in cur.fetchall()}

        cur.execute(
            """SELECT user_id, session_id, rating, raw_message, created_at FROM feedback
                WHERE created_at > now() - make_interval(days => %s)""", (args.days,))
        ratings = cur.fetchall()

        try:
            cur.execute(
                """SELECT request_id, status, error_kind, backend_ms, intent, dose_status, tools,
                          missing_slots, language, gateway_status
                     FROM analytics_requests
                    WHERE started_at > now() - make_interval(days => %s)""", (args.days,))
            requests = {r["request_id"]: r for r in cur.fetchall()}
        except psycopg.Error:
            conn.rollback()
            requests = {}
        try:
            cur.execute("SELECT participant_id, category FROM analytics_audience")
            audience = {r["participant_id"]: r["category"] for r in cur.fetchall()}
        except psycopg.Error:
            conn.rollback()
            audience = {}

    people = {}
    for user_id in users:
        pid = metrics_store.participant_id(user_id)
        farmer = farmers.get(user_id) or {}
        people[user_id] = {
            "participant": pid,
            "kind": kind(user_id),
            "audience": audience.get(pid, "unclassified"),
            "state": farmer.get("state"),
            "district": farmer.get("district"),
            "crops": list(farmer.get("crops") or []),
            "language": farmer.get("language"),
            "conversations": {},
        }

    for m in messages:
        meta = m["meta"] or {}
        channel = meta.get("channel") or "sms"
        # A web chat is its own conversation; SMS goes by the backend session.
        key = f"chat:{meta['chat']}" if meta.get("chat") else f"session:{m['session_id']}"
        convo = people[m["user_id"]]["conversations"].setdefault(
            key, {"channel": channel, "session": m["session_id"], "turns": [], "ratings": []})
        turn = {"at": when(m["created_at"]), "from": "farmer" if m["direction"] == "inbound" else "annadata",
                "text": scrub(m["body"])}
        if m["direction"] == "outbound":
            turn.update({k: meta.get(k) for k in ("intent", "message_type", "dose_status", "tools", "missing")
                         if meta.get(k) is not None})
            req = requests.get(meta.get("request_id"))
            if req:
                turn["seconds"] = round(req["backend_ms"] / 1000, 1) if req["backend_ms"] else None
                if req["status"] != "answered":
                    turn["status"] = req["status"]
                    turn["error"] = req["error_kind"]
                if req["gateway_status"]:
                    turn["sms_delivery"] = req["gateway_status"]
        convo["turns"].append(turn)

    for r in ratings:
        person = people.get(r["user_id"])
        if not person:
            continue
        target = next((c for c in person["conversations"].values() if c["session"] == r["session_id"]), None)
        entry = {"at": when(r["created_at"]), "rating": r["rating"], "said": scrub(r["raw_message"])}
        (target["ratings"] if target else person.setdefault("unattached_ratings", [])).append(entry)

    out = []
    for person in people.values():
        person["conversations"] = sorted(person["conversations"].values(), key=lambda c: c["turns"][0]["at"])
        out.append(person)
    out.sort(key=lambda p: p["conversations"][-1]["turns"][-1]["at"], reverse=True)

    summary = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "participants": len(out),
        "conversations": sum(len(p["conversations"]) for p in out),
        "messages": len(messages),
        "ratings": len(ratings),
    }
    Path(args.out).write_text(json.dumps({"summary": summary, "people": out}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
