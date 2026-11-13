"""Pure, testable metric definitions. Unknown is never a zero success rate."""
import hashlib
import math
import re
from collections import Counter, defaultdict
from statistics import median
from datetime import datetime, timedelta, timezone

from metrics_store import participant_id, conversation_id

PAIN_POINTS = {
 'market_price': 'Markets & selling', 'disease_pest': 'Pests & disease',
 'fertiliser_nutrition': 'Soil & nutrition', 'irrigation_water': 'Irrigation',
 'sowing_planting': 'Crop planning', 'weather_query': 'Weather',
 'scheme_subsidy': 'Schemes & finance', 'storage_postharvest': 'Harvest & storage',
 'animal_intrusion': 'Animal damage', 'equipment_cost': 'Equipment & costs',
 'general': 'Other / unclassified',
}
AUDIENCES = {'farmer','test','unknown','system'}
VERDICTS = {'useful','partial','missed','clarification','out_of_scope','unassessed'}
SEVERITIES = {'clear','minor','major','critical','not_reviewed'}


def redact(value):
    text = str(value or '')
    text = re.sub(r'(?<!\w)(?:\+?91[ -]?)?[6-9](?:[ -]?\d){9}(?!\d)', '[phone]', text)
    return re.sub(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', '[email]', text)


def stamp(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace('Z','+00:00'))


def rate(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'percent': round(100 * numerator / denominator, 1) if denominator else None}


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    return round(values[max(0, math.ceil(p * len(values)) - 1)] / 1000, 2)


def build_conversations(messages, audiences, reviews, excluded, ratings=None):
    groups, active = {}, {}
    for m in sorted(messages, key=lambda x:(stamp(x['created_at']),x['id'])):
        pid = participant_id(m['user_id'])
        at = stamp(m['created_at'])
        session = m.get('session_id')
        inferred = False
        if session is not None:
            key = f'session:{session}'
        elif pid in active and at - active[pid][1] <= timedelta(hours=2):
            key = active[pid][0]
            inferred = True
        else:
            key = f'legacy:{m["id"]}'
            inferred = True
        active[pid] = (key,at)
        cid = conversation_id(pid,key)
        category = 'test' if pid in excluded else audiences.get(pid,'unknown')
        g = groups.setdefault(cid, {'id':cid,'participant_id':pid,'participant_label':'Participant '+pid[:6],
            'audience':category,'started_at':at.isoformat(),'updated_at':at.isoformat(),
            'messages':[],'pain_points':set(),'channels':set(),'inferred':False,
            'review':reviews.get(cid), 'request_ids':set(), 'ratings':[]})
        meta=m.get('meta') or {}
        body=redact(m.get('body'))
        g['messages'].append({'id':m['id'],'direction':m['direction'],'body':body,
            'created_at':at.isoformat(),'request_id':meta.get('request_id'),
            'intent':meta.get('intent'),'message_type':meta.get('message_type'),
            'tools':meta.get('tools')})
        g['updated_at']=at.isoformat()
        g['inferred'] |= inferred
        g['channels'].add(meta.get('channel') or 'unknown')
        if meta.get('request_id'): g['request_ids'].add(meta['request_id'])
        intent=meta.get('intent')
        if intent in PAIN_POINTS and intent!='general':g['pain_points'].add(intent)
    # Farmers' own ratings - a thumbs up or down on the web, a number by SMS -
    # attached to the conversation (session) they were given in. A rating
    # with no session, or one whose conversation is outside the window, is
    # left out rather than guessed onto another conversation.
    for r in ratings or []:
        if r.get('session_id') is None:
            continue
        pid = participant_id(r['user_id'])
        cid = conversation_id(pid, f"session:{r['session_id']}")
        if cid in groups:
            raw = str(r.get('raw_message') or '')
            groups[cid]['ratings'].append({
                'score': r['rating'],
                'source': 'web' if raw.startswith('web:') else 'sms',
                'note': redact(raw.split(' - ', 1)[1]) if raw.startswith('web:') and ' - ' in raw else '',
                'at': stamp(r['created_at']).isoformat(),
            })
    for g in groups.values():
        g['rated_down'] = any(x['score'] <= 2 for x in g['ratings'])
        g['pain_points'] = sorted((g['review'] or {}).get('pain_points') or g['pain_points'] or ['general'])
        g['channels']=sorted(g['channels']);g['request_ids']=sorted(g['request_ids'])
        inbound=[m for m in g['messages'] if m['direction']=='inbound']
        g['preview']=next((m['body'] for m in inbound if len(m['body'].strip())>15),inbound[0]['body'] if inbound else 'Outbound messages only')[:160]
        g['inbound_count']=len(inbound)
        g['outbound_count']=len(g['messages'])-len(inbound)
        g['review_status']='reviewed' if g['review'] and g['review']['verdict']!='unassessed' and g['review']['severity']!='not_reviewed' else 'needs_review'
        g['substantive']=any(m.get('message_type') in ['question','correction'] and m.get('intent') not in [None,'general'] for m in g['messages'])
    return sorted(groups.values(),key=lambda g:g['updated_at'],reverse=True)


def audience_matches(category, selection):
    return selection=='all' or category==selection or (selection=='non_test' and category in {'farmer','unknown'})


def overview(conversations, requests, audiences, excluded, selection, now=None):
    now=now or datetime.now(timezone.utc)
    groups=[g for g in conversations if audience_matches(g['audience'],selection)]
    telemetry=[r for r in requests if r.get('user_id') and audience_matches(
        'test' if participant_id(r['user_id']) in excluded else audiences.get(participant_id(r['user_id']),'unknown'),selection)]
    answered=[r for r in telemetry if r['status']=='answered']
    completed=[r for r in telemetry if r['status'] in {'answered','failed'}]
    pending=[r for r in telemetry if r['status']=='started']
    durations=[r['backend_ms'] for r in answered if r.get('backend_ms') is not None]
    gateway_eligible=[r for r in answered if r['channel'] in {'sms','whatsapp'}]
    gateway_observed=[r for r in gateway_eligible if r.get('gateway_status') in {'gateway_accepted','send_failed'}]
    reviewed=[g for g in groups if g.get('review') and g['review']['verdict']!='unassessed']
    safety_reviewed=[g for g in reviewed if g['review']['severity']!='not_reviewed']
    useful=[g for g in safety_reviewed if g['review']['verdict']=='useful' and g['review']['severity'] in {'clear','minor'}]
    critical=[g for g in safety_reviewed if g['review']['severity']=='critical']
    needs=Counter(p for g in groups for p in g['pain_points'])
    activity=defaultdict(lambda:{'conversations':0,'participants':set()})
    for g in groups:
        day=stamp(g['started_at']).astimezone(timezone(timedelta(hours=5,minutes=30))).date().isoformat()
        activity[day]['conversations']+=1;activity[day]['participants'].add(g['participant_id'])
    return {
      'participants':len({g['participant_id'] for g in groups}), 'conversations':len(groups),
      'messages':sum(len(g['messages']) for g in groups),'inbound_messages':sum(g['inbound_count'] for g in groups),
      'audience_counts':dict(Counter(g['audience'] for g in conversations)),
      'useful_answers':rate(len(useful),len(safety_reviewed)),
      'critical_errors':rate(len(critical),len(safety_reviewed)),
      'review_coverage':rate(len(safety_reviewed),len(groups)),
      'answer_generation':rate(len(answered),len(completed)),
      'telemetry_requests':len(telemetry),'pending_requests':len(pending),
      'abandoned_requests':sum(now-stamp(r['started_at'])>timedelta(minutes=15) for r in pending),
      'backend_latency':{'median_seconds':round(median(durations)/1000,2) if durations else None,'p95_seconds':percentile(durations,.95),'sample_size':len(durations)},
      'gateway_acceptance':rate(sum(r.get('gateway_status')=='gateway_accepted' for r in gateway_observed),len(gateway_observed)),
      'gateway_tracking_coverage':rate(len(gateway_observed),len(gateway_eligible)),
      'confirmed_delivery':None,'cost_per_useful_conversation':None,'retention_7d':None,
      'farmer_confirmed':{'yes':sum(g['review'].get('farmer_confirmed')=='yes' for g in reviewed),
                          'no':sum(g['review'].get('farmer_confirmed')=='no' for g in reviewed)},
      'inferred_conversations':sum(g['inferred'] for g in groups),
      'pain_points':[{'id':k,'label':PAIN_POINTS[k],'count':v,
        'reviewed':sum(k in g['pain_points'] for g in safety_reviewed),
        'useful':sum(k in g['pain_points'] for g in useful)} for k,v in needs.most_common()],
      'activity':[{'date':k,'conversations':v['conversations'],'participants':len(v['participants'])} for k,v in sorted(activity.items())],
      'review_queue':sum(g['review_status']=='needs_review' for g in groups),
      # Farmers' own verdicts, kept apart from the reviewer's: a tap is a
      # signal to look, not a finding.
      'farmer_ratings':{
          'up':sum(x['score']>=4 for g in groups for x in g['ratings']),
          'down':sum(x['score']<=2 for g in groups for x in g['ratings']),
          'conversations_rated_down':sum(g['rated_down'] for g in groups),
      },
    }
