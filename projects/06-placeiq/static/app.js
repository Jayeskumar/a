/* PlaceIQ front-end. Vanilla JS, hand-drawn SVG charts, no external libraries. */
'use strict';

const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
const S = { info: null, dash: null, model: null, eda: null, students: [], current: null, clusters: {}, loaded: {} };

const SHORT = {
  cgpa: 'CGPA', tenth_pct: '10th %', twelfth_pct: '12th %', backlogs: 'Backlogs', internships: 'Internships',
  projects: 'Projects', certifications: 'Certs', coding_problems: 'Coding', hackathons: 'Hackathons',
  aptitude_score: 'Aptitude', communication_score: 'Comm.', mock_interview_score: 'Mock int.', placed: 'Placed'
};
// What-if slider ranges (practical, not hard limits).
const SIM = {
  cgpa: [5, 10, 0.05], tenth_pct: [40, 100, 0.5], twelfth_pct: [40, 100, 0.5], backlogs: [0, 10, 1],
  internships: [0, 6, 1], projects: [0, 12, 1], certifications: [0, 12, 1], coding_problems: [0, 1500, 10],
  hackathons: [0, 10, 1], aptitude_score: [0, 100, 1], communication_score: [0, 100, 1], mock_interview_score: [0, 100, 1]
};

/* ------------------------------------------------------------------ utils */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const pct = (p, d) => (p == null ? '–' : (100 * p).toFixed(d == null ? 0 : d) + '%');
const fmt = (n, d) => (n == null ? '–' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d == null ? 2 : d, minimumFractionDigits: 0 }));
// probabilities below 0.5% read as "<1%" instead of a misleading flat "0%"
const pctP = p => (p != null && p < 0.005 ? '<1%' : pct(p));
// server/UI templates use "(s)": "1 backlog(s)" -> "1 backlog", "8 backlog(s)" -> "8 backlogs"
const plural = t => String(t == null ? '' : t).replace(/\b1 (\w+)\(s\)/g, '1 $1').replace(/(\w)\(s\)/g, '$1s');
// Charts are drawn at their container's pixel width so SVG text stays 12px on phones and projectors.
const cw = (sel, def) => { const el = typeof sel === 'string' ? $(sel) : sel; const w = el ? el.clientWidth : 0; return w > 120 ? Math.round(w) : (def || 460); };
const isNarrow = sel => cw(sel, 999) < 480;
// Round axis maximum: smallest 1/2/2.5/5 x 10^k step that covers max in at most 6 ticks
// (minStep 1 for counts, so small counts never get fractional, duplicated tick labels).
function niceAxis(max, minStep) {
  max = Math.max(max, minStep || 1e-9);
  const p = Math.pow(10, Math.floor(Math.log10(max / 6)));
  for (const m of [1, 2, 2.5, 5, 10, 20]) {
    const step = m * p, n = Math.ceil(max / step - 1e-9);
    if (minStep && step < minStep) continue;
    if (n <= 6) return { top: step * n, n: Math.max(1, n), step };
  }
  return { top: max, n: 4, step: max / 4 };
}
const sigmoid = z => (z >= 0 ? 1 / (1 + Math.exp(-z)) : Math.exp(z) / (1 + Math.exp(z)));
function statusOf(p) {
  if (p >= 0.7) return { cls: 'good', label: 'On track', icon: '✓' };
  if (p >= 0.5) return { cls: 'warn', label: 'Borderline', icon: '~' };
  if (p >= 0.3) return { cls: 'serious', label: 'At risk', icon: '!' };
  return { cls: 'critical', label: 'High risk', icon: '!!' };
}
const probChip = p => { const s = statusOf(p); return `<span class="chip" title="${s.label}"><i class="dot-${s.cls}"></i>${pctP(p)} · ${s.label}</span>`; };
function toast(msg, ms) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), ms || 2800);
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  if (!r.ok) { const err = new Error((body && (body.error || body.message)) || ('HTTP ' + r.status)); err.body = body; throw err; }
  return body;
}
function qs(o) {
  const p = Object.entries(o).filter(([, v]) => v != null && v !== '' && v !== 'ALL').map(([k, v]) => k + '=' + encodeURIComponent(v));
  return p.length ? '?' + p.join('&') : '';
}
const personaColor = i => `var(--s${(i % 6) + 1})`;

/* ------------------------------------------------------------------ tooltip */
(function tooltip() {
  const tip = $('#tip');
  document.addEventListener('mousemove', e => {
    const el = e.target.closest && e.target.closest('[data-tip]');
    if (!el) { tip.classList.remove('show'); return; }
    tip.innerHTML = el.getAttribute('data-tip').split('\n').map(esc).join('<br>');
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + w > innerWidth - 8) x = e.clientX - w - 14;
    if (y + h > innerHeight - 8) y = e.clientY - h - 14;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
    tip.classList.add('show');
  });
  document.addEventListener('mouseleave', () => tip.classList.remove('show'));
})();

/* ------------------------------------------------------------------ SVG helpers */
// Bar path with the data end rounded (r=4) and the baseline end square.
function barH(x0, y, len, h, r) {
  r = Math.min(r == null ? 4 : r, Math.abs(len) / 2, h / 2);
  if (Math.abs(len) < 0.5) return '';
  if (len > 0) {
    const x1 = x0 + len;
    return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x0}Z`;
  }
  const x1 = x0 + len;
  return `M${x0},${y}H${x1 + r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 + r},${y + h}H${x0}Z`;
}
function barV(x, y0, w, len, r) {
  r = Math.min(r == null ? 4 : r, len / 2, w / 2);
  if (len < 0.5) return '';
  const y1 = y0 - len;
  return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`;
}
function svg(w, h, inner, label) {
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label || '')}">${inner}</svg>`;
}

// Horizontal bars: items [{label, value, tip, color, text}]
function hbars(items, o) {
  o = Object.assign({ W: 460, row: 28, labelW: 96, max: null, fmt: v => fmt(v), valueW: 60 }, o || {});
  // 'auto': fit the longest label (≈6.7px per char at 12px), capped at ~half the chart width
  if (o.labelW === 'auto') o.labelW = Math.round(Math.min(o.W * (o.W >= 400 ? 0.56 : 0.45), Math.max(...items.map(d => String(d.label).length)) * 6.7 + 14));
  const maxCh = Math.max(4, Math.floor((o.labelW - 12) / 6.7));
  const clip = t => (String(t).length > maxCh ? String(t).slice(0, maxCh - 1) + '…' : String(t));
  const ax = o.max ? { top: o.max, n: 4 } : niceAxis(Math.max(...items.map(d => d.value)), items.every(d => Number.isInteger(d.value)) ? 1 : 0);
  const max = ax.top;
  const plotW = o.W - o.labelW - o.valueW;
  const H = items.length * o.row + 20;
  let g = '';
  for (let t = 0; t <= ax.n; t++) {
    const x = o.labelW + plotW * t / ax.n;
    g += `<line class="gridline" x1="${x}" x2="${x}" y1="0" y2="${H - 18}"/>`;
    g += `<text class="lbl" x="${x}" y="${H - 3}" text-anchor="middle">${esc(o.fmt(max * t / ax.n))}</text>`;
  }
  items.forEach((d, i) => {
    const y = i * o.row + 5, bh = o.row - 10;
    const len = Math.max(0, plotW * d.value / max);
    g += `<g data-tip="${esc(d.tip || d.label + ': ' + o.fmt(d.value))}">`;
    g += `<rect class="hit" x="0" y="${y - 4}" width="${o.W}" height="${o.row}"/>`;
    g += `<text class="lbl-ink2" x="${o.labelW - 8}" y="${y + bh / 2 + 4}" text-anchor="end">${esc(clip(d.label))}</text>`;
    g += `<path d="${barH(o.labelW, y, len, bh)}" style="fill:${d.color || 'var(--accent-fill)'}"/>`;
    g += `<text class="lbl-ink" x="${o.labelW + len + 6}" y="${y + bh / 2 + 4}">${esc(d.text != null ? d.text : o.fmt(d.value))}</text>`;
    g += `</g>`;
  });
  g += `<line class="baseline" x1="${o.labelW}" x2="${o.labelW}" y1="0" y2="${H - 18}"/>`;
  return svg(o.W, H, g, o.label);
}

