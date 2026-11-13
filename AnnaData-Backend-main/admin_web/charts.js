/* Dependency-free visual summaries; every chart retains exact accessible values. */
const chartColors=['#347966','#6b82b8','#c69642','#be7867','#8b79a4','#879b78'];
function trendChart(rows, series, label) {
 if(!rows.length)return empty('No timeline yet','Recorded activity will appear here.');
 const W=760,H=230,L=42,R=18,T=22,B=34,max=Math.max(1,...rows.flatMap(r=>series.map(s=>Number(r[s.key])||0)));
 const top=Math.max(1,Math.ceil(max/4)*4),x=i=>L+(W-L-R)*(rows.length===1?.5:i/(rows.length-1)),y=n=>H-B-(H-T-B)*n/top;
 let svg=[0,1,2,3,4].map(i=>{const n=top*i/4;return `<line x1="${L}" x2="${W-R}" y1="${y(n)}" y2="${y(n)}" stroke="#e5ebe6" stroke-dasharray="3 5"/><text x="${L-10}" y="${y(n)+4}" text-anchor="end">${fmt(n)}</text>`;}).join('');
 svg+=series.map((s,j)=>{const color=chartColors[j],points=rows.map((r,i)=>`${x(i)},${y(Number(r[s.key])||0)}`).join(' ');return `${j===0?`<polygon points="${x(0)},${H-B} ${points} ${x(rows.length-1)},${H-B}" fill="${color}" opacity=".07"/>`:''}<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/>${rows.map((r,i)=>`<circle tabindex="0" cx="${x(i)}" cy="${y(Number(r[s.key])||0)}" r="${rows.length>60?2:3.5}" fill="${color}" stroke="white" stroke-width="1.5" aria-label="${esc(r.date)}: ${esc(s.label)} ${fmt(r[s.key])}"><title>${esc(r.date)} · ${esc(s.label)}: ${fmt(r[s.key])}</title></circle>`).join('')}`;}).join('');
 svg+=`<text x="${L}" y="${H-7}">${esc(rows[0].date)}</text><text x="${W-R}" y="${H-7}" text-anchor="end">${esc(rows.at(-1).date)}</text>`;
 return `<div class="chart-legend">${series.map((s,i)=>`<span><i style="background:${chartColors[i]}"></i>${esc(s.label)}</span>`).join('')}</div><svg class="trend-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}. Exact values in the daily table below.">${svg}</svg>`;
}
function distributionChart(counts,unit='requests') {
 const entries=Object.entries(counts).filter(([,n])=>Number(n)>0).sort((a,b)=>b[1]-a[1]);
 const total=entries.reduce((s,[,n])=>s+Number(n),0);
 if(!total)return empty('No recorded distribution','A chart will appear when observations are available.');
 const items=entries.length>6?[...entries.slice(0,5),['Other',entries.slice(5).reduce((s,[,n])=>s+Number(n),0)]]:entries;
 let start=0;const stops=items.map(([,n],i)=>{const end=start+100*n/total,s=`${chartColors[i]} ${start}% ${end}%`;start=end;return s;});
 return `<div class="distribution"><div class="donut" style="background:conic-gradient(${stops.join(',')})" role="img" aria-label="${fmt(total)} ${esc(unit)}; breakdown alongside"><div><strong>${fmt(total)}</strong><span>${esc(unit)}</span></div></div><div class="distribution-legend">${items.map(([label,n],i)=>`<div><i style="background:${chartColors[i]}"></i><span>${esc(pretty(label))}</span><strong>${fmt(n)}</strong><small>${(100*n/total).toFixed(1)}%</small></div>`).join('')}</div></div>`;
}
function activationFunnel(w) {
 if(!w.available)return empty('Waiting for traffic measurements','Visitor conversion will appear once tracking is available.');
 const total=w.unique_visitors,both=w.ask_then_signin+w.signin_then_ask;
 const steps=[['Visited the website',total,'Observed browser visitors'],['Sent a message',w.sender_browsers,'Submitted at least one question'],['Also signed in',both,'Message + verified sign-in, in either order']];
 return `<div class="activation-funnel">${steps.map(([label,n,note],i)=>`<div class="funnel-step"><div class="funnel-caption"><span><b>0${i+1}</b>${label}</span><strong>${fmt(n)} <small>${total?(100*n/total).toFixed(1)+'%':'—'}</small></strong></div><div class="funnel-rail"><div style="width:${total?100*n/total:0}%;background:${chartColors[i]}"></div></div><p>${note}${i&&steps[i-1][1]?` · ${fmt(steps[i-1][1]-n)} fewer than the preceding group`:''}</p></div>`).join('')}</div>`;
}
function outcomeCards(w) {
 return `<div class="outcome-grid">${[['Message conversion','visitor_to_message','Visitors who submitted a question'],['Sign-in conversion','visitor_to_signin','Visitors with a verified sign-in'],['Return rate','visitor_return_rate','Visitors seen on an earlier IST date']].map(([label,key,note],i)=>{const p=w.available?w[key]?.percent:null;return `<article class="outcome"><div class="mini-ring" style="--progress:${p??0}%;--ring:${chartColors[i]}"><strong>${p==null?'—':p+'%'}</strong></div><div><h3>${label}</h3><p>${note}</p><small>${w.available?sample(w[key]):'Not measured'}</small></div></article>`;}).join('')}</div>`;
}
