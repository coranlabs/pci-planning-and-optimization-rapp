// Copyright 2025-2026 coRAN LABS Private Limited
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

const { useState, useMemo, useEffect, useRef } = React;


const Icon = ({ name, size = 16, ...rest }) => {
  const paths = {
    grid:      <><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></>,
    map:       <><path d="M9 3 3 6v15l6-3 6 3 6-3V3l-6 3-6-3z"/><path d="M9 3v15M15 6v15"/></>,
    layers:    <><path d="M12 2 2 7l10 5 10-5-10-5z"/><path d="M2 12l10 5 10-5"/><path d="M2 17l10 5 10-5"/></>,
    alert:     <><path d="M12 9v4M12 17h0"/><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0z"/></>,
    list:      <><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></>,
    file:      <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></>,
    settings:  <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    search:    <><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></>,
    activity:  <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>,
    radio:     <><path d="M4.93 19.07A10 10 0 0 1 4.93 4.93"/><path d="M19.07 4.93A10 10 0 0 1 19.07 19.07"/><path d="M7.76 16.24a6 6 0 0 1 0-8.48"/><path d="M16.24 7.76a6 6 0 0 1 0 8.48"/><circle cx="12" cy="12" r="2"/></>,
    cpu:       <><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></>,
    chevron:   <path d="m9 18 6-6-6-6"/>,
    chevronD:  <path d="m6 9 6 6 6-6"/>,
    x:         <path d="M18 6 6 18M6 6l12 12"/>,
    sun:       <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></>,
    moon:      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>,
    download:  <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></>,
    plus:      <path d="M12 5v14M5 12h14"/>,
    arrowRt:   <><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></>,
    filter:    <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>,
    trend:     <><path d="m23 6-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/></>,
    bell:      <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9z"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></>,
    refresh:   <><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></>,
    check:     <path d="M20 6 9 17l-5-5"/>,
    upload:    <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></>,
    logout:    <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></>,
  };
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...rest}>
      {paths[name]}
    </svg>
  );
};


function downloadFile(filename, content, mime = 'text/plain') {
  const blob = new Blob([content], { type: mime + ';charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function csvEscape(v) {
  if (v == null) return '';
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCSV(rows, headers) {

  const cols = headers.map(h => Array.isArray(h) ? h : [h, h]);
  const head = cols.map(c => csvEscape(c[1])).join(',');
  const body = rows.map(r => cols.map(c => csvEscape(r[c[0]])).join(',')).join('\n');
  return head + '\n' + body;
}

function timestamp() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
}


window.exportCellsCSV = () => {
  const rows = window.PCI_DATA.CELLS || [];
  const csv = toCSV(rows, [
    ['id', 'cell_id'], ['site', 'site'], ['region', 'region'],
    ['pci', 'pci'], ['band', 'band'], ['sector', 'sector'], ['status', 'status'],
    ['dl', 'dl_mbps'], ['ul', 'ul_mbps'],
    ['prb', 'prb_pct'], ['ue', 'connected_ue'],
    ['bler', 'bler_pct'], ['cqi', 'cqi'], ['sinr', 'sinr_db'],
    ['lat', 'latitude'], ['lng', 'longitude'],
  ]);
  downloadFile(`pci-cells-${timestamp()}.csv`, csv, 'text/csv');
};

window.exportTimeSeriesCSV = () => {
  const rows = window.PCI_DATA.TS || [];
  const csv = toCSV(rows, [['t', 'time'], ['dl', 'dl_mbps'], ['ul', 'ul_mbps']]);
  downloadFile(`pci-timeseries-${timestamp()}.csv`, csv, 'text/csv');
};

window.exportAlertsCSV = () => {
  const rows = window.PCI_DATA.ALERTS || [];
  const csv = toCSV(rows, [
    ['id', 'alert_id'], ['t', 'time'], ['sev', 'severity'],
    ['cell', 'cell_id'], ['kind', 'kind'], ['msg', 'message'],
  ]);
  downloadFile(`pci-alerts-${timestamp()}.csv`, csv, 'text/csv');
};

window.exportPciPoolCSV = () => {
  const cells = window.PCI_DATA.CELLS || [];
  const conflicts = window.PCI_DATA.CONFLICTS || [];


  const poolSize = window.PCI_TECH === 'lte' ? 504 : 1008;
  const usedByPci = new Map();
  cells.forEach(c => {
    if (!usedByPci.has(c.pci)) usedByPci.set(c.pci, []);
    usedByPci.get(c.pci).push(c.id);
  });
  const conflictByPci = new Map();
  conflicts.forEach(cf => {
    const k = typeof cf.pci === 'number' ? cf.pci : null;
    if (k != null) conflictByPci.set(k, cf.type);
  });
  const rows = [];
  for (let i = 0; i < poolSize; i++) {
    const cellsAtPci = usedByPci.get(i) || [];
    rows.push({
      pci: i,
      status: cellsAtPci.length === 0 ? 'unassigned'
            : cellsAtPci.length > 1 ? 'collision'
            : (conflictByPci.get(i) || 'in_use'),
      cells: cellsAtPci.join('; '),
      cell_count: cellsAtPci.length,
      mod3: i % 3,
      mod30: i % 30,
    });
  }
  const csv = toCSV(rows, [
    ['pci', 'pci'], ['status', 'status'], ['cells', 'cells'],
    ['cell_count', 'cell_count'], ['mod3', 'mod3'], ['mod30', 'mod30'],
  ]);
  downloadFile(`pci-pool-${timestamp()}.csv`, csv, 'text/csv');
};

window.exportOverviewJSON = () => {
  const D = window.PCI_DATA || {};
  const snapshot = {
    exported_at: new Date().toISOString(),
    kpis: D.KPIS,
    cells: D.CELLS,
    conflicts: D.CONFLICTS,
    alerts: D.ALERTS,
    slices: D.SLICES,
    regions: D.REGIONS_HEALTH,
  };
  downloadFile(`pci-overview-${timestamp()}.json`, JSON.stringify(snapshot, null, 2), 'application/json');
};


const Spark = ({ data, color }) => {
  const w = 100, h = 22;
  if (!data || !data.length) return <svg viewBox={`0 0 ${w} ${h}`} className="kpi-spark" />;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => `${(i * step).toFixed(1)},${(h - 2 - ((v - min) / span) * (h - 4)).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="kpi-spark" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke={color || 'var(--accent)'} strokeWidth="1.4" />
    </svg>
  );
};

const KpiCard = ({ label, dot, value, unit, delta, deltaUnit, sparkData, sparkColor, foot }) => (
  <div className="panel kpi">
    <div className="kpi-label"><span className={`dot ${dot || ''}`}></span>{label}</div>
    <div className="kpi-value display-num">
      <span>{value}</span>
      {unit && <span className="unit">{unit}</span>}
    </div>
    <Spark data={sparkData} color={sparkColor} />
    <div className="kpi-foot">
      <span>{foot}</span>
      {delta != null && (
        <span className={delta >= 0 ? 'delta-up' : 'delta-down'}>
          {delta >= 0 ? '▲' : '▼'} {Math.abs(delta)}{deltaUnit || ''}
        </span>
      )}
    </div>
  </div>
);

const HeroSpark = ({ data, color }) => {
  const W = 280, H = 100, pad = 4;
  const min = Math.min(...data), max = Math.max(...data);
  const span = Math.max(0.001, max - min);
  const step = (W - 2 * pad) / (data.length - 1);
  const pts = data.map((v, i) => `${(pad + i * step).toFixed(1)},${(pad + (H - 2 * pad) - ((v - min) / span) * (H - 2 * pad)).toFixed(1)}`);
  const line = pts.join(' ');
  const area = `${pad},${H - pad} ${line} ${(W - pad).toFixed(1)},${H - pad}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%' }}>
      <defs>
        <linearGradient id="hero-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.32"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <polygon points={area} fill="url(#hero-fill)"/>
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.6"/>
    </svg>
  );
};

const KpiRow = ({ status, label, sub, value, unit, spark, sparkColor, delta, deltaUnit, deltaSub, onClick }) => {
  const W = 240, H = 24, pad = 2;
  const safe = (spark && spark.length > 1) ? spark : [0, 0];
  const min = Math.min(...safe), max = Math.max(...safe);
  const span = Math.max(0.001, max - min);
  const step = (W - 2 * pad) / (safe.length - 1);
  const linePts = safe.map((v, i) => `${(pad + i * step).toFixed(1)},${(pad + (H - 2 * pad) - ((v - min) / span) * (H - 2 * pad)).toFixed(1)}`);
  const line = linePts.join(' ');
  const area = `${pad},${H - pad} ${line} ${(W - pad).toFixed(1)},${H - pad}`;
  const gradId = `pulse-grad-${label.replace(/\s+/g, '-')}`;

  const deltaClass = delta == null ? 'flat' : delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
  const deltaSign = delta > 0 ? '▲' : delta < 0 ? '▼' : '●';

  return (
    <div
      className={`pulse-row ${status || ''}${onClick ? ' clickable' : ''}`}
      onClick={onClick || undefined}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }) : undefined}
      title={onClick ? 'View on Cell Map' : undefined}
    >
      <span className="bar"/>
      <div className="pulse-row-label">
        <div className="l">{label}</div>
        {sub && <div className="s">{sub}</div>}
      </div>
      <div className="pulse-row-value">
        <span>{value}</span>
        {unit && <span className="u">{unit}</span>}
      </div>
      <div className="pulse-row-foot">
        <svg className="pulse-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={sparkColor} stopOpacity="0.28"/>
              <stop offset="100%" stopColor={sparkColor} stopOpacity="0"/>
            </linearGradient>
          </defs>
          <polygon points={area} fill={`url(#${gradId})`}/>
          <polyline points={line} fill="none" stroke={sparkColor} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round"/>
        </svg>
        {delta != null ? (
          <span className={`pulse-delta ${deltaClass}`}>
            <span className="arrow">{deltaSign}</span>
            {Math.abs(delta)}{deltaUnit || ''}
            {deltaSub && <span className="sub">{deltaSub}</span>}
          </span>
        ) : null}
      </div>
    </div>
  );
};


