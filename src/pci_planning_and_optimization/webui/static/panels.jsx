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

