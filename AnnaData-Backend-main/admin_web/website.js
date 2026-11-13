function bindWebsiteScope() {
 const button=document.querySelector('#website-all-time');if(!button)return;
 button.onclick=async()=>{
  const snapshot=data;button.disabled=true;
  try {
   const result=await api(`website?days=${$('#period').value}&audience=${$('#audience').value}&all_time=${data.website?.scope!=='Since tracking began'}`);
   if(data!==snapshot)return;
   data.website=result;render();
  }catch(e){toast(e.message);button.disabled=false;}
 };
}
function websitePage() {
 const w=data.website||{available:false,reason:'Website tracking has not been deployed.'};
 const value=k=>w.available?fmt(w[k]):'Not measured';
 const ratio=k=>w.available?pct(w[k]):'Not measured';
 const scope=w.scope||$('#period').selectedOptions[0].text;
 const scopeNote=`<div class="scope-note"><strong>${esc(scope)}</strong><span>${esc($('#audience').selectedOptions[0].text)} · website only</span><button class="secondary" id="website-all-time">${w.scope==='Since tracking began'?'Use selected period':'Since tracking began'}</button></div>`;
 const status=!w.available?`<div class="notice"><div><strong>Tracking is not available yet</strong><p>${esc(w.reason)}</p><p>The funnel will fill with observed traffic after backend and frontend deployment. Existing messages are not a substitute for past visitors.</p></div></div>`:
 `<div class="notice"><div><strong>Tracking available since ${date(w.started_at)}</strong><p>First-party events only. Privacy opt-outs, blocked requests, offline visits and bots affect coverage. Browser identifiers are not guaranteed unique people. A zero means no recorded events, not proof of no visitors.</p></div></div>`;
 const cards=`<section class="kpis">${[
 card('Total visits',value('visits'),'Distinct 30-minute-inactivity browser sessions',true),
 card('Unique website visitors',value('unique_visitors'),'Distinct observed browser identifiers'),
 card('People who sent a message',value('message_senders'),'Distinct guest/account identities after sign-in linking'),
 card('People who signed in',value('signed_in_accounts'),'Distinct accounts with verified sign-in events'),
 card('Returning visitors',value('returning_visitors'),'Browsers seen on an earlier IST date'),
 card('Returned and messaged again',value('repeat_message_senders'),'Identities with a message on an earlier IST date')
 ].join('')}</section>`;
 const stages=[['Website visitors','unique_visitors',null,'Browser identifiers with website activity.'],
 ['Visitors who sent a message','sender_browsers','visitor_to_message','Message submitted; this does not mean an answer succeeded.'],
 ['Visitors who signed in','signed_in_browsers','visitor_to_signin','Verified OTP/widget sign-in; restored sessions are not new sign-ins.'],
 ['Visitors who returned','returning_visitors','visitor_return_rate','At least one earlier visit on a different IST date.']];
 const funnel=panel('Visitor conversion','Each percentage uses unique website visitors as its denominator. These are overlapping outcomes, not a forced sequential funnel.',`<div class="website-stages">${stages.map(([label,key,r,desc],i)=>`<div class="website-stage"><span class="stage-number">0${i+1}</span><div><h3>${esc(label)}</h3><p>${esc(desc)}</p><div class="track"><div style="width:${w.available&&w.unique_visitors?Math.min(100,100*w[key]/w.unique_visitors):0}%"></div></div></div><strong>${value(key)}</strong><span>${r?ratio(r):w.available&&w.unique_visitors?'100%':'—'}</span></div>`).join('')}</div>`);
 const loss=panel('Where visitors stop','Observed within this scope. These are counts, not assumed reasons for leaving.',metricTable(['Outcome','Visitors / conversion'],[
 ['Visited without sending a message',value('no_message')],
 ['Sent a message without a sign-in event',value('message_without_signin')],
 ['Message senders who also signed in',w.available?`${pct(w.message_and_signin)} · ${sample(w.message_and_signin)} browser visitors`:'Not measured'],
 ['App page loads',value('page_views')]
 ]));
 const paths=panel('Both paths count','First observed message and verified sign-in in this scope; not necessarily the same session.',barsFromCounts(w.available?{'Asked, then signed in':w.ask_then_signin,'Signed in, then asked':w.signin_then_ask}:{},'browser visitors'));
 const daily=panel('Daily acquisition & activation','Distinct counts per IST date. Daily unique counts must not be summed to get period uniques.',w.available?metricTable(['Date','Visitors','Message senders','Signed-in accounts','Page loads'],w.daily.map(d=>[esc(d.date),fmt(d.visitors),fmt(d.senders),fmt(d.signed_in),fmt(d.page_views)])):'<p class="muted">Daily values will appear when tracking begins.</p>');
 const definitions=panel('How to read this funnel','Traffic and account counts use different identity units.',`<p>Visits group activity with a 30-minute inactivity timeout. Page views count app loads, not every menu click. Visitors use a first-party browser ID that survives sign-in.</p><p>Message senders are distinct guest/account identities. Guest events link to an account only after verified sign-in. Anonymous browsers cannot be reliably merged across devices, and shared devices remain a limitation.</p><p>Signed-in accounts count successful verification during the selected period. Someone who arrives with a valid saved session can send messages without a new sign-in event. Return counts use earlier retained tracking history, not just the selected period.</p><p>Conversions use browser IDs consistently. For example, two accounts sharing one browser count as two signed-in accounts but one converted visitor. Founder/test exclusions apply when an identity is known; unidentified visitors remain unclassified.</p><p>Since-tracking scope applies only to this page and resets when you change the global period/audience or refresh. No historical traffic is backfilled.</p>`);
 return scopeNote+status+cards+funnel+`<div class="two-col">${loss}${paths}</div>`+daily+definitions;
}
