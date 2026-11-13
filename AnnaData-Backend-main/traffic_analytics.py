"""First-party website events. No URLs, IPs, phone numbers or message content stored.

Browser traffic is observed telemetry, not a bot-proof census. Sign-in events
are emitted only by the verified authentication flow, never accepted from clients.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from typing import Literal
from psycopg.rows import dict_row
from psycopg.errors import UndefinedTable
import auth
import db
import guest_access
from metrics_store import participant_id
from analytics_metrics import audience_matches, rate, stamp

log = logging.getLogger(__name__)
router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
SCHEMA = """
CREATE TABLE IF NOT EXISTS web_analytics_start (
 id INTEGER PRIMARY KEY CHECK (id=1), started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO web_analytics_start(id) VALUES(1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS web_analytics_identity (
 guest_id TEXT PRIMARY KEY, participant_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS web_analytics_events (
 event_id UUID PRIMARY KEY, visitor_id TEXT, session_id TEXT,
 guest_id TEXT, participant_id TEXT, kind TEXT NOT NULL,
 medium TEXT NOT NULL DEFAULT 'web', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS web_analytics_time ON web_analytics_events(created_at);
CREATE INDEX IF NOT EXISTS web_analytics_visitor ON web_analytics_events(visitor_id, created_at);
CREATE INDEX IF NOT EXISTS web_analytics_account ON web_analytics_events(participant_id);
"""


def init():
    if not db.is_available(): return False
    try:
        with db.connection() as c:
            c.execute(SCHEMA)
        return True
    except Exception:
        log.warning('Website analytics storage unavailable')
        return False


class VisitContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    visitor_id: UUID
    session_id: UUID
    guest_id: UUID


class BrowserEvent(VisitContext):
    event_id: UUID
    kind: Literal['page_view', 'visit', 'message_submit']
    medium: Literal['web', 'voice', 'photo'] = 'web'


limiter = guest_access.GuestLimiter(per_guest=300, per_ip=3000, daily_cap=100000)


def record(event, user_id=None):
    if not db.is_available(): return False
    try:
        with db.connection() as c:
            c.execute('SET LOCAL statement_timeout=3000')
            c.execute("""INSERT INTO web_analytics_events
              (event_id,visitor_id,session_id,guest_id,participant_id,kind,medium)
              VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
              (str(event.event_id), participant_id('visitor:'+str(event.visitor_id)),
               participant_id('visit:'+str(event.session_id)), participant_id('guest:'+str(event.guest_id)),
               participant_id(user_id) if user_id else None, event.kind, event.medium))
        return True
    except Exception:
        log.warning('Website analytics event not stored')
        return False


@router.post('/analytics/events', status_code=202)
def receive(event: BrowserEvent, request: Request, authorization: str = Header(default='')):
    # In-memory per-instance limits bound accidental loops and basic abuse.
    address=guest_access.client_ip(request.headers.get('x-forwarded-for'), request.client.host if request.client else None)
    allowed, _, _=limiter.check(str(event.visitor_id), address)
    if not allowed:
        raise HTTPException(429, 'Analytics rate limit')
    user=auth.read_token(authorization[7:]) if authorization.startswith('Bearer ') else None
    return {'stored': record(event, user)}


def signed_in(user_id, guest_id, context=None):
    """Called after OTP/widget verification. A client cannot invent account events."""
    if not context or not db.is_available(): return False
    try:
        with db.connection() as c:
            c.execute('SET LOCAL statement_timeout=3000')
            account=participant_id(user_id)
            guest=guest_access.guest_user_id(guest_id)
            gid=participant_id(guest) if guest else None
            if gid:
                # Immutable claim: do not reassign a previously linked guest to another account.
                c.execute('INSERT INTO web_analytics_identity(guest_id,participant_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(gid,account))
            c.execute("""INSERT INTO web_analytics_events
                (event_id,visitor_id,session_id,guest_id,participant_id,kind)
                VALUES(%s,%s,%s,%s,%s,'sign_in')""",
                (str(uuid4()), participant_id('visitor:'+str(context.visitor_id)) if context else None,
                 participant_id('visit:'+str(context.session_id)) if context else None,gid,account))
        return True
    except Exception:
        log.warning('Website sign-in analytics not stored')
        return False


def summarize(events, first_visits, since, now, started_at, audience='all'):
    visitors={e['visitor_id'] for e in events if e['visitor_id']}
    sending={e['visitor_id'] for e in events if e['kind']=='message_submit' and e['visitor_id'] in visitors}
    signing={e['visitor_id'] for e in events if e['kind']=='sign_in' and e['visitor_id'] in visitors}
    accounts={e['actor'] for e in events if e['kind']=='sign_in'}
    senders={e['actor'] for e in events if e['kind']=='message_submit'}
    sessions={(e['visitor_id'], e['session_id']) for e in events if e['visitor_id'] in visitors and e['session_id']}
    activity=defaultdict(lambda: {'visitors':set(), 'senders':set(), 'accounts':set(), 'page_views':0})
    returned=set(); repeat_senders=set(); order=defaultdict(dict)
    for e in events:
        at=stamp(e['created_at']); date=at.astimezone(IST).date().isoformat()
        v=e['visitor_id']; kind=e['kind']
        if v in visitors:
            activity[date]['visitors'].add(v)
            first=first_visits.get(v)
            if first and stamp(first).astimezone(IST).date()<at.astimezone(IST).date():returned.add(v)
        if kind=='page_view':activity[date]['page_views']+=1
        if kind=='message_submit':
            activity[date]['senders'].add(e['actor'])
            if v in visitors:
                order[v]['message_submit']=min(at,order[v].get('message_submit',at))
                prior=e.get('first_message')
                if prior and stamp(prior).astimezone(IST).date()<at.astimezone(IST).date(): repeat_senders.add(e['actor'])
        if kind=='sign_in':
            activity[date]['accounts'].add(e['actor'])
            if v in visitors:order[v]['sign_in']=min(at,order[v].get('sign_in',at))
    both=sending & signing
    asked_first=sum(order[v]['message_submit']<=order[v]['sign_in'] for v in both)
    daily=[]; day=stamp(since).astimezone(IST).date()
    while day<=now.astimezone(IST).date():
        key=day.isoformat(); a=activity[key]
        daily.append({'date':key, 'visitors':len(a['visitors']), 'senders':len(a['senders']), 'signed_in':len(a['accounts']), 'page_views':a['page_views']})
        day+=timedelta(days=1)
    return {'available':True,'started_at':started_at,'audience':audience,
            'visits':len(sessions), 'page_views':sum(e['kind']=='page_view' for e in events),
            'unique_visitors':len(visitors),'message_senders':len(senders),'signed_in_accounts':len(accounts),
            'returning_visitors':len(returned),'repeat_message_senders':len(repeat_senders),
            'sender_browsers':len(sending),'signed_in_browsers':len(signing),
            'visitor_to_message':rate(len(sending),len(visitors)),
            'visitor_to_signin':rate(len(signing),len(visitors)),
            'visitor_return_rate':rate(len(returned),len(visitors)),
            'message_and_signin':rate(len(both),len(sending)),
            'no_message':len(visitors-sending),'message_without_signin':len(sending-signing),
            'ask_then_signin':asked_first,'signin_then_ask':len(both)-asked_first,
            'daily':daily,'events_observed':len(events)}


def dashboard(days, audience, excluded, all_time=False):
    now=datetime.now(timezone.utc);since=now-timedelta(days=days)
    try:
        with db.connection() as c:
            c.execute('SET LOCAL statement_timeout=15000')
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute('SELECT started_at FROM web_analytics_start WHERE id=1')
                start=cur.fetchone()
                if all_time and start: since=start['started_at']
                cur.execute("""SELECT e.*,COALESCE(e.participant_id,i.participant_id,e.guest_id,e.visitor_id) AS actor,
                    COALESCE(a.category,'unknown') AS category
                    FROM web_analytics_events e LEFT JOIN web_analytics_identity i ON i.guest_id=e.guest_id
                    LEFT JOIN analytics_audience a ON a.participant_id=COALESCE(e.participant_id,i.participant_id,e.guest_id)
                    WHERE e.created_at >= %s ORDER BY e.created_at LIMIT 50001""",(since,))
                rows=cur.fetchall()
                if len(rows)>50000:return {'available':False,'reason':'More than 50,000 website events. Select a shorter window.'}
                rows=[r for r in rows if audience_matches('test' if r['actor'] in excluded else r['category'],audience)]
                visitors=list({r['visitor_id'] for r in rows if r['visitor_id']})
                cur.execute("""SELECT visitor_id,min(created_at) AS first_at FROM web_analytics_events
                    WHERE visitor_id=ANY(%s) GROUP BY visitor_id""",(visitors,))
                first={r['visitor_id']:r['first_at'] for r in cur.fetchall()}
                actors=list({r['actor'] for r in rows})
                cur.execute("""SELECT COALESCE(e.participant_id,i.participant_id,e.guest_id,e.visitor_id) AS actor,
                    min(e.created_at) AS first_at FROM web_analytics_events e
                    LEFT JOIN web_analytics_identity i ON i.guest_id=e.guest_id
                    WHERE e.kind='message_submit' AND COALESCE(e.participant_id,i.participant_id,e.guest_id,e.visitor_id)=ANY(%s)
                    GROUP BY 1""",(actors,))
                first_messages={r['actor']:r['first_at'] for r in cur.fetchall()}
                for r in rows:r['first_message']=first_messages.get(r['actor'])
        result=summarize(rows,first,since,now,start['started_at'] if start else None,audience)
        result['scope']='Since tracking began' if all_time else f'Last {days} days'
        return result
    except UndefinedTable:
        return {'available':False,'reason':'Website tracking is not installed yet. Deploy the backend and frontend to start collecting visits; past visits cannot be reconstructed.'}
    except Exception:
        log.warning('Website funnel unavailable')
        return {'available':False,'reason':'Website analytics could not be read. No traffic totals are inferred from messages.'}
