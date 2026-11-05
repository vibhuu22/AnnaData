"""Initialize only analytics tables and a local admin credential; no farmer writes."""
import argparse
import secrets
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import dotenv_values, set_key
import psycopg
import metrics_store


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--initialize',action='store_true')
    p.add_argument('--test-user',action='append',default=[])
    args=p.parse_args()
    if not args.initialize:
        p.error('Use --initialize to create the analytics tables and local admin config.')
    values=dotenv_values(ROOT/'.env')
    if not values.get('DATABASE_URL'):raise SystemExit('Backend DATABASE_URL is missing.')
    with psycopg.connect(values['DATABASE_URL'],connect_timeout=15) as c:
        c.execute('SET LOCAL statement_timeout=20000')
        c.execute(metrics_store.SCHEMA)
    path=ROOT/'.env.admin'
    current=dotenv_values(path) if path.exists() else {}
    if len(current.get('ADMIN_API_TOKEN',''))<32:
        set_key(path,'ADMIN_API_TOKEN',secrets.token_urlsafe(36))
    # The key participant pseudonyms are made with. It must not change between
    # runs: a new key gives every farmer a new id, and saved classifications and
    # reviews stop matching anyone. Without it the local dashboard would fall
    # back to a per-process random AUTH_SECRET, which is exactly that.
    if len(current.get('ANALYTICS_PSEUDONYM_KEY',''))<32:
        set_key(path,'ANALYTICS_PSEUDONYM_KEY',secrets.token_urlsafe(36))
    users=set(x.strip() for x in current.get('ANALYTICS_TEST_USERS','').split(',') if x.strip())
    users.update(metrics_store.normal_user(x) for x in args.test_user)
    if users:set_key(path,'ANALYTICS_TEST_USERS',','.join(sorted(users)))
    print('Analytics tables ready. Admin credential stored in backend .env.admin (not printed).')
    print('Test exclusions configured:',len(users))
    print('Run: .venv/Scripts/python -m uvicorn admin_server:app --host 127.0.0.1 --port 8766')


if __name__=='__main__':main()