function buildConflictHistory(history) {
  const fmt = (iso, opts) => window.formatTime
    ? window.formatTime(iso, Object.assign({ month: undefined, day: undefined, hour12: false }, opts))
    : new Date(iso).toISOString().slice(11, 16);
  const points = (history || []).filter(p => p && p.ts).map(p => {
    const cells = p.cells || 1;
    const hourKey = fmt(p.iso, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: undefined });
    return {
      ts: p.ts, iso: p.iso,
      label: fmt(p.iso, { hour: '2-digit', minute: '2-digit' }),
      hourLabel: fmt(p.iso, { hour: '2-digit', minute: undefined }).replace(/\D+$/, "") + ':00',
      hourKey,
      collision: p.collision || 0, confusion: p.confusion || 0, modn: p.modn || 0,
      total: (p.collision || 0) + (p.confusion || 0) + (p.modn || 0),
      healthPct: Math.round(((cells - (p.conflictCells || 0)) / cells) * 100),
    };
  });
  const last = points[points.length - 1];
  const first = points[0];
  const spanMin = points.length > 1 ? Math.round((last.ts - first.ts) / 60) : 0;
  return {
    points,
    summary: {
      liveTotal: last ? last.total : 0,
      deltaVsStart: last && first ? last.total - first.total : 0,
      spanMin,
      peak: points.length ? Math.max(...points.map(p => p.total)) : 0,
      avgHealthPct: points.length
        ? Math.round(points.reduce((a, p) => a + p.healthPct, 0) / points.length) : 0,
    },
  };
}

function spanLabel(min) {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}


function computePulse(cells, conflicts) {
  cells = cells || [];
  conflicts = conflicts || [];
  const totalCells = cells.length;
  const activeCells = cells.filter(c => c.status === 'active').length;

  const affectedUes = conflicts.reduce((a, c) => a + (Number(c.affectedUe) || 0), 0);


  const regionByCell = {};
  cells.forEach(c => { if (c.id) regionByCell[c.id] = c.region || '—'; });
  const regionConflicts = {}, regionUes = {};
  conflicts.forEach(cf => {
    const touched = new Set((cf.cells || [])
      .map(cid => regionByCell[cid]).filter(Boolean));
    const ue = Number(cf.affectedUe) || 0;
    touched.forEach(r => {
      regionConflicts[r] = (regionConflicts[r] || 0) + 1;
      regionUes[r] = (regionUes[r] || 0) + ue;
    });
  });
  let worstRegion = null;
  const regionNames = Object.keys(regionConflicts);
  if (regionNames.length) {
    const name = regionNames.reduce((a, b) =>
      regionConflicts[b] > regionConflicts[a] ? b : a);
    worstRegion = { name, conflicts: regionConflicts[name], ues: regionUes[name] || 0 };
  }


  const mod3Cells = new Set();
  conflicts.forEach(cf => {
    if (cf.type === 'mod3') (cf.cells || []).forEach(cid => mod3Cells.add(cid));
  });

  return {
    activeCells, totalCells,
    affectedUes, conflictCount: conflicts.length,
    worstRegion,
    mod3Cells: mod3Cells.size,
  };
}

function niceScale(v) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(v, 1e-9))));
  const m = v / p;
  const [mant, ticks] = [[1, 4], [1.25, 5], [1.5, 3], [2, 4], [2.5, 5], [3, 3], [4, 4], [5, 5], [6, 3], [8, 4], [10, 5]]
    .find(([k]) => m <= k) || [10, 5];
  return { max: mant * p, ticks };
}

const ConflictTrend = ({ history }) => {
  const [hover, setHover] = React.useState(null);
  const { points, summary } = React.useMemo(() => buildConflictHistory(history), [history]);
  if (points.length < 2) {
    return (
      <div className="kpi-hero-trend" style={{ justifyContent: 'flex-end' }}>
        <div className="kht-title"><span>Conflict trend</span></div>
        <div style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>
          Sampled once a minute while the dashboard runs — the trend line appears after the second sample.
        </div>
      </div>
    );
  }

  const W = 640, H = 150, padL = 4, padR = 4, padT = 8, padB = 4;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const yMax = niceScale(Math.max(...points.map(p => p.total)) * 1.08).max;
  const x = (i) => padL + (i / (points.length - 1)) * innerW;
  const y = (v) => padT + innerH - (v / yMax) * innerH;


  const bands = [
    ['modn',      'var(--info)', 'Mod-3'],
    ['confusion', 'var(--warn)', 'Confusion'],
    ['collision', 'var(--crit)', 'Collision'],
  ];
  let base = points.map(() => 0);
  const shapes = bands.map(([key, color, label]) => {
    const top = points.map((p, i) => base[i] + p[key]);
    const fwd = top.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const back = base.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).reverse();
    const shape = { key, color, label, area: [...fwd, ...back].join(' '), line: fwd.join(' ') };
    base = top;
    return shape;
  });

  const ticks = [yMax / 2, yMax];
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    const idx = Math.round(ratio * (points.length - 1));
    setHover({ idx, pctX: (x(idx) / W) * 100, point: points[idx] });
  };

  return (
    <div className="kpi-hero-trend" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <div className="kht-title">
        <span>Conflict trend · last {spanLabel(summary.spanMin)}</span>
        <span className="kht-ticks">{ticks.map((v, i) => (
          <span key={i} style={{ top: `${(y(v) / H) * 100}%` }}>{Number.isInteger(v) ? v : v.toFixed(1)}</span>
        ))}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {ticks.map((v, i) => (
          <line key={i} x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} className="grid-line" vectorEffect="non-scaling-stroke"/>
        ))}
        <line x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} className="grid-line" vectorEffect="non-scaling-stroke"/>
        {shapes.map(sh => (
          <g key={sh.key}>
            <polygon points={sh.area} fill={sh.color} opacity="0.16"/>
            <polyline points={sh.line} fill="none" stroke={sh.color} strokeWidth="1.8" vectorEffect="non-scaling-stroke"/>
          </g>
        ))}
        {hover && (
          <line x1={x(hover.idx)} x2={x(hover.idx)} y1={padT} y2={padT + innerH}
                stroke="var(--fg-3)" strokeDasharray="2 3" vectorEffect="non-scaling-stroke"/>
        )}
      </svg>
      <div className="kht-x">
        {points.map((p, i) => i % Math.max(1, Math.ceil(points.length / 5)) === 0 && i < points.length - 1 && (
          <span key={i} style={{ left: `${(x(i) / W) * 100}%` }}>{p.label}</span>
        ))}
        <span style={{ left: `${(x(points.length - 1) / W) * 100}%` }}>now</span>
      </div>
      {hover && (
        <div className="kht-tip" style={{ left: `${hover.pctX}%`, transform: hover.pctX > 60 ? 'translateX(calc(-100% - 10px))' : 'translateX(10px)' }}>
          <div className="kht-tip-t">{hover.idx === points.length - 1 ? 'now' : hover.point.label} · <b>{hover.point.total}</b> total</div>
          {[...bands].reverse().map(([key, color, label]) => (
            <div key={key}><i style={{ background: color }}/>{label} <b>{hover.point[key]}</b></div>
          ))}
        </div>
      )}
    </div>
  );
};

