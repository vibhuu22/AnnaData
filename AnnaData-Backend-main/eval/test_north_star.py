"""The North Star: weekly returning farmers with an answered question.

Offline: built from messages and request rows the way the dashboard is.
Run: python -m unittest eval/test_north_star.py
"""
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics_metrics import build_conversations
from dashboard_metrics import north_star, EMPTY_MEDIA
from metrics_store import participant_id

NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)          # Friday; IST week began Monday 9 Nov
LAST_WEEK = datetime(2026, 11, 4, 6, tzinfo=timezone.utc)       # Wednesday of the week of 2 Nov
THIS_WEEK = datetime(2026, 11, 11, 6, tzinfo=timezone.utc)      # Wednesday of the week of 9 Nov


class NorthStarTests(unittest.TestCase):
    def setUp(self):
        self.key = patch('metrics_store._pseudonym_key', return_value=b'offline-test-key')
        self.key.start()
        self.addCleanup(self.key.stop)
        self.messages, self.requests, self.next_id = [], [], 1

    def ask(self, user, at, question='Gehu me peela rog', message_type='question', tools=('doses',), status='answered'):
        """One farmer message and AnnaData's answer to it, in their own session."""
        rid = f'r{self.next_id}'
        session = self.next_id
        for direction, body, meta in (
                ('inbound', question, {'request_id': rid}),
                ('outbound', 'An answer', {'request_id': rid, 'message_type': message_type, 'tools': list(tools)})):
            self.messages.append({'id': self.next_id, 'user_id': user, 'session_id': session, 'direction': direction,
                                  'body': body, 'meta': meta, 'created_at': at})
            self.next_id += 1
        self.requests.append({'request_id': rid, 'user_id': user, 'status': status, 'started_at': at})

    def star(self, excluded=()):
        groups = build_conversations(self.messages, {}, {}, {participant_id(u) for u in excluded})
        return north_star(groups, self.requests, NOW - timedelta(days=30), NOW)

    def test_a_farmer_who_comes_back_counts_this_week(self):
        self.ask('+919800000001', LAST_WEEK)
        self.ask('+919800000001', THIS_WEEK)
        week = self.star()['this_week']
        self.assertEqual((week['value'], week['answered'], week['first_time']), (1, 1, 0))
        self.assertTrue(week['partial'])

    def test_first_answer_is_not_a_return_and_same_day_repeats_are_not_either(self):
        self.ask('+919800000002', THIS_WEEK)
        self.ask('+919800000002', THIS_WEEK + timedelta(hours=1))
        week = self.star()['this_week']
        self.assertEqual((week['value'], week['answered'], week['first_time']), (0, 1, 1))

    def test_greetings_about_answers_failures_and_empty_voice_notes_do_not_count(self):
        user = '+919800000003'
        self.ask(user, LAST_WEEK, 'hello', message_type='smalltalk', tools=('greeting',))
        self.ask(user, LAST_WEEK + timedelta(days=1), 'who are you', message_type='meta', tools=('about',))
        self.ask(user, LAST_WEEK + timedelta(days=2), 'Gehu', status='failed')
        self.ask(user, LAST_WEEK + timedelta(days=3), EMPTY_MEDIA)
        self.ask(user, THIS_WEEK)
        week = self.star()['this_week']
        self.assertEqual((week['value'], week['first_time']), (0, 1), 'none of the earlier replies was an answer')

    def test_test_accounts_never_count(self):
        self.ask('+919800000009', LAST_WEEK)
        self.ask('+919800000009', THIS_WEEK)
        self.assertEqual(self.star(excluded=['+919800000009'])['this_week']['answered'], 0)

    def test_an_answer_more_than_30_days_earlier_is_not_a_return(self):
        self.ask('+919800000004', THIS_WEEK - timedelta(days=31))
        self.ask('+919800000004', THIS_WEEK)
        groups = build_conversations(self.messages, {}, {}, set())
        week = north_star(groups, self.requests, NOW - timedelta(days=60), NOW)['this_week']
        self.assertEqual((week['value'], week['first_time']), (0, 1))

    def test_last_complete_week_and_week_on_week_return(self):
        self.ask('+919800000005', LAST_WEEK - timedelta(days=7))
        self.ask('+919800000005', LAST_WEEK)
        self.ask('+919800000006', LAST_WEEK)
        self.ask('+919800000005', THIS_WEEK)
        star = self.star()
        self.assertEqual(star['last_complete_week']['value'], 1)
        self.assertEqual(star['last_complete_week']['answered'], 2)
        self.assertEqual(star['this_week']['returned_from_last_week']['percent'], 50.0)
        self.assertTrue(all(w['week_start'] <= NOW.date().isoformat() for w in star['weeks']))


if __name__ == '__main__':
    unittest.main()
