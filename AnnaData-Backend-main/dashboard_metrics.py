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


# --- North Star: weekly returning farmers with an answered question --------
#
# The one number that says farmers are getting value. Counted per IST week
# (Monday to Sunday): distinct participants who, that week,
#   1. asked a real farming question (message_type "question"),
#   2. got an answer - not a greeting, an "about AnnaData", an acknowledgement,
#      an off-topic reply, a recorded failure, or the reply to a voice note
#      with no words in it,
#   3. and had already had such an answer on an earlier IST date within the
#      previous 30 days.
# Coming back is the measurable stand-in for "found the last answer worth
# acting on". Test and system accounts are never counted.

NOT_ANSWERS = {'greeting', 'about', 'acknowledge', 'direct', 'farm', 'correction'}
EMPTY_MEDIA = 'What is wrong with this crop, and what should I do about it?'
RETURN_DAYS = 30


def answered_questions(groups, requests):
    """participant id -> sorted times of the answers that count."""
    status = {r['request_id']: r['status'] for r in requests if r.get('request_id')}
    events = defaultdict(list)
    for g in groups:
        if g['audience'] in ('test', 'system'):
            continue
        last_in = None
        for m in g['messages']:
            if m['direction'] == 'inbound':
                last_in = m
                continue
            if m.get('message_type') != 'question':
                continue
            tools = set(m.get('tools') or [])
            if tools and tools <= NOT_ANSWERS:
                continue
            if status.get(m.get('request_id')) == 'failed':
                continue
            if last_in and str(last_in.get('body') or '').startswith(EMPTY_MEDIA[:28]):
                continue
            events[g['participant_id']].append(stamp(m['created_at']))
    return {pid: sorted(times) for pid, times in events.items()}


def _week_start(at):
    local = at.astimezone(IST)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday


def north_star(groups, requests, since, now=None):
    now = now or datetime.now(timezone.utc)
    events = answered_questions(groups, requests)
    weeks = []
    start = _week_start(stamp(since))
    current = _week_start(now)
    previous_answered = None
    while start <= current:
        end = start + timedelta(days=7)
        answered, returning, first_time = set(), set(), set()
        for pid, times in events.items():
            in_week = [t for t in times if start <= t.astimezone(IST) < end]
            if not in_week:
                continue
            answered.add(pid)
            first = in_week[0]
            earlier = [t for t in times if t < first and first - t <= timedelta(days=RETURN_DAYS)
                       and t.astimezone(IST).date() < first.astimezone(IST).date()]
            (returning if earlier else first_time).add(pid)
        came_back = rate(len(previous_answered & answered), len(previous_answered)) if previous_answered is not None else None
        weeks.append({
            'week_start': start.date().isoformat(), 'date': start.date().isoformat(),
            'value': len(returning), 'answered': len(answered), 'first_time': len(first_time),
            'returned_from_last_week': came_back,
            'partial': end > now.astimezone(IST),
            # Fewer than RETURN_DAYS of history before this week: some returning
            # farmers can look first-time because their earlier answer is
            # outside the window.
            'lookback_complete': start - timedelta(days=RETURN_DAYS) >= stamp(since).astimezone(IST),
        })
        previous_answered = answered
        start = end
    complete = [w for w in weeks if not w['partial']]
    return {
        'name': 'Weekly returning farmers with an answered question',
        'this_week': weeks[-1] if weeks else None,
        'last_complete_week': complete[-1] if complete else None,
        'week_before': complete[-2] if len(complete) > 1 else None,
        'weeks': weeks,
        'definition': ('Distinct participants who, in an IST week (Mon-Sun), asked a farming question and got an '
                       'answer, and had also had an answered question on an earlier date in the previous 30 days. '
                       'Greetings, "about AnnaData", acknowledgements, off-topic replies, failures and empty voice '
                       'notes do not count. Test and system accounts are excluded; unclassified accounts are '
                       'included, so mark your own and testers\' numbers as test.'),
    }


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
        'north_star': north_star(groups, requests, since, now),
        'insights': insights, 'window_days': round((now-stamp(since)).total_seconds()/86400),
        'definitions': [
            ['North Star: weekly returning farmers with an answered question', 'Distinct participants who, in an IST week (Mon-Sun), asked a farming question and got an answer, and had also had an answered question on an earlier date in the previous 30 days. Greetings, "about AnnaData", acknowledgements, off-topic replies, failures and empty voice notes do not count. Test and system accounts are always excluded, whatever the audience filter.'],
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