const KpiStrip = ({ onNavigate }) => {
  const k = window.PCI_DATA.KPIS;
  const conflicts = window.PCI_DATA.CONFLICTS || [];


  const numberWord = (n) =>
    ['Zero','One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten'][n] || String(n);

  const byType = {
    collision: conflicts.filter(c => c.type === 'collision'),
    confusion: conflicts.filter(c => c.type === 'confusion'),
    mod3:      conflicts.filter(c => c.type === 'mod3'),
  };
  const bySev = (sev, list) => list.filter(c => c.severity === sev);


  const phrases = [];
  for (const [type, label] of [['collision', 'collision'], ['confusion', 'confusion'], ['mod3', 'mod-3 alignment']]) {
    const list = byType[type];
    if (list.length === 0) continue;

    const sevOrder = ['critical', 'major', 'minor'];
    const worst = sevOrder.find(s => bySev(s, list).length > 0) || list[0].severity;
    const worstList = bySev(worst, list);
    const c = worstList[0];
    const count = list.length;
    const head = `${count === 1 ? `${count} ${worst} ${label}` : `${numberWord(count).toLowerCase()} ${worst} ${label}s`}`;
    let detail = '';
    if (count === 1 && c.cells && c.cells.length >= 2 && typeof c.pci === 'number') {
      detail = ` on PCI ${c.pci} (${c.cells[0]} ↔ ${c.cells[1]})`;
    } else if (count === 1 && typeof c.pci === 'number') {
      detail = ` on PCI ${c.pci}`;
    }
    phrases.push({ html: <><b>{head}</b>{detail}</>, type, count });
  }


  const heroDesc = (() => {
    if (phrases.length === 0) {
      return <>No PCI conflicts detected — the pool is clean and handover is stable.</>;
    }
    if (phrases.length === 1) {
      const p = phrases[0];
      const verb = p.count === 1 ? 'is' : 'are';
      return <>{p.html} {verb} degrading handover.</>;
    }

    const lead = phrases.slice(0, 2);
    const tail = phrases.slice(2);
    return (
      <>
        {lead[0].html} and {lead[1].html} are degrading handover.
        {tail.length > 0 && <> {tail.map((p, i) => <React.Fragment key={i}>{i > 0 && ', '}{p.html}</React.Fragment>)} {tail.length === 1 && tail[0].count === 1 ? 'is' : 'are'} queued for re-plan.</>}
      </>
    );
  })();


  const totalUeImpacted = conflicts.reduce((acc, c) => acc + (c.affectedUe || 0), 0);


  const critMajor = conflicts.filter(c => c.severity === 'critical' || c.severity === 'major').length;

  return (
    <div className="kpi-editorial">
      <div className="panel kpi-hero">
        <div className="kpi-hero-head">
          <span className="kpi-hero-eyebrow">
            {conflicts.length === 0
              ? '● All clear · pool stable'
              : critMajor > 0
                ? '● Critical · requires attention'
                : '● Minor · informational'}
          </span>
          <h3 className="kpi-hero-title">PCI conflicts in pool</h3>
        </div>
        <div className="kpi-hero-body">
          <div className="kpi-hero-num">
            {k.pciConflicts}
            <small>active conflict{k.pciConflicts === 1 ? '' : 's'} · {k.totalCells} cells in pool</small>
          </div>
          <p className="kpi-hero-desc">{heroDesc}</p>
          <ConflictTrend history={window.PCI_DATA.HISTORY}/>
        </div>
        <div className="kpi-hero-foot">
          {totalUeImpacted > 0 && (
            <span className="kpi-hero-tag"><span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--crit)' }}/>{totalUeImpacted.toLocaleString()} UEs impacted</span>
          )}
          {conflicts.length === 0 && (
            <span className="kpi-hero-tag"><span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ok)' }}/>handover stable</span>
          )}
        </div>
        <div className="kpi-hero-mix">
          <div className="khm-row">
            <span className="khm-key"><i style={{ background: 'var(--crit)' }}/>Collision</span>
            <b>{byType.collision.length}</b>
          </div>
          <div className="khm-row">
            <span className="khm-key"><i style={{ background: 'var(--warn)' }}/>Confusion</span>
            <b>{byType.confusion.length}</b>
          </div>
          <div className="khm-row">
            <span className="khm-key"><i style={{ background: 'var(--info)' }}/>Mod-3</span>
            <b>{byType.mod3.length}</b>
          </div>
        </div>
      </div>
      <div className="panel pulse-panel">
        <div className="pulse-head">
          <div className="pulse-head-titles">
            <h4>Network Pulse</h4>
            <span className="pulse-head-sub">4 live metrics</span>
          </div>
          <span className="pulse-head-live"><span className="dot"/>Live</span>
        </div>
        <div className="pulse-rows">
          {(() => {
            const p = computePulse(
              window.PCI_DATA.CELLS, window.PCI_DATA.CONFLICTS,
            );
            const totalCells = p.totalCells || 0;
            const worst = p.worstRegion;
            return (
              <>
                <KpiRow
                  status="ok"
                  label="Cells reporting"
                  sub={(() => {
                    const by = (window.PCI_DATA.meta || {}).cellsByTech || {};
                    return `in the last PM ingest · ${by.lte ?? 0} LTE + ${by.nr ?? 0} NR in the feed`;
                  })()}
                  value={totalCells}
                  unit={window.PCI_TECH === 'lte' ? '4G LTE' : '5G NR'}
                  sparkColor="var(--ok)"
                />
                <KpiRow
                  status="accent"
                  label="Affected UEs"
                  sub={`subscribers across ${p.conflictCount || 0} active conflict${(p.conflictCount || 0) === 1 ? '' : 's'}`}
                  value={(p.affectedUes || 0).toLocaleString()}
                  unit=""
                  sparkColor="var(--accent)"
                />
                <KpiRow
                  status={worst ? 'warn' : 'ok'}
                  label="Worst-hit region"
                  sub={worst
                    ? `${worst.conflicts} conflict${worst.conflicts === 1 ? '' : 's'} · ${(worst.ues || 0).toLocaleString()} UEs at risk`
                    : 'no conflicts — every region clean'}
                  value={worst ? worst.name : '—'}
                  unit=""
                  sparkColor="var(--warn)"
                  onClick={worst && onNavigate ? (() => {
                    window.PCI_MAP_FOCUS = worst.name;
                    onNavigate('cell-map');
                  }) : undefined}
                />
                <KpiRow
                  status={(p.mod3Cells || 0) > 0 ? 'info' : 'ok'}
                  label="Mod-3 interference"
                  sub="cells with reference-signal SINR degradation"
                  value={p.mod3Cells || 0}
                  unit={(p.mod3Cells || 0) === 1 ? 'cell' : 'cells'}
                  sparkColor="var(--info)"
                />
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
};


const ThroughputChart = () => {
  const ts = window.PCI_DATA.TS;
  const [hover, setHover] = useState(null);

  if (!ts || ts.length === 0) {
    return (
      <div className="chart-empty">
        <Icon name="activity" size={20}/>
        <div className="chart-empty-title">No throughput yet</div>
        <div className="chart-empty-sub">
          Nothing recorded in the last {(TS_RANGES.find(r => r[0] === window.PCI_TS_RANGE) || TS_RANGES[1])[2]} —
          the series fills in as PM data for the selected technology is ingested.
        </div>
      </div>
    );
  }

  const sliced = ts;

  const W = 920, H = 280;
  const padL = 44, padR = 50, padT = 18, padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const dlMax = Math.max(...sliced.map(p => p.dl), 0);
  const ulMax = Math.max(...sliced.map(p => p.ul), 0);


  const gbps = Math.max(dlMax, ulMax) >= 2000;
  const unitDiv = gbps ? 1000 : 1;
  const unit = gbps ? 'Gbps' : 'Mbps';
  const scale = niceScale(Math.max(dlMax, ulMax, 1) / unitDiv * 1.1);
  const tpMax = scale.max * unitDiv;
  const yTicks = scale.ticks;
  const fmtTp = (v) => { const x = v / unitDiv; return Number.isInteger(x) ? String(x) : x.toFixed(1); };


  const x = (i) => padL + (sliced.length > 1 ? (i / (sliced.length - 1)) * innerW : 0);
  const yTp  = (v) => padT + innerH - (v / tpMax) * innerH;


  const dlPts = sliced.map((p, i) => `${x(i).toFixed(1)},${yTp(p.dl).toFixed(1)}`).join(' ');
  const ulPts = sliced.map((p, i) => `${x(i).toFixed(1)},${yTp(p.ul).toFixed(1)}`).join(' ');


  const dlArea = `${padL},${padT + innerH} ${dlPts} ${(padL + innerW).toFixed(1)},${padT + innerH}`;

  const tpTicks = Array.from({ length: yTicks + 1 }, (_, i) => (tpMax / yTicks) * i);


  const firstIso = sliced.length ? sliced[0].iso : null;
  const lastIso = sliced.length ? sliced[sliced.length - 1].iso : null;
  const spanMs = (firstIso && lastIso) ? (new Date(lastIso) - new Date(firstIso)) : 0;
  const spansDays = spanMs >= 2 * 86400000;
  const xLabelEvery = Math.ceil(sliced.length / (spansDays ? 6 : 8));
  const fmt = (p, opts) => (p.iso && window.formatTime) ? window.formatTime(p.iso, opts) : p.t;
  const tLabel = (p) => fmt(p, spansDays
    ? { month: 'short', day: 'numeric', hour: undefined, minute: undefined }
    : { month: undefined, day: undefined, hour: '2-digit', minute: '2-digit', hour12: false });
  const hoverLabel = (p) => fmt(p, window.PCI_TS_RANGE === '15m' || window.PCI_TS_RANGE === '1h'
    ? { month: undefined, day: undefined, hour: '2-digit', minute: '2-digit', hour12: false }
    : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    if (px < padL || px > padL + innerW) { setHover(null); return; }
    const ratio = (px - padL) / innerW;
    const idx = Math.round(ratio * (sliced.length - 1));
    setHover({ idx, x: x(idx), point: sliced[idx] });
  };


  const pct = (v, axis, denom) => axis === 'x' ? ((v / (denom || innerW)) * 100) : (v / H) * 100;

  return (
    <div className="chart-wrap">
      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="dl-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="var(--accent)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {tpTicks.map((v, i) => {
          const yy = yTp(v);
          return (
            <line key={'g' + i} x1={padL} x2={padL + innerW} y1={yy} y2={yy} className="grid-line" />
          );
        })}

        <polygon points={dlArea} fill="url(#dl-fill)" />
        <polyline points={dlPts} fill="none" stroke="var(--accent)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
        <polyline points={ulPts} fill="none" stroke="var(--maint)" strokeWidth="1.8" strokeDasharray="0" opacity="0.95" vectorEffect="non-scaling-stroke" />

        {hover && (
          <g>
            <line x1={hover.x} x2={hover.x} y1={padT} y2={padT + innerH} stroke="var(--fg-3)" strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />
            <circle cx={hover.x} cy={yTp(hover.point.dl)}  r="3" fill="var(--accent)" />
            <circle cx={hover.x} cy={yTp(hover.point.ul)}  r="3" fill="var(--maint)" />
          </g>
        )}
      </svg>

      <div className="chart-axis chart-axis-y-left">
        <span className="axis-unit">{unit}</span>
        {tpTicks.map((v, i) => (
          <span key={'yl' + i} style={{ top: `${pct(yTp(v), 'y')}%` }}>{fmtTp(v)}</span>
        ))}
      </div>
      <div className="chart-axis chart-axis-x">
        {sliced.map((p, i) => i % xLabelEvery === 0 && (
          <span key={'xl' + i} style={{ left: `${(x(i) / W) * 100}%` }}>{tLabel(p)}</span>
        ))}
      </div>

      {hover && (
        <div style={{
          position: 'absolute',
          left: `calc(${(hover.x / W) * 100}% + 12px)`,
          top: 8,
          background: 'var(--bg-3)',
          border: '1px solid var(--line-2)',
          borderRadius: 'var(--r-sm)',
          padding: '8px 10px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          color: 'var(--fg-2)',
          pointerEvents: 'none',
          minWidth: 140,
          zIndex: 2,
        }}>
          <div style={{ color: 'var(--fg)', marginBottom: 4 }}>{hoverLabel(hover.point)}</div>
          <div><span style={{ color: 'var(--accent)' }}>DL</span> {fmtTp(hover.point.dl)} {unit}</div>
          <div><span style={{ color: 'var(--maint)' }}>UL</span> {fmtTp(hover.point.ul)} {unit}</div>
        </div>
      )}

      <div className="chart-legend">
        <div className="legend-item"><i className="legend-swatch" style={{ background: 'var(--accent)' }} /> DL Throughput</div>
        <div className="legend-item"><i className="legend-swatch" style={{ background: 'var(--maint)' }} /> UL Throughput</div>
      </div>
    </div>
  );
};

const TS_RANGES = [
  ['15m', '15m', '15 min'],
  ['1h',  '1h',  '60 min'],
  ['6h',  '6h',  '6 hours'],
  ['24h', '24h', '24 hours'],
  ['7d',  '7d',  '7 days'],
];

const ChartPanel = () => {
  const range = window.PCI_TS_RANGE;
  const current = TS_RANGES.find(r => r[0] === range) || TS_RANGES[1];
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="titles">
          <h3 className="panel-title">Throughput</h3>
          <div className="panel-sub">Aggregate DL/UL · last {current[2]}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className="seg sm">
            {TS_RANGES.map(([k, short]) => (
              <button key={k} data-on={range === k ? 1 : undefined}
                onClick={() => window.setPciTsRange(k)}>{short}</button>
            ))}
          </div>
          <FeedPill/>
        </div>
      </div>
      <ThroughputChart/>
    </div>
  );
};


const FEED_STALE_AFTER_S = 180;

function feedAgeLabel(sec) {
  if (sec < 90) return `${Math.round(sec)}s`;
  if (sec < 5400) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}

function feedStatus() {
  const meta = window.PCI_DATA.meta || {};
  if (meta.poll_error) return { cls: 'pill stale', label: 'STALE', title: meta.poll_error };
  if (!(window.PCI_DATA.CELLS || []).length) return { cls: 'pill idle', label: 'NO DATA', title: 'No PM data ingested yet' };
  const age = meta.feed_age_seconds;
  if (typeof age === 'number' && age > FEED_STALE_AFTER_S) {
    return {
      cls: 'pill stale',
      label: `STALE · ${feedAgeLabel(age)}`,
      title: `No PM file has arrived for ${feedAgeLabel(age)}. Figures below are the last received snapshot, not current network state.`,
    };
  }
  const seen = (typeof age === 'number') ? ` · last PM ${feedAgeLabel(age)} ago` : '';
  return { cls: 'pill live', label: 'LIVE', title: `Last update ${meta.updated ? window.formatTime(meta.updated) : ''}${seen} · polls every 30 s` };
}
const FeedPill = () => {
  const f = feedStatus();
  return <span className={f.cls} title={f.title}><span className="dot"/>{f.label}</span>;
};

window.alertTime = (a) => (a && a.iso && window.formatTime)
  ? window.formatTime(a.iso, { month: undefined, day: undefined, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  : (a ? a.t : '');

const AlertsPanel = () => {
  const [filter, setFilter] = useState('all');
  const all = window.PCI_DATA.ALERTS;
  const list = useMemo(() => {
    if (filter === 'all') return all;
    return all.filter(a => a.sev === filter);
  }, [filter, all]);
  const counts = useMemo(() => ({
    all: all.length,
    critical: all.filter(a => a.sev === 'critical').length,
    major:    all.filter(a => a.sev === 'major').length,
    minor:    all.filter(a => a.sev === 'minor').length,
    info:     all.filter(a => a.sev === 'info').length,
  }), [all]);

  return (
    <div className="panel" style={{ minHeight: 0 }}>
      <div className="panel-head">
        <div className="titles">
          <h3 className="panel-title">Incident Feed</h3>
          <div className="panel-sub">{counts.critical + counts.major} critical/major · {all.length} open</div>
        </div>
      </div>
      <div className="seg" style={{ alignSelf: 'flex-start' }}>
        {[
          ['all', 'ALL · ' + counts.all],
          ['critical', 'CRIT · ' + counts.critical],
          ['major', 'MAJ · ' + counts.major],
          ['minor', 'MIN · ' + counts.minor],
        ].map(([k, label]) => (
          <button key={k} data-on={filter === k ? 1 : 0} onClick={() => setFilter(k)}>{label}</button>
        ))}
      </div>
      <div className="alerts-list" style={{ overflow: 'auto', maxHeight: 360 }}>
        {list.map(a => (
          <div key={a.id} className={`alert ${a.sev}`}>
            <span className="bar" />
            <div className="body">
              <div className="top">
                <span className="kind">{a.kind}</span>
                <span className={`chip ${a.sev === 'critical' ? 'crit' : a.sev === 'major' ? 'warn' : a.sev === 'minor' ? 'info' : 'idle'}`}>
                  <span className="dot"/>{a.sev}
                </span>
                <span className="cell">· {a.cell}</span>
              </div>
              <div className="msg">{a.msg}</div>
            </div>
            <span className="t">{window.alertTime(a)}</span>
          </div>
        ))}
        {list.length === 0 && (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            No alerts at this severity.
          </div>
        )}
      </div>
    </div>
  );
};


const SPECTRUM_STATE_COLOR = {
  collision: 'var(--crit)',
  confusion: 'var(--warn)',
  mod3: 'var(--info)',
  used: 'var(--accent)',
  free: 'var(--line-2)',
};
const SPECTRUM_STATE_LABEL = {
  collision: 'Collision', confusion: 'Confusion', mod3: 'Mod-3 cluster',
  used: 'In use', free: 'Unassigned',
};

const PciSpectrum = ({ cells, conflicts, poolSize, usedMap, collidedPCIs, confusedPCIs, reusedPCIs }) => {
  const mod3Pcis = useMemo(() => {
    const ids = new Set(conflicts.filter(c => c.type === 'mod3').flatMap(c => c.cells));
    return new Set(cells.filter(c => ids.has(c.id)).map(c => c.pci));
  }, [cells, conflicts]);


  const stateOf = React.useCallback((pci) => {
    if (collidedPCIs.has(pci)) return 'collision';
    if (confusedPCIs.has(pci)) return 'confusion';
    if (mod3Pcis.has(pci)) return 'mod3';
    return usedMap.has(pci) ? 'used' : 'free';
  }, [collidedPCIs, confusedPCIs, mod3Pcis, usedMap]);

  const states = useMemo(
    () => Array.from({ length: poolSize }, (_, i) => stateOf(i)),
    [poolSize, stateOf]
  );

  const counts = useMemo(() => {
    const c = { collision: 0, confusion: 0, mod3: 0, used: 0, free: 0 };
    states.forEach(s => { c[s] += 1; });
    return c;
  }, [states]);

  const [hover, setHover] = useState(null);


  const largestGap = useMemo(() => {
    let best = 0, run = 0, bestAt = 0, at = 0;
    states.forEach((s, i) => {
      if (s === 'free') { if (run === 0) at = i; run += 1; if (run > best) { best = run; bestAt = at; } }
      else run = 0;
    });
    return { size: best, start: bestAt };
  }, [states]);

  const W = 1000, BAND_H = 54, LANE_H = 20, LANE_GAP = 5;
  const colW = W / poolSize;

  const bandRects = (list, y, h) => list.map(({ pci, state }) => (
    <rect key={pci} x={pci * colW} y={y} width={Math.max(colW, 0.9)} height={h}
      fill={SPECTRUM_STATE_COLOR[state]}
      opacity={state === 'free' ? 0.35 : 1}/>
  ));

  const all = states.map((state, pci) => ({ pci, state }));
  const lanes = [0, 1, 2].map(g => all.filter(d => d.pci % 3 === g));

  const svgRef = React.useRef(null);
  const onMove = (e) => {


    const el = svgRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const pci = Math.max(0, Math.min(poolSize - 1,
      Math.floor(((e.clientX - r.left) / r.width) * poolSize)));
    const holders = (usedMap.get(pci) || []).map(c => c.id ?? c);
    setHover({ pci, state: states[pci], holders, reuse: holders.length,
               x: e.clientX - r.left, w: r.width });
  };

  const pct = Math.round(((poolSize - counts.free) / poolSize) * 100);

  return (
    <div className="spectrum">
      <div className="spectrum-stats">
        <div className="sp-stat">
          <div className="sp-stat-k">Namespace in use</div>
          <div className="sp-stat-v">{pct}<small>%</small></div>
          <div className="sp-stat-h">{poolSize - counts.free} of {poolSize} PCIs</div>
        </div>
        <div className="sp-stat">
          <div className="sp-stat-k">Largest free run</div>
          <div className="sp-stat-v">{largestGap.size}</div>
          <div className="sp-stat-h">from PCI {largestGap.start}</div>
        </div>
        <div className="sp-stat">
          <div className="sp-stat-k">Mean reuse</div>
          <div className="sp-stat-v">
            {(() => {
              const used = poolSize - counts.free;
              return used ? (cells.length / used).toFixed(1) : '0';
            })()}<small>×</small>
          </div>
          <div className="sp-stat-h">{(reusedPCIs || new Set()).size} PCIs held by 2+ cells</div>
        </div>
        <div className="sp-stat">
          <div className="sp-stat-k">In conflict</div>
          <div className="sp-stat-v tone-bad">{counts.collision + counts.confusion + counts.mod3}</div>
          <div className="sp-stat-h">
            {counts.collision} collision · {counts.confusion} confusion · {counts.mod3} mod-3
          </div>
        </div>
      </div>

      <div className="spectrum-band-wrap" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <svg ref={svgRef} viewBox={`0 0 ${W} ${BAND_H + (LANE_H + LANE_GAP) * 3 + 26}`}
             preserveAspectRatio="none" className="spectrum-svg">
          {bandRects(all, 0, BAND_H)}
          {lanes.map((lane, g) => (
            <g key={g}>
              {lane.map(({ pci, state }) => (
                <rect key={pci} x={pci * colW} y={BAND_H + 12 + g * (LANE_H + LANE_GAP)}
                  width={Math.max(colW, 0.9)} height={LANE_H}
                  fill={SPECTRUM_STATE_COLOR[state]}
                  opacity={state === 'free' ? 0.22 : 0.95}/>
              ))}
            </g>
          ))}
          {hover && (
            <rect x={hover.pci * colW - 0.5} y={0} width={Math.max(colW, 1.5) + 1}
              height={BAND_H + 12 + (LANE_H + LANE_GAP) * 3}
              fill="none" stroke="var(--fg)" strokeWidth={1.5} vectorEffect="non-scaling-stroke"/>
          )}
        </svg>

        <div className="spectrum-lane-labels">
          <span style={{ top: BAND_H + 12 }}>mod-3 · 0</span>
          <span style={{ top: BAND_H + 12 + (LANE_H + LANE_GAP) }}>mod-3 · 1</span>
          <span style={{ top: BAND_H + 12 + (LANE_H + LANE_GAP) * 2 }}>mod-3 · 2</span>
        </div>

        {hover && (
          <div className="spectrum-tip" style={{
            left: `${62 + Math.min(Math.max(hover.x, 70), hover.w - 70)}px`,
          }}>
            <b>PCI {hover.pci}</b>
            <span className="sp-tip-state" style={{ color: SPECTRUM_STATE_COLOR[hover.state] }}>
              {SPECTRUM_STATE_LABEL[hover.state]}
            </span>
            {hover.reuse > 0 && (
              <span className="sp-tip-cells">
                reused by {hover.reuse} cell{hover.reuse === 1 ? '' : 's'}
              </span>
            )}
            {hover.holders.length > 0 && (
              <span className="sp-tip-cells">{hover.holders.slice(0, 2).join(', ')}
                {hover.holders.length > 2 ? ` +${hover.holders.length - 2}` : ''}</span>
            )}
          </div>
        )}
      </div>

      <div className="spectrum-axis">
        {Array.from({ length: 9 }, (_, i) => Math.round((poolSize - 1) * (i / 8))).map(v => (
          <span key={v}>{v}</span>
        ))}
      </div>

      <div className="pool-legend">
        {['free', 'used', 'mod3', 'confusion', 'collision'].map(k => (
          <div key={k}><i style={{ background: SPECTRUM_STATE_COLOR[k] }}/>{SPECTRUM_STATE_LABEL[k]}</div>
        ))}
      </div>
    </div>
  );
};


const PciPoolPanel = ({ onSelectCell, tech }) => {
  const cells = window.PCI_DATA.CELLS;
  const conflicts = window.PCI_DATA.CONFLICTS;
  const [view, setView] = useState('spectrum');


  const poolSize = tech === 'lte' ? 504 : 1008;

  const usedMap = useMemo(() => {
    const m = new Map();
    cells.forEach(c => {
      if (!m.has(c.pci)) m.set(c.pci, []);
      m.get(c.pci).push(c);
    });
    return m;
  }, [cells]);


  const collidedPCIs = useMemo(() => new Set(
    conflicts.filter(c => c.type === 'collision' && typeof c.pci === 'number').map(c => c.pci)
  ), [conflicts]);


  const reusedPCIs = useMemo(() => new Set(
    [...usedMap.entries()].filter(([_, arr]) => arr.length > 1).map(([k]) => k)
  ), [usedMap]);

  const confusedPCIs = useMemo(() => new Set(
    conflicts.filter(c => c.type === 'confusion' && typeof c.pci === 'number').map(c => c.pci)
  ), [conflicts]);

  const mod3PCIs = useMemo(() => {
    if (view !== 'mod3') return new Set();
    const ids = conflicts.filter(c => c.type === 'mod3').flatMap(c => c.cells);
    return new Set(cells.filter(c => ids.includes(c.id)).map(c => c.pci));
  }, [view, cells, conflicts]);

  const slots = [];
  for (let i = 0; i < poolSize; i++) {
    const arr = usedMap.get(i) || [];
    let cls = 'pool-cell';
    if (arr.length) cls += ' used';
    if (collidedPCIs.has(i)) cls += ' collide';
    if (confusedPCIs.has(i)) cls += ' confuse';
    if (mod3PCIs.has(i))     cls += ' mod3';
    slots.push(
      <div key={i} className={cls} title={arr.length
        ? `PCI ${i}\n${arr.map(c => c.id + ' (' + c.site + ')').join('\n')}`
        : `PCI ${i} · unassigned`}
        onClick={() => arr[0] && onSelectCell && onSelectCell(arr[0])}>
        {arr.length > 0 && i}
      </div>
    );
  }


  const conflictRows = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {conflicts.map(c => (
        <div key={c.id} className="panel" style={{ padding: 12, gap: 8, border: '1px solid var(--line)', background: 'var(--bg-3)' }}>
          <div className="row-h" style={{ justifyContent: 'space-between' }}>
            <div className="row-h" style={{ gap: 10 }}>
              <span className={`chip ${c.severity === 'critical' ? 'crit' : c.severity === 'major' ? 'warn' : 'info'}`}>
                <span className="dot"/>{c.severity}
              </span>
              <span className="mono" style={{ color: 'var(--fg)', fontSize: 14 }}>{c.id}</span>
              <span style={{ color: 'var(--fg-2)', fontSize: 13.5, textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 500 }}>
                {c.type}
              </span>
              <span className="mono" style={{ color: 'var(--fg-3)', fontSize: 12.5 }}>PCI {c.pci}</span>
            </div>
            <span className="mono" style={{ color: 'var(--fg-3)', fontSize: 12 }}>{
              window.formatTime
                ? window.formatTime(c.detected, { month: undefined, day: undefined,
                    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                : c.detected
            }</span>
          </div>
          <div style={{ fontSize: 13.5, color: 'var(--fg-2)', lineHeight: 1.5 }}>{c.impact}</div>
          <div className="row-h" style={{ gap: 10, fontSize: 12.5, color: 'var(--fg-3)' }}>
            <span>cells:</span>
            {c.cells.map(cid => (
              <span key={cid} className="mono" style={{ color: 'var(--fg-2)', padding: '2px 8px', border: '1px solid var(--line-2)', borderRadius: 4 }}>{cid}</span>
            ))}
            <span style={{ marginLeft: 'auto', color: 'var(--fg-2)' }}>{c.affectedUe} UEs impacted</span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="titles">
          <h3 className="panel-title">PCI Pool · 0–{poolSize - 1}</h3>
          <div className="panel-sub">
            {usedMap.size} of {poolSize} PCIs in use ·{' '}
            {collidedPCIs.size} PCI{collidedPCIs.size === 1 ? '' : 's'} in collision ·{' '}
            {confusedPCIs.size} in confusion ·{' '}
            {conflicts.filter(c => c.type === 'mod3').length} mod-3 pairs reported
          </div>
        </div>
        <div className="row-h" style={{ gap: 10 }}>
          <div className="seg">
            {[['spectrum','SPECTRUM'],['pool','POOL'],['mod3','MOD-3'],['conflicts','CONFLICTS']].map(([k,l])=> (
              <button key={k} data-on={view===k?1:0} onClick={()=>setView(k)}>{l}</button>
            ))}
          </div>
          <button className="btn-sm" onClick={() => window.exportPciPoolCSV()}>
            <Icon name="download" size={12}/> Export
          </button>
        </div>
      </div>

      {(view === 'pool' || view === 'mod3') && (
        <>
          <div className="pool-grid">{slots}</div>
          <div className="pool-legend">
            <div><i style={{ background: 'var(--bg-3)', boxShadow: 'inset 0 0 0 1px var(--line-2)' }}/>unassigned</div>
            <div><i style={{ background: 'color-mix(in oklch, var(--accent) 60%, #ffffff)' }}/>in use</div>
            {view === 'mod3' && <div><i style={{ background: '#8b5cf6' }}/>mod-3 aligned</div>}
            <div><i style={{ background: '#f59e0b' }}/>confusion</div>
            <div><i style={{ background: '#dc2626' }}/>collision</div>
            <div className="pool-legend-note">
              {view === 'mod3'
                ? 'Tiles sharing a mod-3 residue with a same-frequency neighbour.'
                : 'One tile per PCI in the namespace.'}
            </div>
          </div>
        </>
      )}
      {view === 'spectrum' && (
        <PciSpectrum
          cells={cells} conflicts={conflicts} poolSize={poolSize}
          usedMap={usedMap} collidedPCIs={collidedPCIs} confusedPCIs={confusedPCIs}
          reusedPCIs={reusedPCIs}
        />
      )}
      {view === 'conflicts' && conflictRows}
    </div>
  );
};


const CellTable = ({ onSelect, selectedId }) => {
  const cells = window.PCI_DATA.CELLS;
  const [sort, setSort] = useState({ key: 'id', dir: 1 });
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');

  const filtered = useMemo(() => {
    let r = cells;
    if (q) r = r.filter(c => (c.id + ' ' + c.site + ' ' + c.region + ' ' + c.band + ' ' + c.pci).toLowerCase().includes(q.toLowerCase()));
    if (statusFilter !== 'all') r = r.filter(c => c.status === statusFilter);
    r = [...r].sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key];
      if (typeof av === 'number') return (av - bv) * sort.dir;
      return String(av).localeCompare(String(bv)) * sort.dir;
    });
    return r;
  }, [cells, sort, q, statusFilter]);


  const headers = [
    ['id', 'CELL', 'l'], ['site', 'SITE', 'l'], ['region', 'REGION', 'l'], ['band', 'BAND', 'l'],
    ['pci', 'PCI', 'r'], ['dl', 'DL Mbps', 'r'], ['ul', 'UL Mbps', 'r'], ['ue', 'UEs', 'r'],
    ['sinr', 'SINR dB', 'r'], ['cqi', 'CQI', 'r'], ['bler', 'BLER %', 'r'], ['prb', 'PRB %', 'r'],
  ];
  const num = (v, d = 1) => (typeof v === 'number' ? v.toFixed(d) : '—');

  const onHeaderClick = (k) => {
    setSort(s => s.key === k ? { key: k, dir: -s.dir } : { key: k, dir: 1 });
  };

  return (
    <div className="panel" style={{ overflow: 'hidden', padding: 0 }}>
      <div className="panel-head" style={{ padding: 'var(--pad-panel)', paddingBottom: 12 }}>
        <div className="titles">
          <h3 className="panel-title">Cell Performance</h3>
          <div className="panel-sub">{filtered.length} of {cells.length} cells · click row to drill in</div>
        </div>
      </div>
      <div style={{ overflow: 'auto', maxHeight: 460 }}>
        <table className="tbl">
          <thead>
            <tr>
              {headers.map(([k, l, a]) => (
                <th key={k} style={{ textAlign: a === 'r' ? 'right' : 'left', cursor: 'pointer' }}
                    onClick={() => onHeaderClick(k)}>
                  {l}{sort.key === k ? (sort.dir > 0 ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(c => {
              const inConflict = window.PCI_DATA.CONFLICTS.some(cf => cf.cells.includes(c.id));
              return (
                <tr key={c.id} className={selectedId === c.id ? 'selected' : ''} onClick={() => onSelect && onSelect(c)}>
                  <td className="id">{c.id}</td>
                  <td>{c.site}</td>
                  <td className="muted">{c.region}</td>
                  <td className="muted">{c.band || '—'}</td>
                  <td className="num">
                    {inConflict ? <span style={{ color: 'var(--crit)', fontWeight: 600 }}>{c.pci} ⚠</span> : c.pci}
                  </td>
                  <td className="num">{num(c.dl)}</td>
                  <td className="num">{num(c.ul)}</td>
                  <td className="num">{typeof c.ue === 'number' ? c.ue : '—'}</td>
                  <td className="num" style={{ color: typeof c.sinr === 'number' && c.sinr < 5 ? 'var(--warn)' : undefined }}>{num(c.sinr)}</td>
                  <td className="num">{num(c.cqi)}</td>
                  <td className="num" style={{ color: typeof c.bler === 'number' && c.bler > 5 ? 'var(--warn)' : undefined }}>{num(c.bler, 2)}</td>
                  <td className="num">
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      <span style={{
                        width: 36, height: 4, background: 'var(--bg-3)', borderRadius: 2,
                        position: 'relative', overflow: 'hidden'
                      }}>
                        <span style={{
                          position: 'absolute', inset: 0, width: c.prb + '%',
                          background: c.prb > 75 ? 'var(--warn)' : 'var(--accent)',
                          borderRadius: 2,
                        }}/>
                      </span>
                      {c.prb}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};


const DrilldownDrawer = ({ cell, onClose, onShowOnMap }) => {

  const [replanState, setReplanState] = React.useState('idle');
  const [proposal, setProposal]       = React.useState(null);
  const [replanErr, setReplanErr]     = React.useState(null);

  React.useEffect(() => {
    setReplanState('idle'); setProposal(null); setReplanErr(null);
  }, [cell?.id]);

  if (!cell) return (
    <>
      <div className="drawer-mask" data-on="0"/>
      <div className="drawer" data-on="0"/>
    </>
  );
  const conflicts = (window.PCI_DATA.CONFLICTS || []).filter(c => (c.cells || []).includes(cell.id));

  const startReplan = async () => {
    setReplanState('proposing'); setReplanErr(null);
    try {
      const r = await fetch('/api/replan/propose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cell_id: cell.id }),
      });
      const data = await r.json();
      if (!data.ok) { setReplanErr(data.error || 'Propose failed'); setReplanState('error'); return; }
      setProposal(data);
      setReplanState('proposed');
    } catch (e) {
      setReplanErr(e.message || 'Network error');
      setReplanState('error');
    }
  };
  const commitReplan = async () => {
    if (!proposal) return;
    setReplanState('committing'); setReplanErr(null);
    try {
      const r = await fetch('/api/replan/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cell_id: cell.id, proposed_pci: proposal.proposed_pci }),
      });
      const data = await r.json();
      if (!data.ok) { setReplanErr(data.error || 'Commit failed'); setReplanState('error'); return; }
      window.reloadPciData(undefined, { quiet: true });
      setTimeout(() => { onClose && onClose(); }, 400);
    } catch (e) {
      setReplanErr(e.message || 'Network error');
      setReplanState('error');
    }
  };
  const cancelReplan = () => { setReplanState('idle'); setProposal(null); setReplanErr(null); };

  return (
    <>
      <div className="drawer-mask" data-on="1" onClick={onClose}/>
      <div className="drawer" data-on="1">
        <div className="drawer-head">
          <div>
            <div className="row-h" style={{ gap: 10 }}>
              <span className={`chip ${cell.status === 'active' ? 'ok' : cell.status === 'degraded' ? 'warn' : cell.status === 'maintenance' ? 'maint' : 'idle'}`}>
                <span className="dot"/>{cell.status}
              </span>
              <span className="mono" style={{ color: 'var(--fg-3)', fontSize: 12 }}>PCI {cell.pci} · {cell.band} · sector {cell.sector}</span>
            </div>
            <h2 style={{ margin: '8px 0 2px', fontSize: 22, fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '-0.02em' }}>
              {cell.id}
            </h2>
            <div style={{ fontSize: 14, color: 'var(--fg-2)' }}>{cell.site} · {cell.region}</div>
          </div>
          <button className="btn-sm" onClick={onClose}><Icon name="x" size={13}/></button>
        </div>
        <div className="drawer-body">
          <div className="drawer-grid">
            <div><div className="l">DL Throughput</div><div className="v">{cell.dl.toFixed(1)} Mbps</div></div>
            <div><div className="l">UL Throughput</div><div className="v">{cell.ul.toFixed(1)} Mbps</div></div>
            <div><div className="l">PRB Usage</div><div className="v">{cell.prb}%</div></div>
            <div><div className="l">UE Connected</div><div className="v">{cell.ue}</div></div>
            <div><div className="l">BLER</div><div className="v">{cell.bler}%</div></div>
            <div><div className="l">CQI / SINR</div><div className="v">{cell.cqi.toFixed(1)} / {cell.sinr.toFixed(1)} dB</div></div>
            <div><div className="l">Mod-3 Group</div><div className="v">{cell.pci % 3}</div></div>
            <div><div className="l">Neighbours</div><div className="v">{cell.neighborCount ?? (cell.neighbors || []).length}</div></div>
          </div>
          {conflicts.length > 0 && (
            <div>
              <div style={{ fontSize: 12, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Active Conflicts</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {conflicts.map(c => (
                  <div key={c.id} style={{
                    padding: 10, borderRadius: 6,
                    border: '1px solid var(--line)',
                    background: 'var(--bg-3)',
                    fontSize: 13.5, color: 'var(--fg-2)'
                  }}>
                    <div className="row-h" style={{ gap: 8, marginBottom: 4 }}>
                      <span className={`chip ${c.severity === 'critical' ? 'crit' : c.severity === 'major' ? 'warn' : 'info'}`}>
                        <span className="dot"/>{c.severity}
                      </span>
                      <span className="mono" style={{ color: 'var(--fg)', fontSize: 13 }}>{c.id}</span>
                      <span style={{ marginLeft: 'auto', textTransform: 'uppercase', fontSize: 12, letterSpacing: '0.04em' }}>{c.type}</span>
                    </div>
                    <div>{c.impact}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div>
            <div style={{ fontSize: 12, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
              Neighbour PCIs{(cell.neighborCount ?? 0) > (cell.neighbors || []).length ? ` · first ${(cell.neighbors || []).length} of ${cell.neighborCount}` : ''}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {(cell.neighbors || []).map(n => (
                <span key={n} className="mono" style={{ padding: '4px 9px', border: '1px solid var(--line-2)', borderRadius: 4, fontSize: 13, color: 'var(--fg-2)' }}>
                  PCI {n}
                </span>
              ))}
              {!(cell.neighbors || []).length && (
                <span style={{ fontSize: 13, color: 'var(--fg-3)' }}>No neighbour relations reported for this cell.</span>
              )}
            </div>
          </div>
          {replanState === 'idle' && (
            <div className="row-h" style={{ gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
              {conflicts.length > 0 ? (
                <button className="btn-sm primary" onClick={startReplan}>
                  <Icon name="refresh" size={12}/>Re-plan PCI
                </button>
              ) : (
                <span className="cell-ok-pill" title="PCI assignment is healthy — no re-plan required">
                  <Icon name="check" size={12}/>
                  No action needed
                  <span className="sub">PCI {cell.pci} is conflict-free</span>
                </span>
              )}
              <button className="btn-sm" onClick={() => onShowOnMap && onShowOnMap(cell)}>
                <Icon name="map" size={12}/>Show on map
              </button>
            </div>
          )}
          {replanState === 'proposing' && (
            <div className="replan-card" data-state="busy">
              <div className="replan-card-head">
                <span className="mono" style={{ color: 'var(--accent)' }}>● proposing</span>
                <span style={{ color: 'var(--fg-3)', fontSize: 13 }}>Searching pool for a safe PCI…</span>
              </div>
            </div>
          )}
          {replanState === 'proposed' && proposal && (
            <div className="replan-card" data-state="ready">
              <div className="replan-card-head">
                <span className="mono" style={{ color: 'var(--accent)', fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase' }}>● Proposal ready</span>
                <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{proposal.free_pcis_remaining} free PCIs in pool</span>
              </div>
              <div className="replan-card-swap">
                <div className="replan-pci old"><div className="lbl">CURRENT</div><div className="v">PCI {proposal.old_pci}</div></div>
                <div className="replan-arrow"><Icon name="arrowRt" size={20}/></div>
                <div className="replan-pci new"><div className="lbl">PROPOSED</div><div className="v">PCI {proposal.proposed_pci}</div></div>
              </div>
              <div className="replan-reasons">
                {proposal.reason.split(' · ').map((r, i) => (
                  <div key={i} className="replan-reason"><span>✓</span>{r}</div>
                ))}
                {!proposal.mod3_safe && (
                  <div className="replan-reason warn">⚠ mod-3 group fully occupied — minor PUSCH DMRS risk remains</div>
                )}
              </div>
              <div className="row-h" style={{ gap: 8, marginTop: 12 }}>
                <button className="btn-sm primary" onClick={commitReplan}>
                  <Icon name="refresh" size={12}/>Confirm re-plan
                </button>
                <button className="btn-sm" onClick={cancelReplan}>Cancel</button>
              </div>
            </div>
          )}
          {replanState === 'committing' && (
            <div className="replan-card" data-state="busy">
              <div className="replan-card-head">
                <span className="mono" style={{ color: 'var(--accent)' }}>● committing</span>
                <span style={{ color: 'var(--fg-3)', fontSize: 13 }}>Applying PCI swap…</span>
              </div>
            </div>
          )}
          {replanState === 'error' && (
            <div className="replan-card" data-state="error">
              <div className="replan-card-head">
                <span className="mono" style={{ color: 'var(--crit)' }}>● error</span>
                <span style={{ color: 'var(--fg-2)', fontSize: 13 }}>{replanErr}</span>
              </div>
              <div className="row-h" style={{ gap: 8, marginTop: 10 }}>
                <button className="btn-sm" onClick={cancelReplan}>Dismiss</button>
                <button className="btn-sm primary" onClick={startReplan}>Retry</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
};


const TopologyPanel = ({ onSelect }) => {
  const cells = window.PCI_DATA.CELLS;
  const conflicts = window.PCI_DATA.CONFLICTS;
  const conflictedIds = new Set(conflicts.flatMap(c => c.cells));
  const regions = window.PCI_DATA.REGIONS_HEALTH;


  const lats = cells.map(c => c.lat);
  const lngs = cells.map(c => c.lng);
  const latMin = lats.length ? Math.min(...lats) : 0;
  const latMax = lats.length ? Math.max(...lats) : 1;
  const lngMin = lngs.length ? Math.min(...lngs) : 0;
  const lngMax = lngs.length ? Math.max(...lngs) : 1;
  const latSpan = (latMax - latMin) || 1;
  const lngSpan = (lngMax - lngMin) || 1;

  const W = 460, H = 280, padX = 28, padY = 22;
  const xy = (lat, lng) => ({
    x: padX + ((lng - lngMin) / lngSpan) * (W - 2 * padX),
    y: padY + (1 - (lat - latMin) / latSpan) * (H - 2 * padY),
  });


  const sev = (r) => r.conflicts === 0 ? 'ok' : r.conflicts >= 3 ? 'crit' : 'warn';
  const barClass = (pct) => pct >= 90 ? 'ok' : pct >= 75 ? 'warn' : 'crit';
  const sortedRegions = [...regions].sort((a, b) => {
    if (b.conflicts !== a.conflicts) return b.conflicts - a.conflicts;
    return a.pct - b.pct;
  });

  return (
    <div className="panel topo-panel">
      <div className="topo-head">
        <div className="topo-head-titles">
          <h4>Topology</h4>
          <span className="topo-head-sub">{cells.length} cells · {regions.length} regions</span>
        </div>
        <button className="btn-sm"><Icon name="layers" size={12}/>Layers</button>
      </div>

      <div className="topo-canvas">
        <div className="topo-legend">
          <div className="topo-legend-title">Status</div>
          <div className="topo-legend-row"><span className="topo-legend-dot" style={{ background: 'var(--accent)', color: 'var(--accent)' }}/>Active</div>
          <div className="topo-legend-row"><span className="topo-legend-dot" style={{ background: 'var(--crit)', color: 'var(--crit)' }}/>In conflict</div>
          <div className="topo-legend-row"><span className="topo-legend-dot" style={{ background: 'var(--warn)', color: 'var(--warn)' }}/>Degraded</div>
          <div className="topo-legend-row"><span className="topo-legend-dot" style={{ background: 'var(--maint)', color: 'var(--maint)' }}/>Maintenance</div>
        </div>
        <div className="topo-compass">
          <span className="topo-compass-needle">
            <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2 L14 11 L12 22 L10 11 Z" fill="currentColor"/>
            </svg>
          </span>
          <span>N · live grid</span>
        </div>

        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          <defs>
            <radialGradient id="topo-pulse">
              <stop offset="0%" stopColor="var(--crit)" stopOpacity="0.45"/>
              <stop offset="100%" stopColor="var(--crit)" stopOpacity="0"/>
            </radialGradient>
          </defs>
          {conflicts.flatMap(cf => {
            if (cf.cells.length < 2) return [];
            const points = cf.cells.map(id => cells.find(c => c.id === id)).filter(Boolean);
            return points.slice(1).map((p, i) => {
              const a = xy(points[0].lat, points[0].lng);
              const b = xy(p.lat, p.lng);
              return <line key={cf.id + i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={cf.severity === 'critical' ? 'var(--crit)' : cf.severity === 'major' ? 'var(--warn)' : 'var(--info)'}
                strokeWidth="1.1" strokeDasharray="3 4" opacity="0.55" />;
            });
          })}
          {cells.map(c => {
            const { x, y } = xy(c.lat, c.lng);
            const isConfl = conflictedIds.has(c.id);
            const fill =
              c.status === 'active' ? (isConfl ? 'var(--crit)' : 'var(--accent)') :
              c.status === 'degraded' ? 'var(--warn)' :
              c.status === 'maintenance' ? 'var(--maint)' : 'var(--fg-4)';
            return (
              <g key={c.id} style={{ cursor: 'pointer' }} onClick={() => onSelect && onSelect(c)}>
                {isConfl && (
                  <circle cx={x} cy={y} r="14" fill="url(#topo-pulse)">
                    <animate attributeName="r" values="9;16;9" dur="2.4s" repeatCount="indefinite"/>
                    <animate attributeName="opacity" values="0.9;0.1;0.9" dur="2.4s" repeatCount="indefinite"/>
                  </circle>
                )}
                <circle cx={x} cy={y} r={isConfl ? 4.2 : 3.4} fill={fill} stroke="var(--bg)" strokeWidth="1.2"/>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="topo-regions">
        {sortedRegions.map(r => {
          const s = sev(r);
          return (
            <div key={r.name} className={`topo-region ${s}`}>
              <div className="topo-region-head">
                <span className="topo-region-name">{r.name}</span>
                <span className="topo-region-status">
                  {r.conflicts === 0 ? (
                    <span className="check">
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 6 9 17l-5-5"/>
                      </svg>
                      Healthy
                    </span>
                  ) : (
                    <>
                      <span className="n">{r.conflicts}</span>
                      <span className="l">{r.conflicts === 1 ? 'Issue' : 'Issues'}</span>
                    </>
                  )}
                </span>
              </div>
              <div className="topo-region-body">
                <div className="topo-region-bar">
                  <div className={`topo-region-bar-fill ${barClass(r.pct)}`} style={{ width: r.pct + '%' }}/>
                </div>
                <span className="pct">{r.pct}%</span>
              </div>
              <div className="meta" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', fontWeight: 600 }}>
                {r.ok} / {r.cells} cells active
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};


Object.assign(window, {
  Icon, KpiStrip, ChartPanel, AlertsPanel, PciPoolPanel,
  CellTable, DrilldownDrawer, TopologyPanel,
  buildConflictHistory, spanLabel, computePulse, feedStatus, FeedPill,
});
