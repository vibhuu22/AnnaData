// Independent from sign-in: signing in must not create another website visitor.
let visitor = null, session = null;
const ID_KEY = 'annadata.analytics.visitor';
const SESSION_KEY = 'annadata.analytics.session';
const TIMEOUT = 30 * 60 * 1000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function eventId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{
    const n=Math.floor(Math.random()*16);return (c==='x'?n:(n&3)|8).toString(16);
  });
}
export function trackingAllowed() {
  return navigator.doNotTrack !== '1' && !navigator.globalPrivacyControl;
}
export function trafficContext() {
  if (!trackingAllowed()) return null;
  try { visitor = localStorage.getItem(ID_KEY) || visitor; } catch (_) { /* page memory */ }
  if (!UUID.test(visitor||'')) visitor=eventId();
  const now=Date.now();
  try { const saved=JSON.parse(localStorage.getItem(SESSION_KEY));if(saved)session=saved; } catch (_) { /* page memory */ }
  if (!session || !UUID.test(session.id||'') || !Number.isFinite(session.last) || now-session.last >= TIMEOUT || now<session.last) session={id:eventId(),last:now};
  session.last=now;
  try { localStorage.setItem(ID_KEY,visitor);localStorage.setItem(SESSION_KEY,JSON.stringify(session)); } catch (_) { /* page memory */ }
  return {visitor_id:visitor,session_id:session.id};
}
