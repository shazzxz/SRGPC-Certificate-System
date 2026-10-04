function escSvg(v){return String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;');}
const PREVIEW_THEMES={
  classic:{bg:'#fbf8ef',ink:'#202124',muted:'#7c7366',accent:'#b38724',soft:'#efe2be'},
  modern:{bg:'#f7faff',ink:'#0f172a',muted:'#64748b',accent:'#2563eb',soft:'#dbeafe'},
  emerald:{bg:'#f7fcfa',ink:'#123c37',muted:'#67817c',accent:'#0f766e',soft:'#d9f2eb'},
  midnight:{bg:'#0b1426',ink:'#f8fafc',muted:'#9fb1ca',accent:'#7dd3fc',soft:'#18345c'},
  royal:{bg:'#fbf9ff',ink:'#2f204b',muted:'#7e7192',accent:'#6d28d9',soft:'#eee6ff'},
  burgundy:{bg:'#fffaf5',ink:'#3f1719',muted:'#8b6d6e',accent:'#8f2027',soft:'#f2e0d8'},
  skyline:{bg:'#f6fbff',ink:'#10233c',muted:'#6e8197',accent:'#0ea5e9',soft:'#dff4ff'},
  minimal:{bg:'#ffffff',ink:'#111827',muted:'#6b7280',accent:'#334155',soft:'#f1f5f9'},
  academic_blueprint:{bg:'#f7fbff',ink:'#16324f',muted:'#60758c',accent:'#1f5f9a',soft:'#e1effb'},
  heritage_seal:{bg:'#fbf8f0',ink:'#273a30',muted:'#758078',accent:'#2f6b4f',soft:'#e4eee7'},
  teal_arch:{bg:'#f7fcfb',ink:'#123b3a',muted:'#6a8382',accent:'#0f766e',soft:'#dcefeb'},
  copper_ledger:{bg:'#fbf4ea',ink:'#422b20',muted:'#826a5c',accent:'#a85b2a',soft:'#f1dfd0'},
  ivory_ribbon:{bg:'#fffdf6',ink:'#24354a',muted:'#738092',accent:'#8b6a1f',soft:'#f5e9c5'},
  crimson_sash:{bg:'#fffafa',ink:'#3e171c',muted:'#866d72',accent:'#b4232f',soft:'#f3d9dd'},
  cobalt_wave:{bg:'#f5f9ff',ink:'#10284a',muted:'#657a96',accent:'#2458c7',soft:'#dbe6fb'},
  sage_garden:{bg:'#f8fbf6',ink:'#263b2b',muted:'#6e806f',accent:'#5f7f51',soft:'#e4eddf'},
  charcoal_gold:{bg:'#171a1f',ink:'#f8fafc',muted:'#b5b8bf',accent:'#d2ad5f',soft:'#3a3325'},
  coastal:{bg:'#f4fbfd',ink:'#173a4f',muted:'#68808c',accent:'#0b82a5',soft:'#d9f0f6'},
  geometric:{bg:'#fbfcff',ink:'#20273a',muted:'#707a8e',accent:'#4056a1',soft:'#e8ebf8'},
  monochrome:{bg:'#ffffff',ink:'#1f2933',muted:'#737b86',accent:'#20252b',soft:'#edf0f2'},
  nss_seven_day:{bg:'#ffffff',ink:'#17345f',muted:'#5f6f85',accent:'#173f93',soft:'#f5e9d1'}
};
const PREVIEW_FONTS={Helvetica:'Arial, Helvetica, sans-serif',Times:'Times New Roman, Times, serif',Courier:'Courier New, Courier, monospace'};
function svgEl(tag,attrs={}){const s=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))s.setAttribute(k,String(v));return s;}
function addText(svg,text,x,y,opts={}){
  const baseSize=Number(opts.size||14);
  const e=svgEl('text',{x,y,'text-anchor':opts.anchor||'middle','dominant-baseline':opts.baseline||'middle','font-family':opts.font||'Arial, Helvetica, sans-serif','font-size':baseSize,'font-weight':opts.weight||400,fill:opts.fill||'#111'});
  if(opts.letterSpacing)e.setAttribute('letter-spacing',opts.letterSpacing);
  if(opts.opacity!=null)e.setAttribute('opacity',opts.opacity);
  e.textContent=String(text??'');
  svg.appendChild(e);
  // IMPORTANT: opts.length is a MAX WIDTH, not a textLength/stretch target.
  // The previous implementation stretched every glyph to fill the box, which
  // made names/headings look unnaturally wide in the live preview.
  if(opts.length){
    const maxWidth=Number(opts.length);
    let measured=0;
    try{measured=e.getComputedTextLength();}catch(_){measured=0;}
    if(measured>0 && maxWidth>0 && measured>maxWidth){
      const minSize=Number(opts.minSize||Math.max(6,baseSize*0.58));
      const fitted=Math.max(minSize,baseSize*(maxWidth/measured));
      e.setAttribute('font-size',fitted.toFixed(2));
    }
  }
  return e;
}
function addRect(svg,x,y,w,h,attrs={}){const e=svgEl('rect',{x,y,width:w,height:h,...attrs});svg.appendChild(e);return e;}
function addLine(svg,x1,y1,x2,y2,attrs={}){const e=svgEl('line',{x1,y1,x2,y2,...attrs});svg.appendChild(e);return e;}
function addCircle(svg,cx,cy,r,attrs={}){const e=svgEl('circle',{cx,cy,r,...attrs});svg.appendChild(e);return e;}
function addPath(svg,d,attrs={}){const e=svgEl('path',{d,...attrs});svg.appendChild(e);return e;}
function addImage(svg,href,x,y,w,h,attrs={}){if(!href)return null;const e=svgEl('image',{href,x,y,width:w,height:h,preserveAspectRatio:'xMidYMid meet',...attrs});svg.appendChild(e);return e;}
function fitLen(text,max){const n=[...String(text||'')].length;return Math.max(24,Math.min(max, max*(Math.max(0.58, 1-(n-24)*0.018))));}
function splitPreview(text,maxChars=58){const words=String(text||'').trim().split(/\s+/).filter(Boolean);let a='',b='';for(const w of words){if((a+' '+w).trim().length<=maxChars||!a)a=(a+' '+w).trim();else b=(b+' '+w).trim();}return [a,b];}
function drawPreviewFrame(svg,t){
  const {bg,accent}=t; addRect(svg,0,0,842,595,{fill:bg});
  if(activePreviewTemplate==='classic'){addRect(svg,24,24,794,547,{fill:'none',stroke:accent,'stroke-width':2.2,rx:10});addRect(svg,36,36,770,523,{fill:'none',stroke:'#d7c596','stroke-width':0.7,rx:8});}
  else if(activePreviewTemplate==='modern'){addRect(svg,0,0,842,78,{fill:'#0f172a'});addRect(svg,0,78,88,517,{fill:'#eaf2ff'});addRect(svg,148,0,646,1,{fill:accent});addRect(svg,34,34,774,527,{fill:'none',stroke:'#cbd5e1','stroke-width':0.7});}
  else if(activePreviewTemplate==='emerald'){addRect(svg,24,24,794,547,{fill:'none',stroke:accent,'stroke-width':2.3,rx:12});addRect(svg,36,36,770,523,{fill:'none',stroke:'#a5d4c8','stroke-width':0.7,rx:9});addRect(svg,350,30,142,10,{fill:t.soft,rx:5});}
  else if(activePreviewTemplate==='midnight'){addRect(svg,24,24,794,547,{fill:'none',stroke:'#a7b5ff','stroke-width':1.5,rx:12});addRect(svg,38,38,766,519,{fill:'none',stroke:'#32496f','stroke-width':0.7,rx:9});addLine(svg,36,84,806,84,{stroke:accent,'stroke-width':1.1});}
  else if(activePreviewTemplate==='royal'){addRect(svg,24,24,794,547,{fill:'none',stroke:accent,'stroke-width':2.4,rx:12});addRect(svg,36,36,770,523,{fill:'none',stroke:'#c9b7e8','stroke-width':0.75,rx:9});for(const [x,y] of [[60,60],[782,60],[60,535],[782,535]])addRect(svg,x-5,y-5,10,10,{fill:t.soft,rx:3});}
  else if(activePreviewTemplate==='burgundy'){addRect(svg,0,0,842,595,{fill:'#fffaf5'});addRect(svg,0,0,842,30,{fill:'#6f1d2a'});addRect(svg,0,583,842,12,{fill:'#8f2f42'});addRect(svg,24,24,794,547,{fill:'none',stroke:'#c6a15b','stroke-width':1.5,rx:12});addRect(svg,34,34,774,527,{fill:'none',stroke:'#dfcda4','stroke-width':0.6,rx:9});}
  else if(activePreviewTemplate==='skyline'){addRect(svg,0,0,102,595,{fill:'#0b3b72'});addRect(svg,0,585,842,10,{fill:'#0ea5e9'});addRect(svg,118,24,700,547,{fill:'none',stroke:'#cbd5e1','stroke-width':0.7});for(const [x,h] of [[18,90],[38,135],[58,108],[78,160]])addRect(svg,x,28,13,h,{fill:'#14508d'});}
  else if(activePreviewTemplate==='academic_blueprint'){addRect(svg,24,24,794,547,{fill:'none',stroke:'#16324f','stroke-width':1.6});addRect(svg,34,34,774,527,{fill:'none',stroke:'#9db8d1','stroke-width':0.7,'stroke-dasharray':'3 2'});addLine(svg,50,58,182,58,{stroke:'#1f5f9a','stroke-width':1.2});addLine(svg,660,58,792,58,{stroke:'#1f5f9a','stroke-width':1.2});addLine(svg,50,537,182,537,{stroke:'#1f5f9a','stroke-width':1.2});addLine(svg,660,537,792,537,{stroke:'#1f5f9a','stroke-width':1.2});}
  else if(activePreviewTemplate==='heritage_seal'){addRect(svg,24,24,794,547,{fill:'none',stroke:'#2f6b4f','stroke-width':2,'rx':10});addRect(svg,36,36,770,523,{fill:'none',stroke:'#b49755','stroke-width':0.8,'rx':8});for(const [x,y] of [[56,56],[786,56],[56,539],[786,539]]){addCircle(svg,x,y,14,{fill:'#e4eee7'});addCircle(svg,x,y,8,{fill:'none',stroke:'#b49755','stroke-width':0.7});addLine(svg,x-5,y,x+5,y,{stroke:'#b49755','stroke-width':0.7});addLine(svg,x,y-5,x,y+5,{stroke:'#b49755','stroke-width':0.7});}}
  else if(activePreviewTemplate==='teal_arch'){addRect(svg,0,0,18,595,{fill:'#eaf7f4'});addRect(svg,824,0,18,595,{fill:'#eaf7f4'});addRect(svg,29,29,784,537,{fill:'none',stroke:'#0f766e','stroke-width':1.5});addPath(svg,'M325 473 A96 96 0 0 1 517 473',{fill:'none',stroke:'#0f766e','stroke-width':0.9});addPath(svg,'M339 485 A82 82 0 0 1 503 485',{fill:'none',stroke:'#9fcfc7','stroke-width':0.7});}
  else if(activePreviewTemplate==='copper_ledger'){addRect(svg,25,25,792,545,{fill:'none',stroke:'#a85b2a','stroke-width':1.6});addRect(svg,36,36,770,523,{fill:'none',stroke:'#d7ae8d','stroke-width':0.7});for(let y=86;y<510;y+=24){addLine(svg,42,y,65,y,{stroke:'#c78960','stroke-width':0.6});addLine(svg,777,y,800,y,{stroke:'#c78960','stroke-width':0.6});}}
  else if(activePreviewTemplate==='ivory_ribbon'){addRect(svg,0,0,842,34,{fill:'#24354a'});addRect(svg,0,561,842,34,{fill:'#24354a'});addRect(svg,0,34,842,3,{fill:'#8b6a1f'});addRect(svg,0,558,842,3,{fill:'#8b6a1f'});addRect(svg,24,28,794,539,{fill:'none',stroke:'#d9cda9','stroke-width':0.8});}
  else if(activePreviewTemplate==='crimson_sash'){addPath(svg,'M622 0 H842 V54 H672 Z',{fill:'#f1c4c9'});addPath(svg,'M0 595 H180 L0 537 Z',{fill:'#f1c4c9'});addRect(svg,26,26,790,543,{fill:'none',stroke:'#b4232f','stroke-width':1.7});addRect(svg,37,37,768,521,{fill:'none',stroke:'#e6aab1','stroke-width':0.6});}
  else if(activePreviewTemplate==='cobalt_wave'){addRect(svg,25,25,792,545,{fill:'none',stroke:'#2458c7','stroke-width':1.8,'rx':14});addPath(svg,'M0 541 C130 560 240 520 370 549 C520 585 650 519 842 558 L842 595 H0 Z',{fill:'#dce6fb'});addPath(svg,'M42 548 A55 34 0 0 1 148 548',{fill:'none',stroke:'#9ab5eb','stroke-width':0.9});addPath(svg,'M694 548 A55 34 0 0 0 800 548',{fill:'none',stroke:'#9ab5eb','stroke-width':0.9});}
  else if(activePreviewTemplate==='sage_garden'){addRect(svg,24,24,794,547,{fill:'none',stroke:'#5f7f51','stroke-width':1.8,'rx':12});addRect(svg,37,37,768,521,{fill:'none',stroke:'#b7c7ad','stroke-width':0.7,'rx':9});for(const [x,y,dx,dy] of [[54,56,16,18],[788,56,-16,18],[54,539,16,-18],[788,539,-16,-18]]){addLine(svg,x,y,x+dx,y+dy,{stroke:'#5f7f51','stroke-width':0.8});addCircle(svg,x+dx,y+dy,4,{fill:'none',stroke:'#5f7f51','stroke-width':0.8});addCircle(svg,x+dx*0.7,y+dy*0.65,3,{fill:'#5f7f51'});}}
  else if(activePreviewTemplate==='charcoal_gold'){addRect(svg,24,24,794,547,{fill:'none',stroke:'#d2ad5f','stroke-width':1.6});addRect(svg,35,35,772,525,{fill:'none',stroke:'#6c5830','stroke-width':0.7});addRect(svg,24,24,794,7,{fill:'#d2ad5f'});addRect(svg,24,564,794,3,{fill:'#d2ad5f'});addCircle(svg,421,68,30,{fill:'#2a2417'});}
  else if(activePreviewTemplate==='coastal'){addRect(svg,0,0,14,595,{fill:'#e49b7e'});addRect(svg,14,0,42,595,{fill:'#d9f0f6'});addRect(svg,66,24,752,547,{fill:'none',stroke:'#0b82a5','stroke-width':1.3,'rx':10});addPath(svg,'M80 544 L220 544 L360 538 L500 546 L640 539 L797 545',{fill:'none',stroke:'#9bcbd8','stroke-width':0.9});}
  else if(activePreviewTemplate==='geometric'){addRect(svg,24,24,794,547,{fill:'none',stroke:'#4056a1','stroke-width':1.4});addRect(svg,34,34,774,527,{fill:'none',stroke:'#d7dcef','stroke-width':0.7});for(const [x,y] of [[56,56],[786,56],[56,539],[786,539]]){addPath(svg,'M '+x+' '+(y-9)+' L '+(x+9)+' '+y+' L '+x+' '+(y+9)+' L '+(x-9)+' '+y+' Z',{fill:'#e8ebf8',stroke:'#4056a1','stroke-width':0.6});}}
  else if(activePreviewTemplate==='monochrome'){addRect(svg,0,0,11,595,{fill:'#20252b'});addRect(svg,0,0,842,8,{fill:'#20252b'});addRect(svg,30,30,782,535,{fill:'none',stroke:'#20252b','stroke-width':0.9});addRect(svg,42,42,758,511,{fill:'none',stroke:'#dfe3e7','stroke-width':0.7});addLine(svg,160,491,682,491,{stroke:'#20252b','stroke-width':0.7});}
  else {addRect(svg,34,34,774,527,{fill:'none',stroke:'#cbd5e1','stroke-width':0.9});addRect(svg,34,34,774,3,{fill:'#111827'});}
}
function nssDateLabel(v){if(!v)return 'Date';const d=new Date(v+'T00:00:00');return Number.isNaN(d.getTime())?'Date':d.toLocaleDateString('en-GB',{day:'2-digit',month:'long',year:'numeric'});}
function renderNssPreview(svg,stage,ff){
  addImage(svg,stage.dataset.nssReferenceUrl,0,0,842,595);
  const name=document.getElementById('name')?.value?.trim()||'Student Name';
  const cert='SRGPC-PREVIEW';
  const from=document.getElementById('date_from')?.value||'';
  const to=document.getElementById('date_to')?.value||'';
  const dateText=v=>{if(!v)return 'Date';const d=new Date(v+'T00:00:00');return Number.isNaN(d.getTime())?'Date':d.toLocaleDateString('en-GB',{day:'2-digit',month:'long',year:'numeric'});};
  const range=from||to?dateText(from)+' – '+dateText(to):'DATE RANGE';

  // Cover only the three placeholders in the supplied artwork.
  addRect(svg,842*.835,595*.700,842*.145,595*.055,{fill:'#fff'});
  addRect(svg,842*.440,595*.390,842*.280,595*.070,{fill:'#fff'});
  addRect(svg,842*.685,595*.205,842*.285,595*.075,{fill:'#fff'});

  addText(svg,cert,842*.907,595*.727,{font:'Times New Roman, Times, serif',size:8.6,weight:700,fill:'#173b93',anchor:'middle'});
  addText(svg,name,842*.580,595*.417,{font:ff,size:16,weight:700,fill:'#b51e27',anchor:'middle',length:206});
  addText(svg,range,842*.825,595*.245,{font:'Times New Roman, Times, serif',size:11.2,weight:700,fill:'#b51e27',anchor:'middle',length:214});
}
function renderLiveCertificate(){
  const stage=document.getElementById('certificateLivePreview');const svg=document.getElementById('certificateLiveSvg');if(!stage||!svg)return;
  const get=id=>document.getElementById(id)?.value?.trim()||'';
  const name=get('name')||'Student Name', roll=get('roll')||'CSE24017', activity=get('activity')||'Activity / Event', position=get('position')||'Position / Achievement';
  const type=get('certificate_type')||'Achievement', year=get('academic_year')||'2026-27', font=get('font_family')||'Helvetica';
  const tpl=get('templateSelect')||'classic'; activePreviewTemplate=tpl;
  const t=PREVIEW_THEMES[tpl]||PREVIEW_THEMES.classic; const ff=PREVIEW_FONTS[font]||PREVIEW_FONTS.Helvetica;
  svg.replaceChildren(); if(tpl==='nss_seven_day'){renderNssPreview(svg,stage,ff);return;} drawPreviewFrame(svg,t);
  const cx=tpl==='skyline'?480:421;
  addImage(svg,stage.dataset.logoUrl,cx-38,49,76,80);
  addText(svg,'SRGPC',cx,139,{font:ff,size:13.5,weight:700,fill:t.accent,letterSpacing:'.6'});
  addText(svg,'CERTIFICATE OF ACHIEVEMENT',cx,175,{font:ff,size:29,weight:800,fill:t.ink,length:670});
  addText(svg,'Presented in recognition of outstanding performance',cx,200,{font:ff,size:10.6,fill:t.muted,length:560});
  addText(svg,'Presented to',cx,225,{font:ff,size:11,fill:t.muted});
  addText(svg,name,cx,265,{font:ff,size:32,weight:700,fill:t.ink,length:fitLen(name,600)});
  addLine(svg,cx-160,285,cx+160,285,{stroke:t.accent,'stroke-width':1.2});
  const [l1,l2]=splitPreview(`for securing ${position} in ${activity}.`,68);
  addText(svg,l1,cx,320,{font:ff,size:13,weight:700,fill:t.ink,length:Math.min(610,Math.max(250,610-(l1.length-35)*3))});
  if(l2)addText(svg,l2,cx,340,{font:ff,size:13,weight:700,fill:t.ink,length:Math.min(610,Math.max(250,610-(l2.length-35)*3))});
  const badgeW=Math.min(240,Math.max(152,60+type.length*5.4));
  addRect(svg,cx-badgeW/2,356,badgeW,36,{fill:t.soft,rx:18});
  addText(svg,type.toUpperCase(),cx,374,{font:ff,size:9,weight:700,fill:t.accent,length:badgeW-22});
  const sx1=tpl==='skyline'?306:306, sx2=tpl==='skyline'?610:610;
  const teacher=stage.dataset.teacherUrl, principal=stage.dataset.principalUrl;
  if(teacher)addImage(svg,teacher,sx1-63,422,126,44);
  if(principal)addImage(svg,principal,sx2-63,422,126,44);
  addLine(svg,sx1-86,470,sx1+86,470,{stroke:'#94a3b8','stroke-width':0.9});addLine(svg,sx2-86,470,sx2+86,470,{stroke:'#94a3b8','stroke-width':0.9});
  addText(svg,'Faculty / Coordinator',sx1,488,{font:ff,size:8.5,fill:t.ink,length:170});addText(svg,'Principal / Head of Institution',sx2,488,{font:ff,size:8.5,fill:t.ink,length:190});
  addText(svg,`Roll No. ${roll}`,165,555,{font:ff,size:8,fill:t.muted,length:150,anchor:'middle'});
  addText(svg,`${type} - ${year}`,425,555,{font:ff,size:8,fill:t.muted,length:210});
  addText(svg,'SRGPC-PREVIEW',640,555,{font:ff,size:7,fill:t.muted,length:130});
  addRect(svg,720,498,98,73,{fill:'#fff',stroke:t.accent,'stroke-width':0.8,rx:8});
  addImage(svg,stage.dataset.qrUrl,732,505,74,54); addText(svg,'SCAN TO VERIFY',769,563,{font:ff,size:6.4,weight:700,fill:t.accent,length:78});
}
let activePreviewTemplate='classic';let previewFrameTimer=null;
function bindCertificateLivePreview(){
  const form=document.getElementById('certForm');const stage=document.getElementById('certificateLivePreview');if(!form||!stage)return;
  const ids=['name','roll','activity','position','certificate_type','academic_year','date_from','date_to','font_family','templateSelect'];
  const refresh=()=>{cancelAnimationFrame(previewFrameTimer);previewFrameTimer=requestAnimationFrame(renderLiveCertificate);};
  ids.forEach(id=>{const el=document.getElementById(id);if(el){el.addEventListener('input',refresh);el.addEventListener('change',refresh);}});
  document.querySelectorAll('.template-option').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.template-option').forEach(b=>b.classList.remove('selected'));btn.classList.add('selected');const select=document.getElementById('templateSelect');if(select){select.value=btn.dataset.template;select.dispatchEvent(new Event('change',{bubbles:true}));}}));
  const applyNssDefaults=()=>{
    const tpl=document.getElementById('templateSelect')?.value,isNss=tpl==='nss_seven_day';
    const type=document.getElementById('certificate_type'),activity=document.getElementById('activity'),position=document.getElementById('position'),hint=document.getElementById('nssDateHint');
    if(isNss){if(type)type.value='NSS';if(activity&&!activity.value)activity.value='NSS Seven-Day Special Camp';if(position&&!position.value)position.value='Volunteer';}
    if(hint)hint.classList.toggle('hidden',!isNss);
  };
  document.getElementById('templateSelect')?.addEventListener('change',applyNssDefaults);applyNssDefaults();
  renderLiveCertificate();
}
function setupSignatureCanvas(kind){const c=document.getElementById('canvas-'+kind);if(!c)return;const ctx=c.getContext('2d');ctx.lineWidth=3;ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle='#0f172a';let drawing=false;function pos(e){const r=c.getBoundingClientRect();return{x:(e.clientX-r.left)*(c.width/r.width),y:(e.clientY-r.top)*(c.height/r.height)}}function start(e){e.preventDefault();drawing=true;const p=pos(e);ctx.beginPath();ctx.moveTo(p.x,p.y);liveSignature(kind,c.toDataURL('image/png'));}function move(e){if(!drawing)return;e.preventDefault();const p=pos(e);ctx.lineTo(p.x,p.y);ctx.stroke();liveSignature(kind,c.toDataURL('image/png'));}function end(){drawing=false;}c.addEventListener('pointerdown',start);c.addEventListener('pointermove',move);window.addEventListener('pointerup',end);}
function liveSignature(kind,dataUrl){const img=document.getElementById(kind==='teacher'?'previewTeacherSignature':'previewPrincipalSignature');if(!img)return;img.src=dataUrl;img.classList.remove('hidden');}
function clearSignature(kind){const c=document.getElementById('canvas-'+kind);if(c)c.getContext('2d').clearRect(0,0,c.width,c.height);const img=document.getElementById(kind==='teacher'?'previewTeacherSignature':'previewPrincipalSignature');if(img){img.src='';img.classList.add('hidden');}}
function saveSignature(kind){const c=document.getElementById('canvas-'+kind);if(!c)return false;const blank=document.createElement('canvas');blank.width=c.width;blank.height=c.height;if(c.toDataURL()===blank.toDataURL()){alert('Please draw the signature first.');return false}document.getElementById('data-'+kind).value=c.toDataURL('image/png');return true}
function bindSignatureUploads(){document.querySelectorAll('.signature-file').forEach(input=>input.addEventListener('change',()=>{const file=input.files&&input.files[0];if(!file)return;const reader=new FileReader();reader.onload=e=>liveSignature(input.dataset.kind,e.target.result);reader.readAsDataURL(file);}));['teacher','principal'].forEach(setupSignatureCanvas);}
function bindLoginRole(){const form=document.getElementById('loginForm');if(!form)return;const roleInput=document.getElementById('loginRole');const register=document.getElementById('studentRegister');const hint=document.getElementById('adminHint');const google=document.getElementById('googleSignIn');const submit=document.getElementById('loginSubmit');const setRole=role=>{roleInput.value=role;if(register)register.style.display=role==='student'?'block':'none';if(hint)hint.style.display=role==='admin'?'flex':'none';if(google)google.style.display=role==='student'?'flex':'none';if(submit)submit.style.display='block';};document.querySelectorAll('.role-tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.role-tab').forEach(x=>x.classList.remove('active'));tab.classList.add('active');setRole(tab.dataset.role);}));setRole(roleInput.value||'student');}
document.addEventListener('DOMContentLoaded',()=>{bindCertificateLivePreview();bindSignatureUploads();bindLoginRole();});

function bindPhase4States(){
  const bar=document.createElement('div');
  bar.className='global-loading-bar';
  bar.setAttribute('aria-hidden','true');
  document.body.prepend(bar);
  document.querySelectorAll('form').forEach(form=>{
    form.addEventListener('submit',()=>{
      if(form.dataset.noLoading==='true')return;
      document.body.classList.add('page-loading');
      const button=form.querySelector('button[type="submit"],input[type="submit"]');
      if(button && !button.disabled){
        button.dataset.loadingLabel=button.textContent || '';
        if(button.tagName==='INPUT'){button.value='Working…';}
        else{button.textContent='Working…';}
        button.disabled=true;
        button.setAttribute('aria-busy','true');
      }
    });
  });
  document.querySelectorAll('a[href]').forEach(link=>{
    const href=link.getAttribute('href')||'';
    if(!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('javascript:') || link.target==='_blank') return;
    link.addEventListener('click',()=>{
      if(link.classList.contains('download-link') || link.hasAttribute('download')) return;
      document.body.classList.add('page-loading');
    });
  });
}
document.addEventListener('DOMContentLoaded',()=>{bindCertificateLivePreview();bindSignatureUploads();bindLoginRole();injectCsrfTokens();bindPhase4States();});