// Vertical columns: items [{label, value, tip, color}]
function columns(items, o) {
  o = Object.assign({ W: 460, H: 200, fmt: v => fmt(v, 0), pad: 30 }, o || {});
  const ax = niceAxis(Math.max(1, ...items.map(d => d.value)), items.every(d => Number.isInteger(d.value)) ? 1 : 0), max = ax.top;
  const plotH = o.H - 44, base = o.H - 24, left = o.pad, plotW = o.W - left - 6;
  const bw = plotW / items.length;
  let g = '';
  for (let t = 0; t <= ax.n; t++) {
    const y = base - plotH * t / ax.n;
    g += `<line class="gridline" x1="${left}" x2="${o.W}" y1="${y}" y2="${y}"/><text class="lbl" x="${left - 6}" y="${y + 4}" text-anchor="end">${esc(o.fmt(max * t / ax.n))}</text>`;
  }
  items.forEach((d, i) => {
    const x = left + i * bw + Math.max(2, bw * 0.18), w = Math.max(2, bw * 0.64);
    const len = plotH * d.value / max;
    g += `<g data-tip="${esc(d.tip || d.label + ': ' + o.fmt(d.value))}"><rect class="hit" x="${left + i * bw}" y="${base - plotH}" width="${bw}" height="${plotH + 20}"/>`;
    g += `<path d="${barV(x, base, w, len)}" style="fill:${d.color || 'var(--accent-fill)'}"/>`;
    if (o.showValues !== false) g += `<text class="lbl-ink" x="${x + w / 2}" y="${base - len - 5}" text-anchor="middle">${esc(o.fmt(d.value))}</text>`;
    g += `<text class="lbl" x="${x + w / 2}" y="${base + 15}" text-anchor="middle">${esc(d.label)}</text></g>`;
  });
  g += `<line class="baseline" x1="${left}" x2="${o.W}" y1="${base}" y2="${base}"/>`;
  return svg(o.W, o.H, g, o.label);
}

// Diverging horizontal bars around zero: items [{label, value, tip}]
function diverging(items, o) {
  o = Object.assign({ W: 460, row: 24, labelW: 120, fmt: v => (v >= 0 ? '+' : '') + v.toFixed(2) }, o || {});
  const max = Math.max(1e-6, ...items.map(d => Math.abs(d.value)));
  // equal room for the value label on both sides so "+0.65" never runs past the edge
  const pad = 44, plotW = o.W - o.labelW - 2 * pad, mid = o.labelW + pad + plotW / 2, half = plotW / 2 - 2;
  const H = items.length * o.row + 20;
  let g = `<text class="lbl" x="${mid - 6}" y="${H - 4}" text-anchor="end">${esc(o.negLabel || '◀ lowers')}</text><text class="lbl" x="${mid + 6}" y="${H - 4}">${esc(o.posLabel || 'raises ▶')}</text>`;
  items.forEach((d, i) => {
    const y = i * o.row + 4, bh = o.row - 9;
    const len = half * d.value / max;
    g += `<g data-tip="${esc(d.tip || d.label + ': ' + o.fmt(d.value))}"><rect class="hit" x="0" y="${y - 3}" width="${o.W}" height="${o.row}"/>`;
    g += `<text class="lbl-ink2" x="${o.labelW - 6}" y="${y + bh / 2 + 4}" text-anchor="end">${esc(d.label)}</text>`;
    g += `<path d="${barH(mid, y, len, bh)}" class="${d.value >= 0 ? 'm-accent' : 'm-neg'}"/>`;
    const tx = d.value >= 0 ? mid + len + 5 : mid + len - 5;
    g += `<text class="lbl" x="${tx}" y="${y + bh / 2 + 4}" text-anchor="${d.value >= 0 ? 'start' : 'end'}">${esc(o.fmt(d.value))}</text></g>`;
  });
  g += `<line class="baseline" x1="${mid}" x2="${mid}" y1="0" y2="${H - 16}"/>`;
  return svg(o.W, H, g, o.label);
}

function lineChart(series, o) {
  // series: [{points:[[x,y]], cls, area}] ; o: {xmax, ymax, xlabel, ylabel}
  o = Object.assign({ W: 460, H: 260, xmin: 0, ymin: 0, xfmt: v => fmt(v), yfmt: v => fmt(v) }, o || {});
  const L = 44, R = 10, T = 10, B = 34, pw = o.W - L - R, ph = o.H - T - B;
  const sx = x => L + pw * (x - o.xmin) / ((o.xmax - o.xmin) || 1), sy = y => T + ph - ph * (y - o.ymin) / ((o.ymax - o.ymin) || 1);
  let g = '';
  const nt = o.ticks || 4;
  for (let t = 0; t <= nt; t++) {
    const y = o.ymin + (o.ymax - o.ymin) * t / nt, x = o.xmin + (o.xmax - o.xmin) * t / nt;
    g += `<line class="gridline" x1="${L}" x2="${L + pw}" y1="${sy(y)}" y2="${sy(y)}"/><text class="lbl" x="${L - 6}" y="${sy(y) + 4}" text-anchor="end">${esc(o.yfmt(y))}</text>`;
    g += `<text class="lbl" x="${sx(x)}" y="${T + ph + 16}" text-anchor="middle">${esc(o.xfmt(x))}</text>`;
  }
  (o.extra || []).forEach(e => { g += e(sx, sy); });
  series.forEach(s => {
    const d = s.points.map((p, i) => (i ? 'L' : 'M') + sx(p[0]).toFixed(1) + ',' + sy(p[1]).toFixed(1)).join('');
    if (s.area) g += `<path d="${d}L${sx(s.points[s.points.length - 1][0])},${sy(o.ymin)}L${sx(s.points[0][0])},${sy(o.ymin)}Z" class="m-soft"/>`;
    g += `<path d="${d}" fill="none" style="stroke:${s.color || 'var(--accent-fill)'};stroke-width:${s.width || 2};${s.dash ? 'stroke-dasharray:4 4;' : ''}" stroke-linejoin="round"/>`;
  });
  g += `<line class="baseline" x1="${L}" x2="${L + pw}" y1="${T + ph}" y2="${T + ph}"/>`;
  if (o.xlabel) g += `<text class="lbl" x="${L + pw / 2}" y="${o.H - 2}" text-anchor="middle">${esc(o.xlabel)}</text>`;
  if (o.ylabel) g += `<text class="lbl" transform="translate(11 ${T + ph / 2}) rotate(-90)" text-anchor="middle">${esc(o.ylabel)}</text>`;
  if (o.hover) g += o.hover(sx, sy, L, T, pw, ph);
  return svg(o.W, o.H, g, o.label);
}

