'use strict';

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Generates a self-contained HTML accessibility report with:
 * - Full page screenshot with colored bounding-box overlays on failing elements
 * - Interactive sidebar showing element details and per-element screenshots on click
 *
 * @param {object} opts
 * @param {string}   opts.url            - The audited URL
 * @param {Array}    opts.findings        - Flat findings array (same shape as analyseUrlFlat)
 * @param {string|null} opts.pageScreenshot - Full-page screenshot as base64 PNG (or null)
 * @param {number}   [opts.pageWidth=1280] - Natural page width (pixels)
 * @returns {string} Self-contained HTML string
 */
function generateReport({ url, findings, pageScreenshot, pageWidth = 1280 }) {
  const violations = findings.filter(f => f.status === 'fail' || f.status === 'needs_review');
  const passCount   = findings.filter(f => f.status === 'pass').length;
  const failCount   = findings.filter(f => f.status === 'fail').length;
  const reviewCount = findings.filter(f => f.status === 'needs_review').length;

  // Build overlay marker data (only for elements that have a bounding box)
  const markers = violations
    .map((f, i) => {
      const bbox = f.element && f.element.bounding_box;
      if (!bbox) return null;
      return { id: i, x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height, status: f.status };
    })
    .filter(Boolean);

  // Slim down findings for inline JSON (avoid serializing the full-page screenshot inside each element)
  const violationsJson = JSON.stringify(
    violations.map(f => ({
      rule_id:        f.rule_id || f.ruleId || '',
      status:         f.status,
      wcag_sc:        f.wcag_sc || null,
      criterion_name: f.criterion_name || null,
      level:          f.level || null,
      severity:       f.severity || null,
      reason:         f.reason || '',
      suggested_fix:  f.suggested_fix || null,
      help_url:       f.help_url || f.helpUrl || null,
      element: f.element ? {
        html:         f.element.html || null,
        selector:     f.element.selector || (Array.isArray(f.element.target) ? f.element.target[0] : null) || null,
        bounding_box: f.element.bounding_box || null,
        screenshot:   f.element.screenshot   || null,
      } : null,
    }))
  );

  const markersJson = JSON.stringify(markers);

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ka11y Report — ${escapeHtml(url)}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f8fa;color:#1a202c;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.header{background:#1a202c;color:#fff;padding:12px 20px;flex-shrink:0}
.header h1{font-size:15px;font-weight:700;letter-spacing:.02em}
.header .url{font-size:11px;color:#a0aec0;margin-top:2px;word-break:break-all}
.summary{display:flex;gap:8px;padding:8px 20px;background:#fff;border-bottom:1px solid #e2e8f0;flex-shrink:0;flex-wrap:wrap}
.badge{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
.b-fail{background:#fff5f5;color:#c53030;border:1px solid #fc8181}
.b-review{background:#fffaf0;color:#c05621;border:1px solid #f6ad55}
.b-pass{background:#f0fff4;color:#276749;border:1px solid #68d391}
.main{display:flex;flex:1;overflow:hidden}
.page-view{flex:1;overflow:auto;padding:16px;background:#e2e8f0}
.sw{position:relative;display:inline-block;min-width:100%}
.sw img{display:block;max-width:100%;height:auto;box-shadow:0 2px 12px rgba(0,0,0,.2)}
.obox{position:absolute;border:2px solid;cursor:pointer;border-radius:2px;transition:opacity .1s}
.obox:hover{opacity:.8;z-index:10}
.obox.active{z-index:20;outline:3px solid #3182ce;outline-offset:2px}
.mnum{position:absolute;top:-18px;left:-1px;font-size:10px;font-weight:700;padding:1px 4px;border-radius:2px 2px 0 0;color:#fff;line-height:1.5;pointer-events:none;white-space:nowrap}
.sidebar{width:360px;min-width:360px;background:#fff;border-left:1px solid #e2e8f0;display:flex;flex-direction:column;overflow:hidden}
.panel{display:flex;flex-direction:column;height:100%;overflow:hidden}
.ph{padding:10px 14px;border-bottom:1px solid #e2e8f0;font-weight:600;font-size:12px;background:#f7f8fa;flex-shrink:0;color:#4a5568}
.plist{flex:1;overflow-y:auto}
.fi{padding:9px 12px;border-bottom:1px solid #f0f0f0;cursor:pointer}
.fi:hover{background:#f7f8fa}
.fi.active{background:#ebf8ff;border-left:3px solid #3182ce;padding-left:9px}
.fi-top{display:flex;align-items:center;gap:5px;margin-bottom:2px}
.sb{padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;text-transform:uppercase}
.sb-fail{background:#fff5f5;color:#c53030}
.sb-review{background:#fffaf0;color:#c05621}
.fi-num{font-size:10px;color:#a0aec0}
.fi-rule{font-size:11px;font-weight:600;color:#2d3748;margin-bottom:1px}
.fi-sc{font-size:10px;color:#718096;margin-bottom:2px}
.fi-reason{font-size:10px;color:#4a5568;line-height:1.4}
.dpanel{display:none;flex-direction:column;height:100%}
.dpanel.open{display:flex}
.back{padding:9px 12px;font-size:11px;color:#3182ce;cursor:pointer;border-bottom:1px solid #e2e8f0;background:#f7f8fa;flex-shrink:0}
.back:hover{background:#ebf8ff}
.dbody{flex:1;overflow-y:auto;padding:12px}
.df{margin-bottom:8px}
.dl{font-size:9px;font-weight:700;color:#718096;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px}
.dv{font-size:11px;color:#2d3748;line-height:1.5}
.code{font-family:'SFMono-Regular',Consolas,monospace;background:#f7f8fa;padding:6px 8px;border-radius:3px;font-size:10px;word-break:break-all;border:1px solid #e2e8f0;white-space:pre-wrap}
.el-img img{max-width:100%;border:1px solid #e2e8f0;border-radius:3px;margin-top:3px}
.no-img{background:#f7f8fa;border:1px dashed #e2e8f0;border-radius:3px;padding:12px;text-align:center;color:#a0aec0;font-size:10px}
.doc-link{display:inline-block;margin-top:3px;color:#3182ce;font-size:11px;text-decoration:none}
.doc-link:hover{text-decoration:underline}
.no-ss{padding:32px;text-align:center;color:#a0aec0;font-size:12px}
</style>
</head>
<body>
<div class="header">
  <h1>ka11y Accessibility Report</h1>
  <div class="url">${escapeHtml(url)}</div>
</div>
<div class="summary">
  <span class="badge b-fail">&#x2715; ${failCount} Violation${failCount !== 1 ? 's' : ''}</span>
  <span class="badge b-review">&#x26A0; ${reviewCount} Needs Review</span>
  <span class="badge b-pass">&#x2713; ${passCount} Passed</span>
</div>
<div class="main">
  <div class="page-view" id="pv">
    ${pageScreenshot
      ? `<div class="sw" id="sw"><img id="pi" src="data:image/png;base64,${pageScreenshot}" alt="Page screenshot" onload="init()" /></div>`
      : '<div class="no-ss">No page screenshot captured.</div>'
    }
  </div>
  <div class="sidebar">
    <div class="panel" id="listPanel">
      <div class="ph">Findings (${violations.length})</div>
      <div class="plist">
        ${violations.map((f, i) => `
          <div class="fi" id="li-${i}" onclick="openFinding(${i})">
            <div class="fi-top">
              <span class="sb ${f.status === 'fail' ? 'sb-fail' : 'sb-review'}">${f.status === 'fail' ? 'Fail' : 'Review'}</span>
              <span class="fi-num">#${i + 1}</span>
            </div>
            <div class="fi-rule">${escapeHtml(f.rule_id || f.ruleId || '')}</div>
            <div class="fi-sc">WCAG ${escapeHtml(f.wcag_sc || '')}${f.criterion_name ? ' — ' + escapeHtml(f.criterion_name) : ''}</div>
            <div class="fi-reason">${escapeHtml((f.reason || '').slice(0, 90))}${(f.reason || '').length > 90 ? '…' : ''}</div>
          </div>`).join('')}
      </div>
    </div>
    <div class="dpanel" id="detailPanel">
      <div class="back" onclick="closeDetail()">← All findings</div>
      <div class="dbody" id="db"></div>
    </div>
  </div>
</div>
<script>
const V=${violationsJson};
const M=${markersJson};
const PW=${pageWidth};
const C={fail:'#e53e3e',needs_review:'#dd6b20'};
const BG={fail:'rgba(229,62,62,.1)',needs_review:'rgba(221,107,32,.1)'};
let act=-1,sx=1,sy=1;

function eh(s){if(!s)return'';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function init(){
  const img=document.getElementById('pi');
  if(!img)return;
  sx=img.offsetWidth/(img.naturalWidth||PW);
  sy=img.offsetHeight/(img.naturalHeight||(img.naturalWidth*0.75)||600);
  draw();
}

function draw(){
  const sw=document.getElementById('sw');
  if(!sw)return;
  sw.querySelectorAll('.obox').forEach(e=>e.remove());
  M.forEach(m=>{
    const d=document.createElement('div');
    d.className='obox'+(act===m.id?' active':'');
    d.style.cssText='left:'+m.x*sx+'px;top:'+m.y*sy+'px;width:'+Math.max(m.width*sx,4)+'px;height:'+Math.max(m.height*sy,4)+'px;border-color:'+(C[m.status]||'#e53e3e')+';background:'+(BG[m.status]||'rgba(229,62,62,.1)');
    const n=document.createElement('div');n.className='mnum';n.style.background=C[m.status]||'#e53e3e';n.textContent='#'+(m.id+1);
    d.appendChild(n);
    d.addEventListener('click',()=>openFinding(m.id));
    sw.appendChild(d);
  });
}

function openFinding(i){
  act=i;
  document.querySelectorAll('.fi').forEach(e=>e.classList.remove('active'));
  const li=document.getElementById('li-'+i);
  if(li){li.classList.add('active');li.scrollIntoView({block:'nearest'});}
  draw();
  const m=M.find(x=>x.id===i);
  if(m){const pv=document.getElementById('pv');if(pv)pv.scrollTo({top:Math.max(0,m.y*sy-80),behavior:'smooth'});}
  const f=V[i];if(!f)return;
  const el=f.element||{};
  const bb=el.bounding_box;
  document.getElementById('db').innerHTML=
    '<div class="df"><div class="dl">Rule ID</div><div class="dv"><strong>'+eh(f.rule_id)+'</strong></div></div>'+
    '<div class="df"><div class="dl">Status</div><div class="dv"><span class="sb '+(f.status==='fail'?'sb-fail':'sb-review')+'">'+(f.status==='fail'?'Fail':'Needs Review')+'</span></div></div>'+
    '<div class="df"><div class="dl">WCAG Criterion</div><div class="dv">SC '+eh(f.wcag_sc||'')+' '+eh(f.criterion_name||'')+(f.level?' (Level '+eh(f.level)+')')+'</div></div>'+
    (f.severity?'<div class="df"><div class="dl">Severity</div><div class="dv">'+eh(f.severity)+'</div></div>':'')+
    '<div class="df"><div class="dl">Issue</div><div class="dv">'+eh(f.reason||'')+'</div></div>'+
    (f.suggested_fix?'<div class="df"><div class="dl">Suggested Fix</div><div class="dv">'+eh(f.suggested_fix)+'</div></div>':'')+
    (el.html?'<div class="df"><div class="dl">HTML Element</div><div class="code">'+eh(el.html)+'</div></div>':'')+
    (el.selector?'<div class="df"><div class="dl">CSS Selector</div><div class="code">'+eh(el.selector)+'</div></div>':'')+
    (bb?'<div class="df"><div class="dl">Position on Page</div><div class="dv">x:'+Math.round(bb.x)+', y:'+Math.round(bb.y)+', '+Math.round(bb.width)+'\xd7'+Math.round(bb.height)+'px</div></div>':'')+
    (el.screenshot
      ?'<div class="df"><div class="dl">Element Screenshot</div><div class="el-img"><img src="data:image/png;base64,'+el.screenshot+'" alt="element" /></div></div>'
      :'<div class="df"><div class="dl">Element Screenshot</div><div class="no-img">Not captured</div></div>')+
    (f.help_url?'<div class="df"><a class="doc-link" href="'+eh(f.help_url)+'" target="_blank" rel="noopener">→ View WCAG documentation</a></div>':'');
  document.getElementById('listPanel').style.display='none';
  document.getElementById('detailPanel').classList.add('open');
}

function closeDetail(){
  document.getElementById('listPanel').style.display='';
  document.getElementById('detailPanel').classList.remove('open');
}

window.addEventListener('resize',init);
</script>
</body>
</html>`;
}

module.exports = { generateReport };
