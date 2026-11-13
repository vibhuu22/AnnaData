import { trafficContext } from './trafficIdentity';
import { startTraffic, trackMessage } from './traffic';
import { setToken } from './session';

beforeEach(()=>{localStorage.clear();global.fetch=jest.fn(async()=>({ok:true}));setToken('');});
afterEach(()=>{jest.restoreAllMocks();delete global.fetch;});

test('browser identity survives sign-in while inactive sessions rotate',()=>{
 const first=trafficContext();setToken('signed-in');
 expect(trafficContext()).toEqual(first);
 jest.spyOn(Date,'now').mockReturnValue(Date.now()+31*60*1000);
 const later=trafficContext();expect(later.visitor_id).toBe(first.visitor_id);expect(later.session_id).not.toBe(first.session_id);
});
test('tracking cannot submit an OTP verification event',()=>{
 trackMessage('photo');const calls=fetch.mock.calls.map(c=>JSON.parse(c[1].body));
 expect(calls.at(-1).kind).toBe('message_submit');expect(calls.at(-1).medium).toBe('photo');
 expect(calls.some(c=>c.kind==='sign_in')).toBe(false);
 expect(Object.keys(calls[0]).sort()).toEqual(['event_id','guest_id','kind','medium','session_id','visitor_id']);
});
test('StrictMode initialization records one page load',()=>{
 startTraffic();startTraffic();expect(fetch.mock.calls.map(c=>JSON.parse(c[1].body)).filter(c=>c.kind==='page_view')).toHaveLength(1);
});
test('storage restrictions do not block tracking or messages',()=>{
 jest.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new Error('blocked')});
 jest.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('blocked')});
 expect(()=>trackMessage()).not.toThrow();expect(trafficContext().visitor_id).toBeTruthy();
});
test('privacy opt-out suppresses events',()=>{
 Object.defineProperty(navigator,'doNotTrack',{value:'1',configurable:true});
 trackMessage();expect(fetch).not.toHaveBeenCalled();expect(trafficContext()).toBeNull();
 delete navigator.doNotTrack;
});
