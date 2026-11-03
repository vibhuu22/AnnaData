import hashlib
import hmac
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook_auth import verify_sms, verify_whatsapp


class WebhookAuthentication(unittest.TestCase):
    def test_sms_authenticates_exact_bytes_and_timestamp(self):
        body, stamp, key = b'{"message":"hello"}', '1700000000', 'test-key'
        sig = hmac.new(key.encode(), body + stamp.encode(), hashlib.sha256).hexdigest()
        self.assertTrue(verify_sms(body, sig, stamp, key, now=1700000000))
        for data, signature, timestamp, secret, now in [
            (body + b' ', sig, stamp, key, 1700000000),
            (body, '', stamp, key, 1700000000),
            (body, sig, stamp, '', 1700000000),
            (body, sig, 'bad', key, 1700000000),
            (body, sig, stamp, key, 1700000301),
            (body, sig, stamp, key, 1699999699),
        ]:
            with self.subTest(timestamp=timestamp, now=now, secret=secret):
                self.assertFalse(verify_sms(data, signature, timestamp, secret, now=now))

    def test_whatsapp_rejects_unsigned_tampered_or_wrong_key(self):
        body, key = b'{"object":"whatsapp_business_account"}', 'test-key'
        sig = 'sha256=' + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_whatsapp(body, sig, key))
        self.assertFalse(verify_whatsapp(body + b' ', sig, key))
        self.assertFalse(verify_whatsapp(body, '', key))
        self.assertFalse(verify_whatsapp(body, sig, 'wrong'))
        self.assertFalse(verify_whatsapp(body, sig, ''))
        self.assertFalse(verify_whatsapp(body, 'sha256=é', key))
