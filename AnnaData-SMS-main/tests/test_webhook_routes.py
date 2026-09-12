"""Real Quart requests with all message-processing side effects replaced."""
import hashlib
import hmac
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as bridge


class WebhookRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_failed_erasure_is_not_confirmed_as_success(self):
        with patch.object(bridge, 'forget_farmer', new_callable=AsyncMock, return_value=False), \
                patch.object(bridge, 'send_sms', new_callable=AsyncMock) as send:
            await bridge.process_sms({'payload': {'sender': '+919999000099', 'message': 'STOP'}})
            send.assert_awaited_once_with('+919999000099', bridge.config.STOP_FAILURE_REPLY)

    async def test_unsigned_sms_never_queues_work(self):
        with patch.object(bridge.config, 'SMS_WEBHOOK_SIGNING_KEY', 'test-key'), \
                patch.object(bridge, 'process_sms', new_callable=AsyncMock) as process:
            response = await bridge.app.test_client().post('/incoming-sms', json={
                'payload': {'messageId': 'unsigned', 'sender': '+919999000099', 'message': 'STOP'}})
            self.assertEqual(response.status_code, 401)
            process.assert_not_called()

    async def test_unconfigured_authentication_fails_closed(self):
        with patch.object(bridge.config, 'SMS_WEBHOOK_SIGNING_KEY', None):
            response = await bridge.app.test_client().post('/incoming-sms', json={})
            self.assertEqual(response.status_code, 503)

    async def test_valid_sms_is_accepted_and_duplicate_is_ignored(self):
        import asyncio
        raw = json.dumps({'payload': {'messageId': 'signed-audit', 'sender': '+919999000099',
                                      'message': 'Hello'}}).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(b'test-key', raw + stamp.encode(), hashlib.sha256).hexdigest()
        headers = {'X-Signature': signature, 'X-Timestamp': stamp, 'Content-Type': 'application/json'}
        with patch.object(bridge.config, 'SMS_WEBHOOK_SIGNING_KEY', 'test-key'), \
                patch.object(bridge, 'processed_ids', {}), \
                patch.object(bridge, 'process_sms', new_callable=AsyncMock) as process:
            client = bridge.app.test_client()
            self.assertEqual((await client.post('/incoming-sms', data=raw, headers=headers)).status_code, 200)
            await asyncio.sleep(0)
            duplicate = await client.post('/incoming-sms', data=raw, headers=headers)
            self.assertEqual((await duplicate.get_json())['status'], 'duplicate')
            process.assert_awaited_once()

    async def test_unsigned_whatsapp_never_queues_work(self):
        with patch.object(bridge.config, 'WHATSAPP_APP_SECRET', 'test-key'), \
                patch.object(bridge, 'process_whatsapp', new_callable=AsyncMock) as process:
            response = await bridge.app.test_client().post('/whatsapp', json={'object': 'whatsapp_business_account'})
            self.assertEqual(response.status_code, 401)
            process.assert_not_called()
