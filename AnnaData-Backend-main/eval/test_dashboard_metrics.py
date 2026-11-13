"""Offline aggregate checks for the owner dashboard."""
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from dashboard_metrics import detailed_metrics
from analytics_metrics import build_conversations, overview
from metrics_store import participant_id

NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.key = patch('metrics_store._pseudonym_key', return_value=b'offline-test-key')
        self.key.start()
        self.addCleanup(self.key.stop)

    def calculate(self, groups=None, rows=None, **kw):
        return detailed_metrics(groups or [], rows or [], {}, set(), 'all', NOW-timedelta(days=7), NOW, **kw)

    def group(self, review=None):
        return build_conversations([
            {'id':i+1, 'user_id':'guest:one', 'session_id':1, 'direction':'inbound', 'body':'Question',
             'meta':{'request_id':str(i)}, 'created_at':NOW-timedelta(days=i)} for i in (0, 2)
        ], {}, {} if review is None else {}, set())

    def row(self, status='answered', **kw):
        return dict(user_id='guest:one', request_id='0', status=status, started_at=NOW, channel='voice', **kw)

    def test_zero_dates_distinct_activity_and_repeat(self):
        d=self.calculate(self.group())['adoption']
        self.assertEqual(len(d['activity']),8)
        self.assertEqual(d['active_in_window'],1)
        self.assertEqual(d['repeat_on_multiple_days']['percent'],100)
        self.assertEqual(sum(r['messages']==0 for r in d['activity']),6)

    def test_failure_denominator_excludes_pending_and_latency_excludes_failed(self):
        d=self.calculate(rows=[self.row(backend_ms=1000), self.row('failed',backend_ms=90000,error_kind='Timeout'), self.row('started')])
        self.assertEqual(d['efficiency']['failure_rate']['percent'],50)
        self.assertEqual(d['efficiency']['p95_seconds'],1)
        self.assertEqual(d['efficiency']['errors'],{'Timeout':1})

    def test_unknown_is_not_zero(self):
        d=self.calculate(ratings_available=False)
        self.assertIsNone(d['feedback']['total'])
        self.assertIsNone(d['feedback']['coverage'])
        self.assertIsNone(d['efficiency']['failure_rate']['percent'])

    def test_neutral_ratings_in_denominator(self):
        groups=self.group(); groups[0]['ratings']=[{'score':3,'source':'sms'}, {'score':5,'source':'web'}]
        d=self.calculate(groups)['feedback']
        self.assertEqual(d['positive']['percent'],50)
        self.assertEqual(d['scores']['3'],1)

    def test_audience_exclusion_applies_to_every_dimension(self):
        rows=[self.row()];pid=participant_id('guest:one')
        d=detailed_metrics(self.group(),rows,{}, {pid}, 'farmer', NOW-timedelta(days=7), NOW)
        self.assertEqual(d['dimensions']['channel'],[])

    def test_partial_review_not_counted_as_complete(self):
        groups=self.group();groups[0]['review']={'verdict':'useful','severity':'not_reviewed','farmer_confirmed':'unknown'}
        self.assertEqual(overview(groups,[],{},set(),'all',NOW)['review_coverage']['numerator'],0)

    def test_duplicate_identities_not_summed_across_days(self):
        d=self.calculate(self.group())
        self.assertEqual(d['adoption']['active']['7'],1)
        self.assertEqual(d['health']['linked_incoming']['percent'],0)


if __name__=='__main__': unittest.main()
