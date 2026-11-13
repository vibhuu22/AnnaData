import { getApiUrl } from './api';
import { getGuestId, authHeaders } from './session';
import { eventId, trafficContext } from './trafficIdentity';
let initialized=false, visit=null, lastTouch=0;

function send(kind, context, medium='web') {
  const payload={...context,guest_id:getGuestId(),event_id:eventId(),kind,medium};
  // Best effort only. One event UUID makes a retry idempotent. No persistent
  // queue or question content; analytics never waits on or blocks advice.
  const headers={'Content-Type':'application/json',...authHeaders()};
  const attempt=()=>fetch(`${getApiUrl()}/analytics/events`,{
    method:'POST',headers,body:JSON.stringify(payload),keepalive:true,
  });
  try { Promise.resolve(attempt()).catch(()=>attempt()).catch(()=>{}); } catch (_) { /* disabled/offline */ }
}
export function trackMessage(medium='web') {
  const context=trafficContext();if(!context)return;
  if(visit!==context.session_id){visit=context.session_id;send('visit',context);}
  send('message_submit',context,medium);
}
export function startTraffic() {
  // React StrictMode must not turn a single app load into two page views.
  if(initialized)return;
  initialized=true;
  const context=trafficContext();if(!context)return;
  visit=context.session_id;send('visit',context);send('page_view',context);
  const touch=()=>{
    if(document.hidden || Date.now()-lastTouch<10000)return;
    lastTouch=Date.now();const next=trafficContext();if(!next)return;
    if(visit!==next.session_id){visit=next.session_id;send('visit',next);}
  };
  window.addEventListener('pointerdown',touch,{passive:true});
  window.addEventListener('keydown',touch);
  document.addEventListener('visibilitychange',touch);
}
