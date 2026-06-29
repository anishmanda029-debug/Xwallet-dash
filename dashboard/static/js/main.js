/* ═══════════════════════════════════════════════════════
   PremiumBot Dashboard — Main JavaScript
   Particles, sidebar, animations, toast, clipboard
   ═══════════════════════════════════════════════════════ */
'use strict';

/* ── Particles ─────────────────────────────────────────── */
(function () {
  const canvas = document.getElementById('particles-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, pts = [], raf;

  const CFG = {
    count: 50, minR: 0.8, maxR: 2.2,
    minSpd: 0.06, maxSpd: 0.22, dist: 130,
    colors: ['#5865F2','#9B59B6','#2ECC71','#3498DB','#F1C40F'],
    lineAlpha: 0.09,
  };

  const rand = (a, b) => Math.random() * (b - a) + a;

  function mkPt() {
    return {
      x: rand(0, W), y: rand(0, H),
      vx: rand(-CFG.maxSpd, CFG.maxSpd) || CFG.minSpd,
      vy: rand(-CFG.maxSpd, CFG.maxSpd) || CFG.minSpd,
      r: rand(CFG.minR, CFG.maxR),
      color: CFG.colors[Math.floor(Math.random() * CFG.colors.length)],
      alpha: rand(0.25, 0.65),
    };
  }

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    // connections
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
        const d  = Math.sqrt(dx*dx + dy*dy);
        if (d < CFG.dist) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(88,101,242,${CFG.lineAlpha*(1-d/CFG.dist)})`;
          ctx.lineWidth   = 0.5;
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.stroke();
        }
      }
    }
    // dots
    pts.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
      ctx.fillStyle = p.color + Math.round(p.alpha*255).toString(16).padStart(2,'0');
      ctx.fill();
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
    });
    raf = requestAnimationFrame(draw);
  }

  function init() { resize(); pts = Array.from({length: CFG.count}, mkPt); }
  init(); draw();
  window.addEventListener('resize', () => { cancelAnimationFrame(raf); init(); draw(); });
})();

/* ── Sidebar ────────────────────────────────────────────── */
(function () {
  const sidebar  = document.getElementById('sidebar');
  const mToggle  = document.getElementById('mobileToggle');
  if (!sidebar) return;

  const overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  document.body.appendChild(overlay);

  const open  = () => { sidebar.classList.add('open');  overlay.classList.add('active');  document.body.style.overflow='hidden'; };
  const close = () => { sidebar.classList.remove('open'); overlay.classList.remove('active'); document.body.style.overflow=''; };

  if (mToggle) mToggle.addEventListener('click', open);
  overlay.addEventListener('click', close);
  sidebar.querySelectorAll('.nav-item').forEach(i => i.addEventListener('click', () => { if(window.innerWidth<900) close(); }));
})();

/* ── Entrance animations ────────────────────────────────── */
(function () {
  const cards = document.querySelectorAll('.stat-card, .feature-card, .panel');
  cards.forEach((c, i) => {
    c.style.cssText += `opacity:0;transform:translateY(14px);transition:opacity .28s ease ${i*40}ms,transform .28s ease ${i*40}ms`;
    requestAnimationFrame(() => requestAnimationFrame(() => { c.style.opacity='1'; c.style.transform='translateY(0)'; }));
  });
})();

/* ── Table row animations ───────────────────────────────── */
(function () {
  document.querySelectorAll('.data-table tbody tr').forEach((r, i) => {
    r.style.cssText += `opacity:0;transform:translateY(6px);transition:opacity .2s ease ${i*25}ms,transform .2s ease ${i*25}ms`;
    requestAnimationFrame(() => requestAnimationFrame(() => { r.style.opacity='1'; r.style.transform='translateY(0)'; }));
  });
})();

/* ── Counter animations ─────────────────────────────────── */
(function () {
  document.querySelectorAll('.stat-value').forEach(el => {
    const raw = el.textContent.replace(/[₹, LTC]/g,'').trim();
    const num = parseFloat(raw);
    if (isNaN(num) || num === 0) return;
    const orig = el.textContent;
    const hasRupee = orig.includes('₹');
    const hasLTC   = orig.includes('LTC');
    const decs = (hasRupee || hasLTC) ? 2 : 0;
    const steps=40, dur=800;
    let count=0;
    const timer = setInterval(() => {
      count++;
      const v = Math.min(num * (count/steps), num);
      const formatted = v.toLocaleString(undefined, {minimumFractionDigits:decs, maximumFractionDigits:decs});
      el.textContent = hasRupee ? `₹${formatted}` : hasLTC ? `${formatted} LTC` : formatted;
      if (count >= steps) { clearInterval(timer); el.textContent = orig; }
    }, dur/steps);
  });
})();

/* ── Toast ──────────────────────────────────────────────── */
window.showToast = function(msg, type='success', ms=3500) {
  let container = document.getElementById('_tc');
  if (!container) {
    container = document.createElement('div');
    container.id = '_tc';
    container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none';
    document.body.appendChild(container);
  }
  const colors = {success:'#2ECC71',error:'#E74C3C',info:'#3498DB',warn:'#F39C12'};
  const t = document.createElement('div');
  t.style.cssText = `
    background:rgba(10,11,15,.96);border:1px solid ${colors[type]||colors.info}44;
    border-left:3px solid ${colors[type]||colors.info};color:#EAECF0;padding:11px 16px;
    border-radius:10px;font-size:13px;font-family:'DM Sans',sans-serif;
    box-shadow:0 8px 32px rgba(0,0,0,.5);backdrop-filter:blur(12px);
    max-width:300px;opacity:0;transform:translateX(20px);
    transition:all .22s cubic-bezier(.4,0,.2,1);pointer-events:auto;cursor:pointer;
  `;
  t.textContent = msg;
  container.appendChild(t);
  requestAnimationFrame(() => { t.style.opacity='1'; t.style.transform='translateX(0)'; });
  const rm = () => { t.style.opacity='0'; t.style.transform='translateX(20px)'; setTimeout(()=>t.remove(), 250); };
  t.addEventListener('click', rm);
  setTimeout(rm, ms);
};

/* ── Copy ───────────────────────────────────────────────── */
window.copyText = async function(text, label='Copied!') {
  try { await navigator.clipboard.writeText(text); showToast('📋 ' + label, 'success', 2000); }
  catch { showToast('Copy failed', 'error', 2000); }
};

/* ── Keyboard shortcuts ─────────────────────────────────── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
  }
  if (e.ctrlKey && e.key === '/') {
    const inp = document.querySelector('.search-input');
    if (inp) { e.preventDefault(); inp.focus(); }
  }
});

/* ── Page fade in ───────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  document.body.style.opacity = '0';
  document.body.style.transition = 'opacity .25s ease';
  requestAnimationFrame(() => { document.body.style.opacity = '1'; });
});

/* ── Auto-refresh status dot ────────────────────────────── */
setInterval(() => {
  const dot = document.querySelector('.status-dot');
  if (dot) { dot.style.boxShadow = '0 0 12px #2ECC71'; setTimeout(()=>{ dot.style.boxShadow='0 0 8px #2ECC71'; }, 300); }
}, 5000);
