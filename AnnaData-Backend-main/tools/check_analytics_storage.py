"""Check real PostgreSQL semantics using temporary tables, always rolled back.

Run explicitly: .venv/Scripts/python tools/check_analytics_storage.py
No production messages, classifications, reviews or telemetry are modified.
"""
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import psycopg
from dotenv import dotenv_values
from fastapi import HTTPException
import metrics_store as store
import admin_api


def main():
    values=dotenv_values(ROOT/'.env')
    with psycopg.connect(values['DATABASE_URL'],connect_timeout=15) as conn:
        try:
            conn.execute('SET LOCAL statement_timeout=10000')
            conn.execute(store.SCHEMA.replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE IF NOT EXISTS'))
            with patch.object(store.db,'is_available',return_value=True), patch.object(store.db,'connection',side_effect=lambda:nullcontext(conn)):
                user='+919999000099'
                rid=store.begin(user,1,'sms')
                store.begin(user,1,'sms',rid)
                result=SimpleNamespace(intent='market_price',message_type='question',crop='potato',state='WB',dose_status=None,tools_used=['mandi'],source_evidence={},missing_slots=[])
                assert store.finish(rid,user,result,1250,'en')
                store.finish(rid,user,result,9999,'en')
                store.fail(rid,user,'late_failure')
                store.delivery(rid,'gateway_accepted',2)
                store.delivery(rid,'send_failed',1)
                row=conn.execute('SELECT attempts,status,backend_ms,gateway_status FROM analytics_requests WHERE request_id=%s',(rid,)).fetchone()
                assert row==(2,'answered',1250,'gateway_accepted'),row
                group={'id':'a'*24,'participant_id':store.participant_id(user),'request_ids':[]}
                with patch.object(admin_api,'dataset',return_value=([group],[],{},[],None)):
                    review=admin_api.Review(conversation_id=group['id'],verdict='partial',severity='major',pain_points=['market_price'])
                    admin_api.save_review(review)
                    try: admin_api.save_review(review)
                    except HTTPException as exc: assert exc.status_code==409
                    else: raise AssertionError('Stale review overwrite was accepted')
                    review.expected_version=1
                    review.verdict='useful'
                    review.severity='clear'
                    admin_api.save_review(review)
                    assert conn.execute('SELECT version FROM analytics_reviews').fetchone()[0]==2
            print('PASS: retries, first-success retention, gateway non-regression, review persistence and stale-write protection.')
        finally:
            conn.rollback()
            print('Temporary verification transaction rolled back; production records unchanged.')


if __name__=='__main__':main()
