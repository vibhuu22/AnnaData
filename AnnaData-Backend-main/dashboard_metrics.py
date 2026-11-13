"""Owner analytics derived from recorded events, never inferred farm outcomes."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from analytics_metrics import audience_matches, stamp, rate, percentile
from metrics_store import participant_id

IST = timezone(timedelta(hours=5, minutes=30))


def breakdown(rows, field):
    buckets = defaultdict(list)
    for row in rows:
        buckets[str(row.get(field) or 'unknown')].append(row)
    result = []
    for label, items in buckets.items():
        done = [r for r in items if r['status'] in ('answered', 'failed')]
        failed = sum(r['status'] == 'failed' for r in done)
        times = [r['backend_ms'] for r in items if r['status'] == 'answered' and r.get('backend_ms') is not None]
        result.append({'label': label, 'requests': len(items),
                       'participants': len({participant_id(r['user_id']) for r in items if r.get('user_id')}),
                       'failure_rate': rate(failed, len(done)), 'p95_seconds': percentile(times, .95)})
    return sorted(result, key=lambda r: (-r['requests'], r['label']))


def detailed_metrics(groups, requests, audiences, excluded, selection, since, now=None,
                     ratings_available=True):
    now = now or datetime.now(timezone.utc)
    selected = [g for g in groups if audience_matches(g['audience'], selection)]
    rows = [r for r in requests if r.get('user_id') and audience_matches(
        'test' if participant_id(r['user_id']) in excluded else audiences.get(participant_id(r['user_id']), 'unknown'), selection)]
    days = {}
    day = stamp(since).astimezone(IST).date()
    while day <= now.astimezone(IST).date():
        days[day.isoformat()] = {'date': day.isoformat(), 'messages': 0, 'participants': set(), 'requests': 0, 'failed': 0}
        day += timedelta(days=1)
    user_days = defaultdict(set)
    inbound = []
    for g in selected:
        for m in g['messages']:
            if m['direction'] != 'inbound':
                continue
            at = stamp(m['created_at'])
            key = at.astimezone(IST).date().isoformat()
            if key in days:
                days[key]['messages'] += 1
                days[key]['participants'].add(g['participant_id'])
                user_days[g['participant_id']].add(key)
                inbound.append((g['participant_id'], at))
    for r in rows:
        key = stamp(r['started_at']).astimezone(IST).date().isoformat()
        if key in days:
            days[key]['requests'] += 1
            days[key]['failed'] += r['status'] == 'failed'
    active = {str(n): len({pid for pid, at in inbound if at >= now-timedelta(days=n)}) for n in (1, 7, 30)}
    completed = [r for r in rows if r['status'] in ('answered', 'failed')]
    failed = [r for r in completed if r['status'] == 'failed']
    answered = [r for r in rows if r['status'] == 'answered']
    times = [r['backend_ms'] for r in answered if r.get('backend_ms') is not None]
    ratings = [r for g in selected for r in g.get('ratings', [])]
    scores = Counter(r['score'] for r in ratings)
    reviewed = [g for g in selected if g['review_status'] == 'reviewed']
    rated_groups = [g for g in selected if g.get('ratings')]
    request_ids = {r['request_id'] for r in rows}
    incoming_links = [m.get('request_id') for g in selected for m in g['messages'] if m['direction'] == 'inbound']
    tools = Counter(t for r in rows for t in set(r.get('tools') or []))
    evidence = defaultdict(lambda: {'observed': 0, 'available': 0})
    for r in rows:
        for name, info in (r.get('evidence') or {}).items():
            if isinstance(info, dict) and isinstance(info.get('available'), bool):
                evidence[name]['observed'] += 1
                evidence[name]['available'] += info['available']
    topic = Counter(p for g in selected for p in g['pain_points'])
    dimensions = {field: breakdown(rows, field) for field in ('channel', 'language', 'state', 'crop', 'intent', 'dose_status', 'release')}
    classified = Counter(g['audience'] for g in selected)
    insights = []
    if classified['unknown']:
        insights.append({'tone': 'warning', 'title': 'Audience classification is incomplete',
                         'text': f"{classified['unknown']} conversations are unclassified. Participant identifiers are not verified farmer counts.", 'view': 'reviews'})
    if not reviewed:
        insights.append({'tone': 'warning', 'title': 'Answer quality has no reviewed baseline',
                         'text': 'No complete outcome-and-safety reviews in this selection. A generated answer is not proof that it helped.', 'view': 'reviews'})
    if any(g.get('rated_down') for g in selected):
        insights.append({'tone': 'warning', 'title': 'Negative feedback needs investigation',
                         'text': f"{sum(g.get('rated_down', False) for g in selected)} conversations received a negative rating. Read the exchange before judging the cause.", 'view': 'feedback'})
    if failed:
        insights.append({'tone': 'danger', 'title': 'Recorded backend failures', 'text': f'{len(failed)} of {len(completed)} completed requests failed. Inspect the error breakdown.', 'view': 'efficiency'})
    messaging = [r for r in answered if r['channel'] in ('sms', 'whatsapp')]
    missing_delivery = sum(r.get('gateway_status') not in ('gateway_accepted', 'send_failed') for r in messaging)
    if missing_delivery:
        insights.append({'tone': 'warning', 'title': 'Messaging delivery tracking is incomplete', 'text': f'{missing_delivery} answered messaging requests have no gateway result. Delivery cannot be confirmed.', 'view': 'health'})
    return {
        'adoption': {'active': active, 'active_in_window': len(user_days),
                     'repeat_on_multiple_days': rate(sum(len(v) > 1 for v in user_days.values()), len(user_days)),
                     'incoming_per_active': round(len(inbound)/len(user_days), 2) if user_days else None,
                     'activity': [{**d, 'participants': len(d['participants'])} for d in days.values()],
                     'observed_days': sum(bool(d['messages']) for d in days.values())},
        'efficiency': {'failure_rate': rate(len(failed), len(completed)),
                       'failed': len(failed), 'answered': len(answered),
                       'p50_seconds': percentile(times, .5), 'p95_seconds': percentile(times, .95), 'p99_seconds': percentile(times, .99),
                       'latency_samples': len(times), 'retried_requests': sum((r.get('attempts') or 1) > 1 for r in rows),
                       'extra_attempts': sum(max(0, (r.get('attempts') or 1)-1) for r in rows),
                       'errors': dict(Counter(r.get('error_kind') or 'unknown' for r in failed)),
                       'message_types': dict(Counter(r.get('message_type') or 'unknown' for r in rows))},
        'dimensions': dimensions, 'topics': dict(topic),
        'feedback': {'available': ratings_available, 'total': len(ratings) if ratings_available else None,
                     'scores': {str(k): scores[k] for k in range(1, 6)} if ratings_available else None,
                     'positive': rate(sum(r['score'] >= 4 for r in ratings), len(ratings)) if ratings_available else None,
                     'coverage': rate(len(rated_groups), len(selected)) if ratings_available else None,
                     'sources': dict(Counter(r['source'] for r in ratings)) if ratings_available else None,
                     'review_outcomes': dict(Counter(g['review']['verdict'] for g in reviewed)),
                     'severity': dict(Counter(g['review']['severity'] for g in reviewed)),
                     'oldest_unreviewed': min((g['started_at'] for g in selected if g['review_status'] != 'reviewed'), default=None)},
        'health': {'linked_incoming': rate(sum(rid in request_ids for rid in incoming_links), len(incoming_links)),
                   'coverage': {k: rate(sum(bool(r.get(k)) for r in rows), len(rows)) for k in ('crop', 'state', 'language', 'evidence', 'release')},
                   'tools': dict(tools), 'evidence': dict(evidence), 'ratings_available': ratings_available},
        'insights': insights, 'window_days': round((now-stamp(since)).total_seconds()/86400),
        'definitions': [
            ['Active participant', 'A distinct pseudonymous identifier with an incoming message. Guest browsers and test identities can inflate this count.'],
            ['Active 24h / 7d / 30d', 'Distinct incoming-message participants in each trailing interval, limited to the selected data window. Longer intervals are unavailable when the selection is shorter.'],
            ['Repeat activity', 'Participants active on at least two IST dates within this window / participants active in the window. This is not cohort retention.'],
            ['Backend failure rate', 'Failed / (answered + failed) tracked requests. Pending requests, pre-pipeline failures and browser failures are excluded.'],
            ['Latency percentiles', 'Nearest-rank p50/p95/p99 backend duration for answered requests with timing. Failed requests and media preprocessing are excluded.'],
            ['Diversity breakdowns', 'Recorded request context, not demographics. One identifier can appear in multiple channels, crops, states or reply-language codes. State is answer context, not verified residence; language is reply speech code, not native language.'],
            ['Positive ratings', 'Scores 4–5 / all attached ratings, including neutral score 3. Ratings are events, not unique people.'],
            ['Review coverage', 'Conversations with both outcome and safety reviewed / conversations in the selection. Reviews and farmer ratings are separate.'],
            ['Tracking linkage', 'Incoming messages whose request ID matches selected telemetry / selected incoming messages. Legacy records and identity changes can reduce linkage.'],
            ['Time window', 'Rolling timestamp cutoff; first and current IST calendar days can be partial. Zero-activity dates are included.'],
        ]}
