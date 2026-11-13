"""Owner-only analytics routes. Separate credential; never trusts a farmer token."""
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg import OperationalError, InterfaceError, Error as DatabaseError
from psycopg.errors import UndefinedTable, UndefinedColumn, QueryCanceled
from psycopg_pool import PoolTimeout

import db
import metrics_store as store
from dashboard_metrics import detailed_metrics
from analytics_metrics import (AUDIENCES, VERDICTS, SEVERITIES, PAIN_POINTS,
    build_conversations, overview, audience_matches, redact)

router=APIRouter()
WEB=Path(__file__).parent/'admin_web'


class ConversationDataset(list):
    ratings_available = True


def require_admin(x_admin_token: str = Header(default='')):
    expected=os.getenv('ADMIN_API_TOKEN','')
    if len(expected)<32:
        raise HTTPException(503,'Admin access is not configured')
    if not secrets.compare_digest(x_admin_token.encode(),expected.encode()):
        raise HTTPException(401,'Invalid admin credential')


@router.get('/admin', include_in_schema=False)
@router.get('/admin/', include_in_schema=False)
def page():
    return FileResponse(WEB/'index.html',headers={'Cache-Control':'no-store',
        'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"})


def excluded_participants():
    return {store.participant_id(x.strip()) for x in os.getenv('ANALYTICS_TEST_USERS','').split(',') if x.strip()}


def dataset(days):
    # Only repeat this read-only operation, never review or classification writes.
    for attempt in range(2):
        try:
            return _dataset(days)
        except (OperationalError, InterfaceError, PoolTimeout) as exc:
            logging.getLogger(__name__).warning('Admin database connection failed: %s (attempt %s)',type(exc).__name__,attempt+1)
            if attempt:
                raise HTTPException(503,'Database connection temporarily unavailable. Please try again shortly; analytics setup is not required for a connection failure.') from None


def _dataset(days):
    if not db.is_available(): raise HTTPException(503,'Analytics database unavailable')
    since=datetime.now(timezone.utc)-timedelta(days=days)
    try:
        with db.connection() as c:
            c.execute('SET LOCAL statement_timeout=15000')
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute('SELECT id,user_id,direction,body,meta,created_at,session_id FROM messages WHERE created_at >= %s ORDER BY created_at,id LIMIT 20001',(since,))
                messages=cur.fetchall()
                cur.execute('SELECT * FROM analytics_requests WHERE started_at >= %s ORDER BY started_at LIMIT 20001',(since,))
                requests=cur.fetchall()
                cur.execute('SELECT * FROM analytics_audience');audiences={r['participant_id']:r['category'] for r in cur.fetchall()}
                cur.execute('SELECT * FROM analytics_reviews');reviews={r['conversation_id']:r for r in cur.fetchall()}
                cur.execute("SELECT state,fetched_at,jsonb_array_length(records) AS records, (SELECT jsonb_agg(DISTINCT item->>'arrival_date') FROM jsonb_array_elements(mandi_cache.records) item) AS source_dates FROM mandi_cache WHERE commodity='' ORDER BY state")
                caches=cur.fetchall()
    except (UndefinedTable, UndefinedColumn):
        raise HTTPException(503,'Analytics schema is missing or outdated. Run the analytics setup command.') from None
    except QueryCanceled:
        raise HTTPException(503,'The analytics query timed out. Try again or select a shorter date window.') from None
    except (OperationalError, InterfaceError, PoolTimeout):
        raise
    except DatabaseError as exc:
        logging.getLogger(__name__).error('Admin query failed: %s; SQLSTATE=%s',type(exc).__name__,exc.sqlstate)
        raise HTTPException(503,'Analytics query failed. Check the dashboard server log for the error category.') from None
    # Farmers' ratings, read apart so a database without the feedback table
    # still shows the rest of the dashboard.
    ratings=[]
    ratings_available=True
    try:
        with db.connection() as c:
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute('SELECT user_id,session_id,rating,raw_message,created_at FROM feedback WHERE created_at >= %s ORDER BY created_at LIMIT 20001',(since,))
                ratings=cur.fetchall()
    except DatabaseError as exc:
        ratings_available=False
        logging.getLogger(__name__).warning('Ratings unavailable for the dashboard: %s',type(exc).__name__)
    if len(messages)>20000 or len(requests)>20000 or len(ratings)>20000:
        raise HTTPException(422,'Window exceeds 20,000 records. Select fewer days; partial metrics are not shown.')
    for cache in caches:
        dates=[]
        for value in cache.pop('source_dates') or []:
            try: dates.append(datetime.strptime(value,'%d/%m/%Y'))
            except (ValueError,TypeError): pass
        cache['example_date']=max(dates).strftime('%d/%m/%Y') if dates else None
    groups=ConversationDataset(build_conversations(messages,audiences,reviews,excluded_participants(),ratings))
    groups.ratings_available=ratings_available
    return groups,requests,audiences,caches,since


def check_audience(audience):
    if audience not in AUDIENCES|{'all','non_test'}:raise HTTPException(422,'Unknown audience')


@router.get('/admin/api/dashboard',dependencies=[Depends(require_admin)])
# 'all' by default: until accounts are classified, a farmers-only view is
# empty, and an empty dashboard on the first day reads as a broken one.
def dashboard(days: int=Query(30,ge=1,le=180),audience: str='all'):
    check_audience(audience)
    groups,requests,audiences,caches,since=dataset(days)
    selected=[g for g in groups if audience_matches(g['audience'],audience)]
    public=[{k:v for k,v in g.items() if k!='messages'} for g in selected]
    return {'metrics':overview(groups,requests,audiences,excluded_participants(),audience),
        'detailed':detailed_metrics(groups,requests,audiences,excluded_participants(),audience,since,
                                   ratings_available=getattr(groups,'ratings_available',True)),
        'conversations':public,'cache':caches,'window_start':since,'generated_at':datetime.now(timezone.utc),
        'definitions_version':'2.0','pain_point_labels':PAIN_POINTS,
        'limitations':['Legacy conversations can contain inferred reply matching; they are excluded from request-success and latency metrics.',
          'Gateway acceptance is not confirmed handset delivery.',
          'All traffic is the default. Only explicitly classified farmer accounts appear in the verified-farmer view.',
          'Retention and costs are not yet measured. Missing data is never counted as zero.',
          'Backend telemetry excludes requests that never reach the backend and media failures before the advisory pipeline.']}


@router.get('/admin/api/conversations/{cid}',dependencies=[Depends(require_admin)])
def conversation(cid: str,days: int=Query(30,ge=1,le=180)):
    groups,requests,_,_,_=dataset(days)
    group=next((g for g in groups if g['id']==cid),None)
    if not group:raise HTTPException(404,'Conversation not found in this window')
    group['telemetry']=[{k:v for k,v in r.items() if k!='user_id'} for r in requests if r['request_id'] in group['request_ids']]
    return group


class Review(BaseModel):
    conversation_id: str=Field(min_length=24,max_length=24)
    verdict: str
    severity: str
    pain_points: list[str]=Field(max_length=12)
    notes: str=Field(default='',max_length=4000)
    farmer_confirmed: str='unknown'
    expected_version: int=Field(default=0,ge=0)
    days: int=Field(default=30,ge=1,le=180)


@router.post('/admin/api/reviews',dependencies=[Depends(require_admin)])
def save_review(review: Review):
    if review.verdict not in VERDICTS or review.severity not in SEVERITIES or any(p not in PAIN_POINTS for p in review.pain_points) or review.farmer_confirmed not in {'yes','no','unknown'}:
        raise HTTPException(422,'Invalid review category')
    if review.verdict!='unassessed' and not review.pain_points:raise HTTPException(422,'Choose at least one pain point')
    group=conversation(review.conversation_id,review.days)
    with db.connection() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(review.conversation_id,))
        previous=c.execute('SELECT version FROM analytics_reviews WHERE conversation_id=%s',(review.conversation_id,)).fetchone()
        if (previous[0] if previous else 0)!=review.expected_version:
            raise HTTPException(409,'This review changed. Reload the conversation before saving.')
        from json import dumps
        c.execute("""INSERT INTO analytics_reviews
          (conversation_id,participant_id,verdict,severity,pain_points,notes,farmer_confirmed)
          VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT(conversation_id) DO UPDATE SET
          verdict=EXCLUDED.verdict,severity=EXCLUDED.severity,pain_points=EXCLUDED.pain_points,
          notes=EXCLUDED.notes,farmer_confirmed=EXCLUDED.farmer_confirmed,
          version=analytics_reviews.version+1,updated_at=now()""",
          (group['id'],group['participant_id'],review.verdict,review.severity,dumps(review.pain_points),redact(review.notes),review.farmer_confirmed))
    return {'saved':True}


class Audience(BaseModel):
    participant_id: str=Field(min_length=20,max_length=20)
    category: str
    days: int=Field(default=30,ge=1,le=180)


@router.post('/admin/api/audience',dependencies=[Depends(require_admin)])
def save_audience(item: Audience):
    if item.category not in AUDIENCES:raise HTTPException(422,'Invalid audience')
    if item.participant_id in excluded_participants() and item.category!='test':
        raise HTTPException(409,'This account is excluded by ANALYTICS_TEST_USERS. Update server configuration to change that decision.')
    groups,_,_,_,_=dataset(item.days)
    if not any(g['participant_id']==item.participant_id for g in groups):raise HTTPException(404,'Participant not found')
    with db.connection() as c:
        c.execute('INSERT INTO analytics_audience(participant_id,category) VALUES (%s,%s) ON CONFLICT(participant_id) DO UPDATE SET category=EXCLUDED.category,updated_at=now()',
            (item.participant_id,item.category))
    return {'saved':True}
