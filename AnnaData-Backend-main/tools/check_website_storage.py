"""Verify website events against temporary PostgreSQL tables; always roll back."""
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import psycopg
import config
import traffic_analytics as traffic
from metrics_store import participant_id


def main():
    with psycopg.connect(config.DATABASE_URL,connect_timeout=15) as conn:
        try:
            conn.execute(traffic.SCHEMA.replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE IF NOT EXISTS'))
            conn.execute('CREATE TEMP TABLE analytics_audience(participant_id TEXT PRIMARY KEY, category TEXT)')
            ctx=traffic.VisitContext(visitor_id=uuid4(),session_id=uuid4(),guest_id=uuid4())
            page=traffic.BrowserEvent(**ctx.model_dump(),event_id=uuid4(),kind='page_view')
            message=traffic.BrowserEvent(**ctx.model_dump(),event_id=uuid4(),kind='message_submit')
            account='+919999000088'
            with patch.object(traffic.db,'is_available',return_value=True),patch.object(traffic.db,'connection',side_effect=lambda:nullcontext(conn)):
                assert traffic.record(page)
                assert traffic.record(page)  # same network event is not another view
                assert traffic.record(message)
                assert traffic.signed_in(account,str(ctx.guest_id),ctx)
                assert traffic.record(traffic.BrowserEvent(**ctx.model_dump(),event_id=uuid4(),kind='message_submit'))  # late anonymous event follows alias
                assert traffic.record(traffic.BrowserEvent(**ctx.model_dump(),event_id=uuid4(),kind='message_submit'),account)
                result=traffic.dashboard(7,'all',set())
                assert result['available'],result
                assert result['page_views']==1,result
                assert result['visits']==1,result
                assert result['message_senders']==1,result
                assert result['signed_in_accounts']==1,result
                assert result['visitor_to_message']['percent']==100,result
                # A return in the current window, with original activity outside it.
                conn.execute("UPDATE web_analytics_events SET created_at=now()-interval '10 days' WHERE event_id IN (%s,%s)",(page.event_id,message.event_id))
                conn.execute("UPDATE web_analytics_start SET started_at=now()-interval '11 days'")
                result=traffic.dashboard(7,'all',set())
                assert result['returning_visitors']==1,result
                assert result['repeat_message_senders']==1,result
                conn.execute("INSERT INTO analytics_audience VALUES(%s,'test')",(participant_id(account),))
                assert traffic.dashboard(7,'non_test',set())['unique_visitors']==0
                assert traffic.dashboard(7,'all',set(),True)['page_views']==1
            print('PASS: deduplication, verified sign-in linking, delayed anonymous events, returns, audience filtering and all-time scope.')
        finally:
            conn.rollback()
            print('Temporary tables rolled back. Production records unchanged.')


if __name__=='__main__':main()