function mixColor(v) {
  // diverging blue (+) / red (-) through a neutral midpoint, |v| in [0,1]
  const a = Math.min(1, Math.abs(v));
  const pole = v >= 0 ? 'var(--accent-fill)' : 'var(--neg)';
  return `color-mix(in oklab, ${pole} ${Math.round(a * 100)}%, var(--mid))`;
}
function heatmap(rowLabels, colLabels, M, o) {
  o = Object.assign({ cell: 34, labelW: 92, top: 70, scale: 1, fmt: v => v.toFixed(2), tip: null }, o || {});
  const W = o.labelW + colLabels.length * o.cell + 4, H = o.top + rowLabels.length * o.cell + 4;
  let g = '';
  colLabels.forEach((c, j) => {
    const x = o.labelW + j * o.cell + o.cell / 2;
    g += `<text class="lbl-ink2" transform="translate(${x + 4} ${o.top - 6}) rotate(-50)">${esc(c)}</text>`;
  });
  rowLabels.forEach((r, i) => {
    const y = o.top + i * o.cell;
    g += `<text class="lbl-ink2" x="${o.labelW - 6}" y="${y + o.cell / 2 + 4}" text-anchor="end">${esc(r)}</text>`;
    colLabels.forEach((c, j) => {
      const v = M[i][j];
      const x = o.labelW + j * o.cell;
      const tip = o.tip ? o.tip(i, j, v) : `${r} × ${c}\n${v == null ? '—' : o.fmt(v)}`;
      const fill = v == null ? 'var(--surface-2)' : mixColor(v / o.scale);
      g += `<g data-tip="${esc(tip)}"><rect x="${x + 1}" y="${y + 1}" width="${o.cell - 2}" height="${o.cell - 2}" rx="4" style="fill:${fill}"/>`;
      if (v != null && o.showText !== false) {
        const strong = Math.abs(v / o.scale) > 0.55;
        g += `<text x="${x + o.cell / 2}" y="${y + o.cell / 2 + 4}" text-anchor="middle" style="font-size:12px;fill:${strong ? '#fff' : 'var(--ink-2)'}">${esc(o.short ? o.short(v) : o.fmt(v))}</text>`;
      }
      g += `</g>`;
    });
  });
  return `<div class="table-wrap">${svg(W, H, g, o.label).replace('<svg ', `<svg style="min-width:${Math.min(W, 640)}px;max-width:${W * 1.25}px;margin:0 auto" `)}</div>${W > 360 ? '<p class="hint swipe">Swipe sideways to see every column →</p>' : ''}`;
}

function gauge(p, o) {
  o = o || {};
  const W = 200, H = 122, cx = 100, cy = 104, r = 80;
  const s = statusOf(p);
  const ang = a => [cx + r * Math.cos(Math.PI * (1 - a)), cy - r * Math.sin(Math.PI * (1 - a))];
  const arc = (a0, a1) => { const [x0, y0] = ang(a0), [x1, y1] = ang(a1); return `M${x0},${y0}A${r},${r} 0 0 1 ${x1},${y1}`; };
  const pv = Math.max(0.001, Math.min(0.999, p));
  const [tx0, ty0] = [cx + (r - 12) * Math.cos(Math.PI * 0.3), cy - (r - 12) * Math.sin(Math.PI * 0.3)];
  const [tx1, ty1] = [cx + (r + 12) * Math.cos(Math.PI * 0.3), cy - (r + 12) * Math.sin(Math.PI * 0.3)];
  let g = `<path d="${arc(0, 1)}" style="stroke:var(--grid);stroke-width:16;fill:none" stroke-linecap="round"/>`;
  g += `<path d="${arc(0, pv)}" style="stroke:var(--${s.cls});stroke-width:16;fill:none" stroke-linecap="round"/>`;
  g += `<line x1="${tx0}" y1="${ty0}" x2="${tx1}" y2="${ty1}" style="stroke:var(--ink);stroke-width:2"/>`;
  g += `<text x="${tx1 + 2}" y="${ty1 - 2}" class="lbl">70%</text>`;
  g += `<text x="${cx}" y="${cy - 18}" text-anchor="middle" style="font-size:34px;font-weight:800;fill:var(--ink)">${pctP(p)}</text>`;
  g += `<text x="${cx}" y="${cy + 2}" text-anchor="middle" style="font-size:12px;font-weight:700;fill:var(--ink-2)">${esc(s.icon + ' ' + s.label)}</text>`;
  return `<div class="gauge-wrap">${svg(W, H, g, 'Predicted placement probability ' + pct(p))}<div class="gauge-cap">${esc(o.caption || 'P(placed)')}</div></div>`;
}

