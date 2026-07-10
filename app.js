const places = {
  tallinn:{name:'Tallinn · Tartu mnt / Liivalaia',center:[59.4322,24.7649]},
  tartu:{name:'Tartu · Riia / Ringtee',center:[58.3548,26.6948]},
  parnu:{name:'Pärnu · Tallinna mnt',center:[58.3924,24.5156]},
  kuressaare:{name:'Kuressaare · Tallinna tn',center:[58.2537,22.4894]}
};
let current='tallinn', allData=[], dataStatus=null;
const map=L.map('map',{zoomControl:false}).setView(places[current].center,14);
L.control.zoom({position:'topright'}).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(map);
const layer=L.layerGroup().addTo(map); let radiusCircle;

function withinRadius(p,c,km){const R=6371,dLat=(p.lat-c[0])*Math.PI/180,dLon=(p.lng-c[1])*Math.PI/180;const a=Math.sin(dLat/2)**2+Math.cos(c[0]*Math.PI/180)*Math.cos(p.lat*Math.PI/180)*Math.sin(dLon/2)**2;return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a))<=km}
function filtered(){const yf=document.querySelector('#yearFilter').value,tf=document.querySelector('#typeFilter').value,sf=document.querySelector('#severityFilter').value,rad=+document.querySelector('#radius').value,c=places[current].center;return allData.filter(p=>(yf==='all'||String(p.year)===yf)&&(tf==='all'||p.type===tf)&&(sf==='all'||p.severity===sf)&&withinRadius(p,c,rad))}
function riskScore(data, radius){
  if(!data.length) return 0;
  const fatal=data.reduce((s,x)=>s+(x.fatalities||0),0);
  const vulnerable=data.filter(x=>['jalakäija','jalgrattur'].includes(x.type)).length/data.length;
  const latest=dataStatus?.latest_year||new Date().getFullYear();
  const recent=data.filter(x=>x.year>=latest-1).length/data.length;
  const density=data.length/(Math.PI*radius*radius);
  return Math.min(100,Math.round(Math.min(60,density*8)+Math.min(20,fatal*8)+vulnerable*12+recent*8));
}
function render(){
 const p=places[current],data=filtered();layer.clearLayers();const rad=+document.querySelector('#radius').value;
 if(radiusCircle)map.removeLayer(radiusCircle);radiusCircle=L.circle(p.center,{radius:rad*1000,color:'#0d6b49',weight:1,fillColor:'#0d6b49',fillOpacity:.05}).addTo(map);
 const visible=data.length>1200?data.filter((_,i)=>i%Math.ceil(data.length/1200)===0):data;
 visible.forEach(d=>L.circleMarker([d.lat,d.lng],{radius:d.severity==='hukkunu'?8:5,color:'#fff',weight:1.5,fillColor:d.severity==='hukkunu'?'#e84b3c':'#ff8b52',fillOpacity:.85}).bindPopup(`<b>${d.severity==='hukkunu'?'Hukkunuga':'Vigastatuga'} õnnetus</b><br>${d.year||'Aasta teadmata'} · ${d.type}<br>Kannatanuid: ${d.victims||1}`).addTo(layer));
 const fatal=data.reduce((s,x)=>s+(x.fatalities||0),0),victims=data.reduce((s,x)=>s+(x.victims||1),0),vul=data.length?Math.round(data.filter(x=>['jalakäija','jalgrattur'].includes(x.type)).length/data.length*100):0;const score=riskScore(data,rad);
 document.querySelector('#score').textContent=score;document.querySelector('#scoreBar').style.width=score+'%';document.querySelector('#scoreText').textContent=score>70?'Selles piirkonnas on valitud ajavahemikul kõrge õnnetuste koondumine.':score>45?'Piirkonnas esineb mõõdukas ajalooline liiklusrisk.':'Valitud tingimustel on õnnetuste koondumine pigem madal.';document.querySelector('.score-suffix span').textContent=score>70?'kõrge':score>45?'mõõdukas':'madal';
 document.querySelector('#areaTitle').textContent=p.name;document.querySelector('#accidentCount').textContent=data.length;document.querySelector('#victimCount').textContent=victims;document.querySelector('#fatalCount').textContent=fatal;document.querySelector('#vulnerableShare').textContent=vul+'%';
 const peakHour=getPeakHour(data),peakType=getPeakType(data),recentTrend=getTrend(data);
 document.querySelector('#insights').innerHTML=[[peakHour.title,peakHour.text,'◷'],[peakType.title,peakType.text,'♙'],[recentTrend.title,recentTrend.text,'↗']].map(x=>`<div class="insight"><span class="insight-icon">${x[2]}</span><div><b>${x[0]}</b><p>${x[1]}</p></div></div>`).join('');renderBars(data);
}
function getPeakHour(data){const bins=Array(24).fill(0);data.forEach(x=>{if(Number.isInteger(x.hour))bins[x.hour]++});const max=Math.max(...bins);if(!max)return{title:'Kellaaeg puudub',text:'Selle valiku kirjete kellaajaandmed pole piisavad.'};const h=bins.indexOf(max);return{title:`Kõige rohkem kell ${String(h).padStart(2,'0')}–${String((h+1)%24).padStart(2,'0')}`,text:`Selles tunnis on ${max} valitud tingimustele vastavat juhtumit.`}}
function getPeakType(data){if(!data.length)return{title:'Juhtumeid ei leitud',text:'Muuda raadiust või filtreid.'};const c={};data.forEach(x=>c[x.type]=(c[x.type]||0)+1);const [type,n]=Object.entries(c).sort((a,b)=>b[1]-a[1])[0];return{title:`Sagedasim: ${type}`,text:`${n} juhtumit ehk ${Math.round(n/data.length*100)}% valitud juhtumitest.`}}
function getTrend(data){const latest=dataStatus?.latest_year;if(!latest)return{title:'Trend pole veel saadaval',text:'Andmete sünkroniseerimine pole lõppenud.'};const a=data.filter(x=>x.year===latest).length,b=data.filter(x=>x.year===latest-1).length;if(!b)return{title:`${latest}: ${a} juhtumit`,text:'Eelmise aastaga võrdlemiseks pole piisavalt kirjeid.'};const pct=Math.round((a-b)/b*100);return{title:pct>0?'Juhtumeid rohkem':pct<0?'Juhtumeid vähem':'Juhtumite arv sama',text:`${latest}. aasta näit on ${Math.abs(pct)}% ${pct>0?'kõrgem':pct<0?'madalam':'muutumatu'} kui ${latest-1}. aastal. Jooksev aasta võib olla pooleli.`}}
function renderBars(data){const bins=Array(12).fill(0);data.forEach(d=>{if(Number.isInteger(d.hour))bins[Math.min(11,Math.floor(d.hour/2))]++});const max=Math.max(1,...bins);document.querySelector('#bars').innerHTML=bins.map((v,i)=>`<div class="bar-col"><div class="bar ${v===max&&v?'peak':''}" style="--h:${Math.max(4,v/max*150)}px" title="${v} juhtumit"></div>${String(i*2).padStart(2,'0')}</div>`).join('')}
function populateYears(){const years=[...new Set(allData.map(x=>x.year).filter(Boolean))].sort((a,b)=>b-a);document.querySelector('#yearFilter').innerHTML='<option value="all">Kõik aastad</option>'+years.map(y=>`<option>${y}</option>`).join('')}
async function loadData(){
 try{
  const [d,s]=await Promise.all([fetch('data/accidents.json',{cache:'no-store'}),fetch('data/status.json',{cache:'no-store'})]);
  if(!d.ok||!s.ok)throw new Error('Andmefaili ei leitud');allData=await d.json();dataStatus=await s.json();
  if(!allData.length)throw new Error('Esimene automaatne andmeuuendus pole veel käivitunud');
  populateYears();const date=new Date(dataStatus.generated_at).toLocaleString('et-EE',{dateStyle:'medium',timeStyle:'short'});document.querySelector('#dataStatus').textContent=`${allData.length.toLocaleString('et-EE')} päris kirjet`;document.querySelector('#freshness').textContent=`Ametlikud andmed sünkroniseeritud ${date}. Uusim andmetes olev aasta: ${dataStatus.latest_year}.`;render();
 }catch(e){document.querySelector('#dataStatus').textContent='Andmeuuendus ootel';document.querySelector('#freshness').textContent='GitHub Actions peab tegema esimese andmete sünkroniseerimise. Ava repositooriumis Actions → Uuenda liiklusõnnetuste andmeid → Run workflow.';document.querySelector('#scoreText').textContent=e.message;render();}
}
document.querySelector('#analyseBtn').onclick=()=>{current=document.querySelector('#placeSelect').value;map.setView(places[current].center,14);render()};['yearFilter','typeFilter','severityFilter','radius'].forEach(id=>document.querySelector('#'+id).oninput=()=>{document.querySelector('#radiusValue').textContent=String(document.querySelector('#radius').value).replace('.',',')+' km';render()});document.querySelector('#resetBtn').onclick=()=>{document.querySelector('#yearFilter').value='all';document.querySelector('#typeFilter').value='all';document.querySelector('#severityFilter').value='all';document.querySelector('#radius').value=1.5;document.querySelector('#radiusValue').textContent='1,5 km';render()};const dlg=document.querySelector('#methodDialog');document.querySelector('#methodBtn').onclick=()=>dlg.showModal();dlg.querySelector('.close').onclick=()=>dlg.close();loadData();
