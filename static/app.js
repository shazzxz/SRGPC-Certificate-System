function escSvg(v){return String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;');}
const PREVIEW_THEMES={
  classic:{bg:'#fbf8ef',ink:'#202124',muted:'#7c7366',accent:'#b38724',soft:'#efe2be'},
  modern:{bg:'#f7faff',ink:'#0f172a',muted:'#64748b',accent:'#2563eb',soft:'#dbeafe'},
  emerald:{bg:'#f7fcfa',ink:'#123c37',muted:'#67817c',accent:'#0f766e',soft:'#d9f2eb'},
  midnight:{bg:'#0b1426',ink:'#f8fafc',muted:'#9fb1ca',accent:'#7dd3fc',soft:'#18345c'},
  royal:{bg:'#fbf9ff',ink:'#2f204b',muted:'#7e7192',accent:'#6d28d9',soft:'#eee6ff'},
  burgundy:{bg:'#fffaf5',ink:'#3f1719',muted:'#8b6d6e',accent:'#8f2027',soft:'#f2e0d8'},
  skyline:{bg:'#f6fbff',ink:'#10233c',muted:'#6e8197',accent:'#0ea5e9',soft:'#dff4ff'},
  minimal:{bg:'#ffffff',ink:'#111827',muted:'#6b7280',accent:'#334155',soft:'#f1f5f9'}
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
  else {addRect(svg,34,34,774,527,{fill:'none',stroke:'#cbd5e1','stroke-width':0.9});addRect(svg,34,34,774,3,{fill:'#111827'});}
}
function renderLiveCertificate(){
  const stage=document.getElementById('certificateLivePreview');const svg=document.getElementById('certificateLiveSvg');if(!stage||!svg)return;
  const get=id=>document.getElementById(id)?.value?.trim()||'';
  const name=get('name')||'Student Name', roll=get('roll')||'CSE24017', activity=get('activity')||'Activity / Event', position=get('position')||'Position / Achievement';
  const type=get('certificate_type')||'Achievement', year=get('academic_year')||'2026-27', font=get('font_family')||'Helvetica';
  const tpl=get('templateSelect')||'classic'; activePreviewTemplate=tpl;
  const t=PREVIEW_THEMES[tpl]||PREVIEW_THEMES.classic; const ff=PREVIEW_FONTS[font]||PREVIEW_FONTS.Helvetica;
  svg.replaceChildren(); drawPreviewFrame(svg,t);
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
  const ids=['name','roll','activity','position','certificate_type','academic_year','font_family','templateSelect'];
  const refresh=()=>{cancelAnimationFrame(previewFrameTimer);previewFrameTimer=requestAnimationFrame(renderLiveCertificate);};
  ids.forEach(id=>{const el=document.getElementById(id);if(el){el.addEventListener('input',refresh);el.addEventListener('change',refresh);}});
  document.querySelectorAll('.template-option').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.template-option').forEach(b=>b.classList.remove('selected'));btn.classList.add('selected');const select=document.getElementById('templateSelect');if(select){select.value=btn.dataset.template;select.dispatchEvent(new Event('change',{bubbles:true}));}}));
  renderLiveCertificate();
}
function setupSignatureCanvas(kind){const c=document.getElementById('canvas-'+kind);if(!c)return;const ctx=c.getContext('2d');ctx.lineWidth=3;ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle='#0f172a';let drawing=false;function pos(e){const r=c.getBoundingClientRect();return{x:(e.clientX-r.left)*(c.width/r.width),y:(e.clientY-r.top)*(c.height/r.height)}}function start(e){e.preventDefault();drawing=true;const p=pos(e);ctx.beginPath();ctx.moveTo(p.x,p.y);liveSignature(kind,c.toDataURL('image/png'));}function move(e){if(!drawing)return;e.preventDefault();const p=pos(e);ctx.lineTo(p.x,p.y);ctx.stroke();liveSignature(kind,c.toDataURL('image/png'));}function end(){drawing=false;}c.addEventListener('pointerdown',start);c.addEventListener('pointermove',move);window.addEventListener('pointerup',end);}
function liveSignature(kind,dataUrl){const img=document.getElementById(kind==='teacher'?'previewTeacherSignature':'previewPrincipalSignature');if(!img)return;img.src=dataUrl;img.classList.remove('hidden');}
function clearSignature(kind){const c=document.getElementById('canvas-'+kind);if(c)c.getContext('2d').clearRect(0,0,c.width,c.height);const img=document.getElementById(kind==='teacher'?'previewTeacherSignature':'previewPrincipalSignature');if(img){img.src='';img.classList.add('hidden');}}
function saveSignature(kind){const c=document.getElementById('canvas-'+kind);if(!c)return false;const blank=document.createElement('canvas');blank.width=c.width;blank.height=c.height;if(c.toDataURL()===blank.toDataURL()){alert('Please draw the signature first.');return false}document.getElementById('data-'+kind).value=c.toDataURL('image/png');return true}
function bindSignatureUploads(){document.querySelectorAll('.signature-file').forEach(input=>input.addEventListener('change',()=>{const file=input.files&&input.files[0];if(!file)return;const reader=new FileReader();reader.onload=e=>liveSignature(input.dataset.kind,e.target.result);reader.readAsDataURL(file);}));['teacher','principal'].forEach(setupSignatureCanvas);}
function bindLoginRole(){const form=document.getElementById('loginForm');if(!form)return;const roleInput=document.getElementById('loginRole');const register=document.getElementById('studentRegister');const hint=document.getElementById('adminHint');document.querySelectorAll('.role-tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.role-tab').forEach(x=>x.classList.remove('active'));tab.classList.add('active');roleInput.value=tab.dataset.role;if(register)register.style.display=tab.dataset.role==='student'?'block':'none';if(hint)hint.style.display=tab.dataset.role==='admin'?'flex':'none';}));}
document.addEventListener('DOMContentLoaded',()=>{bindCertificateLivePreview();bindSignatureUploads();bindLoginRole();});

function setupThemeToggle(){
  const root=document.documentElement, body=document.body, btn=document.getElementById('themeToggle'); if(!btn)return;
  const saved=localStorage.getItem('srgpc-theme');
  const apply=dark=>{root.classList.toggle('dark-mode',dark);body.classList.toggle('dark-mode',dark);btn.querySelector('.theme-icon').textContent=dark?'☀':'☾';btn.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');};
  apply(saved!=='light');
  btn.addEventListener('click',()=>{const dark=!root.classList.contains('dark-mode');localStorage.setItem('srgpc-theme',dark?'dark':'light');apply(dark);});
}
document.addEventListener('DOMContentLoaded',setupThemeToggle);