/* ------------------------------------------------------------------ tabs */
function showTab(name) {
  $$('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  try { history.replaceState(null, '', '#' + name); } catch (e) { /* ignore */ }
  loadTab(name);
}
async function loadTab(name) {
  try {
    if (name === 'overview') await loadOverview();
    if (name === 'students') await loadStudents();
    if (name === 'risk') await loadRisk();
    if (name === 'personas') await loadPersonas();
    if (name === 'model') await loadModel();
    if (name === 'eda') await loadEda();
    if (name === 'data') await loadData();
  } catch (e) { toast('Could not load: ' + e.message); }
}

function fillSelect(sel, values, allLabel) {
  const cur = sel.value;
  sel.innerHTML = `<option value="ALL">${esc(allLabel)}</option>` + values.map(v => `<option>${esc(v)}</option>`).join('');
  if (values.includes(cur)) sel.value = cur;
}

/* ------------------------------------------------------------------ overview */
function kpi(label, value, sub, alert) {
  return `<div class="kpi${alert ? ' alert' : ''}"><div class="k-label">${esc(label)}</div><div class="k-value">${value}</div><div class="k-sub">${esc(sub || '')}</div></div>`;
}
async function loadOverview() {
  const dept = $('#ovDept').value, batch = $('#ovBatch').value;
  const d = await api('/api/dashboard' + qs({ dept, batch }));
  S.dash = d;
  const k = d.kpis;
  $('#kpis').innerHTML = [
    kpi('Students', fmt(k.students, 0), k.labelled < k.students ? `${k.students - k.labelled} pending outcome` : 'in view'),
    kpi('Placement rate', pct(k.placement_rate, 1), `${fmt(k.placed, 0)} of ${fmt(k.labelled, 0)} placed`),
    kpi('Avg package', k.avg_package == null ? '–' : fmt(k.avg_package, 1) + ' LPA', k.median_package == null ? '' : `median ${fmt(k.median_package, 1)} · max ${fmt(k.max_package, 1)}`),
    kpi('At risk now', fmt(k.at_risk, 0), 'P(placed) < 50%, not placed', k.at_risk > 0),
    kpi('Model ROC-AUC', fmt(k.test_auc, 3), `hold-out accuracy ${pct(k.test_accuracy, 1)}`),
  ].join('');
  $('#ovHint').textContent = S.info ? S.info.source : '';
  $('#ovDeptChart').innerHTML = hbars(d.dept_rates.map(r => ({
    label: r.dept, value: r.rate, text: pct(r.rate),
    tip: `${r.dept}\nPlaced ${r.placed} of ${r.n} (${pct(r.rate, 1)})\nAvg package ${r.avg_package == null ? '–' : fmt(r.avg_package, 2) + ' LPA'}`,
    color: dept !== 'ALL' && dept !== r.dept ? 'var(--axis)' : undefined
  })), { W: cw('#ovDeptChart'), max: 1, fmt: v => pct(v), labelW: 60, label: 'Placement rate by department' });
  const bandColor = ['var(--critical)', 'var(--serious)', 'var(--warn)', 'var(--good)', 'var(--good)'];
  $('#ovBands').innerHTML = columns(d.probability_bands.map((b, i) => ({ label: b.band, value: b.count, color: bandColor[i], tip: `${b.band}: ${b.count} students` })), { W: cw('#ovBands'), label: 'Students per probability band' });
  $('#ovGaps').innerHTML = d.top_gaps.length ? hbars(d.top_gaps.slice(0, 6).map(g => ({ label: SHORT[keyOfLabel(g.label)] || g.label, value: g.count, tip: `${g.label}: top gap for ${g.count} at-risk students` })), { W: cw('#ovGaps'), labelW: 96, fmt: v => fmt(v, 0), label: 'Most common top gap' }) : '<p class="hint">No at-risk students in this view.</p>';
  $('#ovPersonas').innerHTML = hbars(d.personas.map(p => ({ label: p.name, value: p.count, color: personaColor(p.id), tip: `${p.name}: ${p.count} students` })), { labelW: 'auto', fmt: v => fmt(v, 0), W: cw('#ovPersonas', 480), label: 'Persona sizes' });
  const risk = await api('/api/at-risk' + qs({ dept, batch, threshold: 0.5 }));
  const top = risk.students.slice(0, 6);
  $('#ovUrgent').innerHTML = top.length ? `<div class="urgent">${top.map(s => `
    <button class="urgent-item" type="button" data-sid="${esc(s.student_id)}">
      <div class="u-top"><span class="u-name">${esc(s.name)}</span>${probChip(s.probability)}</div>
      <div class="u-meta">${esc(s.student_id)} · ${esc(s.dept)} · batch ${esc(s.batch)}</div>
      <div class="u-fix">Fix first: <b>${esc(plural(s.top_gap))}</b></div>
    </button>`).join('')}</div>` : '<p class="hint">Nobody below 50% in this view.</p>';
}
function keyOfLabel(label) {
  if (!S.model) return null;
  const f = S.model.features.find(x => x.label === label);
  return f ? f.feature : null;
}

/* ------------------------------------------------------------------ students */
async function loadStudents(force, noAuto) {
  if (!S.loaded.students || force) {
    const r = await api('/api/students');
    S.students = r.students;
    S.loaded.students = true;
    fillSelect($('#stuDept'), S.info.departments, 'All depts');
  }
  renderStudentList();
  if (!S.current && !noAuto && S.students.length) await openStudent(pickDemoStudent());
}
function pickDemoStudent() {
  // A borderline student makes the best demo: show the one closest to 40%.
  let best = S.students[0];
  S.students.forEach(s => { if (s.status !== 'Placed' && Math.abs(s.probability - 0.4) < Math.abs(best.probability - 0.4)) best = s; });
  return best.student_id;
}
function renderStudentList() {
  const q = $('#stuSearch').value.trim().toLowerCase(), dept = $('#stuDept').value;
  const list = S.students.filter(s => (dept === 'ALL' || s.dept === dept) && (!q || s.student_id.toLowerCase().includes(q) || String(s.name).toLowerCase().includes(q)));
  $('#stuMeta').textContent = `${list.length} students · sorted by risk (lowest probability first)`;
  $('#stuList').innerHTML = list.slice(0, 400).map(s => `
    <button class="stu-item${S.current && S.current.student_id === s.student_id ? ' active' : ''}" type="button" data-sid="${esc(s.student_id)}" role="option">
      <span><span class="s-name">${esc(s.name)}</span><br><span class="s-meta">${esc(s.student_id)} · ${esc(s.dept)} · ${esc(s.status)}</span></span>
      ${probChip(s.probability).replace(/ · [^<]+/, '')}
    </button>`).join('') + (list.length > 400 ? `<p class="hint">Showing 400 of ${list.length} – refine the search.</p>` : '');
}
async function openStudent(sid) {
  if (!S.model) S.model = await api('/api/model');
  const d = await api('/api/student/' + encodeURIComponent(sid));
  S.current = d;
  S.sim = Object.fromEntries(S.model.features.map(f => [f.feature, Number(d[f.feature])]));
  renderStudentList();
  renderStudent(d);
}
function renderStudent(d) {
  const plan = d.plan;
  const persona = d.persona ? `<span class="chip"><i style="background:${personaColor(d.persona.id)}"></i>${esc(d.persona.name)}</span>` : '';
  const statusChip = `<span class="chip">${esc(d.status)}</span>`;
  const head = `
    <div class="card wide"><div class="stu-head">
      <div class="who"><h2>${esc(d.name)}</h2>
        <div class="meta">${esc(d.student_id)} · ${esc(d.dept)} · batch ${esc(d.batch)} · CGPA ${fmt(d.cgpa)} · ${plural(fmt(d.backlogs, 0) + ' backlog(s)')}</div>
        <div class="tags">${statusChip}${persona}</div>
        <div class="stat-row" style="margin-top:12px">
          <div><div class="v">${d.expected_package_lpa == null ? '–' : fmt(d.expected_package_lpa, 1) + ' LPA'}</div><div class="l">expected package if placed</div></div>
          <div><div class="v">${pct(d.baseline_probability)}</div><div class="l">average student</div></div>
          <div><div class="v">${plan.already_above ? '0 wks' : fmt(plan.total_effort_weeks, 1) + ' wks'}</div><div class="l">effort to reach ${pct(plan.target)}</div></div>
        </div>
      </div>
      ${gauge(d.probability, { caption: 'predicted P(placed) today' })}
    </div></div>`;
  const contrib = `
    <div class="card"><div class="card-h"><h3>Why this prediction</h3><span class="sub">feature contribution = coefficient × standardised value (log-odds vs. an average student)</span></div>
      <div class="chart" id="contribChart"></div></div>`;
  $('#stuDetail').innerHTML = head + contrib + `<div class="card" id="planCard">${planHtml(plan, false)}</div>` + simHtml(d);
  drawContrib(d);
  bindSim();
}
// drawn after insertion so it can use the card's real width (and redrawn on resize)
function drawContrib(d) {
  const narrow = isNarrow('#contribChart');
  $('#contribChart').innerHTML = diverging(d.contributions.map(c => ({
    label: narrow ? (SHORT[c.feature] || c.label) : c.label, value: c.contribution,
    tip: `${c.label} = ${fmt(c.value)}\n${c.z >= 0 ? '+' : ''}${fmt(c.z, 2)} SD vs cohort\ncontribution ${c.contribution >= 0 ? '+' : ''}${fmt(c.contribution, 3)} log-odds`
  })), { W: cw('#contribChart'), labelW: narrow ? 84 : 150, label: 'Feature contributions' });
}
function planHtml(plan, fromSim) {
  let h = `<div class="card-h"><h3>What to fix next</h3><span class="sub">${fromSim ? 'from the simulator values' : 'minimum-effort plan'} → ${pct(plan.target)}</span></div>`;
  if (plan.already_above) {
    h += `<p>Already at <b>${pct(plan.p_before)}</b>, above the ${pct(plan.target)} target. Best next boosters (gain per week of effort):</p>`;
    h += `<div class="plan">${(plan.boosters || []).map((a, i) => stepHtml(a, i)).join('')}</div>`;
    return h;
  }
  if (!plan.actions.length) return h + '<p class="hint">No actionable lever raises the probability under the current model.</p>';
  h += `<div class="plan">${plan.actions.map((a, i) => stepHtml(a, i)).join('')}</div>`;
  h += `<div class="plan-sum"><span>${pct(plan.p_before)} → <b>${pct(plan.p_after)}</b> ${plan.reachable ? '' : '<span class="flag">(target not reachable within realistic limits – best possible shown)</span>'}</span><span>total ≈ <b>${fmt(plan.total_effort_weeks, 1)} weeks</b> of focused effort</span></div>`;
  if (plan.single_lever_options && plan.single_lever_options.length) {
    h += `<div class="subhead">Or one lever alone</div><ul class="alt-list">${plan.single_lever_options.slice(0, 4).map(a => `<li><span>${esc(plural(a.text))}</span><span>${fmt(a.effort_weeks, 1)} wks → ${pct(a.p_after)}</span></li>`).join('')}</ul>`;
  }
  h += `<div class="row-actions"><button class="btn btn-small" type="button" id="applyPlan" style="margin-left:0">Try this plan in the simulator ↓</button></div>`;
  return h;
}
function stepHtml(a, i) {
  const from = a.feature === 'cgpa' ? fmt(a.from, 2) : fmt(a.from, 1), to = a.feature === 'cgpa' ? fmt(a.to, 2) : fmt(a.to, 1);
  return `<div class="plan-step" data-tip="${esc(a.label + ': ' + from + ' → ' + to + '\n+' + fmt(a.logit_gain, 2) + ' log-odds\n≈ ' + fmt(a.effort_weeks, 1) + ' weeks (assumed effort)')}">
    <span class="n">${i + 1}</span><span><span class="t">${esc(plural(a.text))}</span><br><span class="d">${esc(a.label)} ${from} → ${to} · ≈ ${fmt(a.effort_weeks, 1)} wks</span></span>
    <span class="p">${pct(a.p_after)}<small>after step</small></span></div>`;
}
function simHtml(d) {
  const sl = S.model.features.map(f => {
    const [lo, hi0, step] = SIM[f.feature];
    const v = Number(d[f.feature]);
    const hi = Math.max(hi0, v);
    return `<div class="slider"><label for="sim-${f.feature}">${esc(f.label)} <b id="simv-${f.feature}">${fmt(v)}</b></label>
      <input type="range" id="sim-${f.feature}" data-f="${f.feature}" min="${Math.min(lo, v)}" max="${hi}" step="${step}" value="${v}"></div>`;
  }).join('');
  return `<div class="card wide"><div class="card-h"><h3>What-if simulator</h3><span class="sub">drag any slider – probability is recomputed live from the model's coefficients in your browser</span></div>
    <div class="sim"><div class="sliders">${sl}</div>
    <div class="sim-side"><div id="simGauge"></div><div id="simDelta" class="delta"></div><div id="simPkg" class="hint"></div>
    <div class="btns"><button class="btn btn-small" style="margin-left:0" type="button" id="simReset">Reset</button><button class="btn btn-small btn-primary" style="margin-left:0" type="button" id="simPlan">Plan from here</button></div></div></div></div>`;
}
function simPredict(vals) {
  const m = S.model;
  let z = m.intercept;
  m.features.forEach((f, j) => { z += m.coefficients[j].weight * (vals[f.feature] - m.scaler.mean[j]) / m.scaler.std[j]; });
  let pkg = null;
  if (m.package) {
    pkg = m.package.intercept;
    m.features.forEach((f, j) => { pkg += m.package.coefficients[j].weight * (vals[f.feature] - m.package.scaler.mean[j]) / m.package.scaler.std[j]; });
    pkg = Math.max(0, pkg);
  }
  return { p: sigmoid(z), pkg };
}
function updateSim() {
  const d = S.current;
  const r = simPredict(S.sim);
  $('#simGauge').innerHTML = gauge(r.p, { caption: 'simulated P(placed)' });
  const delta = r.p - d.probability;
  const el = $('#simDelta');
  el.className = 'delta ' + (delta > 0.0005 ? 'up' : delta < -0.0005 ? 'down' : '');
  el.textContent = Math.abs(delta) < 0.0005 ? 'no change yet' : `${delta > 0 ? '▲ +' : '▼ '}${(100 * delta).toFixed(1)} pts vs today`;
  $('#simPkg').textContent = r.pkg == null ? '' : `expected package ≈ ${fmt(r.pkg, 1)} LPA`;
  S.model.features.forEach(f => {
    const b = $('#simv-' + f.feature);
    b.textContent = fmt(S.sim[f.feature]);
    b.classList.toggle('changed', Math.abs(S.sim[f.feature] - Number(d[f.feature])) > 1e-9);
  });
}
function setSim(vals) {
  Object.entries(vals).forEach(([k, v]) => {
    S.sim[k] = v;
    const inp = $('#sim-' + k);
    if (inp) { if (v > Number(inp.max)) inp.max = v; inp.value = v; }
  });
  updateSim();
}
function bindSim() {
  $$('#stuDetail input[type=range]').forEach(inp => inp.addEventListener('input', () => { S.sim[inp.dataset.f] = Number(inp.value); updateSim(); }));
  $('#simReset').addEventListener('click', () => setSim(Object.fromEntries(S.model.features.map(f => [f.feature, Number(S.current[f.feature])]))));
  $('#simPlan').addEventListener('click', async () => {
    try {
      const res = await api('/api/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ features: S.sim }) });
      $('#planCard').innerHTML = planHtml(res.plan, true);
      bindApply(res.plan);
      toast('Plan recomputed on the server for the simulated profile.');
    } catch (e) { toast('Plan failed: ' + e.message); }
  });
  bindApply(S.current.plan);
  updateSim();
}
function bindApply(plan) {
  const b = $('#applyPlan');
  if (!b) return;
  b.addEventListener('click', () => {
    const vals = {};
    plan.actions.forEach(a => { vals[a.feature] = a.to; });
    setSim(vals);
    $('#simGauge').scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
}

/* ------------------------------------------------------------------ at risk */
async function loadRisk() {
  const dept = $('#riskDept').value, batch = $('#riskBatch').value, threshold = $('#riskThr').value;
  const include_placed = $('#riskPlaced').checked ? 1 : null;
  $('#riskThrVal').textContent = pct(Number(threshold));
  const q = qs({ dept, batch, threshold, include_placed });
  $('#riskCsv').href = '/api/at-risk.csv' + q;
  const r = await api('/api/at-risk' + q);
  $('#riskTitle').textContent = `${r.count} at-risk student${r.count === 1 ? '' : 's'}`;
  const rows = r.students.slice(0, 300);
  $('#riskTable').innerHTML = `<thead><tr><th>#</th><th>Student</th><th>Dept</th><th>Batch</th><th>Status</th><th>P(placed)</th><th>Top gap (fix first)</th><th class="num">Plan effort</th><th class="num">P after plan</th></tr></thead><tbody>` +
    rows.map((s, i) => `<tr class="click" data-sid="${esc(s.student_id)}"><td>${i + 1}</td><td><b>${esc(s.name)}</b><br><span class="hint">${esc(s.student_id)}</span></td><td>${esc(s.dept)}</td><td>${esc(s.batch)}</td><td class="nowrap">${esc(s.status)}</td>
      <td>${probChip(s.probability)}</td><td>${esc(plural(s.top_gap))}</td><td class="num">${fmt(s.plan_effort_weeks, 1)} wks</td><td class="num">${pct(s.plan_p_after)}${s.plan_reachable ? '' : ' <span class="flag" title="target not reachable with realistic changes">*</span>'}</td></tr>`).join('') +
    `</tbody>` + (r.count > 300 ? `<caption class="hint" style="caption-side:bottom;text-align:left;padding-top:6px">Showing 300 of ${r.count}; export the CSV for all.</caption>` : '');
}

/* ------------------------------------------------------------------ personas */
async function loadPersonas() {
  const k = $('#kSel').value;
  const c = S.clusters[k] || await api('/api/clusters?k=' + k);
  S.clusters[k] = c;
  $('#kHint').textContent = `k-means++ on ${c.features.length} standardised features · ${c.iterations} Lloyd iterations · inertia ${fmt(c.inertia, 0)}`;
  $('#personaCards').innerHTML = c.clusters.map(g => {
    const zs = Object.entries(g.z).filter(z => z[0] !== 'backlogs').sort((a, b) => b[1] - a[1]);
    const strong = zs.slice(0, 2).filter(z => z[1] > 0.15).map(z => SHORT[z[0]]);
    const weak = zs.slice(-2).reverse().filter(z => z[1] < -0.15).map(z => SHORT[z[0]]);
    if (g.z.backlogs > 0.3) weak.unshift('many backlogs');
    const mix = Object.entries(g.dept_mix).filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 3).map(e => `${e[0]} ${e[1]}`).join(' · ');
    return `<div class="card persona" style="--c:${personaColor(g.id)}"><h4><i></i>${esc(g.name)}</h4><div class="desc">${esc(g.description)}</div>
      <div class="nums"><div><div class="v">${g.size}</div><div class="l">students</div></div><div><div class="v">${pct(g.placement_rate)}</div><div class="l">placed</div></div><div><div class="v">${pct(g.mean_probability)}</div><div class="l">mean P(placed)</div></div></div>
      <div class="mix">Strong: ${esc(strong.join(', ') || '–')} · Weak: ${esc(weak.join(', ') || '–')}</div>
      <div class="mix">${esc(mix)}</div></div>`;
  }).join('');
  const M = c.clusters.map(g => c.features.map(f => g.z[f]));
  $('#personaHeat').innerHTML = heatmap(c.clusters.map(g => g.name), c.features.map(f => SHORT[f]), M, {
    labelW: 220, cell: 46, top: 64, scale: 1.5, fmt: v => (v >= 0 ? '+' : '') + v.toFixed(2), short: v => (v >= 0 ? '+' : '') + v.toFixed(1),
    tip: (i, j, v) => `${c.clusters[i].name}\n${c.labels[j]}: mean ${fmt(c.clusters[i].means[c.features[j]], 2)}\n${v >= 0 ? '+' : ''}${v.toFixed(2)} SD vs cohort`,
    label: 'Persona profile heatmap'
  });
}

/* ------------------------------------------------------------------ model */
async function loadModel() {
  const m = S.model = await api('/api/model');
  const t = m.test;
  $('#modelKpis').innerHTML = [
    kpi('Accuracy', pct(t.accuracy, 1), `majority baseline ${pct(t.majority_baseline_accuracy, 1)}`),
    kpi('Precision', pct(t.precision, 1), 'of predicted placed'),
    kpi('Recall', pct(t.recall, 1), 'of actually placed'),
    kpi('F1 score', fmt(t.f1, 3), 'harmonic mean P/R'),
    kpi('ROC-AUC', fmt(t.roc_auc, 3), `${m.hyperparameters.cv_folds}-fold CV ${fmt(t.cv_auc, 3)}`),
    m.package ? kpi('Package R²', fmt(m.package.r2, 3), `MAE ${fmt(m.package.mae, 2)} LPA (baseline ${fmt(m.package.baseline_mae, 2)})`) : kpi('Package model', '–', 'too few placed rows'),
  ].join('');
  $('#rocSub').textContent = `hold-out test set · n = ${t.n} · AUC ${fmt(t.roc_auc, 3)}`;
  const pts = m.roc.map(p => [p.fpr, p.tpr]);
  $('#rocChart').innerHTML = lineChart([{ points: pts, area: true }], {
    xmax: 1, ymax: 1, xfmt: v => v.toFixed(2), yfmt: v => v.toFixed(2), xlabel: 'False positive rate', ylabel: 'True positive rate', H: 280, W: cw('#rocChart'),
    extra: [(sx, sy) => `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" style="stroke:var(--axis);stroke-dasharray:4 4"/><text class="lbl" x="${sx(0.62)}" y="${sy(0.55)}">random (0.5)</text>`],
    hover: (sx, sy) => m.roc.filter((p, i) => i % Math.max(1, Math.floor(m.roc.length / 40)) === 0).map(p => `<circle cx="${sx(p.fpr)}" cy="${sy(p.tpr)}" r="7" fill="transparent" data-tip="threshold ${p.threshold.toFixed(2)}\nTPR ${p.tpr.toFixed(2)} · FPR ${p.fpr.toFixed(2)}"/>`).join(''),
    label: 'ROC curve'
  });
  const c = m.confusion;
  $('#confusion').innerHTML = `<div class="cm"><div></div><div class="h">Predicted placed</div><div class="h">Predicted not placed</div>
    <div class="h">Actually placed</div><div class="cell ok"><b>${c.tp}</b><span>true positive</span></div><div class="cell bad"><b>${c.fn}</b><span>false negative</span></div>
    <div class="h">Actually not placed</div><div class="cell bad"><b>${c.fp}</b><span>false positive</span></div><div class="cell ok"><b>${c.tn}</b><span>true negative</span></div></div>
    <p class="notes">A false negative is a student we would wrongly flag as at risk (cheap: extra coaching). A false positive is a student we would miss – the costlier error, so the at-risk list can use a higher threshold.</p>`;
  const coefs = m.coefficients.slice().sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight));
  $('#coefChart').innerHTML = diverging(coefs.map(cf => ({ label: isNarrow('#coefChart') ? (SHORT[cf.feature] || cf.label) : cf.label, value: cf.weight, tip: `${cf.label}\nweight ${cf.weight.toFixed(3)} per SD\nodds ×${Math.exp(cf.weight).toFixed(2)} per +1 SD` })), { W: cw('#coefChart'), labelW: isNarrow('#coefChart') ? 84 : 150, label: 'Coefficients' });
  const lh = m.loss_history;
  const it = lh.map((v, i) => [i === 0 ? 1 : i * 25, v]);
  $('#lossChart').innerHTML = lineChart([{ points: it }], { xmin: 0, xmax: it[it.length - 1][0], ymin: Math.floor(Math.min(...lh) * 10) / 10, ymax: Math.ceil(lh[0] * 10) / 10, xfmt: v => fmt(v, 0), yfmt: v => v.toFixed(2), xlabel: `iteration (converged after ${t.iterations})`, ylabel: 'log-loss + L2', W: cw('#lossChart'), label: 'Training loss' });
  if (m.package) {
    const P = m.package.points, ax = niceAxis(Math.max(...P.map(p => Math.max(p.actual, p.pred)))), mx = ax.top;
    $('#pkgSub').textContent = `placed students, test set n = ${m.package.n_test} · R² ${fmt(m.package.r2, 3)} · MAE ${fmt(m.package.mae, 2)} LPA`;
    $('#pkgChart').innerHTML = lineChart([], {
      xmin: 0, xmax: mx, ymin: 0, ymax: mx, ticks: ax.n, xfmt: v => fmt(v, 1), yfmt: v => fmt(v, 1), xlabel: 'actual package (LPA)', ylabel: 'predicted (LPA)', W: cw('#pkgChart'),
      extra: [(sx, sy) => `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(mx)}" y2="${sy(mx)}" style="stroke:var(--axis);stroke-dasharray:4 4"/>` +
        P.map(p => `<circle cx="${sx(p.actual)}" cy="${sy(Math.min(mx, Math.max(0, p.pred)))}" r="4" style="fill:var(--accent-fill);fill-opacity:.7;stroke:var(--surface);stroke-width:1.5" data-tip="actual ${fmt(p.actual, 2)} LPA\npredicted ${fmt(p.pred, 2)} LPA"/>`).join('')],
      label: 'Predicted vs actual package'
    });
  } else $('#pkgChart').innerHTML = '<p class="hint">Not enough placed students with a package to fit.</p>';
  const h = m.hyperparameters;
  $('#modelNotes').innerHTML = `<ul>
    <li><b>Logistic regression</b> on ${m.features.length} standardised features, full-batch gradient descent (lr ${h.lr}, L2 λ = ${h.l2}); ${t.converged ? 'converged' : 'stopped'} after ${t.iterations} iterations.</li>
    <li>Stratified split: ${t.n_train} train / ${t.n_test} test (${pct(h.test_fraction)} held out). Train accuracy ${pct(t.train_accuracy, 1)} vs test ${pct(t.accuracy, 1)} – no overfitting.</li>
    <li>${h.cv_folds}-fold cross-validation: AUC ${fmt(t.cv_auc, 3)}, accuracy ${pct(t.cv_accuracy, 1)}.</li>
    <li>The deployed model is refit on all labelled rows; every number here is computed live by the server.</li>
    <li><b>Package</b>: ridge linear regression (normal equations, Gaussian elimination) on placed students only.</li>
    <li>Department is <b>not</b> a model input – the fairness check below audits the result by department.</li></ul>`;
  renderFairness(m.fairness);
}
function renderFairness(f) {
  $('#fairSub').textContent = `${f.method} · threshold ${f.threshold} · flagged when a gap exceeds ${pct(f.flag_threshold)} points`;
  const o = f.overall;
  $('#fairTable').innerHTML = `<thead><tr><th>Department</th><th class="num">n</th><th class="num">Actual placed</th><th class="num">Mean P(placed)</th><th class="num">Accuracy</th><th class="num">False positive rate</th><th class="num">False negative rate</th><th class="num">Calibration gap</th><th>Flag</th></tr></thead><tbody>` +
    f.groups.map(g => `<tr><td><b>${esc(g.dept)}</b></td><td class="num">${g.n}</td><td class="num">${pct(g.actual_rate, 1)}</td><td class="num">${pct(g.mean_probability, 1)}</td><td class="num">${pct(g.accuracy, 1)}</td><td class="num">${pct(g.fpr, 1)}</td><td class="num">${pct(g.fnr, 1)}</td><td class="num">${g.calibration_gap >= 0 ? '+' : ''}${(100 * g.calibration_gap).toFixed(1)} pts</td><td>${g.flags.length ? `<span class="flag">! ${esc(g.flags.join('; '))}</span>` : g.watch && g.watch.length ? `<span class="watch">~ watch: ${esc(g.watch.join('; '))}</span>` : '<span class="hint">✓ within band</span>'}</td></tr>`).join('') +
    `<tr><td><b>Overall</b></td><td class="num">${o.n}</td><td></td><td></td><td class="num">${pct(o.accuracy, 1)}</td><td class="num">${pct(o.fpr, 1)}</td><td class="num">${pct(o.fnr, 1)}</td><td></td><td></td></tr></tbody>`;
  let note = f.notes.length
    ? `<p><span class="flag">Flagged</span>: ${f.notes.map(esc).join(' · ')}. Small groups make error rates noisy (±10 pts is common at n≈80), so treat a flag as "review", not proof of bias.</p>`
    : `<p>✓ No department's false-positive or false-negative rate differs from the overall rate by more than ${pct(f.flag_threshold)} points.</p>`;
  if (f.watch && f.watch.length) note += `<p><span class="watch">~ Watch</span>: ${f.watch.map(esc).join(' · ')}. Department is not a model input, so a gap like this means placement in that department depends on something the 12 features do not capture (e.g. fewer recruiters for the branch). The coach's probabilities there should be read as slightly optimistic.</p>`;
  note += `<p class="hint">Positive calibration gap = the model is more optimistic than reality for that department. Computed on ${esc(f.method)}, so every student is scored by a model that never saw them.</p>`;
  $('#fairNotes').innerHTML = note;
}

/* ------------------------------------------------------------------ EDA */
async function loadEda() {
  if (!S.model) S.model = await api('/api/model');
  const e = S.eda = S.eda || await api('/api/eda');
  $('#driverTable').innerHTML = `<thead><tr><th>Rank</th><th>Feature</th><th>Model weight (per SD)</th><th class="num">Odds ×</th><th class="num">Correlation r</th><th class="num">Placed (bottom 25%)</th><th class="num">Placed (top 25%)</th></tr></thead><tbody>` +
    e.drivers.map((d, i) => {
      const w = Math.min(100, Math.abs(d.coefficient) / Math.abs(e.drivers[0].coefficient) * 100);
      return `<tr><td>${i + 1}</td><td><b>${esc(d.label)}</b></td><td><div class="bar-cell"><span style="width:44px;text-align:right">${d.coefficient >= 0 ? '+' : ''}${d.coefficient.toFixed(2)}</span><span class="track"><span class="fill" style="width:${w}%;background:${d.coefficient >= 0 ? 'var(--accent-fill)' : 'var(--neg)'};display:block"></span></span></div></td>
      <td class="num">${d.odds_ratio_per_sd.toFixed(2)}</td><td class="num">${d.correlation >= 0 ? '+' : ''}${d.correlation.toFixed(2)}</td><td class="num">${pct(d.rate_bottom_quartile)}</td><td class="num">${pct(d.rate_top_quartile)}</td></tr>`;
    }).join('') + '</tbody>';
  $('#edaDept').innerHTML = hbars(e.dept_rates.map(r => ({ label: r.dept, value: r.rate, text: pct(r.rate), tip: `${r.dept}: ${r.placed}/${r.n} placed\navg package ${r.avg_package == null ? '–' : fmt(r.avg_package, 2) + ' LPA'}` })), { W: cw('#edaDept'), max: 1, fmt: v => pct(v), labelW: 60 });
  const names = e.correlation.names;
  $('#corrChart').innerHTML = heatmap(names.map(n => SHORT[n] || n), names.map(n => SHORT[n] || n), e.correlation.matrix, {
    cell: 44, labelW: 90, top: 70, scale: 1, short: v => v.toFixed(2),
    tip: (i, j, v) => `${e.correlation.labels[i]} × ${e.correlation.labels[j]}\nr = ${v == null ? '1 (self)' : v.toFixed(3)}`, label: 'Correlation heatmap'
  });
  $('#histGrid').innerHTML = e.columns.map(c => `<div><h5>${esc(c.label)} <span class="hint">mean ${fmt(c.mean, 1)} · median ${fmt(c.median, 1)}</span></h5>${histogram(c)}</div>`).join('') +
    (e.package ? `<div><h5>Package (LPA, placed) <span class="hint">mean ${fmt(e.package.mean, 1)} · median ${fmt(e.package.median, 1)}</span></h5>${histogram(e.package)}</div>` : '');
  $('#summaryTable').innerHTML = `<thead><tr><th>Column</th>${['count', 'mean', 'std', 'min', 'q1', 'median', 'q3', 'max'].map(h => `<th class="num">${h}</th>`).join('')}</tr></thead><tbody>` +
    e.columns.map(c => {
      // consistent decimals per row: whole-number columns stay whole, mean/std always 2 dp
      const q = ['min', 'q1', 'median', 'q3', 'max'], whole = q.every(k => c[k] == null || Number.isInteger(c[k]));
      const f = k => (c[k] == null ? '–' : k === 'count' ? fmt(c[k], 0) : (k === 'mean' || k === 'std' || !whole) ? Number(c[k]).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : fmt(c[k], 0));
      return `<tr><td><b>${esc(c.label)}</b></td>${['count', 'mean', 'std', 'min', 'q1', 'median', 'q3', 'max'].map(k => `<td class="num">${f(k)}</td>`).join('')}</tr>`;
    }).join('') + '</tbody>';
}
function histogram(c) {
  const bins = c.histogram, W = 240, H = 92, base = H - 16, max = Math.max(...bins.map(b => b.count)), bw = (W - 4) / bins.length;
  let g = '';
  bins.forEach((b, i) => {
    const len = (base - 6) * b.count / max;
    const range = b.lo === b.hi ? fmt(b.lo, 2) : `${fmt(b.lo, 1)} – ${fmt(b.hi, 1)}`;
    g += `<g data-tip="${esc(range + ': ' + b.count + ' students')}"><rect class="hit" x="${2 + i * bw}" y="0" width="${bw}" height="${base}"/><path d="${barV(2 + i * bw + 1, base, Math.max(1, bw - 2), len, 3)}" class="m-accent"/></g>`;
  });
  g += `<line class="baseline" x1="0" x2="${W}" y1="${base}" y2="${base}"/><text class="lbl" x="2" y="${H - 2}">${fmt(c.min, 1)}</text><text class="lbl" x="${W - 2}" y="${H - 2}" text-anchor="end">${fmt(c.max, 1)}</text>`;
  return svg(W, H, g, c.label + ' histogram');
}

/* ------------------------------------------------------------------ data */
async function loadData() {
  const info = S.info = await api('/api/dataset?limit=20');
  $('#previewSub').textContent = `${info.source} · ${info.rows} rows (${info.labelled_rows} labelled, ${info.pending_rows} pending) · lowest probability first`;
  const cols = ['student_id', 'name', 'dept', 'batch', 'cgpa', 'backlogs', 'internships', 'projects', 'coding_problems', 'aptitude_score', 'mock_interview_score', 'status', 'package_lpa', 'probability'];
  $('#previewTable').innerHTML = `<thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>` +
    info.sample.map(r => `<tr>${cols.map(c => `<td>${previewCell(r, c)}</td>`).join('')}</tr>`).join('') + '</tbody>';
  $('#schema').innerHTML = `<p>Required: ${info.required_columns.map(c => `<code>${esc(c)}</code>`).join(' ')}</p>
    <p>Optional: <code>student_id</code> <code>name</code> <code>batch</code> <code>package_lpa</code></p>
    <ul><li><code>dept</code> one of ${S.info.departments.length ? 'CSE, AI&amp;DS, CSD, IT, ECE, MECH' : ''} (aliases like AIDS, MECHANICAL accepted)</li>
    <li><code>placed</code>: yes/no, 1/0, true/false – or blank for students whose outcome is still pending (scored, not trained on)</li>
    <li>Scores are 0–100, CGPA 0–10; counts must be whole numbers</li>
    <li>Bad rows are skipped and listed with the line number and the reason; at least 40 valid labelled rows with both outcomes are needed to retrain</li></ul>`;
  if (info.upload_report) renderReport({ ok: true, message: info.source, report: info.upload_report });
}
function previewCell(r, c) {
  const v = r[c];
  if (c === 'probability') return v != null && v < 0.0005 ? '&lt;0.1%' : pct(v, 1);
  if (v == null || v === '') return '–';
  if (c === 'cgpa') return Number(v).toFixed(2);
  // a package only exists for placed students; 0 for the others reads like a real salary
  if (c === 'package_lpa') return Number(v) > 0 ? Number(v).toFixed(1) : '–';
  return esc(v);
}
function renderReport(res) {
  const r = res.report || {};
  const errs = (r.errors || []).map(e => `<tr><td>${e.line}</td><td>${esc(e.student_id)}</td><td>${esc(e.problems.join('; '))}</td></tr>`).join('');
  $('#uploadReport').innerHTML = `<div class="report ${res.ok ? 'ok' : 'fail'}"><b>${res.ok ? '✓' : '✗'} ${esc(res.message)}</b>
    <div>${r.total_rows || 0} rows read · ${r.valid_rows || 0} valid · ${r.invalid_rows || 0} rejected${r.missing_columns && r.missing_columns.length ? ' · missing: ' + r.missing_columns.map(esc).join(', ') : ''}${r.ignored_columns && r.ignored_columns.length ? ' · ignored columns: ' + r.ignored_columns.map(esc).join(', ') : ''}</div>
    ${(r.warnings || []).map(w => `<div class="hint">${esc(w)}</div>`).join('')}
    ${errs ? `<div class="errs table-wrap"><table class="tbl"><thead><tr><th>Line</th><th>Student</th><th>Problem</th></tr></thead><tbody>${errs}</tbody></table></div>` : ''}</div>`;
}
async function uploadText(text, filename) {
  try {
    const res = await api('/api/upload?filename=' + encodeURIComponent(filename), { method: 'POST', headers: { 'Content-Type': 'text/csv' }, body: text });
    renderReport(res);
    await afterDatasetChange(res.message);
  } catch (e) {
    renderReport(e.body || { ok: false, message: e.message, report: {} });
    toast('Upload rejected: ' + e.message, 4000);
  }
}
async function afterDatasetChange(msg) {
  S.info = await api('/api/dataset?limit=0');
  S.model = null; S.eda = null; S.clusters = {}; S.loaded = {}; S.current = null;
  setSource();
  fillFilters();
  toast(msg || 'Dataset updated');
  // model first: the overview's short feature labels (keyOfLabel) need it
  S.model = await api('/api/model');
  const active = ($('.tabs button.active') || {}).dataset;
  await loadTab(active ? active.tab : 'overview');
}
function setSource() {
  const i = S.info;
  $('#sourcePill').textContent = `${i.source.replace(/^Synthetic demo cohort/, 'Demo cohort')} · ${i.rows} students`;
  $('#sourcePill').title = i.source;
}
function fillFilters() {
  ['#ovDept', '#riskDept'].forEach(s => fillSelect($(s), S.info.departments, 'All departments'));
  ['#ovBatch', '#riskBatch'].forEach(s => fillSelect($(s), S.info.batches, 'All batches'));
}

/* ------------------------------------------------------------------ theme */
function applyTheme(t) {
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
  $('#themeBtn').textContent = t === 'dark' ? 'Dark' : t === 'light' ? 'Light' : 'Auto theme';
}

/* ------------------------------------------------------------------ boot */
async function loadDemo(btn) {
  const b = btn || $('#demoBtn');
  b.disabled = true; const old = b.textContent; b.textContent = 'Training…';
  try {
    const r = await api('/api/demo', { method: 'POST' });
    $('#uploadReport').innerHTML = '';
    await afterDatasetChange(r.message);
  } catch (e) { toast('Demo load failed: ' + e.message); }
  b.disabled = false; b.textContent = old;
}
function bind() {
  $('#tabs').addEventListener('click', e => { const b = e.target.closest('button[data-tab]'); if (b) showTab(b.dataset.tab); });
  document.addEventListener('click', e => {
    const g = e.target.closest('[data-goto]'); if (g) { showTab(g.dataset.goto); return; }
    const s = e.target.closest('[data-sid]');
    if (s) {
      if (!$('#tab-students').classList.contains('active')) showTabNoLoad('students');
      loadStudents(false, true).then(() => openStudent(s.dataset.sid)).catch(err => toast(err.message));
    }
  });
  $('#demoBtn').addEventListener('click', () => loadDemo($('#demoBtn')));
  $('#demoBtn2').addEventListener('click', () => loadDemo($('#demoBtn2')));
  ['#ovDept', '#ovBatch'].forEach(s => $(s).addEventListener('change', () => loadOverview().catch(e => toast(e.message))));
  ['#riskDept', '#riskBatch', '#riskPlaced'].forEach(s => $(s).addEventListener('change', () => loadRisk().catch(e => toast(e.message))));
  let rt; $('#riskThr').addEventListener('input', () => { $('#riskThrVal').textContent = pct(Number($('#riskThr').value)); clearTimeout(rt); rt = setTimeout(() => loadRisk().catch(e => toast(e.message)), 150); });
  $('#kSel').addEventListener('change', () => loadPersonas().catch(e => toast(e.message)));
  $('#stuSearch').addEventListener('input', renderStudentList);
  $('#stuDept').addEventListener('change', renderStudentList);
  const fi = $('#fileInput'), drop = $('#drop');
  fi.addEventListener('change', () => { const f = fi.files[0]; if (f) readFile(f); fi.value = ''; });
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => { const f = e.dataTransfer.files[0]; if (f) readFile(f); });
  $('#errDemoBtn').addEventListener('click', async () => {
    const r = await fetch('samples/students_with_errors.csv');
    uploadText(await r.text(), 'students_with_errors.csv');
  });
  let theme = 'auto';
  try { theme = localStorage.getItem('placeiq-theme') || 'auto'; } catch (e) { /* storage blocked */ }
  applyTheme(theme);
  $('#themeBtn').addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'auto';
    const next = cur === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark') : cur === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    try { localStorage.setItem('placeiq-theme', next); } catch (e) { /* ignore */ }
  });
}
function showTabNoLoad(name) {
  $$('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  try { history.replaceState(null, '', '#' + name); } catch (e) { /* ignore */ }
}
function readFile(f) {
  if (f.size > 4 * 1024 * 1024) { toast('File is larger than 4 MB'); return; }
  const rd = new FileReader();
  rd.onload = () => uploadText(String(rd.result), f.name);
  rd.onerror = () => toast('Could not read the file');
  rd.readAsText(f);
}
async function boot() {
  bind();
  let lastW = innerWidth, rz;
  addEventListener('resize', () => {
    clearTimeout(rz);
    rz = setTimeout(() => {
      if (Math.abs(innerWidth - lastW) < 40) return;
      lastW = innerWidth;
      const a = ($('.tabs button.active') || {}).dataset;
      if (a) loadTab(a.tab);
      if (a && a.tab === 'students' && S.current && $('#contribChart')) drawContrib(S.current);
    }, 250);
  });
  try {
    S.info = await api('/api/dataset?limit=0');
    setSource();
    fillFilters();
    S.model = await api('/api/model');
    const tab = (location.hash || '#overview').slice(1);
    showTab($$('.tabs button').some(b => b.dataset.tab === tab) ? tab : 'overview');
  } catch (e) { toast('Server not reachable: ' + e.message, 6000); }
}
boot();
