/* Structured views. Values come only from the authenticated aggregate endpoint. */
const dashboardTitles = {
 funnel:['From first visit to repeat use.','Website traffic, message senders, verified sign-ins and returning visitors.','Website funnel'],
 overview:['The whole picture.','Adoption, service performance and feedback — with evidence behind every number.','Overview'],
 adoption:['Are people coming back?','Incoming-message activity across the selected audience and period.','Adoption'],
 efficiency:['How well does it run?','Backend speed, tracked failures and retry pressure.','Efficiency & errors'],
 diversity:['Who are we reaching?','Explore identifiers and recorded request context, without inferring demographics.','User diversity'],
 feedback:['Are we actually helping?','Farmer feedback and human quality reviews, shown separately.','Feedback & quality'],
 health:['Can we trust the data?','Measurement coverage, source availability and messaging delivery.','Data & delivery']
};
const pretty = s => String(s).replaceAll('_',' ');
const seconds = n => n == null ? 'Not measured' : `${n}s`;
const route = (label, v) => `<button class="plain" data-go="${v}">${esc(label)} →</button>`;
function panel(title, note, body, extra='') {
 return `<section class="card metric-panel"><div class="section-head"><div><h2>${esc(title)}</h2><p>${esc(note)}</p></div>${extra}</div>${body}</section>`;
}
function metricTable(headers, rows) {
 return rows.length ? `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : empty('No observations in this selection','Try a longer period or a different audience. Missing measurements are not zero.');
}
function barsFromCounts(counts, unit='observations', ordered=false) {
 const entries=Object.entries(counts);if(!ordered)entries.sort((a,b)=>b[1]-a[1]);const max=Math.max(1,...entries.map(x=>x[1]));
 return entries.length ? `<div class="ranked-bars">${entries.map(([label,n])=>`<div class="rank-row"><div><span>${esc(pretty(label))}</span><strong>${fmt(n)} <small>${esc(unit)}</small></strong></div><div class="track"><div style="width:${100*n/max}%"></div></div></div>`).join('')}</div>` : empty('No observations','There are no recorded values for this selection.');
}
function insightPanel() {
 const items=data.detailed.insights;
 return panel('What needs your attention','Rules based on this selection, not AI-generated conclusions.',items.length ? `<div class="insight-grid">${items.map(i=>`<article class="insight ${esc(i.tone)}"><span class="eyebrow">${i.tone==='danger'?'INVESTIGATE':'CHECK THE EVIDENCE'}</span><h3>${esc(i.title)}</h3><p>${esc(i.text)}</p>${route('Explore',i.view)}</article>`).join('')}</div>` : '<p class="muted">No rules triggered. This is not a guarantee of answer quality or system health.</p>');
}
function activityPanel() {
 const rows=data.detailed.adoption.activity;
 return panel('Activity over time','Daily incoming messages and active identifiers � IST. First and current days may be partial.',trendChart(rows,[{key:'messages',label:'Incoming messages'},{key:'participants',label:'Active identifiers'}],'Daily activity')+`<details class="data-details"><summary>View daily values (${rows.length} dates)</summary>${metricTable(['IST date','Active identifiers','Incoming messages','Tracked requests','Recorded failures'],rows.map(r=>[esc(r.date),fmt(r.participants),fmt(r.messages),fmt(r.requests),fmt(r.failed)]))}</details>`);
}
function dimensionPanel(field, title, note) {
 const rows=data.detailed.dimensions[field];
 return panel(title,note,barsFromCounts(Object.fromEntries(rows.slice(0,8).map(r=>[r.label,r.requests])),'requests')+`<details class="data-details"><summary>Explore exact counts and performance</summary>`+metricTable(['Recorded value','Requests','Identifiers','Failure rate','p95'],rows.map(r=>[esc(pretty(r.label)),fmt(r.requests),fmt(r.participants),`${pct(r.failure_rate)}<small class="cell-note">${sample(r.failure_rate)}</small>`,seconds(r.p95_seconds)]))+`</details>`);
}
function unavailablePanel() {
 return panel('Measurement roadmap','These metrics need additional tracking. They are not estimated from message volume.',`<div class="availability-grid">${[
 ['Cohort retention','D1 / D7 / D30 with stable identities and complete observation periods.'],
 ['Onboarding conversion','Visits → first question → sign-in → completed farm profile.'],
 ['Voice & photo experience','Recording failures, transcription, first audio, playback and photo-processing errors.'],
 ['Costs & actual model usage','Tokens, model fallback used, audio/image charges, SMS and cloud billing.'],
 ['Confirmed delivery','Handset receipts, separate from gateway acceptance.'],
 ['Demographic diversity','Age, gender and other demographics are not recorded; never inferred from text.']
 ].map(([h,t])=>`<div><span class="tag">Not measured</span><h3>${h}</h3><p>${t}</p></div>`).join('')}</div>`);
}
function dashboardPage(which) {
 if(which==='funnel')return websitePage();
 const d=data.detailed,m=data.metrics,a=d.adoption,e=d.efficiency,f=d.feedback;
 const kpis=items=>`<section class="kpis">${items.join('')}</section>`;
 const context=`<div class="scope-note"><span class="private-dot"></span><strong>${esc($('#audience').selectedOptions[0].text)}</strong><span>Rolling ${d.window_days}-day window · identifiers are not verified people</span></div>`;
 if(which==='overview')return context+kpis([
  card('Active participant identifiers',fmt(a.active_in_window),'Sent at least one incoming message',true),
  card('Repeat activity',pct(a.repeat_on_multiple_days),sample(a.repeat_on_multiple_days)+' active on multiple dates'),
  card('Recorded backend failure rate',pct(e.failure_rate),sample(e.failure_rate)+' completed requests'),
  card('Backend p95 response time',seconds(e.p95_seconds),`${e.latency_samples} timed successful requests`),
  card('Positive feedback',f.available?pct(f.positive):'Unavailable',f.available?sample(f.positive)+' rating events':'Ratings could not be read'),
  card('Complete review coverage',pct(m.review_coverage),sample(m.review_coverage)+' conversations')
 ])+insightPanel()+activityPanel()+`<div class="two-col">${panel('Demand by need','Conversation labels; more than one label can apply.',barsFromCounts(Object.fromEntries(Object.entries(d.topics).map(([k,n])=>[data.pain_point_labels[k]||k,n])),'conversations'),route('View diversity','diversity'))}${panel('Channel mix','Tracked advisory requests, including test traffic when selected.',distributionChart(Object.fromEntries(d.dimensions.channel.map(r=>[r.label,r.requests])),'requests'),route('View efficiency','efficiency'))}</div>`;
 if(which==='adoption')return context+kpis([
  card('Active in last 24 hours',fmt(a.active['1']),'Incoming-message identifiers',true),
  card('Active in last 7 days',d.window_days>=7?fmt(a.active['7']):'Not measured',d.window_days>=7?'Distinct identifiers, not a sum of daily counts':'Select at least 7 days'),
  card('Active in last 30 days',d.window_days>=30?fmt(a.active['30']):'Not measured',d.window_days>=30?'Distinct identifiers, not verified farmers':'Select at least 30 days'),
  card('Conversations',fmt(m.conversations),'Backend sessions; may combine separate web chats'),
  card('Incoming per active identifier',fmt(a.incoming_per_active),`${m.inbound_messages} incoming messages in this window`),
  card('Repeat on multiple dates',pct(a.repeat_on_multiple_days),sample(a.repeat_on_multiple_days)+' · not cohort retention')
 ])+activityPanel()+panel('What kind of interaction?','Tracked request classifications; a greeting does not establish product activation.',barsFromCounts(e.message_types,'requests'))+unavailablePanel();
 if(which==='efficiency')return context+kpis([
  card('Recorded failure rate',pct(e.failure_rate),sample(e.failure_rate)+' completed requests',true),
  card('Answered requests',fmt(e.answered),`${m.telemetry_requests} tracked requests total`),
  card('Pending / unresolved',fmt(m.pending_requests),`${m.abandoned_requests} started over 15 minutes ago`),
  card('p50 / p95 / p99',`${seconds(e.p50_seconds)} / ${seconds(e.p95_seconds)} / ${seconds(e.p99_seconds)}`,`${e.latency_samples} successful timing samples`),
  card('Requests retried',fmt(e.retried_requests),'Same request ID observed more than once'),
  card('Extra attempts',fmt(e.extra_attempts),'Additional attempts beyond the initial request')
 ])+`<div class="notice"><p>Failures before advisory tracking, media preprocessing failures and browser playback failures are not included. No recorded failures does not establish 100% end-to-end reliability.</p></div>`+panel('Request outcomes','Tracked backend outcomes; pending requests have no completed result yet.',distributionChart({'Answered':e.answered,'Failed':e.failure_rate?.numerator||0,'Pending':m.pending_requests},'requests'))+dimensionPanel('channel','Performance by channel','Each channel uses the same completed-request failure denominator.')+panel('Recorded error categories','Only requests marked failed; this does not include poor-quality answers.',Object.keys(e.errors).length?barsFromCounts(e.errors,'failures'):'<p class="muted">No failed backend requests recorded in this selection. Check tracking coverage before interpreting this as reliability.</p>')+dimensionPanel('release','Performance by backend release','Recorded release identifiers; these comparisons are observational, not controlled experiments.');
 if(which==='diversity')return context+`<div class="notice"><p>These are request-context breakdowns, not demographics. The same identifier can appear in several categories. State is not verified residence; reply-language code is not native language.</p></div>`+kpis([
 card('Observed channels',fmt(d.dimensions.channel.filter(r=>r.label!=='unknown').length),'Across tracked requests',true),
 card('Recorded states',fmt(d.dimensions.state.filter(r=>r.label!=='unknown').length),'Request context; missing values shown below'),
 card('Recorded crops',fmt(d.dimensions.crop.filter(r=>r.label!=='unknown').length),'Raw stored labels; synonyms may be separate')
 ])+dimensionPanel('channel','Channel diversity','Identifier counts overlap between channels.')+dimensionPanel('language','Reply speech-language codes','Latin-script Hinglish may use en-IN; this is not a reliable measure of language preference.')+`<div class="two-col">${dimensionPanel('state','State context','As recorded on requests; not verified home location.')}${dimensionPanel('crop','Crops discussed','Raw recorded crop values.')}</div>`+panel('Audience classification','Conversation counts across all audiences, regardless of the audience filter.',distributionChart(m.audience_counts,'conversations'));
 if(which==='feedback')return context+(!f.available?'<div class="error">Ratings are currently unavailable. Quality reviews remain separate and available.</div>':'')+kpis([
  card('Rating events',fmt(f.total),'All attached scores, including neutral',true),
  card('Positive rating rate',pct(f.positive),sample(f.positive)+' scores of 4–5'),
  card('Conversations rated',pct(f.coverage),sample(f.coverage)+' conversations'),
  card('Reviewed useful & safe',pct(m.useful_answers),sample(m.useful_answers)+' complete reviews'),
  card('Critical reviewed findings',pct(m.critical_errors),sample(m.critical_errors)+' complete reviews'),
  card('Awaiting complete review',fmt(m.review_queue),`Oldest: ${date(f.oldest_unreviewed,true)}`)
 ])+`<div class="two-col">${panel('Rating distribution','1–2 negative · 3 neutral · 4–5 positive. Events may repeat per person.',f.available?distributionChart(Object.fromEntries(Object.entries(f.scores).map(([k,n])=>[`${k} / 5`,n])),'ratings'):'<p>Unavailable</p>')}${panel('Reviewer outcomes','Only conversations with outcome and safety assessments.',barsFromCounts(f.review_outcomes,'conversations'))}</div>`+`<div class="two-col">${panel('Safety severity','Human assessment, not an automated correctness score.',barsFromCounts(f.severity,'conversations'))}${panel('Farmer-confirmed outcome','Explicit confirmation recorded by a reviewer; not inferred from a thank-you.',barsFromCounts(m.farmer_confirmed,'conversations'))}</div>`+panel('Negative-feedback conversations','Start here to find actionable improvements.',f.available?listTable(data.conversations.filter(g=>g.rated_down)):'<p>Unavailable until ratings can be read.</p>',route('Open review queue','reviews'));
 if(which==='health')return context+kpis([
  card('Incoming-message tracking linkage',pct(d.health.linked_incoming),sample(d.health.linked_incoming)+' incoming messages',true),
  card('Gateway tracking coverage',pct(m.gateway_tracking_coverage),sample(m.gateway_tracking_coverage)+' messaging replies'),
  card('Gateway acceptance',pct(m.gateway_acceptance),sample(m.gateway_acceptance)+' observed sends')
 ])+panel('Recorded field coverage','A missing crop or state may be appropriate for greetings; these are coverage figures, not quality scores.',metricTable(['Field','Present','Coverage'],Object.entries(d.health.coverage).map(([k,r])=>[esc(pretty(k)),sample(r),pct(r)])))+`<div class="two-col">${panel('Tool usage','Requests mentioning each tool; tools can overlap.',barsFromCounts(d.health.tools,'requests'))}${panel('Evidence availability','Stored evidence summaries only; availability is not proof of correctness.',metricTable(['Source','Available / observed','Availability'],Object.entries(d.health.evidence).map(([k,v])=>[esc(k),`${v.available} / ${v.observed}`,pct({percent:v.observed?Math.round(v.available/v.observed*1000)/10:null})])))}</div>`+dimensionPanel('dose_status','Registered-dose outcomes','Refusal or no match is a safety outcome, not automatically a service error.')+cachePanel()+unavailablePanel();
 return '';
}
function dashboardGuide() {
 return `<div class="guide-grid">${data.detailed.definitions.map(([h,t])=>panel(h,'',`<p>${esc(t)}</p>`)).join('')}</div>`+panel('Known measurement boundaries','Read these before drawing conclusions.',data.limitations.map(t=>`<p>${esc(t)}</p>`).join(''));
}
