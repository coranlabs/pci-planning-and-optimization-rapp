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

const BASEMAP_URL = { light: '', dark: '' };

function planMapStyle(theme) {
  if (BASEMAP_URL[theme]) return BASEMAP_URL[theme];
  return {
    version: 8,
    sources: {},
    layers: [{
      id: 'background',
      type: 'background',
      paint: { 'background-color': theme === 'dark' ? '#0F1115' : '#EEF1F5' },
    }],
  };
}

const EMPTY_FC = { type: 'FeatureCollection', features: [] };
const RESOLVED_COLOR = '#15803d';
const CHANGED_COLOR = '#15803d';


const EDGE_STYLE = {
  collision: { color: '#dc2626', width: 3 },
  confusion: { color: '#f59e0b', width: 2.2 },
  mod3:      { color: '#8b5cf6', width: 1.4 },
  mod4:      { color: '#0ea5e9', width: 1.2 },
  mod30:     { color: '#14b8a6', width: 1.2 },
};
const CLASS_LABEL = {
  collision: 'Collision', confusion: 'Confusion',
  mod3: 'Mod-3', mod4: 'Mod-4', mod30: 'Mod-30',
};
const CLASS_MEANING = {
  collision: 'Neighbours sharing a PCI',
  confusion: 'Two neighbours a UE cannot tell apart',
  mod3: 'Reference signals aligned',
  mod4: 'PBCH DM-RS aligned',
  mod30: 'UL DM-RS group aligned',
};


function pciColor(pci) {
  if (pci === null || pci === undefined) return '#94a3b8';
  const hue = (Number(pci) * 137.508) % 360;
  return `hsl(${hue.toFixed(1)}, 62%, 48%)`;
}

