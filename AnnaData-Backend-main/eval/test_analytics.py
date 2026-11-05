import os
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics_metrics import build_conversations,overview,rate,percentile,redact
from metrics_store import participant_id,normal_user,evidence_summary
from fastapi import FastAPI
from fastapi.testclient import TestClient
import admin_api

NOW=datetime(2026,11,3,12,tzinfo=timezone.utc)
USER='+919999999999'


def message(id,direction,session=1,body='Potato price?',minute=0,meta=None,user=USER):
    return dict(id=id,direction=direction,session_id=session,body=body,
                created_at=NOW+timedelta(minutes=minute),user_id=user,meta=meta or {})


class MetricsTests(unittest.TestCase):
    def test_missing_data_is_not_zero(self):
        result=overview([],[],{},set(),'farmer',NOW)
        self.assertIsNone(result['useful_answers']['percent'])
        self.assertIsNone(result['backend_latency']['median_seconds'])
        self.assertIsNone(result['confirmed_delivery'])

    def test_founder_exclusion_overrides_farmer_classification(self):
        pid=participant_id(USER)
        groups=build_conversations([message(1,'inbound')],{pid:'farmer'},{},{pid})
        result=overview(groups,[],{pid:'farmer'},{pid},'farmer',NOW)
        self.assertEqual(result['participants'],0)
        self.assertEqual(groups[0]['audience'],'test')

    def test_phone_formats_share_analytics_identity(self):
        self.assertEqual(participant_id(USER),participant_id('919999999999'))
        self.assertEqual(participant_id(USER),participant_id('9999999999'))
        self.assertNotEqual(normal_user('AD-JIO'),USER)

    def test_legacy_matching_marked_and_not_used_as_latency(self):
        groups=build_conversations([message(1,'inbound'),message(2,'outbound',None,minute=1)],{}, {},set())
        self.assertEqual(len(groups),1)
        self.assertTrue(groups[0]['inferred'])
        self.assertIsNone(overview(groups,[],{},set(),'all',NOW)['backend_latency']['median_seconds'])

    def test_sessions_do_not_collide_across_users(self):
        groups=build_conversations([message(1,'inbound'),message(2,'inbound',user='+918888888888')],{},{},set())
        self.assertEqual(len(groups),2)

    def test_answer_and_gateway_denominators_remain_separate(self):
        requests=[dict(user_id=USER,status=s,started_at=NOW,channel='sms',backend_ms=1000,
                  gateway_status=g) for s,g in [('answered','gateway_accepted'),('answered',None),('failed',None),('started',None)]]
        result=overview([],requests,{},set(),'all',NOW)
        self.assertEqual(result['answer_generation'],rate(2,3))
        self.assertEqual(result['gateway_acceptance'],rate(1,1))
        self.assertEqual(result['gateway_tracking_coverage'],rate(1,2))
        self.assertEqual(result['pending_requests'],1)

    def test_useful_requires_safety_review(self):
        groups=build_conversations([message(1,'inbound')],{},{},set())
        groups[0]['review']={'verdict':'useful','severity':'not_reviewed','farmer_confirmed':'unknown'}
        self.assertIsNone(overview(groups,[],{},set(),'all',NOW)['useful_answers']['percent'])
        groups[0]['review']['severity']='critical'
        result=overview(groups,[],{},set(),'all',NOW)
        self.assertEqual(result['useful_answers'],rate(0,1))
        self.assertEqual(result['critical_errors'],rate(1,1))

    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(percentile([1000,2000,3000,20000],.95),20)
        self.assertEqual(percentile([1000,2000,3000,20000],.5),2)

    def test_median_averages_even_samples(self):
        requests=[dict(user_id=USER,status='answered',started_at=NOW,channel='web',backend_ms=n) for n in [1000,3000]]
        self.assertEqual(overview([],requests,{},set(),'all',NOW)['backend_latency']['median_seconds'],2)

    def test_missing_safety_review_stays_in_queue(self):
        groups=build_conversations([message(1,'inbound')],{},{},set())
        reviews={groups[0]['id']:{'verdict':'useful','severity':'not_reviewed','pain_points':['market_price']}}
        groups=build_conversations([message(1,'inbound')],{},reviews,set())
        self.assertEqual(groups[0]['review_status'],'needs_review')

    def test_stop_erases_analytics_without_requiring_tables(self):
        from unittest.mock import MagicMock
        import profile_store
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=('exists',)
        with patch.object(profile_store.db,'is_available',return_value=True), patch.object(profile_store.db,'connection') as connection:
            connection.return_value.__enter__.return_value=conn
            self.assertTrue(profile_store.forget(USER))
        deletes=[call.args for call in conn.execute.call_args_list if call.args[0].startswith('DELETE FROM analytics_')]
        self.assertEqual(len(deletes),3)
        self.assertEqual(deletes[1][1],(participant_id(USER),))
        conn.reset_mock()
        conn.execute.return_value.fetchone.return_value=(None,)
        with patch.object(profile_store.db,'is_available',return_value=True), patch.object(profile_store.db,'connection') as connection:
            connection.return_value.__enter__.return_value=conn
            self.assertTrue(profile_store.forget(USER))
        self.assertFalse(any(call.args[0].startswith('DELETE FROM analytics_') for call in conn.execute.call_args_list))

    def test_phone_and_email_redaction(self):
        self.assertNotIn('9999999999',redact('Call +91 99999 99999 or 9999999999'))
        self.assertNotIn('example.org',redact('owner@example.org'))

    def test_source_date_not_fetch_date(self):
        e=evidence_summary({'mandi':'Market: Ghatal APMC | Arrival Date: 03/11/2026 | Modal Price: Rs820'})
        self.assertEqual(e['mandi']['arrival_dates'],['03/11/2026'])
        self.assertIn('Ghatal APMC ',e['mandi']['markets'])


class AccessTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(admin_api.router);self.client=TestClient(app)

    def test_transient_read_failure_retries_once(self):
        from psycopg import OperationalError
        expected=([],[],{},[],NOW)
        with patch.object(admin_api,'_dataset',side_effect=[OperationalError('disconnected'),expected]) as read:
            self.assertEqual(admin_api.dataset(30),expected)
            self.assertEqual(read.call_count,2)

    def test_persistent_connection_error_does_not_claim_missing_schema(self):
        from psycopg import OperationalError
        from fastapi import HTTPException
        with patch.object(admin_api,'_dataset',side_effect=OperationalError('disconnected')) as read:
            with self.assertRaises(HTTPException) as raised:admin_api.dataset(30)
        self.assertEqual(read.call_count,2)
        self.assertEqual(raised.exception.status_code,503)
        self.assertIn('connection temporarily unavailable',raised.exception.detail)

    def test_schema_failure_is_not_retried(self):
        from fastapi import HTTPException
        with patch.object(admin_api,'_dataset',side_effect=HTTPException(503,'Analytics schema is missing')) as read:
            with self.assertRaises(HTTPException):admin_api.dataset(30)
        self.assertEqual(read.call_count,1)

    @patch.dict(os.environ,{'ADMIN_API_TOKEN':'x'*40})
    def test_farmer_or_bridge_credentials_cannot_read_admin(self):
        for h in [{},{'Authorization':'Bearer farmer-token'},{'X-Bridge-Token':'bridge-token'},{'X-Admin-Token':'wrong'}]:
            self.assertEqual(self.client.get('/admin/api/dashboard',headers=h).status_code,401)

    @patch.dict(os.environ,{'ADMIN_API_TOKEN':''})
    def test_unconfigured_admin_is_closed(self):
        self.assertEqual(self.client.get('/admin/api/dashboard').status_code,503)

    @patch.dict(os.environ,{'ADMIN_API_TOKEN':'x'*40})
    def test_authorized_empty_dashboard_reports_unknown(self):
        with patch.object(admin_api,'dataset',return_value=([],[],{},[],NOW)):
            r=self.client.get('/admin/api/dashboard',headers={'X-Admin-Token':'x'*40})
        self.assertEqual(r.status_code,200)
        self.assertIsNone(r.json()['metrics']['answer_generation']['percent'])

    @patch.dict(os.environ,{'ADMIN_API_TOKEN':'x'*40})
    def test_review_enums_validated(self):
        r=self.client.post('/admin/api/reviews',headers={'X-Admin-Token':'x'*40},json={
            'conversation_id':'a'*24,'verdict':'invented','severity':'clear','pain_points':['general']})
        self.assertEqual(r.status_code,422)


if __name__=='__main__':unittest.main()
