"""Offline October dashboard; all values come from the read-only evidence report."""
import json


def render_tracker(report):
    data = json.dumps(report, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    return TEMPLATE.replace("__REPORT__", data)


TEMPLATE = r'''<!doctype html>
<html lang="nb"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HBI · Oktober 2026</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#10151e;color:#e6edf5}
body{max-width:1240px;margin:auto;padding:32px}h1{font-size:34px;margin:8px 0}
h2{font-size:21px}h3{font-size:17px}p{line-height:1.6}.muted,small{color:#aebbd0}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card,section{background:#1a2230;
border:1px solid #303d50;border-radius:12px;padding:20px}section{margin-top:20px}
.value{font-size:32px;font-weight:700}.tag{display:inline-block;border-radius:20px;background:#30455e;
padding:5px 10px;font-size:12px}.warning{color:#ffd38b}.good{color:#93e2c1}
progress{width:100%;accent-color:#93e2c1}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #303d50}th{color:#aebbd0}
.scroll{overflow:auto;max-height:420px}select{background:#10151e;color:#e6edf5;padding:10px;border:1px solid #52647b;
border-radius:6px}label{display:flex;gap:12px;align-items:center;margin-top:18px}
.split{display:grid;grid-template-columns:1fr 1fr;gap:20px}.milestones p{font-size:14px}
ul{padding-left:20px;line-height:1.7}.bars{display:flex;align-items:end;height:100px;gap:5px}
.bar{flex:1;background:#93e2c1;min-height:1px}.days{font-size:12px;color:#aebbd0}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.split{grid-template-columns:1fr}}
@media(max-width:540px){body{padding:16px}.grid{grid-template-columns:1fr}h1{font-size:28px}}
</style>
<header><small>HORSE BETTING INTELLIGENCE · MÅLEPERIODE</small><h1>Oktober 2026</h1>
<p class="muted">Datakvalitet → sannsynligheter → økonomisk resultat. Milepæler krever evidens.</p>
<p id="snapshot"></p><p id="guard"></p></header>
<div class="grid" id="counts"></div>
<section><h2>Hvor er vi i prosessen?</h2><div class="grid milestones" id="milestones"></div></section>
<section><h2>Utvalget vokser</h2><div class="grid" id="targets"></div>
<p id="interpretation" class="muted"></p><div class="bars" id="bars" aria-label="Sammenlignbare løp per dag"></div>
<p class="days">1. oktober ← løp med resultat per dag → 31. oktober</p></section>
<label>Vis land <select id="country"><option value="ALL">Alle land</option><option value="SE">Sverige</option>
<option value="DK">Danmark</option><option value="NO">Norge</option><option value="FR">Frankrike</option></select></label>
<section><h2>Daglig drift</h2><p class="muted">Tomt eller fremtidig døgn er ikke godkjent. T−4-bånd: ±60 sekunder.</p>
<div class="scroll"><table><thead><tr><th>Dato / land</th><th>Observasjon</th><th>Oppdaget</th>
<th>Fullt felt*</th><th>Beslutninger</th><th>T−4 innen bånd</th><th>Mangler beslutning</th>
<th>Oppgjort / spill</th><th>Forfalt</th></tr></thead><tbody id="operations"></tbody></table></div>
<p class="muted">*Providerbevis; kvalifisert modellkohort krever også fryste sannsynligheter og sporbarhet.</p>
<details><summary>Avvisningsgrunner og oppgjør som venter</summary><ul id="rejections"></ul></details></section>
<div class="split"><section><h2>Historikk og markedsforløp</h2><p id="history"></p>
<p id="paths"></p><p class="muted">Oddsforløp lagres separat og teller aldri som fundamental hestehistorikk.</p></section>
<section><h2>Fundamentals utover markedet?</h2><p id="paired"></p><table><thead><tr><th>Lag</th>
<th>Log loss ↓</th><th>Brier ↓</th></tr></thead><tbody id="scores"></tbody></table>
<p id="difference"></p><details><summary>Kalibrering per sannsynlighetsbånd</summary>
<div class="scroll"><table><thead><tr><th>Lag / bånd</th><th>Hester</th><th>Forventet</th>
<th>Observert</th></tr></thead><tbody id="calibration"></tbody></table></div></details></section></div>
<div class="split"><section><h2>Realistiske paper-priser</h2><p id="economics"></p>
<p class="muted">Krever fryst, fersk pris over minimumspris før start. Manglende CLV er ukjent.</p>
<ul id="price-exclusions"></ul></section><section><h2>Separat Challenger</h2><div id="challengers"></div>
<p class="muted">Ingen automatisk registrering, modellbytte eller ekte penger. En fremovertest teller kun løp etter registrering og historikkens skjæringsdato.</p></section></div>
<section><h2>Integritetskontroller</h2><ul id="integrity"></ul><p class="muted">Dette er et lagret øyeblikksbilde. Ny rapport hentes fra siste daglige GitHub-kjøring.</p></section>
<script id="report-data" type="application/json">__REPORT__</script>
<script>
'use strict';
const R=JSON.parse(document.getElementById('report-data').textContent);
const $=id=>document.getElementById(id), fmt=(v,d=3)=>v==null?'Ukjent':Number(v).toLocaleString('nb-NO',{maximumFractionDigits:d}),
 pct=v=>v==null?'Ukjent':fmt(100*v,1)+' %';
const labels={IN_PROGRESS:'Pågår',REVIEW_REQUIRED:'Krever sluttkontroll',NOT_STARTED:'Ikke startet',
READY_FOR_REVIEW:'Klar for vurdering',COLLECTING:'Samler data',NO_EVIDENCE:'Ingen evidens',
FORWARD_TESTING:'Fremovertest registrert',READY_FOR_HUMAN_REVIEW:'Krever forskningsvurdering',BLOCKED:'Blokkert',
FUTURE:'Fremtidig',PARTIAL_DAY:'Døgnet pågår',OBSERVED:'Observasjoner finnes'};
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;
if(cls)e.className=cls;return e};
function row(target,values){const tr=node('tr');values.forEach(v=>tr.append(node('td',v)));$(target).append(tr)}
$('snapshot').textContent='Oppdatert '+new Date(R.generated_at).toLocaleString('nb-NO',{timeZone:'Europe/Oslo'})+' · Oslo';
$('guard').textContent=R.guardrails_ok?'Champion v1.1 er låst · Kun paper / forskning':'STOPP: Champion eller sikkerhetsregler avviker';
$('guard').className=R.guardrails_ok?'good':'warning';
[[R.qualified_races_n,'Kvalifiserte løp'],[R.paired_races_n,'Sammenlignbare løp med resultat'],
[R.economics.settled_verified_price_n,'Oppgjorte spill med prisbevis'],[R.challengers.length,'Registrerte Challengers']].forEach(([v,t])=>{
const e=node('div',null,'card');e.append(node('div',fmt(v),'value'),node('p',t));$('counts').append(e)});
R.milestones.forEach(m=>{const e=node('div',null,'card');e.append(node('small',m.period),node('h3',m.title),
node('span',labels[m.status]||m.status,'tag'),node('p',m.next));const ul=node('ul');
m.blockers.forEach(b=>ul.append(node('li',b,'warning')));e.append(ul);$('milestones').append(e)});
R.sample_targets.forEach(t=>{const e=node('div');e.append(node('h3',t.n+' løp'));const p=node('progress');
p.max=t.n;p.value=t.current;e.append(p,node('p',t.current+' / '+t.n+' · '+t.remaining+' gjenstår'));$('targets').append(e)});
$('interpretation').textContent=R.interpretation;
const max=Math.max(1,...R.daily_samples.map(d=>d.paired));R.daily_samples.forEach(d=>{const e=node('div',null,'bar');
e.style.height=(100*d.paired/max)+'%';e.title=d.day+': '+d.paired+' med resultat / '+d.qualified+' kvalifiserte';$('bars').append(e)});
$('history').textContent=(R.history.starts==null?'Ingen verifisert historikk per tidligere start. ':
fmt(R.history.starts)+' tidligere starter · '+fmt(R.history.horses)+' hester. ')+R.history.reason;
$('paths').textContent=fmt(R.market_paths.runner_paths_with_2_plus_times)+' hest/løp med minst to prisobservasjoner · '+
fmt(R.market_paths.pre_race_snapshots)+' prisobservasjoner før start.';
for(const [type,a] of Object.entries(R.integrity))$('integrity').append(node('li',type+': '+a.status+' · '+a.at));
if(!Object.keys(R.integrity).length)$('integrity').append(node('li','Ingen integritetskontroll er lagret.','warning'));
if(!R.challengers.length)$('challengers').append(node('p','Ingen Challenger registrert.'));
R.challengers.forEach(c=>$('challengers').append(node('p',c.id+' · '+c.status+' · '+c.forward_n+' / '+c.minimum_n+' fremoverløp')));
function refresh(){const country=$('country').value,all=country==='ALL';
['operations','rejections','scores','calibration','price-exclusions'].forEach(id=>$(id).replaceChildren());
const daily=R.operations.daily.filter(d=>all||d.country===country);
daily.forEach(d=>row('operations',[d.day+' / '+d.country,labels[d.observation_status]||d.observation_status,d.discovered,
d.coverage.FULL_FIELD_EVIDENCE_PASS||0,d.decisions,d.t4_within_60_seconds,d.missing_decision_after_start,
d.settled_tickets+' / '+d.tickets,d.overdue_tickets]));
const reasons={};daily.forEach(d=>Object.entries(d.rejections).forEach(([k,v])=>reasons[k]=(reasons[k]||0)+v));
Object.entries(reasons).forEach(([k,v])=>$('rejections').append(node('li',k+': '+v)));
Object.entries(R.excluded_decisions).forEach(([k,v])=>$('rejections').append(node('li','Modellkohort (alle land) · '+k+': '+v)));
R.operations.open_settlement_backlog_all_dates.filter(t=>all||t.country===country).forEach(t=>
$('rejections').append(node('li','Venter på oppgjør · '+t.race_id+' · '+fmt(t.age_hours,1)+' timer')));
const s=all?R.paired_evaluation:R.evaluation_by_country[country];$('paired').textContent=s.n+' løp · identisk kohort for alle tre lag.';
const names={fundamental:'Fundamentals',market:'Marked',combined:'Kombinasjon'};
Object.entries(s.layers).forEach(([k,v])=>{row('scores',[names[k],fmt(v.log_loss),fmt(v.brier)]);
v.calibration.forEach(b=>row('calibration',[names[k]+' '+pct(b.bin_low)+'–'+pct(b.bin_high),b.n,pct(b.mean_predicted),pct(b.observed_rate)]))});
$('difference').textContent='Feil mot markedet: fundamentals '+fmt(s.fundamental_minus_market_log_loss)+
' · kombinasjon '+fmt(s.combined_minus_market_log_loss)+'. Lavere er bedre; lite utvalg beviser ikke edge.';
const e=all?R.economics:R.economics_by_country[country];$('economics').textContent=e.settled_verified_price_n+
' verifiserte oppgjør · paper-P/L '+fmt(e.paper_pnl_nok,2)+' NOK · ROI '+pct(e.roi)+' · CLV '+fmt(e.mean_clv)+
' ('+e.clv_n+' målinger; '+e.missing_clv_n+' mangler).';
Object.entries(e.excluded).forEach(([k,v])=>$('price-exclusions').append(node('li',k+': '+v)));
} $('country').addEventListener('change',refresh);refresh();
</script></html>'''