function PlanView({ embedded }) {
  const [plans, setPlans] = React.useState([]);
  const [plan, setPlan] = React.useState(null);
  const [side, setSide] = React.useState('before');
  const [colorBy, setColorBy] = React.useState('status');
  const [filter, setFilter] = React.useState('auto');
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState(null);
  const fileRef = React.useRef(null);

  const loadList = React.useCallback(() => {
    fetch('/api/plan').then(r => r.json()).then(setPlans).catch(() => {});
  }, []);
  React.useEffect(() => { loadList(); }, [loadList]);

  const openPlan = React.useCallback((id) => {
    fetch(`/api/plan/${id}`)
      .then(r => r.json())
      .then(p => { setPlan(p); setSide('before'); })
      .catch(e => setMsg({ kind: 'err', text: String(e) }));
  }, []);

  async function upload(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    setBusy(true); setMsg(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/plan/upload', { method: 'POST', body: fd });
      const body = await res.json();
      if (!body.ok) {
        const rows = (body.invalid_rows || [])
          .map(r => `row ${r.row}${r.cell_id ? ` (${r.cell_id})` : ''}: ${r.reason}`)
          .slice(0, 5);
        setMsg({ kind: 'err', text: body.error || 'Upload failed', rows });
      } else {
        setMsg({
          kind: 'ok',
          text: `Imported ${body.rows} cells — ${body.before.total} conflicts before, ` +
                `${body.after.total} after, ${body.changes} PCI change(s).` +
                (body.dangling_neighbors
                  ? ` ${body.dangling_neighbors} neighbour reference(s) pointed at cells not in the sheet and were ignored.`
                  : ''),
        });
        loadList();
        openPlan(body.plan_id);
      }
    } catch (e) {
      setMsg({ kind: 'err', text: String(e) });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  const view = plan ? plan[side] : null;
  const delta = plan ? plan.before.summary.total - plan.after.summary.total : 0;

  const actions = (
    <>
      {plan && (
        <a className="btn-sm" href={`/api/plan/${plan.id}/export`} download
          title="The same sheet with our optimised PCIs">
          <Icon name="download" size={12}/>Optimised plan
        </a>
      )}
      <a className="btn-sm" href="/api/plan/template" download>
        <Icon name="file" size={12}/>Template
      </a>
      <button className="btn-sm primary" disabled={busy}
        onClick={() => fileRef.current && fileRef.current.click()}>
        <Icon name="upload" size={12}/>{busy ? 'Importing…' : 'Import plan'}
      </button>
    </>
  );

  return (
    <>
      <div className={embedded ? 'plan-toolbar' : ''}>
      {!embedded && <SectionHead title="PCI Plan" subtitle="" actions={actions}/>}
      {embedded && <div className="plan-toolbar-inner">{actions}</div>}
      <input ref={fileRef} type="file" accept=".xlsx,.xls"
        style={{ display: 'none' }} onChange={upload}/>
      </div>

      {msg && (
        <div className={`plan-banner ${msg.kind}`}>
          <Icon name={msg.kind === 'ok' ? 'check' : 'alert'} size={14}/>
          <div>
            <div>{msg.text}</div>
            {msg.rows && msg.rows.length > 0 && (
              <ul className="plan-banner-rows">
                {msg.rows.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}

      {!plan && <PlanEmpty plans={plans} onOpen={openPlan} onImported={(id) => { loadList(); openPlan(id); }}
        onPick={() => fileRef.current && fileRef.current.click()}/>}

      {plan && (
        <>
          <div className="plan-stats">
            <PlanStat label="Cells in plan" value={plan.cell_count}
              hint={`${plan.changes.length} re-assigned`}/>
            <PlanStat label="Conflicts before" value={plan.before.summary.total}
              hint={`${plan.before.summary.hard} hard · ${plan.before.summary.total - plan.before.summary.hard} mod-N`}/>
            <PlanStat label="Conflicts after" value={plan.after.summary.total}
              tone={delta > 0 ? 'ok' : delta < 0 ? 'bad' : undefined}
              hint={`${plan.after.resolved_count} resolved · ${plan.after.new_count} new`}/>
            <PlanStat
              label={delta >= 0 ? 'Conflicts removed' : 'Conflicts added'}
              value={Math.abs(delta)}
              tone={delta > 0 ? 'ok' : delta < 0 ? 'bad' : undefined}
              hint={plan.before.summary.total
                ? `${Math.round(Math.abs(delta) / plan.before.summary.total * 100)}% of the original count`
                : '—'}/>
          </div>

          <div className="plan-grid">
            <div className="panel plan-map-panel">
              <div className="plan-map-head">
                <div className="titles">
                  <h3 className="panel-title">{plan.filename}</h3>
                  <div className="panel-sub">
                    {side === 'before'
                      ? 'As supplied by the operator — sectors fanned along their azimuth'
                      : 'After optimisation — re-assigned cells ringed, resolved pairs in green'}
                  </div>
                </div>
                <div className="ab-toggle" role="group" aria-label="Compare plan states">
                  <button className={side === 'before' ? 'on' : ''}
                    onClick={() => setSide('before')}>BEFORE</button>
                  <button className={side === 'after' ? 'on' : ''}
                    onClick={() => setSide('after')}>AFTER</button>
                </div>
              </div>

              <div className="plan-map-controls">
                <span className="ctl-label">Colour</span>
                <div className="seg sm">
                  <button data-on={colorBy === 'status' ? 1 : undefined}
                    onClick={() => setColorBy('status')}>Status</button>
                  <button data-on={colorBy === 'pci' ? 1 : undefined}
                    onClick={() => setColorBy('pci')}>PCI</button>
                </div>
                <span className="ctl-label">Edges</span>
                <div className="seg sm">
                  <button data-on={filter === 'collision' ? 1 : undefined}
                    onClick={() => setFilter('collision')}>Collisions</button>
                  <button data-on={filter === 'auto' || filter === 'hard' ? 1 : undefined}
                    onClick={() => setFilter('hard')}>Conflicts</button>
                  <button data-on={filter === 'all' ? 1 : undefined}
                    onClick={() => setFilter('all')}>All + mod-N</button>
                  <button data-on={filter === 'none' ? 1 : undefined}
                    onClick={() => setFilter('none')}>Hide</button>
                </div>
              </div>

              <PlanMap view={view} side={side} changes={plan.changes}
                colorBy={colorBy} filter={filter}/>
              <PlanLegend colorBy={colorBy} view={view}/>
            </div>

            <div className="plan-side">
              <ChangeList changes={plan.changes}/>
              <ConflictList view={view} side={side}/>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function PlanEmpty({ plans, onOpen, onPick, onImported }) {
  const [samples, setSamples] = React.useState([]);
  const [loading, setLoading] = React.useState(null);
  React.useEffect(() => {
    fetch('/api/plan/samples').then(r => r.json()).then(setSamples).catch(() => {});
  }, []);

  const runSample = (region) => {
    setLoading(region);
    fetch(`/api/plan/samples/${encodeURIComponent(region)}`, { method: 'POST' })
      .then(r => r.json())
      .then(b => { if (b.plan_id && onImported) onImported(b.plan_id); })
      .finally(() => setLoading(null));
  };

  return (
    <div className="panel plan-empty">
      <div className="plan-empty-icon"><Icon name="upload" size={22}/></div>
      <h3 className="panel-title">Import a cell plan to begin</h3>
      <p className="panel-sub plan-empty-copy">
        A sheet with one row per cell. <b>cell_id, lat, lng, pci, neighbors</b> are
        required; <b>technology, azimuth, arfcn, cell_type</b> are optional.
        The neighbours column is that cell's neighbour relation table — a
        comma-separated list of the cell_ids it can hand over to.
      </p>
      <div className="plan-empty-actions">
        <button className="btn-sm primary" onClick={onPick}>
          <Icon name="upload" size={12}/>Import plan
        </button>
        <a className="btn-sm" href="/api/plan/template" download>
          <Icon name="file" size={12}/>Download template
        </a>
      </div>
      {samples.length > 0 && (
        <div className="plan-recent">
          <div className="ctl-label">Or start from a sample</div>
          <div className="panel-sub" style={{ marginTop: 4, marginBottom: 8 }}>
            Built from the network the rApp has ingested — real coordinates,
            neighbour relations and current PCIs.
          </div>
          <div className="plan-recent-list">
            {samples.map(sm => (
              <button key={sm.id} className="plan-recent-item" disabled={loading === sm.id}
                onClick={() => runSample(sm.id)}>
                <span className="pri-name">{sm.name}</span>
                <span className="pri-meta">
                  {loading === sm.id ? 'Optimising…' : `${sm.cells} cells`}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {plans.length > 0 && (
        <div className="plan-recent">
          <div className="ctl-label">Previously imported</div>
          <div className="plan-recent-list">
            {plans.map(p => (
              <button key={p.id} className="plan-recent-item" onClick={() => onOpen(p.id)}>
                <span className="pri-name">{p.filename}</span>
                <span className="pri-meta">{p.cell_count} cells · {p.changes} changes</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PlanStat({ label, value, hint, tone }) {
  return (
    <div className="panel plan-stat">
      <div className="plan-stat-label">{label}</div>
      <div className={`plan-stat-value${tone ? ' tone-' + tone : ''}`}>{value}</div>
      {hint && <div className="plan-stat-hint">{hint}</div>}
    </div>
  );
}

function PlanLegend({ colorBy, view }) {


  const present = React.useMemo(() => {
    const seen = new Set();
    ((view && view.edges) || []).forEach(e => { if (!e.resolved) seen.add(e.type); });
    return ['collision', 'confusion', 'mod3', 'mod4', 'mod30'].filter(k => seen.has(k));
  }, [view]);
  const anyResolved = ((view && view.edges) || []).some(e => e.resolved);

  return (
    <div className="plan-legend">
      <div className="plegend-group">
        <span className="plegend-head">Cells</span>
        {colorBy === 'pci' ? (
          <span className="plegend-item">
            <i className="plegend-ramp"/>
            <span className="plegend-txt"><b>PCI</b><em>Hue identifies the assigned PCI</em></span>
          </span>
        ) : (
          <>
            {present.map(k => (
              <span className="plegend-item" key={k}>
                <i className="plegend-dot" style={{ background: SEV_COLOR[k] }}/>
                <span className="plegend-txt"><b>{CLASS_LABEL[k]}</b><em>{CLASS_MEANING[k]}</em></span>
              </span>
            ))}
            <span className="plegend-item">
              <i className="plegend-dot" style={{ background: SEV_COLOR.clean }}/>
              <span className="plegend-txt"><b>Clean</b><em>No conflict on this cell</em></span>
            </span>
          </>
        )}
        <span className="plegend-item">
          <i className="plegend-dot ring"/>
          <span className="plegend-txt"><b>Re-assigned</b><em>PCI changed by the plan</em></span>
        </span>
      </div>

      <div className="plegend-group">
        <span className="plegend-head">Relations</span>
        {present.map(k => (
          <span className="plegend-item" key={k}>
            <i className="plegend-line" style={{
              background: EDGE_STYLE[k].color,
              height: Math.max(2, EDGE_STYLE[k].width),
            }}/>
            <span className="plegend-txt"><b>{CLASS_LABEL[k]} pair</b></span>
          </span>
        ))}
        {anyResolved && (
          <span className="plegend-item">
            <i className="plegend-line" style={{ background: RESOLVED_COLOR, height: 2 }}/>
            <span className="plegend-txt"><b>Resolved</b><em>Fixed by the plan</em></span>
          </span>
        )}
        {present.length === 0 && !anyResolved && (
          <span className="plegend-item"><span className="plegend-txt"><em>No conflicting pairs</em></span></span>
        )}
      </div>
    </div>
  );
}


const R_EARTH = 6378137;


const SECTOR_FAN_M = 55;

function offsetLngLat(lat, lng, bearingDeg, metres) {
  const dLat = (metres * Math.cos(bearingDeg * Math.PI / 180)) / 111320;
  const dLng = (metres * Math.sin(bearingDeg * Math.PI / 180)) /
               (111320 * Math.cos(lat * Math.PI / 180) || 1);
  return [lng + dLng, lat + dLat];
}


const SEV_RANK = { collision: 5, confusion: 4, mod3: 3, mod4: 2, mod30: 1 };

function severityByCell(edges) {
  const out = {};
  (edges || []).forEach(e => {
    if (e.resolved) return;
    const r = SEV_RANK[e.type] || 0;
    [e.a, e.b].forEach(id => {
      if (!out[id] || (SEV_RANK[out[id]] || 0) < r) out[id] = e.type;
    });
  });
  return out;
}

const SEV_COLOR = {
  collision: '#dc2626',
  confusion: '#f59e0b',
  mod3: '#8b5cf6',
  mod4: '#0ea5e9',
  mod30: '#14b8a6',
  clean: '#94a3b8',
};

function planCellGeoJSON(view, { colorBy, changedIds, side }) {
  const cells = (view && view.cells) || [];
  const sev = severityByCell(view && view.edges);


  const bySite = new Map();
  cells.forEach(c => {
    const k = `${c.lat},${c.lng}`;
    if (!bySite.has(k)) bySite.set(k, []);
    bySite.get(k).push(c);
  });

  const features = [];
  bySite.forEach(group => {
    group.forEach((c, i) => {
      if (typeof c.lat !== 'number' || typeof c.lng !== 'number') return;
      const bearing = typeof c.azimuth === 'number'
        ? c.azimuth
        : (360 / group.length) * i;

      const metres = group.length > 1 ? SECTOR_FAN_M : 0;
      const [lng, lat] = metres
        ? offsetLngLat(c.lat, c.lng, bearing, metres)
        : [c.lng, c.lat];
      const status = sev[c.id] || 'clean';
      const changed = side === 'after' && changedIds.has(c.id);
      features.push({
        type: 'Feature',
        properties: {
          id: c.id,
          pci: c.pci,
          tech: c.tech || '',
          cellType: c.cell_type || '',
          azimuth: typeof c.azimuth === 'number' ? c.azimuth : null,
          status,
          changed,
          color: colorBy === 'pci' ? pciColor(c.pci) : (SEV_COLOR[status] || SEV_COLOR.clean),
          sortKey: changed ? 3 : (status === 'collision' ? 2 : status === 'confusion' ? 1 : 0),
          anchorLng: c.lng,
          anchorLat: c.lat,
        },
        geometry: { type: 'Point', coordinates: [lng, lat] },
      });
    });
  });
  return { type: 'FeatureCollection', features };
}

function planEdgeGeoJSON(view, positions, filter) {
  const feats = [];
  if (filter === 'none') return { type: 'FeatureCollection', features: [] };
  const hasHard = (view.edges || []).some(
    e => !e.resolved && (e.type === 'collision' || e.type === 'confusion'));
  (view.edges || []).forEach(e => {


    const effective = filter === 'auto' ? (hasHard ? 'hard' : 'all') : filter;
    if (effective === 'hard' && !e.resolved
        && e.type !== 'collision' && e.type !== 'confusion') return;
    if (effective === 'collision' && e.type !== 'collision' && !e.resolved) return;
    const a = positions[e.a], b = positions[e.b];
    if (!a || !b) return;
    feats.push({
      type: 'Feature',
      properties: {
        color: e.resolved ? RESOLVED_COLOR : (EDGE_STYLE[e.type] || EDGE_STYLE.confusion).color,
        resolved: !!e.resolved,
        weight: e.resolved ? 1 : (e.type === 'collision' ? 3 : 2),
      },
      geometry: { type: 'LineString', coordinates: [a, b] },
    });
  });
  return { type: 'FeatureCollection', features: feats };
}


function addPlanLayers(m) {
  if (!m.getSource('plan-edges')) {
    m.addSource('plan-edges', { type: 'geojson', data: EMPTY_FC });
  }
  if (!m.getSource('plan-cells')) {
    m.addSource('plan-cells', { type: 'geojson', data: EMPTY_FC });
  }

  if (!m.getLayer('plan-edges')) {
    m.addLayer({
      id: 'plan-edges',
      type: 'line',
      source: 'plan-edges',
      layout: { 'line-cap': 'round' },
      paint: {
        'line-color': ['get', 'color'],
        'line-width': ['interpolate', ['linear'], ['zoom'],
          9, ['*', ['get', 'weight'], 0.35],
          13, ['*', ['get', 'weight'], 0.8],
          16, ['*', ['get', 'weight'], 1.6]],


        'line-opacity': ['case',
          ['get', 'resolved'], 0.55,
          ['==', ['get', 'weight'], 3], 0.6,
          0.2],
      },
    });
  }


  if (!m.getLayer('plan-cells')) {
    m.addLayer({
      id: 'plan-cells',
      type: 'circle',
      source: 'plan-cells',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'],
          8, 2.4, 11, 4.2, 14, 7, 17, 12],
        'circle-color': ['get', 'color'],
        'circle-stroke-width': ['case', ['get', 'changed'], 2.2, 1],
        'circle-stroke-color': ['case', ['get', 'changed'], CHANGED_COLOR,
          document.documentElement.classList.contains('theme-light') ? '#ffffff' : '#0E1428'],
        'circle-opacity': 0.95,
      },
    });
  }
}

function PlanMap({ view, side, changes, colorBy, filter }) {
  const elRef = React.useRef(null);
  const mapRef = React.useRef(null);
  const [ready, setReady] = React.useState(false);
  const themeObsRef = React.useRef(null);
  const fittedRef = React.useRef(null);
  const changedIds = React.useMemo(
    () => new Set((changes || []).map(c => c.cell_id)), [changes]
  );

  React.useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const theme = document.documentElement.classList.contains('theme-light') ? 'light' : 'dark';
    const cells = (view && view.cells) || [];
    const valid = cells.filter(c => typeof c.lat === 'number' && typeof c.lng === 'number');
    const center = valid.length
      ? [valid.reduce((a, c) => a + c.lng, 0) / valid.length,
         valid.reduce((a, c) => a + c.lat, 0) / valid.length]
      : [-6.26, 53.35];

    const m = new window.maplibregl.Map({
      container: elRef.current,
      style: planMapStyle(theme),
      center, zoom: 11, minZoom: 3, maxZoom: 18,
      attributionControl: { compact: true },
    });
    m.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    m.addControl(new window.maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    m.on('load', () => {
      addPlanLayers(m);

      const pop = new window.maplibregl.Popup({
        offset: 12, closeButton: false, className: 'plan-pop',
      });
      m.on('mouseenter', 'plan-cells', () => { m.getCanvas().style.cursor = 'pointer'; });
      m.on('mouseleave', 'plan-cells', () => {
        m.getCanvas().style.cursor = '';
        pop.remove();
      });
      m.on('mousemove', 'plan-cells', (ev) => {
        const f = ev.features && ev.features[0];
        if (!f) return;
        const p = f.properties;
        pop.setLngLat(f.geometry.coordinates)
          .setHTML(
            `<div class="plan-pop-body">
               <div class="plan-pop-id">${p.id}</div>
               <div class="plan-pop-row"><span>PCI</span><b>${p.pci}</b></div>
               <div class="plan-pop-row"><span>Status</span><b class="sev-${p.status}">${p.status}</b></div>
               ${p.azimuth !== null && p.azimuth !== undefined
                 ? `<div class="plan-pop-row"><span>Azimuth</span><b>${p.azimuth}°</b></div>` : ''}
               <div class="plan-pop-row"><span>Type</span><b>${(p.tech || '').toUpperCase()} · ${p.cellType}</b></div>
               ${p.changed === true || p.changed === 'true'
                 ? '<div class="plan-pop-changed">Re-assigned by the plan</div>' : ''}
             </div>`)
          .addTo(m);
      });
      setReady(true);
    });
    mapRef.current = m;
    window.__planMap = m;


    let current = theme;
    const obs = new MutationObserver(() => {
      const next = document.documentElement.classList.contains('theme-light') ? 'light' : 'dark';
      if (next === current) return;
      current = next;
      setReady(false);
      m.setStyle(planMapStyle(next));

      m.once('styledata', () => { addPlanLayers(m); setReady(true); });
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    themeObsRef.current = obs;
    return () => {
      if (themeObsRef.current) themeObsRef.current.disconnect();
      m.remove(); mapRef.current = null; window.__planMap = null; setReady(false);
    };

  }, []);

  React.useEffect(() => {
    const m = mapRef.current;
    if (!m || !ready || !view) return;

    const cellFC = planCellGeoJSON(view, { colorBy, changedIds, side });


    const pos = {};
    cellFC.features.forEach(f => { pos[f.properties.id] = f.geometry.coordinates; });

    m.getSource('plan-cells').setData(cellFC);
    m.getSource('plan-edges').setData(planEdgeGeoJSON(view, pos, filter));


    const key = (view.cells || []).length + ':' + (view.cells || [])[0]?.id;
    if (fittedRef.current !== key && cellFC.features.length > 1) {
      fittedRef.current = key;
      const c0 = cellFC.features[0].geometry.coordinates;
      const b = new window.maplibregl.LngLatBounds(c0, c0);
      cellFC.features.forEach(f => b.extend(f.geometry.coordinates));
      m.fitBounds(b, { padding: 70, maxZoom: 14, duration: 500 });
    }
  }, [view, side, ready, colorBy, filter, changedIds]);

  return <div ref={elRef} className="plan-map"/>;
}
function ChangeList({ changes }) {
  return (
    <div className="panel plan-list-panel">
      <div className="panel-head"><div className="titles">
        <h3 className="panel-title">Recommended changes</h3>
        <div className="panel-sub">{changes.length} cell{changes.length === 1 ? '' : 's'} re-assigned</div>
      </div></div>
      {changes.length === 0
        ? <div className="plan-empty-row">No changes required — the plan is already conflict-free.</div>
        : (
          <div className="plan-scroll">
            {changes.map((c, i) => (
              <div key={`${c.cell_id}-${i}`} className="plan-change">
                <span className="pc-id" title={c.cell_id}>{c.cell_id}</span>
                <span className="pc-pci">
                  <b style={{ color: pciColor(c.pci_old) }}>{c.pci_old}</b>
                  <i className="pc-arrow">→</i>
                  <b style={{ color: pciColor(c.pci_new) }}>{c.pci_new}</b>
                </span>
              </div>
            ))}
          </div>
        )}
    </div>
  );
}

function ConflictList({ view, side }) {
  const edges = (view && view.edges) || [];
  const shown = edges.slice(0, 300);
  return (
    <div className="panel plan-list-panel">
      <div className="panel-head"><div className="titles">
        <h3 className="panel-title">Conflicts · {side.toUpperCase()}</h3>
        <div className="panel-sub">
          {edges.length} pair{edges.length === 1 ? '' : 's'}
          {edges.length > shown.length ? ` · showing first ${shown.length}` : ''}
        </div>
      </div></div>
      {edges.length === 0
        ? <div className="plan-empty-row">No collision or confusion pairs.</div>
        : (
          <div className="plan-scroll">
            {shown.map((e, i) => (
              <div key={i} className="plan-conflict">
                <span className="pcf-pair">
                  <span title={e.a}>{e.a}</span>
                  <i className="pcf-link"/>
                  <span title={e.b}>{e.b}</span>
                </span>
                <span className={`pcf-tag ${e.resolved ? 'resolved' : e.type}`}>
                  {e.resolved ? 'resolved' : e.type}
                </span>
              </div>
            ))}
          </div>
        )}
    </div>
  );
}
