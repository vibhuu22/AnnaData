import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from traffic_analytics import summarize, router, BrowserEvent, record, signed_in
from pydantic import ValidationError

NOW=datetime(2026,11,13,12,tzinfo=timezone.utc)


def event(kind, visitor='v1', actor='a1', day=0, session='s1', hour=0):
    return dict(kind=kind,visitor_id=visitor,actor=actor,created_at=NOW-timedelta(days=day)+timedelta(hours=hour),
                session_id=session, first_message=NOW-timedelta(days=2))


class FunnelTests(unittest.TestCase):
    def calc(self,events,first=None):
        return summarize(events,first or {},NOW-timedelta(days=7),NOW,NOW-timedelta(days=10))

    def test_pageviews_sessions_and_people_are_different(self):
        r=self.calc([event('page_view'),event('page_view'),event('visit',session='s2'),event('message_submit')])
        self.assertEqual((r['page_views'],r['visits'],r['unique_visitors'],r['message_senders']),(2,2,1,1))

    def test_both_auth_orders_and_dropoff(self):
        r=self.calc([event('page_view'),event('message_submit',hour=-1),event('sign_in'),
                     event('page_view','v2','a2'),event('sign_in','v2','a2',hour=-1),event('message_submit','v2','a2'),event('page_view','v3','a3')])
        self.assertEqual(r['ask_then_signin'],1)
        self.assertEqual(r['signin_then_ask'],1)
        self.assertEqual(r['no_message'],1)
        self.assertEqual(r['visitor_to_message']['percent'],66.7)

    def test_returning_requires_different_ist_date_and_prior_history(self):
        r=self.calc([event('page_view'),event('message_submit')],{'v1':NOW-timedelta(days=10)})
        self.assertEqual(r['returning_visitors'],1)
        self.assertEqual(r['repeat_message_senders'],1)
        self.assertEqual(self.calc([event('page_view')],{'v1':NOW-timedelta(hours=1)})['returning_visitors'],0)

    def test_same_account_across_devices_does_not_inflate_account_count(self):
        r=self.calc([event('sign_in','v1'),event('sign_in','v2'),event('message_submit','v1'),event('message_submit','v2')])
        self.assertEqual(r['signed_in_accounts'],1)
        self.assertEqual(r['message_senders'],1)
        self.assertEqual(r['unique_visitors'],2)

    def test_shared_browser_cannot_make_conversion_over_100(self):
        r=self.calc([event('sign_in',actor='a1'),event('sign_in',actor='a2')])
        self.assertEqual(r['signed_in_accounts'],2)
        self.assertEqual(r['visitor_to_signin']['percent'],100)

    def test_empty_is_unknown_conversion(self):
        r=self.calc([])
        self.assertIsNone(r['visitor_to_message']['percent'])
        self.assertEqual(len(r['daily']),8)

    def test_public_endpoint_cannot_claim_verified_signin_or_inject_content(self):
        app=FastAPI();app.include_router(router)
        payload={k:str(uuid4()) for k in ['visitor_id','session_id','guest_id','event_id']}
        with TestClient(app) as client:
            self.assertEqual(client.post('/analytics/events',json={**payload,'kind':'sign_in'}).status_code,422)
            self.assertEqual(client.post('/analytics/events',json={**payload,'kind':'visit','phone':'123'}).status_code,422)
            with patch('traffic_analytics.record',return_value=True) as write:
                self.assertEqual(client.post('/analytics/events',json={**payload,'kind':'visit'}).status_code,202)
                self.assertIsNone(write.call_args.args[1])

    def test_missing_analytics_never_breaks_auth(self):
        self.assertFalse(signed_in('account','guest',None))
        with patch('traffic_analytics.db.is_available',return_value=False):
            self.assertFalse(record(BrowserEvent(visitor_id=uuid4(),session_id=uuid4(),guest_id=uuid4(),event_id=uuid4(),kind='visit')))


if __name__=='__main__':unittest.main()
