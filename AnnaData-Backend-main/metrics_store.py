"""Optional operational telemetry. Failures here must never fail a farmer reply."""
import hashlib
import json
import os
import re
from uuid import uuid4

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS analytics_requests (
 request_id TEXT PRIMARY KEY, user_id TEXT, session_id BIGINT, channel TEXT NOT NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT now(), answered_at TIMESTAMPTZ, failed_at TIMESTAMPTZ,
 backend_ms DOUBLE PRECISION, attempts INTEGER NOT NULL DEFAULT 1,
 status TEXT NOT NULL DEFAULT 'started', error_kind TEXT, intent TEXT,
 message_type TEXT, crop TEXT, state TEXT, language TEXT, dose_status TEXT,
 tools JSONB NOT NULL DEFAULT '[]', evidence JSONB NOT NULL DEFAULT '{}',
 missing_slots JSONB NOT NULL DEFAULT '[]', release TEXT, models TEXT,
 gateway_status TEXT, gateway_updated_at TIMESTAMPTZ, sms_segments INTEGER
);
CREATE INDEX IF NOT EXISTS analytics_requests_time ON analytics_requests(started_at);
CREATE INDEX IF NOT EXISTS analytics_requests_user ON analytics_requests(user_id);
CREATE TABLE IF NOT EXISTS analytics_audience (
 participant_id TEXT PRIMARY KEY, category TEXT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS analytics_reviews (
 conversation_id TEXT PRIMARY KEY, participant_id TEXT NOT NULL,
 verdict TEXT NOT NULL, severity TEXT NOT NULL, pain_points JSONB NOT NULL,
 notes TEXT NOT NULL DEFAULT '', farmer_confirmed TEXT NOT NULL DEFAULT 'unknown',
 version INTEGER NOT NULL DEFAULT 1, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def normal_user(value):
    raw = str(value or '').strip()
    digits = re.sub(r'[\s()+.-]', '', raw)
    if digits.isdigit():
        if len(digits) == 12 and digits.startswith('91'):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith('0'):
            digits = digits[1:]
        if len(digits) == 10 and digits[0] in '6789':
            return '+91' + digits
    return raw


def participant_id(user):
    return hashlib.sha256(normal_user(user).encode()).hexdigest()[:20]


def conversation_id(participant, session):
    return hashlib.sha256(f'{participant}:{session}'.encode()).hexdigest()[:24]


def init():
    if not db.is_available():
        return False
    try:
        with db.connection() as c:
            c.execute(SCHEMA)
        return True
    except Exception:
        print('Analytics storage unavailable; advisory service remains available')
        return False


def _write(sql, params):
    if not db.is_available():
        return False
    try:
        with db.connection() as c:
            c.execute('SET LOCAL statement_timeout=3000')
            c.execute(sql, params)
        return True
    except Exception:
        print('Analytics write failed (no request content or credentials logged)')
        return False


def begin(user_id, session_id, channel, request_id=None):
    request_id = request_id or str(uuid4())
    _write("""INSERT INTO analytics_requests
       (request_id,user_id,session_id,channel,release,models) VALUES (%s,%s,%s,%s,%s,%s)
       ON CONFLICT (request_id) DO UPDATE SET attempts=analytics_requests.attempts+1
       WHERE analytics_requests.user_id IS NOT DISTINCT FROM EXCLUDED.user_id""",
       (request_id, normal_user(user_id) if user_id else None, session_id, channel,
        os.getenv('K_REVISION') or os.getenv('APP_RELEASE', 'local'), os.getenv('TEXT_MODELS', 'default')))
    return request_id


def finish(request_id, user_id, result, elapsed_ms, language):
    return _write("""UPDATE analytics_requests SET status='answered',answered_at=now(),
       backend_ms=%s,intent=%s,message_type=%s,crop=%s,state=%s,language=%s,dose_status=%s,
       tools=%s::jsonb,evidence=%s::jsonb,missing_slots=%s::jsonb,error_kind=NULL
       WHERE request_id=%s AND user_id IS NOT DISTINCT FROM %s AND answered_at IS NULL""",
       (elapsed_ms,result.intent,result.message_type,result.crop,result.state,language,
        result.dose_status,json.dumps(result.tools_used),json.dumps(getattr(result,'source_evidence',{})),
        json.dumps(result.missing_slots),request_id,normal_user(user_id) if user_id else None))


def fail(request_id, user_id, error_kind):
    _write("""UPDATE analytics_requests SET status='failed',failed_at=now(),error_kind=%s
       WHERE request_id=%s AND user_id IS NOT DISTINCT FROM %s AND answered_at IS NULL""",
       (error_kind,request_id,normal_user(user_id) if user_id else None))


def delivery(request_id, status, segments=None):
    # Accepted by the gateway is not a handset delivery receipt.
    return _write("""UPDATE analytics_requests SET gateway_status=%s,
       gateway_updated_at=now(),sms_segments=%s WHERE request_id=%s
       AND status='answered' AND gateway_status IS DISTINCT FROM 'gateway_accepted'""",
       (status,segments,request_id))


def evidence_summary(evidence):
    result = {}
    for name, value in (evidence or {}).items():
        text = str(value or '')
        result[name] = {
            'output_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'available': bool(text) and not any(s in text.lower() for s in
                ['unavailable', 'no mandi price', 'no approved', 'no registered', 'no records']),
        }
        if name == 'mandi':
            result[name]['arrival_dates'] = sorted(set(re.findall(r'Arrival Date:\s*(\d{2}/\d{2}/\d{4})', text)))
            result[name]['markets'] = sorted(set(re.findall(r'Market:\s*([^|\n]+)', text)))[:100]
            result[name]['date_provenance'] = 'source arrival_date, not download time'
    return result
