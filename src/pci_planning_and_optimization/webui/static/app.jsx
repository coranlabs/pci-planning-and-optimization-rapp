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

function useTheme() {
  const [theme, setThemeState] = React.useState(() => {
    try { const t = localStorage.getItem('pci-theme'); if (t === 'light' || t === 'dark') return t; } catch (e) {}
    return document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light';
  });
  const setTheme = (v) => {
    if (v !== 'light' && v !== 'dark') return;
    setThemeState(v);
    try { localStorage.setItem('pci-theme', v); } catch (e) {}
  };
  return [theme, setTheme];
}


function useSettings() {
  const [s, setS] = React.useState(() => ({ ...(window.PCI_SETTINGS || {}) }));
  React.useEffect(() => {
    if (window.subscribeSettings) {
      window.subscribeSettings((next) => setS({ ...next }));
    }
  }, []);
  return s;
}


function AvatarMenu({ onToggleTheme, theme, onNavigate }) {
  const settings = useSettings();
  const name = settings.account_name || 'Operator';
  const initial = name.trim().charAt(0).toUpperCase() || 'O';
  const [open, setOpen] = React.useState(false);
  const wrapRef = React.useRef(null);
  React.useEffect(() => {
    function onDocClick(e) { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); }
    function onKey(e)      { if (e.key === 'Escape') setOpen(false); }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, []);
  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button className="avatar avatar-btn" onClick={() => setOpen(o => !o)} aria-label="Account menu" data-on={open ? 1 : 0}>{initial}</button>
      {open && (
        <div className="user-menu">
          <div className="user-menu-head">
            <div style={{ fontWeight: 600, color: 'var(--fg)', fontSize: 13.5 }}>{name}</div>
          </div>
          <div className="user-menu-list">
            <button className="user-menu-item" onClick={() => { setOpen(false); onNavigate && onNavigate('settings'); }}>
              <Icon name="settings" size={14}/><span>Account &amp; settings</span>
            </button>
            <button className="user-menu-item" onClick={() => { setOpen(false); onToggleTheme(); }}>
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={14}/>
              <span>Switch to {theme === 'dark' ? 'light' : 'dark'} theme</span>
            </button>
            <button className="user-menu-item" onClick={() => {
              setOpen(false);
              fetch('/api/auth/logout', { method: 'POST' })
                .catch(() => {})
                .finally(() => { window.location.replace('/login'); });
            }}>
              <Icon name="logout" size={14}/><span>Sign out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


function TopBar({ onToggleTheme, theme, sectionTitle, onSelectCell, onNavigate }) {
  const [now, setNow] = React.useState(new Date());
  React.useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const tz = (window.PCI_SETTINGS || {}).account_timezone || undefined;
  let t;
  try { t = now.toLocaleTimeString('en-GB', { timeZone: tz, hour12: false }); }
  catch (e) { t = now.toTimeString().slice(0, 8); }
  const feed = feedStatus();

  return (
    <header className="top-bar">
      <div className="brand-block">
        <h1>{sectionTitle}</h1>
      </div>


      <div className="top-meta">
        <span className={feed.cls} title={feed.title}><span className="dot"/>{feed.label}</span>
        <span className="pill" title={tz ? `Clock in ${tz} (Settings → Account)` : 'Local time'}><span className="mono">{t}</span></span>
        <button className="btn-sm" onClick={onToggleTheme} aria-label="Toggle theme">
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={13}/>
        </button>
        <AvatarMenu onToggleTheme={onToggleTheme} theme={theme} onNavigate={onNavigate}/>
      </div>
    </header>
  );
}


const navSub = (k) => (NAV.find(n => n.k === k) || {}).sub || '';

const NAV = [
  { k: 'overview',     icon: 'grid',    label: 'Overview',     title: 'Overview',     sub: 'Real-time pulse across the PCI pool — KPIs, throughput, conflicts and incidents.' },
  { k: 'cell-map',     icon: 'map',     label: 'Cell Map',     title: 'Cell Map',     sub: 'Geo-projected topology with conflict overlays, regional health and per-cell drill-in.' },
  { k: 'pci-planning', icon: 'upload',  label: 'PCI Planning', title: 'PCI Planning', sub: 'Import an operator cell plan, compare the current PCI assignment against the optimised one, and review the resulting activity.' },
  { k: 'settings',     icon: 'settings',label: 'Settings',     title: 'Settings',     sub: 'Alert thresholds, appearance, operator identity and notifications.' },
];

function Sidebar({ active, onSelect, onOpenNotifications }) {
  const settings = useSettings();

  const alertCount = (window.PCI_DATA?.ALERTS || []).filter(a => a.sev === 'critical' || a.sev === 'major').length;

  const productName = settings.brand_product_name || 'PCI Planning and Optimization · rApp';
  const [brandMain, brandTag] = (() => {
    const parts = productName.split(/\s·\s|\s\|\s/);
    if (parts.length >= 2) return [parts[0], parts.slice(1).join(' · ')];
    return [productName, 'rApp'];
  })();
  const logoUrl = settings.brand_logo_url || '';
  return (
    <nav className="rail">
      <div className="rail-brand-row">
        <div className="rail-brand">
          <img
            src={logoUrl || '/static/img/coran-logo.png'}
            alt="Coran Labs"
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        </div>
        <div className="rail-brand-name"><b>{brandMain}</b><small>{brandTag}</small></div>
      </div>
      <div className="rail-section-label">Workspace</div>
      <div className="rail-nav">
        {NAV.map(it => (
          <button key={it.k}
                  className="rail-btn"
                  data-on={active === it.k ? 1 : 0}
                  onClick={() => onSelect(it.k)}>
            <Icon name={it.icon}/>
            <span>{it.label}</span>
          </button>
        ))}
      </div>
      <div className="rail-foot">
        <button className="rail-btn" onClick={onOpenNotifications} title="Recent alerts">
          <Icon name="bell"/>
          <span>Notifications</span>
          {alertCount > 0 && <span className="rail-badge">{alertCount}</span>}
        </button>
        <button className="rail-btn" onClick={() => onSelect('settings')} title="Account & settings">
          <Icon name="settings"/><span>Account</span>
        </button>
      </div>
    </nav>
  );
}


function NotificationsDrawer({ open, onClose, onJumpToAudit }) {
  const alerts = window.PCI_DATA?.ALERTS || [];
  React.useEffect(() => {
    function onKey(e) { if (e.key === 'Escape' && open) onClose(); }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  return (
    <>
      <div className="drawer-mask" data-on={open ? 1 : 0} onClick={onClose}/>
      <aside className="drawer notifications-drawer" data-on={open ? 1 : 0}>
        <div className="drawer-head">
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, letterSpacing: '-0.01em' }}>Notifications</h2>
            <div style={{ fontSize: 13, color: 'var(--fg-3)', marginTop: 4 }}>
              {alerts.length} total · {alerts.filter(a => a.sev === 'critical').length} critical
            </div>
          </div>
          <button className="btn-sm" onClick={onClose}><Icon name="x" size={13}/></button>
        </div>
        <div className="drawer-body">
          {alerts.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--fg-3)' }}>No active alerts.</div>
          )}
          {alerts.map(a => (
            <div key={a.id} className={`alert ${a.sev}`}>
              <span className="bar"/>
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
        </div>
        <div className="drawer-foot">
          <button className="btn-sm primary" onClick={() => { onClose(); onJumpToAudit(); }}>
            Open Audit log
          </button>
        </div>
      </aside>
    </>
  );
}


function SectionHead({ title, subtitle, actions }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="row-h" style={{ gap: 8 }}>{actions}</div>}
    </div>
  );
}


function TechSwitcher({ value, onChange }) {
  const [open, setOpen] = React.useState(false);
  const wrapRef = React.useRef(null);
  const counts = (window.PCI_DATA.meta || {}).cellsByTech || (() => {
    const c = { lte: 0, nr: 0 };
    (window.PCI_DATA.CELLS || []).forEach(x => { const t = x.tech || (String(x.id).startsWith('LT') ? 'lte' : 'nr'); c[t] = (c[t] || 0) + 1; });
    return c;
  })();
  const options = [
    { id: 'nr',  label: '5G NR',  desc: `${counts.nr ?? 0} cells`,  pool: 'PCI 0–1007' },
    { id: 'lte', label: '4G LTE', desc: `${counts.lte ?? 0} cells`, pool: 'PCI 0–503' },
  ];
  const active = options.find(o => o.id === value) || options[0];

  React.useEffect(() => {
    if (!open) return;
    function onDoc(e) { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); }
    function onKey(e) { if (e.key === 'Escape') setOpen(false); }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="tech-switcher" ref={wrapRef}>
      <button className="tech-trigger" data-on={open ? 1 : 0} onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox" aria-expanded={open}>
        <span className="tech-trigger-dot"/>
        <span className="tech-trigger-meta">
          <span className="tech-trigger-label">{active.label}</span>
        </span>
        <svg className="tech-trigger-chev" viewBox="0 0 24 24" width="13" height="13"
          fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="m6 9 6 6 6-6"/>
        </svg>
      </button>
      {open && (
        <div className="tech-menu" role="listbox">
          <div className="tech-menu-head">Select Radio Access Technology</div>
          {options.map(o => (
            <button key={o.id} className="tech-menu-item" data-on={value === o.id ? 1 : 0}
              role="option" aria-selected={value === o.id}
              onClick={() => { onChange(o.id); setOpen(false); }}>
              <span className="tech-menu-marker"/>
              <span className="tech-menu-meta">
                <span className="tech-menu-label">{o.label}</span>
                <span className="tech-menu-sub">{o.desc} <span className="pool">· {o.pool}</span></span>
              </span>
              {value === o.id && (
                <span className="tech-menu-active-pill">Active</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function OverviewView({ onSelectCell, selectedCell, onNavigate }) {

  const tech = window.PCI_TECH || 'nr';
  const setTech = (next) => {
    if (next === tech) return;
    if (window.setPciTech) window.setPciTech(next);
    if (typeof onSelectCell === 'function') onSelectCell(null);
  };
  return (
    <>
      <SectionHead title="Overview" subtitle={navSub('overview')}
        actions={<>
          <TechSwitcher value={tech} onChange={setTech}/>
          <button className="btn-sm" data-busy={window.__PCI_LOADING ? 1 : 0} onClick={() => window.reloadPciData()}>
            <Icon name="refresh" size={12}/>{window.__PCI_LOADING ? 'Refreshing…' : 'Refresh'}
          </button>
          <button className="btn-sm primary" onClick={() => window.exportOverviewJSON()}>
            <Icon name="download" size={12}/>Export
          </button>
        </>}/>
      <KpiStrip onNavigate={onNavigate} />
      <div className="row-primary">
        <ChartPanel />
        <AlertsPanel />
      </div>
      <PciPoolPanel onSelectCell={onSelectCell} tech={tech} />
      <CellTable onSelect={onSelectCell} selectedId={selectedCell?.id} />
    </>
  );
}

const MAP_LEGEND_TITLE = { status: 'Cell Status', heat: 'PRB Utilisation' };


function mapHeatColor(prb) {
  const v = Math.max(0, Math.min(100, Number(prb) || 0));
  return `hsl(${(210 - (v / 100) * 210).toFixed(0)}, 72%, 48%)`;
}
function markerColorFor(cell, mode) {
  return mode === 'heat' ? mapHeatColor(cell.prb) : null;
}


const MAP_COLOR_MODES = [['status','STATUS'],['heat','HEAT']];

function CellMapView({ onSelectCell, selectedCell }) {
  const [colorMode, setColorMode] = React.useState('status');
  const [showOverlays, setShowOverlays] = React.useState(true);
  return (
    <>
      <SectionHead title="Cell Map" subtitle={navSub('cell-map')}
        actions={<>
          <TechSwitcher value={window.PCI_TECH || 'nr'} onChange={(next) => { window.setPciTech(next); onSelectCell(null); }}/>
          <div className="seg">
            {MAP_COLOR_MODES.map(([k, l]) => (
              <button key={k} data-on={colorMode === k ? 1 : undefined}
                onClick={() => setColorMode(k)}>{l}</button>
            ))}
          </div>
          <button className="btn-sm" data-on={showOverlays ? 1 : undefined}
            onClick={() => setShowOverlays(v => !v)}
            title="Show or hide the on-map view, layer and legend panels">
            <Icon name="layers" size={12}/>Layers
          </button>
        </>}/>
      <div className="grid cell-map-grid" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(360px, 1fr)', alignItems: 'flex-start' }}>
        <div className="panel" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 230px)', maxHeight: 820, minHeight: 540 }}>
          <div className="panel-head" style={{ padding: 'var(--pad-panel)', paddingBottom: 8, flexShrink: 0 }}>
            <div className="titles">
              <h3 className="panel-title">Topology · live</h3>
              <div className="panel-sub">{window.PCI_DATA.CELLS.length} cells across {window.PCI_DATA.REGIONS_HEALTH.length} regions</div>
            </div>
            <FeedPill/>
          </div>
          <BigTopo onSelectCell={onSelectCell} selectedCell={selectedCell}
            colorMode={colorMode} showOverlays={showOverlays}/>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <RegionPanel/>
          <AlertsPanel />
        </div>
      </div>
      <CellTable onSelect={onSelectCell} selectedId={selectedCell?.id} />
    </>
  );
}


// Basemap. Blank by default, so the dashboard makes no third-party request,
// works in an air-gapped cluster, and does not hand a tile host the operator's
// map viewport. Set a style URL, your own tile server or a public basemap, for
// street detail.
const BASEMAP_URL = { light: '', dark: '' };

function mapStyle(theme) {
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


const REGION_CITY_CENTRES = {
  Dublin:   [-6.2603, 53.3498],
  Cork:     [-8.4756, 51.8985],
  Galway:   [-9.0568, 53.2707],
  Limerick: [-8.6267, 52.6638],
  Belfast:  [-5.9301, 54.5973],
  Midlands: [-7.9407, 53.4239],
};

function applySky(m, isDark) {
  try {
    m.setSky({
      'sky-color':         isDark ? '#0b1430' : '#cfe3ff',
      'sky-horizon-blend': isDark ? 0.55 : 0.7,
      'horizon-color':     isDark ? '#3a6fb5' : '#7ab0ff',
      'horizon-fog-blend': isDark ? 0.6 : 0.8,
      'fog-color':         isDark ? '#06091a' : '#dbe5f5',
      'fog-ground-blend':  isDark ? 0.5 : 0.7,
    });
  } catch (e) {  }
}


const ARC_SEV_COLOR = ['match', ['get', 'severity'],
  'critical', '#EF4444', 'major', '#F59E0B', '#9DB0D9'];




function BigTopo({ onSelectCell, selectedCell, colorMode = 'status', showOverlays = true }) {

  const colorModeRef = React.useRef(colorMode);
  React.useEffect(() => { colorModeRef.current = colorMode; }, [colorMode]);
  const cells = window.PCI_DATA.CELLS;
  const conflicts = window.PCI_DATA.CONFLICTS;


  const approxCount = React.useMemo(
    () => cells.reduce((n, c) => n + (c.approxPos ? 1 : 0), 0), [cells]);


  const conflictedIds = React.useMemo(
    () => new Set(conflicts.filter(c => c.severity === 'critical' || c.severity === 'major').flatMap(c => c.cells)),
    [conflicts]
  );


  const focusIds = React.useMemo(() => {
    if (!selectedCell) return null;
    const keep = new Set([selectedCell.id]);
    for (const cf of conflicts) {
      if (cf.type !== 'collision' && cf.type !== 'confusion') continue;
      const ids = cf.cells || [];
      if (ids.includes(selectedCell.id)) ids.forEach(id => keep.add(id));
    }
    return keep;
  }, [selectedCell, conflicts]);

  const focusCells = React.useMemo(
    () => (focusIds ? cells.filter(c => focusIds.has(c.id)) : cells),
    [cells, focusIds],
  );
  const mapRef = React.useRef(null);
  const mapEl = React.useRef(null);
  const markersRef = React.useRef([]);

  const [pitch, setPitch] = React.useState(0);
  const [projection, setProjection] = React.useState('globe');
  const [viewMode, setViewMode] = React.useState('3d');
  const [show3DBuildings, setShow3DBuildings] = React.useState(true);
  const [showCoverage, setShowCoverage] = React.useState(false);
  const themeRef = React.useRef(document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light');


  const coverageGeoJSON = React.useMemo(() => {
    const features = cells.map(c => {

      const N = 36, R_m = 220;
      const lat = c.lat, lng = c.lng;
      const dLat = R_m / 111320;
      const dLng = R_m / (111320 * Math.cos(lat * Math.PI / 180));
      const ring = [];
      for (let i = 0; i <= N; i++) {
        const a = (i / N) * Math.PI * 2;
        ring.push([lng + Math.cos(a) * dLng, lat + Math.sin(a) * dLat]);
      }
      const status =
        conflictedIds.has(c.id) ? 'conflict' :
        c.status === 'active' ? 'active' : c.status;
      return {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [ring] },
        properties: { id: c.id, status, height: 20 + c.prb * 1.2 },
      };
    });
    return { type: 'FeatureCollection', features };
  }, [cells, conflictedIds]);


  const [conflictGeoJSON, conflictLabelGeoJSON] = React.useMemo(() => {
    const lines = [], labels = [];
    const byId = new Map(cells.map(c => [c.id, c]));

    conflicts.forEach(cf => {
      if (cf.type !== 'collision' && cf.type !== 'confusion') return;
      const pts = (cf.cells || []).map(id => byId.get(id)).filter(Boolean);
      const focus = !focusIds || pts.some(c => focusIds.has(c.id));
      for (let i = 1; i < pts.length; i++) {
        const a = pts[0], b = pts[i];
        if (a.lng === b.lng && a.lat === b.lat) continue;
        const props = {
          id: cf.id, severity: cf.severity, focus,
          label: (cf.type === 'collision' ? 'COLLISION' : 'CONFUSION') + ' \u00B7 PCI ' + cf.pci,
        };
        lines.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[a.lng, a.lat], [b.lng, b.lat]] }, properties: props });
        labels.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [(a.lng + b.lng) / 2, (a.lat + b.lat) / 2] }, properties: props });
      }
    });
    return [
      { type: 'FeatureCollection', features: lines },
      { type: 'FeatureCollection', features: labels },
    ];
  }, [cells, conflicts, focusIds]);


  React.useEffect(() => {
    if (!window.maplibregl || mapRef.current) return;
    const isDark = document.documentElement.classList.contains('theme-dark');
    themeRef.current = isDark ? 'dark' : 'light';


    let center = [77.2090, 28.6139];
    const valid = cells.filter(c => typeof c.lat === 'number' && typeof c.lng === 'number');
    if (valid.length) {
      const avgLat = valid.reduce((a, c) => a + c.lat, 0) / valid.length;
      const avgLng = valid.reduce((a, c) => a + c.lng, 0) / valid.length;
      center = [avgLng, avgLat];
    }
    const lngs = valid.map(c => c.lng), lats = valid.map(c => c.lat);
    const startBounds = valid.length > 1
      ? [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]]
      : null;


    const m = new window.maplibregl.Map({
      container: mapEl.current,
      style: mapStyle(themeRef.current),


      center,
      zoom: 10.5,
      bounds: startBounds || undefined,
      fitBoundsOptions: { padding: { top: 80, right: 320, bottom: 80, left: 80 }, maxZoom: 12 },
      pitch: 0,
      bearing: 0,
      minZoom: 3.0,
      maxZoom: 18,
      antialias: true,
      attributionControl: { compact: true },
    });
    m.addControl(new window.maplibregl.NavigationControl({ visualizePitch: true }), 'top-left');
    m.addControl(new window.maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
    mapRef.current = m;
    window.__bigTopoMap = m;


    m.on('moveend', () => {
      const fn = paintMarkersRef.current; if (fn) fn(m);
    });


    m.on('movestart', () => {
      towerMapRef.current.forEach(e   => { try { e.popup.remove(); } catch (err) {} });
      clusterMapRef.current.forEach(e => { try { e.popup.remove(); } catch (err) {} });
    });

    m.on('style.load', () => {
      const fn = restoreLayersRef.current;
      if (fn) fn(m);


      const focus = window.PCI_MAP_FOCUS;
      window.PCI_MAP_FOCUS = null;
      if (focus && typeof focus === 'object' && focus.cellId) {
        const target = valid.find(c => c.id === focus.cellId);
        if (target) m.flyTo({ center: [target.lng, target.lat], zoom: 15, duration: 900 });
      } else if (typeof focus === 'string' && REGION_CITY_CENTRES[focus]) {
        m.flyTo({ center: REGION_CITY_CENTRES[focus], zoom: 11.5, duration: 800 });
      }
    });

    return () => {
      m.remove();
      mapRef.current = null;
      markersRef.current = [];
      towerMapRef.current.clear();
      clusterMapRef.current.clear();
    };

  }, []);


  const addLayers = React.useCallback((m) => {

    ['conflict-labels-text', 'conflicts-line', 'conflicts-line-critical', 'conflicts-line-glow',
     'coverage-outline', 'coverage-3d', '3d-buildings']
      .forEach(id => { if (m.getLayer(id)) m.removeLayer(id); });
    ['coverage', 'conflicts', 'conflict-labels']
      .forEach(id => { if (m.getSource(id)) m.removeSource(id); });

    m.addSource('coverage', { type: 'geojson', data: coverageGeoJSON });
    m.addSource('conflicts', { type: 'geojson', data: conflictGeoJSON });
    m.addSource('conflict-labels', { type: 'geojson', data: conflictLabelGeoJSON });

    const styleLayers = m.getStyle().layers || [];
    const labelLayer = styleLayers.find(l => l.type === 'symbol' && l.layout && l.layout['text-field']);


    m.addLayer({
      id: 'coverage-3d',
      type: 'fill',
      source: 'coverage',


      minzoom: 11,
      layout: { visibility: showCoverage ? 'visible' : 'none' },
      paint: {
        'fill-color': [
          'match', ['get', 'status'],
          'conflict',    '#EF4444',
          'degraded',    '#F59E0B',
          'maintenance', '#A78BFA',
          'idle',        '#6B7280',
             ['to-color', getCSSVar('--accent') || '#A3E635'],
        ],
        'fill-opacity': 0.18,
      },
    });


    m.addLayer({
      id: 'coverage-outline',
      type: 'line',
      source: 'coverage',
      minzoom: 11,
      layout: { visibility: showCoverage ? 'visible' : 'none' },
      paint: {
        'line-color': [
          'match', ['get', 'status'],
          'conflict', '#EF4444',
          'degraded', '#F59E0B',
          'maintenance', '#A78BFA',
          'idle', '#6B7280',
          ['to-color', getCSSVar('--accent') || '#A3E635'],
        ],
        'line-width': 1.2,
        'line-opacity': 0.7,
      },
    });


    const isDark = themeRef.current === 'dark';
    const lineWidth = (w) => ['interpolate', ['linear'], ['zoom'], 9, w * 0.7, 14, w, 17, w * 1.3];
    m.addLayer({
      id: 'conflicts-line-glow',
      type: 'line',
      source: 'conflicts',
      minzoom: 8.5,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': ARC_SEV_COLOR, 'line-width': 8, 'line-opacity': ['case', ['get', 'focus'], 0.12, 0], 'line-blur': 4 },
    });
    m.addLayer({
      id: 'conflicts-line',
      type: 'line',
      source: 'conflicts',
      minzoom: 8.5,
      filter: ['!=', ['get', 'severity'], 'critical'],
      layout: { 'line-cap': 'butt', 'line-join': 'round' },
      paint: {
        'line-color': ARC_SEV_COLOR,
        'line-width': lineWidth(1.8),
        'line-dasharray': [3, 2.2],
        'line-opacity': ['case', ['get', 'focus'], 0.9, 0.15],
      },
    });
    m.addLayer({
      id: 'conflicts-line-critical',
      type: 'line',
      source: 'conflicts',
      minzoom: 8.5,
      filter: ['==', ['get', 'severity'], 'critical'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': '#EF4444',
        'line-width': lineWidth(2.6),
        'line-dasharray': [0, 2],
        'line-opacity': ['case', ['get', 'focus'], 0.95, 0.15],
      },
    });
    m.addLayer({
      id: 'conflict-labels-text',
      type: 'symbol',
      source: 'conflict-labels',
      minzoom: 11,
      filter: ['get', 'focus'],
      layout: {
        'text-field': ['get', 'label'],
        'text-font': ['Open Sans Semibold', 'Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10, 15, 11.5],
        'text-letter-spacing': 0.08,
        'text-max-width': 20,
        'text-anchor': 'bottom',
        'text-offset': [0, -0.7],
        'text-padding': 6,
        'symbol-sort-key': ['match', ['get', 'severity'], 'critical', 0, 1],
      },
      paint: {
        'text-color': ['match', ['get', 'severity'],
          'critical', isDark ? '#F87171' : '#DC2626',
          'major',    isDark ? '#FBBF24' : '#B45309',
          isDark ? '#9DB0D9' : '#475569'],
        'text-halo-color': isDark ? 'rgba(9, 13, 24, 0.92)' : 'rgba(255, 255, 255, 0.92)',
        'text-halo-width': 1.6,
      },
    });

    if (show3DBuildings) {
      try {
        m.addLayer({
          id: '3d-buildings',
          source: 'carto',
          'source-layer': 'building',
          type: 'fill-extrusion',
          minzoom: 13,
          paint: {
            'fill-extrusion-color': themeRef.current === 'dark' ? '#1A2240' : '#D9D5C7',
            'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 12],
            'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
            'fill-extrusion-opacity': themeRef.current === 'dark' ? 0.55 : 0.6,
          },
        }, labelLayer ? labelLayer.id : undefined);
      } catch (e) {  }
    }
  }, [coverageGeoJSON, conflictGeoJSON, conflictLabelGeoJSON, show3DBuildings, showCoverage]);


  const onSelectRef = React.useRef(onSelectCell);
  React.useEffect(() => { onSelectRef.current = onSelectCell; }, [onSelectCell]);


  const paintMarkersRef = React.useRef(null);
  const restoreLayersRef = React.useRef(null);


  const CLUSTER_PX = 48;
  const towerMapRef   = React.useRef(new Map());
  const clusterMapRef = React.useRef(new Map());


  const computeClusters = React.useCallback((m, cellList) => {
    const lowZoom = m.getZoom() < 8.5;
    const projected = cellList
      .filter(c => typeof c.lat === 'number' && typeof c.lng === 'number')
      .map(c => {
        const p = m.project([c.lng, c.lat]);
        return { c, x: p.x, y: p.y, isConfl: !lowZoom && conflictedIds.has(c.id) };
      });
    const groups = [];
    const taken = new Array(projected.length).fill(false);

    for (let i = 0; i < projected.length; i++) {
      if (!projected[i].isConfl || taken[i]) continue;
      groups.push([projected[i].c]);
      taken[i] = true;
    }

    for (let i = 0; i < projected.length; i++) {
      if (taken[i]) continue;
      const group = [projected[i].c];
      taken[i] = true;
      for (let j = i + 1; j < projected.length; j++) {
        if (taken[j] || projected[j].isConfl) continue;
        const dx = projected[i].x - projected[j].x;
        const dy = projected[i].y - projected[j].y;
        if (dx * dx + dy * dy <= CLUSTER_PX * CLUSTER_PX) {
          group.push(projected[j].c);
          taken[j] = true;
        }
      }
      groups.push(group);
    }
    return groups;
  }, [conflictedIds]);

  const paintMarkers = React.useCallback((m) => {
    const groups = computeClusters(m, cells);
    const wantedTowers = new Set();
    const wantedClusters = new Set();

    groups.forEach((group) => {
      if (group.length === 1) {
        renderTower(m, group[0], wantedTowers);
      } else {

        const lat = group.reduce((a, c) => a + c.lat, 0) / group.length;
        const lng = group.reduce((a, c) => a + c.lng, 0) / group.length;

        const clusterId = 'CL-' + group.map(c => c.id).sort().join('-');
        wantedClusters.add(clusterId);
        renderCluster(m, clusterId, lat, lng, group);
      }
    });


    for (const [id, entry] of towerMapRef.current) {
      if (!wantedTowers.has(id)) {
        try { entry.popup.remove(); } catch (e) {}
        entry.marker.remove();
        towerMapRef.current.delete(id);
      }
    }

    for (const [id, entry] of clusterMapRef.current) {
      if (!wantedClusters.has(id)) {
        try { entry.popup.remove(); } catch (e) {}
        entry.marker.remove();
        clusterMapRef.current.delete(id);
      }
    }

    markersRef.current = [
      ...[...towerMapRef.current.values()].map(e => e.marker),
      ...[...clusterMapRef.current.values()].map(e => e.marker),
    ];
  }, [cells, conflictedIds, computeClusters, focusIds]);


  const renderTower = React.useCallback((m, c, wantedTowers) => {
    wantedTowers.add(c.id);
    const isConfl = conflictedIds.has(c.id);
    const isDim = !!focusIds && !focusIds.has(c.id);


    const sig = `${c.status}|${c.pci}|${isConfl ? 1 : 0}|${isDim ? 1 : 0}|${c.approxPos ? 1 : 0}|${c.lat.toFixed(5)}|${c.lng.toFixed(5)}`;

    let entry = towerMapRef.current.get(c.id);
    if (!entry) {
      const el = document.createElement('div');
      el.dataset.cellId = c.id;


      el.innerHTML = `
        <div class="cell-tower-body">
          <div class="label"></div>
          <div class="pulse"></div>
          <div class="top"></div>
          <div class="mast"></div>
          <div class="base"></div>
          <div class="shadow"></div>
        </div>
      `;
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const cur = (cells || []).find(cc => cc.id === el.dataset.cellId);
        onSelectRef.current && onSelectRef.current(cur || { id: el.dataset.cellId });
      });


      const popup = new window.maplibregl.Popup({ anchor: 'bottom', offset: 46, closeButton: false, closeOnClick: false });
      el.addEventListener('mouseenter', () => {

        const fresh = towerMapRef.current.get(el.dataset.cellId);
        if (fresh && fresh.popupHtml) popup.setLngLat(fresh.popupLngLat).setHTML(fresh.popupHtml);
        popup.addTo(m);
      });
      el.addEventListener('mouseleave', () => popup.remove());


      const marker = new window.maplibregl.Marker({
        element: el,
        anchor: 'bottom',
        pitchAlignment: 'viewport',
        rotationAlignment: 'viewport',
      })
        .setLngLat([c.lng, c.lat])
        .addTo(m);

      entry = { marker, el, popup, lastSig: '' };
      towerMapRef.current.set(c.id, entry);
    }

    if (entry.lastSig !== sig + ':' + colorModeRef.current) {
      const cl = entry.el.classList;
      cl.add('cell-tower');
      cl.toggle('conflict', isConfl);
      ['degraded', 'maintenance', 'idle'].forEach(k => cl.toggle(k, !isConfl && c.status === k));
      cl.toggle('dim', isDim);
      cl.toggle('approx', !!c.approxPos);


      const tint = markerColorFor(c, colorModeRef.current);
      if (tint) entry.el.style.setProperty('--accent', tint);
      else entry.el.style.removeProperty('--accent');


      const labelEl = entry.el.querySelector('.label');
      const wantLabel = `${c.id} · PCI ${c.pci}`;
      if (labelEl.textContent !== wantLabel) labelEl.textContent = wantLabel;
      if (entry.marker.getLngLat().lng !== c.lng || entry.marker.getLngLat().lat !== c.lat) {
        entry.marker.setLngLat([c.lng, c.lat]);
      }
      entry.lastSig = sig + ':' + colorModeRef.current;
    }


    entry.popupHtml = `<b>${c.id}</b> · PCI ${c.pci}<br/>${c.site} · ${c.region}<br/>${c.status} · ${c.dl.toFixed(0)} Mbps DL · ${c.prb}% PRB`
      + (isConfl ? '<br/><span style="color:#EF4444">⚠ in conflict</span>' : '')
      + (c.approxPos ? '<br/><span style="color:#F59E0B">◌ approximate position — no TOPO geodata</span>' : '');
    entry.popupLngLat = [c.lng, c.lat];
    if (entry.popup.isOpen()) {
      entry.popup.setLngLat(entry.popupLngLat).setHTML(entry.popupHtml);
    }
  }, [cells, conflictedIds, focusIds]);


  const renderCluster = React.useCallback((m, clusterId, lat, lng, members) => {
    const conflictCount = members.filter(c => conflictedIds.has(c.id)).length;
    const sig = `${members.length}|${conflictCount}|${lat.toFixed(5)}|${lng.toFixed(5)}`;

    let entry = clusterMapRef.current.get(clusterId);
    if (!entry) {
      const el = document.createElement('div');
      el.className = 'cell-cluster';


      el.innerHTML = `<div class="cell-cluster-body"><div class="count"></div></div><div class="ring"></div>`;
      el.addEventListener('click', (e) => {
        e.stopPropagation();


        const fresh = clusterMapRef.current.get(clusterId);
        const ms = (fresh && fresh.members) || members;
        const pts = ms.map(c => m.project([c.lng, c.lat]));
        const xs = pts.map(q => q.x), ys = pts.map(q => q.y);
        const spread = Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
        const dz = spread > 1 ? Math.log2((CLUSTER_PX * 1.4) / spread) : 3;
        m.easeTo({ center: [lng, lat], zoom: Math.min(18, m.getZoom() + Math.max(1, dz)), duration: 700 });
      });
      const popup = new window.maplibregl.Popup({ anchor: 'bottom', offset: 22, closeButton: false, closeOnClick: false });
      el.addEventListener('mouseenter', () => {
        const fresh = clusterMapRef.current.get(clusterId);
        if (fresh && fresh.popupHtml) popup.setLngLat(fresh.popupLngLat).setHTML(fresh.popupHtml);
        popup.addTo(m);
      });
      el.addEventListener('mouseleave', () => popup.remove());
      const marker = new window.maplibregl.Marker({
        element: el,
        anchor: 'center',
        pitchAlignment: 'viewport',
        rotationAlignment: 'viewport',
      })
        .setLngLat([lng, lat])
        .addTo(m);
      entry = { marker, el, popup, lastSig: '' };
      clusterMapRef.current.set(clusterId, entry);
    }

    if (entry.lastSig !== sig + ':' + colorModeRef.current) {
      entry.el.querySelector('.count').textContent = members.length;
      entry.el.classList.toggle('has-conflict', conflictCount > 0);
      if (entry.marker.getLngLat().lng !== lng || entry.marker.getLngLat().lat !== lat) {
        entry.marker.setLngLat([lng, lat]);
      }
      entry.lastSig = sig + ':' + colorModeRef.current;
    }


    entry.members = members;


    const ids = members.slice(0, 6).map(c => c.id).join(', ') + (members.length > 6 ? `, +${members.length - 6} more` : '');
    entry.popupHtml = `<b>${members.length} cells</b>${conflictCount > 0 ? ` · <span style="color:#EF4444">${conflictCount} in conflict</span>` : ''}<br/><span style="font-size:11px;color:#9DB0D9">${ids}</span><br/><span style="font-size:11px;color:#5E709C">Click or zoom in to expand</span>`;
    entry.popupLngLat = [lng, lat];
    if (entry.popup.isOpen()) {
      entry.popup.setLngLat(entry.popupLngLat).setHTML(entry.popupHtml);
    }
  }, [conflictedIds]);


  React.useEffect(() => {
    markersRef.current.forEach(mk => {
      const el = mk.getElement();
      if (el.dataset.cellId === selectedCell?.id) el.classList.add('selected');
      else el.classList.remove('selected');
    });
  }, [selectedCell]);


  React.useEffect(() => {
    const onThemeChange = () => {
      const m = mapRef.current; if (!m) return;
      const isDark = document.documentElement.classList.contains('theme-dark');
      const want = isDark ? 'dark' : 'light';
      if (themeRef.current === want) return;
      themeRef.current = want;
      m.setStyle(mapStyle(want), { diff: false });
    };
    const obs = new MutationObserver(onThemeChange);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, [addLayers, paintMarkers]);


  React.useEffect(() => {
    const m = mapRef.current; if (!m || !m.getSource) return;
    if (m.getSource('coverage')) m.getSource('coverage').setData(coverageGeoJSON);
    if (m.getSource('conflicts')) m.getSource('conflicts').setData(conflictGeoJSON);
    if (m.getSource('conflict-labels')) m.getSource('conflict-labels').setData(conflictLabelGeoJSON);
  }, [coverageGeoJSON, conflictGeoJSON, conflictLabelGeoJSON]);


  React.useEffect(() => {
    const m = mapRef.current; if (!m) return;
    const apply = () => {
      ['coverage-3d', 'coverage-outline'].forEach(id => {
        if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', showCoverage ? 'visible' : 'none');
      });
      if (m.getLayer('3d-buildings')) m.setLayoutProperty('3d-buildings', 'visibility', show3DBuildings ? 'visible' : 'none');
      else if (show3DBuildings && m.isStyleLoaded()) addLayers(m);
    };
    if (m.isStyleLoaded()) apply(); else m.once('style.load', apply);
  }, [showCoverage, show3DBuildings, addLayers]);


  React.useEffect(() => {
    const m = mapRef.current;
    if (!m || !focusIds) return;
    const pts = focusCells.filter(
      c => typeof c.lat === 'number' && typeof c.lng === 'number',
    );
    if (!pts.length) return;
    const lngs = pts.map(c => c.lng);
    const lats = pts.map(c => c.lat);
    const flat = Math.max(...lngs) === Math.min(...lngs)
              && Math.max(...lats) === Math.min(...lats);


    if (pts.length === 1 || flat) {
      m.easeTo({
        center: [lngs[0], lats[0]],
        zoom: Math.max(m.getZoom(), 16),
        duration: 700,
      });
      return;
    }
    m.fitBounds(
      new window.maplibregl.LngLatBounds(
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ),
      { padding: { top: 80, right: 320, bottom: 80, left: 80 },
        maxZoom: 16, duration: 700 },
    );
  }, [focusIds, focusCells]);


  React.useEffect(() => {
    restoreLayersRef.current = (m) => {
      applySky(m, themeRef.current === 'dark');
      addLayers(m);
      paintMarkers(m);
    };
  }, [addLayers, paintMarkers]);


  React.useEffect(() => {
    paintMarkersRef.current = paintMarkers;
    const m = mapRef.current; if (!m) return;
    if (m.isStyleLoaded()) paintMarkers(m);
    else m.once('style.load', () => paintMarkers(m));
  }, [paintMarkers, colorMode]);


  React.useEffect(() => {
    window.__focusMapRegion = (regionName) => {
      const m = mapRef.current; if (!m || !regionName) return;
      const centre = REGION_CITY_CENTRES[regionName];
      if (centre) {

        m.flyTo({ center: centre, zoom: 11.5, duration: 800 });
        return;
      }

      const inRegion = cells.filter(c =>
        c.region === regionName
        && typeof c.lat === 'number' && typeof c.lng === 'number');
      if (!inRegion.length) return;
      const cLat = inRegion.reduce((a, c) => a + c.lat, 0) / inRegion.length;
      const cLng = inRegion.reduce((a, c) => a + c.lng, 0) / inRegion.length;
      m.flyTo({ center: [cLng, cLat], zoom: 10.5, duration: 800 });
    };
    return () => { window.__focusMapRegion = null; };
  }, [cells]);


  React.useEffect(() => {
    const m = mapRef.current; if (!m) return;
    m.easeTo({ pitch, duration: 600 });
  }, [pitch]);


  React.useEffect(() => {
    const onZoom = (ev) => {
      const ids = (ev && ev.detail && ev.detail.cellIds) || [];
      if (!ids.length) return;
      const tryFit = (attempt) => {
        const m = mapRef.current;
        if (!m) {
          if (attempt < 20) setTimeout(() => tryFit(attempt + 1), 200);
          return;
        }
        const cellList = window.PCI_DATA?.CELLS || [];
        const points = cellList
          .filter(c => ids.includes(c.id) && typeof c.lat === 'number' && typeof c.lng === 'number');
        if (!points.length) return;
        if (points.length === 1) {

          m.easeTo({ center: [points[0].lng, points[0].lat], zoom: 14, duration: 1200 });
          return;
        }
        const lngs = points.map(p => p.lng);
        const lats = points.map(p => p.lat);
        const bounds = new window.maplibregl.LngLatBounds(
          [Math.min(...lngs), Math.min(...lats)],
          [Math.max(...lngs), Math.max(...lats)],
        );
        m.fitBounds(bounds, {
          padding: { top: 100, right: 360, bottom: 100, left: 100 },
          maxZoom: 14,
          duration: 1200,
        });
      };

      setTimeout(() => tryFit(0), 250);
    };
    window.addEventListener('pci-apply-zoom', onZoom);
    return () => window.removeEventListener('pci-apply-zoom', onZoom);
  }, []);


  React.useEffect(() => {
    const m = mapRef.current; if (!m || !m.setProjection) return;
    try { m.setProjection({ type: projection }); } catch (e) {  }
  }, [projection]);


  React.useEffect(() => {
    const m = mapRef.current; if (!m) return;
    const floor = viewMode === 'globe' ? 2.0 : 4.0;
    m.setMinZoom(floor);


    if (m.getZoom() < floor) m.easeTo({ zoom: floor, duration: 500 });
  }, [viewMode]);


  React.useEffect(() => {
    if (!mapEl.current || !window.ResizeObserver) return;
    const ro = new ResizeObserver(() => {
      if (mapRef.current) mapRef.current.resize();
    });
    ro.observe(mapEl.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div style={{ position: 'relative', width: '100%', flex: 1, minHeight: 480 }}>
      <div ref={mapEl} style={{ position: 'absolute', inset: 0 }}/>

      {showOverlays && <div className="map-controls">
        <div className="map-pill">
          <span style={{ color: 'var(--fg-3)' }}>VIEW</span>
          <button data-on={viewMode === '2d' ? 1 : 0}
                  onClick={() => { setViewMode('2d'); setProjection('mercator'); setPitch(0); }}
                  title="Flat 2D map">2D</button>
          <button data-on={viewMode === 'tilt' ? 1 : 0}
                  onClick={() => { setViewMode('tilt'); setProjection('globe'); setPitch(50); }}
                  title="Tilted street view">TILT</button>
          <button data-on={viewMode === '3d' ? 1 : 0}
                  onClick={() => {
                    setViewMode('3d'); setProjection('globe'); setPitch(0);
                    if (mapRef.current) mapRef.current.easeTo({ zoom: 4.0, duration: 700 });
                  }}
                  title="Globe centered (Earth from space)">3D</button>
          <button data-on={viewMode === 'globe' ? 1 : 0}
                  onClick={() => {
                    setViewMode('globe'); setProjection('globe'); setPitch(0);
                    if (mapRef.current) {
                      mapRef.current.setMinZoom(2.0);
                      mapRef.current.easeTo({ zoom: 2.0, duration: 800 });
                    }
                  }}
                  title="Full globe — wide orbital view">GLOBE</button>
        </div>
        <div className="map-pill">
          <span style={{ color: 'var(--fg-3)' }}>LAYERS</span>
          <button data-on={showCoverage ? 1 : 0} onClick={() => setShowCoverage(v => !v)}>COV</button>
          <button data-on={show3DBuildings ? 1 : 0} onClick={() => setShow3DBuildings(v => !v)}>BLDG</button>
        </div>
      </div>}

      {showOverlays && <div className="map-legend">
        <div className="map-legend-title">{MAP_LEGEND_TITLE[colorMode]}</div>
        {colorMode === 'status' && <>
          <div className="map-legend-row"><i style={{ background: 'var(--accent)', color: 'var(--accent)' }}/>Cell · no conflict</div>
          <div className="map-legend-row"><i style={{ background: 'var(--crit)', color: 'var(--crit)' }}/>Cell in a PCI conflict</div>
          <div className="map-legend-row"><i style={{ background: 'var(--accent)', color: 'var(--accent)', borderRadius: '50%', boxShadow: '0 0 0 3px color-mix(in oklch, var(--accent) 30%, transparent)' }}/>Cluster · number = cells inside</div>
          <div className="map-legend-title" style={{ marginTop: 8 }}>Conflict edges</div>
          <div className="map-legend-row"><span className="map-legend-line" style={{ borderTopStyle: 'dotted', borderTopColor: '#EF4444', borderTopWidth: 3 }}/>Collision · critical</div>
          <div className="map-legend-row"><span className="map-legend-line" style={{ borderTopStyle: 'dashed', borderTopColor: '#F59E0B' }}/>Confusion · major</div>
          <div className="map-legend-row"><span className="map-legend-line" style={{ borderTopStyle: 'dashed', borderTopColor: '#9DB0D9' }}/>Mod-N · minor</div>
          <div className="map-legend-note">Edges dim until a conflict is focused; labels appear from zoom 11.</div>
        </>}
        {approxCount > 0 && (
          <div className="map-legend-note" style={{ marginTop: 2 }}>
            {approxCount} of {cells.length} cells have no TOPO geodata — drawn at an
            approximate site position (dashed base). Distances are not survey data.
          </div>
        )}
        {colorMode === 'heat' && <>
          <div className="map-legend-ramp" style={{ background: 'linear-gradient(90deg, hsl(210,72%,48%), hsl(105,72%,48%), hsl(0,72%,48%))' }}/>
          <div className="map-legend-note">PRB utilisation, 0% to 100%.</div>
        </>}
      </div>}

      {showOverlays && <ConflictsOverlay mapRef={mapRef} cells={cells} conflicts={conflicts} onSelectCell={onSelectCell}/>}
    </div>
  );
}


function ConflictsOverlay({ mapRef, cells, conflicts, onSelectCell }) {
  const active = conflicts.filter(c =>
    (c.type === 'collision' || c.type === 'confusion')
    && (c.severity === 'critical' || c.severity === 'major')
  );
  if (!active.length) return null;
  const focusConflict = (cf) => {
    const m = mapRef.current; if (!m) return;
    const pts = cf.cells.map(id => cells.find(c => c.id === id)).filter(Boolean);
    if (pts.length < 2) return;
    const lngs = pts.map(c => c.lng);
    const lats = pts.map(c => c.lat);
    const bounds = new window.maplibregl.LngLatBounds(
      [Math.min(...lngs), Math.min(...lats)],
      [Math.max(...lngs), Math.max(...lats)],
    );
    m.fitBounds(bounds, {
      padding: { top: 80, right: 320, bottom: 80, left: 80 },


      maxZoom: 16.5,
      duration: 700,
    });


  };
  return (
    <div className="map-conflicts">
      <div className="map-conflicts-head">
        <span className="dot crit"/>
        <span className="title">Active conflicts</span>
        <span className="count">{active.length}</span>
      </div>
      <div className="map-conflicts-list">
        {active.map(cf => (
          <button key={cf.id} className={`map-conflicts-row sev-${cf.severity}`} onClick={() => focusConflict(cf)}>
            <span className="bar"/>
            <div className="meta">
              <div className="row1">
                <span className={`kind ${cf.type}`}>{cf.type === 'collision' ? 'COLLISION' : 'CONFUSION'}</span>
                <span className="pci">PCI {cf.pci}</span>
              </div>
              <div className="row2">
                {cf.cells.join(' \u2194 ')}
              </div>
            </div>
            <span className="focus" title="Fit map to this conflict">FOCUS</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function RegionPanel() {
  const regions = window.PCI_DATA.REGIONS_HEALTH;

  const totalCells     = regions.reduce((a, r) => a + r.cells,     0);
  const totalClean     = regions.reduce((a, r) => a + r.ok,        0);
  const totalIssues    = regions.reduce((a, r) => a + r.conflicts, 0);
  const healthyRegions = regions.filter(r => r.conflicts === 0).length;


  const sorted = [...regions].sort((a, b) => {
    if (b.conflicts !== a.conflicts) return b.conflicts - a.conflicts;
    return a.pct - b.pct;
  });


  const severity = (r) => r.conflicts === 0 ? 'ok' : r.conflicts >= 3 ? 'crit' : 'warn';


  const barClass = (pct) => pct >= 90 ? 'ok' : pct >= 75 ? 'warn' : 'crit';

  return (
    <div className="panel rh-panel">
      <div className="rh-head">
        <div className="rh-head-titles">
          <h4>Regional Health</h4>
          <span className="rh-head-sub">{regions.length} region{regions.length === 1 ? '' : 's'} reported by the PM feed · sorted by severity</span>
        </div>
      </div>

      <div className="rh-summary">
        <div className="rh-summary-stat ok">
          <span className="n">{totalClean}</span>
          <span className="l">/ {totalCells} conflict-free</span>
        </div>
        <div className="rh-summary-divider"/>
        <div className={`rh-summary-stat ${totalIssues > 0 ? 'crit' : 'ok'}`}>
          <span className="n">{totalIssues}</span>
          <span className="l">open issue{totalIssues === 1 ? '' : 's'}</span>
        </div>
        <div className="rh-summary-divider"/>
        <div className={`rh-summary-stat ${healthyRegions === regions.length ? 'ok' : 'warn'}`}>
          <span className="n">{healthyRegions}</span>
          <span className="l">healthy region{healthyRegions === 1 ? '' : 's'}</span>
        </div>
      </div>

      <div className="rh-rows">
        {sorted.map(r => {
          const sev = severity(r);

          const focus = () => window.__focusMapRegion && window.__focusMapRegion(r.name);
          return (
            <div key={r.name} className={`rh-row ${sev} clickable`}
                 role="button" tabIndex={0}
                 title={`Focus ${r.name} on the map`}
                 onClick={focus}
                 onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); focus(); } }}>
              <div className="rh-row-meta">
                <div className="name">{r.name}</div>
                <div className="caption">{r.ok} / {r.cells} cells conflict-free</div>
              </div>
              <span className={`rh-row-status ${sev}`}>
                {r.conflicts === 0 ? (
                  <span className="check">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
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
              <div className="rh-row-progress">
                <div className="rh-bar">
                  <div className={`rh-bar-fill ${barClass(r.pct)}`} style={{ width: r.pct + '%' }}/>
                </div>
                <span className="rh-bar-pct" title="Share of cells in no conflict">{r.pct}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


const DH_COLORS = { collision: 'var(--crit)', confusion: 'var(--warn)', modn: 'var(--info)' };


function DhRing({ pct, color }) {
  const r = 17, c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(100, pct)) / 100;
  return (
    <svg className="dh-stat-fig" viewBox="0 0 44 44">
      <circle cx="22" cy="22" r={r} fill="none" stroke="var(--bg-3)" strokeWidth="5"/>
      <circle cx="22" cy="22" r={r} fill="none" stroke={color} strokeWidth="5"
        strokeLinecap="round" strokeDasharray={`${c * frac} ${c}`}
        transform="rotate(-90 22 22)"/>
    </svg>
  );
}


function DhStatBand({ history, replans }) {
  const s = history.summary;
  const d = s.deltaVsStart;
  const span = s.spanMin >= 1 ? `the last ${spanLabel(s.spanMin)}` : 'the first sample';

  const deltaCls = d < 0 ? 'down' : d > 0 ? 'up' : 'flat';
  const deltaTxt = s.spanMin < 1 ? 'history starts now'
    : d === 0 ? `— unchanged over ${spanLabel(s.spanMin)}` : `${d < 0 ? '▼' : '▲'} ${Math.abs(d)} vs ${spanLabel(s.spanMin)} ago`;


  const conflicts = window.PCI_DATA.CONFLICTS || [];
  const nCol = conflicts.filter(c => c.type === 'collision').length;
  const nCnf = conflicts.filter(c => c.type === 'confusion').length;
  const nMod = conflicts.filter(c => c.type === 'mod3').length;
  const liveTotal = s.liveTotal || 0;

  const peakFrac = s.peak > 0 ? Math.round((liveTotal / s.peak) * 100) : 0;

  return (
    <div className="dh-band">
      <div className={`panel dh-stat ${liveTotal > 0 ? 'crit' : 'ok'}`}>
        <div className="dh-stat-label">Active conflicts</div>
        <div className="dh-stat-value">{liveTotal}</div>
        <div className="dh-stat-fig-row">
          <span className="dh-segbar">
            {liveTotal > 0 ? <>
              {nCol > 0 && <span style={{ flex: nCol, background: 'var(--crit)' }}/>}
              {nCnf > 0 && <span style={{ flex: nCnf, background: 'var(--warn)' }}/>}
              {nMod > 0 && <span style={{ flex: nMod, background: 'var(--info)' }}/>}
            </> : <span style={{ flex: 1, background: 'var(--ok)' }}/>}
          </span>
        </div>
        <div className="dh-stat-foot">
          <span className={`dh-delta ${deltaCls}`}>{deltaTxt}</span>
        </div>
      </div>

      <div className="panel dh-stat warn">
        <div className="dh-stat-label">Peak conflicts</div>
        <div className="dh-stat-value">{s.peak}</div>
        <div className="dh-stat-fig-row">
          <span className="dh-gauge">
            <span style={{ width: `${peakFrac}%`, background: 'var(--warn)' }}/>
          </span>
          <span className="dh-fig-cap">now {liveTotal}</span>
        </div>
        <div className="dh-stat-foot">highest in {span}</div>
      </div>

      <div className="panel dh-stat info">
        <div className="dh-stat-label">PCI changes committed</div>
        <div className="dh-stat-value">{replans.length}</div>
        <div className="dh-stat-foot">operator re-plans written to SDNR this session</div>
      </div>

      <div className="panel dh-stat ok">
        <div className="dh-stat-label">Avg conflict-free cells</div>
        <div className="dh-stat-value">{s.avgHealthPct}<span className="u">%</span></div>
        <div className="dh-stat-foot">mean over {span}</div>
        <DhRing pct={s.avgHealthPct} color="var(--ok)"/>
      </div>
    </div>
  );
}


function DhTrendChart({ history }) {
  const pts = history.points;
  const [hover, setHover] = React.useState(null);
  const W = 960, H = 300, padT = 12, padB = 8;
  const innerH = H - padT - padB;
  const yMax = Math.max(4, Math.ceil(Math.max(...pts.map(p => p.total), 1) * 1.25));
  const x = (i) => (i / Math.max(1, pts.length - 1)) * W;
  const y = (v) => padT + innerH - (v / yMax) * innerH;


  const layer = (key, below) => {
    const top = pts.map((p, i) => {
      const stack = (key === 'modn' ? p.modn
        : key === 'confusion' ? p.modn + p.confusion
        : p.modn + p.confusion + p.collision);
      return [x(i), y(stack)];
    });
    const base = pts.map((p, i) => {
      const stack = below === 'none' ? 0
        : below === 'modn' ? p.modn
        : p.modn + p.confusion;
      return [x(i), y(stack)];
    }).reverse();
    return [...top, ...base].map(c => c.join(',')).join(' ');
  };
  const yTicks = 4;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((yMax / yTicks) * i));
  const xEvery = Math.ceil(pts.length / 8);

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - r.left) / r.width;
    const idx = Math.max(0, Math.min(pts.length - 1, Math.round(ratio * (pts.length - 1))));
    setHover({ idx, p: pts[idx] });
  };

  return (
    <div className="dh-chart-wrap">
      <svg className="dh-chart-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <defs>
          {['collision', 'confusion', 'modn'].map(k => (
            <linearGradient key={k} id={`dh-g-${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={DH_COLORS[k]} stopOpacity="0.55"/>
              <stop offset="100%" stopColor={DH_COLORS[k]} stopOpacity="0.12"/>
            </linearGradient>
          ))}
        </defs>
        {ticks.map((v, i) => (
          <line key={i} x1={0} x2={W} y1={y(v)} y2={y(v)} className="dh-chart-grid"/>
        ))}
        <polygon points={layer('modn', 'none')}      fill="url(#dh-g-modn)"/>
        <polygon points={layer('confusion', 'modn')} fill="url(#dh-g-confusion)"/>
        <polygon points={layer('collision', 'confusion')} fill="url(#dh-g-collision)"/>
        <polyline fill="none" stroke="var(--crit)" strokeWidth="1.8"
          vectorEffect="non-scaling-stroke"
          points={pts.map((p, i) => `${x(i)},${y(p.total)}`).join(' ')}/>
        {hover && (
          <g>
            <line x1={x(hover.idx)} x2={x(hover.idx)} y1={padT} y2={padT + innerH}
              stroke="var(--fg-3)" strokeDasharray="2 3" vectorEffect="non-scaling-stroke"/>
            <circle cx={x(hover.idx)} cy={y(hover.p.total)} r="3.5" fill="var(--crit)"/>
          </g>
        )}
      </svg>
      <div className="dh-chart-axis-y">
        {ticks.map((v, i) => (
          <span key={i} style={{ top: `${((y(v) - padT) / innerH) * 100}%` }}>{v}</span>
        ))}
      </div>
      <div className="dh-chart-axis-x">
        {pts.map((p, i) => i % xEvery === 0 && (
          <span key={i} style={{ left: `${(x(i) / W) * 100}%` }}>{p.label}</span>
        ))}
      </div>
      {hover && (
        <div className="dh-chart-tip" style={{
          left: `calc(${(x(hover.idx) / W) * 100}% + 14px)`, top: 10,
        }}>
          <div className="tt">{hover.p.label}</div>
          <div className="tr"><span><i style={{ background: DH_COLORS.collision }}/>Collision</span><span>{hover.p.collision}</span></div>
          <div className="tr"><span><i style={{ background: DH_COLORS.confusion }}/>Confusion</span><span>{hover.p.confusion}</span></div>
          <div className="tr"><span><i style={{ background: DH_COLORS.modn }}/>Mod-N</span><span>{hover.p.modn}</span></div>
          <div className="tr" style={{ borderTop: '1px solid var(--line)', marginTop: 4, paddingTop: 4 }}>
            <span style={{ color: 'var(--fg)' }}>Total</span>
            <span style={{ color: 'var(--fg)' }}>{hover.p.total}</span>
          </div>
        </div>
      )}
      <div className="dh-legend">
        <div className="dh-legend-item"><i style={{ background: DH_COLORS.collision }}/>Collision</div>
        <div className="dh-legend-item"><i style={{ background: DH_COLORS.confusion }}/>Confusion</div>
        <div className="dh-legend-item"><i style={{ background: DH_COLORS.modn }}/>Mod-N interference</div>
      </div>
    </div>
  );
}


function DhWorstRegions() {
  const cells = window.PCI_DATA.CELLS || [];
  const conflicts = window.PCI_DATA.CONFLICTS || [];
  const regionByCell = {};
  cells.forEach(c => { if (c.id) regionByCell[c.id] = c.region || '—'; });
  const tally = {};
  conflicts.forEach(cf => {
    const touched = new Set((cf.cells || []).map(cid => regionByCell[cid]).filter(Boolean));
    touched.forEach(r => { tally[r] = (tally[r] || 0) + 1; });
  });
  const ranked = Object.entries(tally).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const max = ranked.length ? ranked[0][1] : 1;
  if (!ranked.length) {
    return <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
      No conflicts — every region clean.
    </div>;
  }
  return (
    <div className="dh-rank">
      {ranked.map(([name, n], i) => (
        <div key={name} className={`dh-rank-row ${i === 0 ? 'top' : ''}`}>
          <span className="dh-rank-no">{i + 1}</span>
          <span className="dh-rank-name">{name}</span>
          <span className="dh-rank-bar"><span style={{ width: `${(n / max) * 100}%` }}/></span>
          <span className="dh-rank-val">{n}</span>
        </div>
      ))}
    </div>
  );
}


function rollupByHour(points, replans) {
  const byHour = new Map();
  points.forEach(p => byHour.set(p.hourKey, { ...p, samples: (byHour.get(p.hourKey)?.samples || 0) + 1 }));
  const changes = new Map();
  replans.forEach(iso => {
    const k = window.formatTime(iso, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: undefined, hour12: false });
    changes.set(k, (changes.get(k) || 0) + 1);
  });
  return [...byHour.values()].reverse().map(p => ({ ...p, changes: changes.get(p.hourKey) || 0 }));
}

function DhRollupTable({ history, replans }) {
  const pts = rollupByHour(history.points, replans);
  const clsPill = (n, kind) => (
    <span className={`dh-cls-pill ${n > 0 ? kind : 'zero'}`}>{n}</span>
  );
  const healthColor = (pct) =>
    pct >= 90 ? 'var(--ok)' : pct >= 75 ? 'var(--warn)' : 'var(--crit)';
  return (
    <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="panel-head" style={{ padding: 'var(--pad-panel)', paddingBottom: 12 }}>
        <div className="titles">
          <h3 className="panel-title">Hourly Rollup</h3>
          <div className="panel-sub">Last sample of each hour · conflicts by class, PCI changes committed and conflict-free share</div>
        </div>
        <button className="btn-sm" onClick={() => window.exportConflictHistoryCSV()}>
          <Icon name="download" size={12}/>Export CSV
        </button>
      </div>
      <div style={{ overflow: 'auto', maxHeight: 440 }}>
        <table className="dh-tbl">
          <thead>
            <tr>
              <th>Hour</th>
              <th>Samples</th>
              <th>Collision</th>
              <th>Confusion</th>
              <th>Mod-N</th>
              <th>Total</th>
              <th>Changes</th>
              <th style={{ textAlign: 'right' }}>Conflict-free</th>
            </tr>
          </thead>
          <tbody>
            {pts.map((p, i) => (
              <tr key={i}>
                <td>{p.hourLabel}</td>
                <td style={{ color: 'var(--fg-3)' }}>{p.samples}</td>
                <td>{clsPill(p.collision, 'collision')}</td>
                <td>{clsPill(p.confusion, 'confusion')}</td>
                <td>{clsPill(p.modn, 'modn')}</td>
                <td style={{ color: 'var(--fg)', fontWeight: 600 }}>{p.total}</td>
                <td>{p.changes > 0
                  ? <span style={{ color: 'var(--info)' }}>+{p.changes}</span>
                  : <span style={{ color: 'var(--fg-4)' }}>0</span>}</td>
                <td style={{ textAlign: 'right' }}>
                  <span className="dh-health-bar">
                    <span style={{ width: `${p.healthPct}%`, background: healthColor(p.healthPct) }}/>
                  </span>
                  <span style={{ marginLeft: 8, color: 'var(--fg-2)' }}>{p.healthPct}%</span>
                </td>
              </tr>
            ))}
            {!pts.length && (
              <tr><td colSpan={8} style={{ color: 'var(--fg-3)', textAlign: 'center', padding: 24 }}>
                No samples yet — the first row appears about a minute after PM data is ingested.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}


window.exportConflictHistoryCSV = () => {
  const h = window.buildConflictHistory(window.PCI_DATA.HISTORY);
  const head = 'time_utc,collision,confusion,modn,total,conflict_free_pct';
  const body = h.points.map(p =>
    `${p.iso},${p.collision},${p.confusion},${p.modn},${p.total},${p.healthPct}`
  ).join('\n');
  const blob = new Blob([head + '\n' + body], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `pci-conflict-history-${Date.now()}.csv`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};


const PLANNING_TABS = [
  ['plan', 'Plan', 'Import a cell plan and compare the operator assignment against the optimised one'],
  ['history', 'History', 'Conflict trend and hourly rollup since the dashboard started'],
  ['activity', 'Activity', 'Logins, imports, re-plans and configuration changes'],
];

function PciPlanningView({ initialTab = 'plan', onTabChange }) {
  const [tab, setTab] = React.useState(initialTab);
  React.useEffect(() => { setTab(initialTab); }, [initialTab]);
  const pick = (k) => { setTab(k); if (onTabChange) onTabChange(k); };
  const meta = PLANNING_TABS.find(t => t[0] === tab) || PLANNING_TABS[0];

  return (
    <>
      <SectionHead title="PCI Planning" subtitle={meta[2]}
        actions={
          <div className="seg">
            {PLANNING_TABS.map(([k, label]) => (
              <button key={k} data-on={tab === k ? 1 : undefined} onClick={() => pick(k)}>{label}</button>
            ))}
          </div>
        }/>
      {tab === 'plan' && <PlanView embedded/>}
      {tab === 'history' && <DataHistoryView embedded/>}
      {tab === 'activity' && <ActivityView/>}
    </>
  );
}


const ACT_SEV_CLASS = { critical: 'crit', major: 'warn', warning: 'warn', minor: 'info', info: 'info' };

function ActivityView() {
  const [logs, setLogs] = React.useState(null);
  const [err, setErr] = React.useState(null);
  const [filter, setFilter] = React.useState('all');

  const load = React.useCallback(() => {
    fetch('/api/audit?per_page=300')
      .then(r => r.json())
      .then(d => setLogs(d.logs || []))
      .catch(e => setErr(String(e)));
  }, []);
  React.useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const shown = React.useMemo(() => {
    if (!logs) return [];
    if (filter === 'all') return logs;
    if (filter === 'system') return logs.filter(l => l.source === 'system');
    return logs.filter(l => l.source !== 'system');
  }, [logs, filter]);
  const who = (l) => l.actor ? `${l.actor.name}${l.actor.email ? ` · ${l.actor.email}` : ''}` : (l.source || 'system');

  return (
    <div className="panel act-panel">
      <div className="panel-head">
        <div className="titles">
          <h3 className="panel-title">Activity</h3>
          <div className="panel-sub">
            {logs === null ? 'Loading…' : `${logs.length} event${logs.length === 1 ? '' : 's'} since the dashboard started · sign-ins, imports, re-plans and setting changes, each with who did it`}
          </div>
        </div>
        <div className="row-h" style={{ gap: 10 }}>
          <div className="seg sm">
            {[['all','All'],['operator','Operator'],['system','System']].map(([k,l]) => (
              <button key={k} data-on={filter === k ? 1 : undefined} onClick={() => setFilter(k)}>{l}</button>
            ))}
          </div>
          <button className="btn-sm" onClick={load}><Icon name="refresh" size={12}/>Refresh</button>
        </div>
      </div>

      {err && <div className="plan-empty-row">Could not load the activity log: {err}</div>}
      {logs !== null && shown.length === 0 && (
        <div className="plan-empty-row">
          No events yet. Imports, re-plans and configuration changes appear here as they happen.
        </div>
      )}
      <div className="act-list">
        {shown.map(l => (
          <div key={l.id} className={`act-row ${ACT_SEV_CLASS[l.severity] || 'info'}`}>
            <span className="act-bar"/>
            <div className="act-body">
              <div className="act-top">
                <span className="act-kind">{(l.event_type || '').replace(/_/g, ' ')}</span>
                <span className="act-src" title={l.actor ? `${l.actor.role || ''}`.trim() : ''}>{who(l)}</span>
                {l.cell_id && <span className="act-cell">{l.cell_id}</span>}
                {l.pci_old !== null && l.pci_new !== null && (
                  <span className="act-pci">PCI {l.pci_old} → {l.pci_new}</span>
                )}
              </div>
              <div className="act-desc">{l.description}</div>
            </div>
            <span className="act-t" title={l.timestamp}>{window.formatTime(l.timestamp, { year: 'numeric', second: '2-digit', hour12: false })}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DataHistoryView({ embedded }) {
  const [, force] = React.useReducer(x => x + 1, 0);
  const [replans, setReplans] = React.useState([]);
  React.useEffect(() => {
    if (window.subscribePCI) window.subscribePCI(() => force());
    fetch('/api/audit?type=pci_replan&per_page=1000')
      .then(r => r.json())
      .then(d => setReplans((d.logs || []).map(l => l.timestamp).filter(Boolean)))
      .catch(() => {});
  }, []);
  const history = window.buildConflictHistory(window.PCI_DATA.HISTORY);

  return (
    <>
      {!embedded && (
        <SectionHead title="Data History"
          subtitle="PCI conflict and optimization trends across the network."
          actions={
            <button className="btn-sm" onClick={() => window.exportConflictHistoryCSV()}>
              <Icon name="download" size={12}/>Export CSV
            </button>
          }/>
      )}

      <DhStatBand history={history} replans={replans}/>

      <div className="panel">
        <div className="panel-head">
          <div className="titles">
            <h3 className="panel-title">Worst-hit Regions</h3>
            <div className="panel-sub">Ranked by active conflict count</div>
          </div>
        </div>
        <DhWorstRegions/>
      </div>

      <DhRollupTable history={history} replans={replans}/>
    </>
  );
}

function PCIPlanPanel() {
  const [uploads, setUploads] = React.useState([]);
  const [selectedId, setSelectedId] = React.useState(null);
  const [records, setRecords] = React.useState([]);
  const [recTotal, setRecTotal] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const [drag, setDrag] = React.useState(false);
  const [flash, setFlash] = React.useState(null);
  const [applyResult, setApplyResult] = React.useState(null);
  const [filter, setFilter] = React.useState('all');
  const [q, setQ] = React.useState('');
  const fileRef = React.useRef(null);

  const loadUploads = React.useCallback(async () => {
    try {
      const r = await fetch('/api/excel/uploads');
      const j = await r.json();
      const list = (Array.isArray(j) ? j : []).map(u => ({
        ...u,
        applied: !!u.applied_at,
        uploaded_by: u.applied_by || u.uploaded_by || null,
      }));
      setUploads(list);
      if (list.length && selectedId == null) setSelectedId(list[0].id);
    } catch (e) {  }
  }, [selectedId]);

  const loadRecords = React.useCallback(async (id) => {
    if (!id) { setRecords([]); setRecTotal(0); return; }
    try {
      const r = await fetch(`/api/excel/uploads/${id}/records?page=1&per_page=500`);
      const j = await r.json();


      const liveById = {};
      (window.PCI_DATA?.CELLS || []).forEach(c => { liveById[c.id] = c; });
      const PLANNING_FIELDS = [
        'lat', 'lng', 'site_name', 'height_m', 'azimuth',
        'mech_tilt', 'elec_tilt', 'antenna_model',
        'antenna_gain_dbi', 'beamwidth_deg', 'tx_power_dbm',
      ];
      const enriched = (j.records || []).map(rec => {
        const live = liveById[rec.cell_id];

        const diffFields = [];
        if (live) {
          PLANNING_FIELDS.forEach(f => {
            const newVal = rec[f];

            const liveKey = f === 'site_name' ? 'site' : f;
            const oldVal = live[liveKey];
            if (newVal == null) return;
            if (oldVal == null) { diffFields.push(f); return; }
            if (typeof newVal === 'number') {
              if (Math.abs(Number(oldVal) - newVal) > 1e-9) diffFields.push(f);
            } else if (String(oldVal) !== String(newVal)) {
              diffFields.push(f);
            }
          });
        }
        return {
          ...rec,
          live,
          diffFields,
          known_cell: !!live,

          row_status: !rec.valid     ? 'error'
                    : !live           ? 'unknown'
                    : diffFields.length ? 'change'
                                        : 'noop',
        };
      });
      setRecords(enriched);
      setRecTotal(j.total || 0);
    } catch (e) {  }
  }, []);

  React.useEffect(() => { loadUploads(); }, []);
  React.useEffect(() => { loadRecords(selectedId); setApplyResult(null); }, [selectedId, loadRecords]);

  const showFlash = (kind, msg) => {
    setFlash({ kind, msg });


    const hold = kind === 'err' ? 10000 : 4500;
    setTimeout(() => setFlash(null), hold);
  };

  const upload = async (file) => {
    if (!file) return;
    if (!/\.(xlsx|xls|csv)$/i.test(file.name)) { showFlash('err', 'Use .xlsx, .xls, or .csv'); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('description', 'Site & antenna config upload');
      const r = await fetch('/api/excel/upload', { method: 'POST', body: fd });
      const j = await r.json();
      if (!r.ok || !j.ok) {


        let msg = j.error || 'Upload failed';
        if (Array.isArray(j.invalid_rows) && j.invalid_rows.length) {
          const first = j.invalid_rows.slice(0, 3)
            .map(ir => `row ${ir.row}: ${ir.reason}`)
            .join(' · ');
          msg += `  —  ${first}`;
          if (j.invalid_rows.length < (j.invalid_count || 0)) {
            msg += ` … (+${j.invalid_count - j.invalid_rows.length} more)`;
          }
        }
        showFlash('err', msg);
      } else {
        showFlash('ok', `Stored ${j.rows} rows · review and apply to push to the live network.`);
        await loadUploads();
        setSelectedId(j.upload_id);
      }
    } catch (e) { showFlash('err', 'Network error: ' + (e.message || e)); }
    finally { setBusy(false); }
  };

  const apply = async () => {
    if (!selectedId) return;
    setBusy(true); setApplyResult(null);
    try {
      const r = await fetch(`/api/excel/uploads/${selectedId}/apply`, { method: 'POST' });
      const j = await r.json();
      if (!r.ok || !j.ok) {
        showFlash('err', j.error || 'Apply failed');
      } else {
        setApplyResult(j);
        showFlash('ok',
          `${j.applied_count} cell${j.applied_count === 1 ? '' : 's'} configured to the live network ` +
          `· positions and antenna parameters updated`);


        const appliedIds = (j.applied || []).map(a => a.cell_id).filter(Boolean);
        if (appliedIds.length) {
          window.dispatchEvent(new CustomEvent('pci-apply-zoom', {
            detail: { cellIds: appliedIds },
          }));
        }
      }
    } catch (e) { showFlash('err', 'Network error: ' + (e.message || e)); }
    finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!confirm('Delete this PCI plan? Cells already changed are not reverted.')) return;
    try {
      await fetch(`/api/excel/uploads/${id}`, { method: 'DELETE' });
      if (id === selectedId) setSelectedId(null);
      await loadUploads();
    } catch (e) {  }
  };

  const onDrop = (e) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) upload(f);
  };

  const selected = uploads.find(u => u.id === selectedId) || null;
  const fmtTime = (iso) => (window.formatTime ? window.formatTime(iso) : iso);
  const fmtRelative = (iso) => {
    if (!iso) return '—';
    try {
      const d = new Date(/\dZ$|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
      const diff = (Date.now() - d.getTime()) / 1000;
      if (diff < 60)        return Math.round(diff) + 's ago';
      if (diff < 3600)      return Math.round(diff / 60) + 'm ago';
      if (diff < 3600 * 24) return Math.round(diff / 3600) + 'h ago';
      return Math.round(diff / 86400) + 'd ago';
    } catch (e) { return iso; }
  };


  const changedCount   = records.filter(r => r.row_status === 'change').length;
  const unchangedCount = records.filter(r => r.row_status === 'noop').length;
  const unknownCount   = records.filter(r => r.row_status === 'unknown').length;
  const errorCount     = records.filter(r => r.row_status === 'error').length;

  const totalFieldChanges = records.reduce(
    (a, r) => a + (r.row_status === 'change' ? (r.diffFields?.length || 0) : 0), 0,
  );

  const filtered = React.useMemo(() => {
    let rows = records;
    if (q) {
      const t = q.toLowerCase();
      rows = rows.filter(r =>
        (r.cell_id || '').toLowerCase().includes(t) ||
        (r.site_name || '').toLowerCase().includes(t) ||
        (r.live?.site || '').toLowerCase().includes(t) ||
        String(r.lat ?? '').includes(t) ||
        String(r.lng ?? '').includes(t)
      );
    }
    if (filter === 'changed')   rows = rows.filter(r => r.row_status === 'change');
    if (filter === 'unchanged') rows = rows.filter(r => r.row_status === 'noop');
    if (filter === 'errors')    rows = rows.filter(r => r.row_status === 'error');
    if (filter === 'unknown')   rows = rows.filter(r => r.row_status === 'unknown');
    return rows;
  }, [records, q, filter]);


  const [showAntenna, setShowAntenna] = React.useState(false);


  const fmtVal = (v, prec = 4) => {
    if (v == null || v === '') return '—';
    if (typeof v === 'number') return prec === 0 ? Math.round(v).toString() : v.toFixed(prec);
    return String(v);
  };
  const diffCell = (r, field, prec = 4) => {
    const newVal = r[field];
    const liveKey = field === 'site_name' ? 'site' : field;
    const oldVal = r.live ? r.live[liveKey] : null;
    const changed = r.diffFields?.includes(field);
    if (newVal == null) {

      return <span style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>{fmtVal(oldVal, prec)}</span>;
    }
    if (changed) {
      return (
        <span style={{ display: 'inline-flex', gap: 5, alignItems: 'baseline', fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>
          <span style={{ color: 'var(--fg-3)' }}>{fmtVal(oldVal, prec)}</span>
          <span style={{ color: 'var(--accent)' }}>→</span>
          <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmtVal(newVal, prec)}</span>
        </span>
      );
    }
    return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>{fmtVal(newVal, prec)}</span>;
  };

  return (
    <div className="panel ppl-wrap">
      <div className="ppl-head">
        <div className="titles">
          <h3>Site &amp; Antenna Configuration</h3>
          <p>Upload planning data the live gNB feed doesn't carry — coordinates, antenna parameters, site labels. Reviewed and applied on demand.</p>
        </div>
        <div className="ppl-head-actions">
          <a className="btn-sm" href="/api/excel/template" download>
            <Icon name="download" size={12}/>Template
          </a>
          <button className="btn-sm" onClick={() => fileRef.current && fileRef.current.click()} disabled={busy}>
            <Icon name="plus" size={12}/>New Upload
          </button>
          <button className="btn-sm primary" onClick={apply} disabled={!selected || busy}>
            <Icon name="arrowRt" size={12}/>Apply Config
          </button>
        </div>
      </div>

      <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files && e.target.files[0]; e.target.value = ''; upload(f); }}/>

      <div className="ppl-summary">
        <div className="ppl-summary-cell">
          <div className="lbl"><span className="dot ok"/>Stored plans</div>
          <div className="val big">{uploads.length}</div>
          <div className="sub">{uploads.length === 1 ? 'plan' : 'plans'} committed to database</div>
        </div>
        <div className="ppl-summary-cell">
          <div className="lbl"><span className="dot"/>Last upload</div>
          <div className="val">{uploads[0] ? fmtRelative(uploads[0].upload_time) : '—'}</div>
          <div className="sub">{uploads[0] ? `${uploads[0].row_count} rows · ${uploads[0].uploaded_by || 'unknown'}` : 'no uploads yet'}</div>
        </div>
        <div className="ppl-summary-cell">
          <div className="lbl"><span className={`dot ${selected && !selected.applied ? 'warn' : 'ok'}`}/>Selected plan</div>
          <div className="val" title={selected ? selected.filename : ''}>
            {selected ? selected.filename.replace(/^\d{8}_\d{6}_/, '') : '—'}
          </div>
          <div className="sub">
            {selected
              ? <>{recTotal} rows · <span style={{ color: 'var(--accent)' }}>{changedCount} cell{changedCount === 1 ? '' : 's'} to update</span></>
              : 'pick a plan to preview'}
          </div>
        </div>
        <div className="ppl-summary-cell">
          <div className="lbl"><span className="dot"/>Required schema</div>
          <div className="val" style={{ fontSize: 13, color: 'var(--fg-2)' }}>cell_id · lat · lng · azimuth</div>
          <div className="sub">+ 8 optional antenna fields · template available</div>
        </div>
      </div>

      {flash && (
        <div className={`ppl-flash ${flash.kind}`} role="status">
          <Icon name={flash.kind === 'ok' ? 'check' : 'alert'} size={flash.kind === 'err' ? 18 : 14}/>
          <span>{flash.msg}</span>
        </div>
      )}

      <div className="ppl-body">
        <aside className="ppl-side">
          <div className={`ppl-dropzone ${drag ? 'drag' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            onClick={() => !busy && fileRef.current && fileRef.current.click()}>
            <div className="ppl-dropzone-icon"><Icon name="upload" size={18}/></div>
            <div className="ppl-dropzone-t1">Drop a plan file</div>
            <div className="ppl-dropzone-t2">or <span className="lk">browse</span><br/>.xlsx · .xls · .csv</div>
            {busy && <div className="ppl-dropzone-busy">uploading…</div>}
          </div>

          <div className="ppl-side-head">
            <span className="t">Uploads</span>
            <span className="count">{uploads.length}</span>
          </div>

          <div className="ppl-list">
            {uploads.length === 0 && (
              <div className="ppl-side-empty">No plans uploaded yet.</div>
            )}
            {uploads.map(u => {
              const isSel = u.id === selectedId;
              return (
                <div key={u.id} className={`ppl-card ${isSel ? 'selected' : ''}`} onClick={() => setSelectedId(u.id)}>
                  <div className="ico"><Icon name="file" size={14}/></div>
                  <div className="meta">
                    <div className="name" title={u.filename}>{u.filename.replace(/^\d{8}_\d{6}_/, '')}</div>
                    <div className="info">
                      <span>{u.row_count} rows</span>
                      <span className="dot"/>
                      <span>{fmtRelative(u.upload_time)}</span>
                      <span className="dot"/>
                      <span className={`badge ${u.applied ? 'applied' : 'pending'}`}>{u.applied ? 'applied' : 'pending'}</span>
                    </div>
                  </div>
                  <button className="del" onClick={(e) => { e.stopPropagation(); remove(u.id); }} title="Delete plan">
                    <Icon name="x" size={12}/>
                  </button>
                </div>
              );
            })}
          </div>
        </aside>

        <section className="ppl-main">
          <div className="ppl-main-head">
            <div>
              <div className="t-title">
                {selected ? <>Preview <span className="filename">· {selected.filename.replace(/^\d{8}_\d{6}_/, '')}</span></> : 'Preview'}
              </div>
              <div className="t-sub">
                {selected
                  ? <>Showing {filtered.length} of {records.length} rows · {changedCount} cell{changedCount === 1 ? '' : 's'} to update · {totalFieldChanges} field change{totalFieldChanges === 1 ? '' : 's'}{errorCount > 0 && <> · <span style={{ color: 'var(--crit)' }}>{errorCount} validation error{errorCount === 1 ? '' : 's'}</span></>}</>
                  : 'Select an upload from the list to preview its rows'}
              </div>
            </div>
          </div>

          {selected && records.length > 0 && (
            <div className="ppl-filters">
              <div className="ppl-search">
                <Icon name="search" size={12}/>
                <input placeholder="Filter rows by cell, site, or coordinates…" value={q} onChange={(e) => setQ(e.target.value)}/>
              </div>
              <button className="ppl-chip" data-on={filter === 'all' ? '1' : '0'} onClick={() => setFilter('all')}>
                All <span className="ct">{records.length}</span>
              </button>
              <button className="ppl-chip" data-on={filter === 'changed' ? '1' : '0'} onClick={() => setFilter('changed')}>
                Changed <span className="ct">{changedCount}</span>
              </button>
              <button className="ppl-chip" data-on={filter === 'unchanged' ? '1' : '0'} onClick={() => setFilter('unchanged')}>
                No-op <span className="ct">{unchangedCount}</span>
              </button>
              {unknownCount > 0 && (
                <button className="ppl-chip" data-on={filter === 'unknown' ? '1' : '0'} onClick={() => setFilter('unknown')}>
                  Unknown <span className="ct">{unknownCount}</span>
                </button>
              )}
              {errorCount > 0 && (
                <button className="ppl-chip" data-on={filter === 'errors' ? '1' : '0'} onClick={() => setFilter('errors')}>
                  Errors <span className="ct">{errorCount}</span>
                </button>
              )}
              <button className="ppl-chip" data-on={showAntenna ? '1' : '0'}
                      onClick={() => setShowAntenna(v => !v)}
                      title="Show antenna parameters in the table">
                Antenna <Icon name={showAntenna ? 'check' : 'plus'} size={11}/>
              </button>
            </div>
          )}

          <div className="ppl-table-wrap">
            {!selected && (
              <div className="ppl-empty">
                <div className="ppl-empty-ico"><Icon name="list" size={22}/></div>
                <div className="t">No plan selected</div>
                <div className="s">Upload a new sheet, or pick one from the sidebar to preview proposed PCI changes before applying.</div>
              </div>
            )}
            {selected && records.length === 0 && (
              <div className="ppl-empty">
                <div className="ppl-empty-ico"><Icon name="file" size={22}/></div>
                <div className="t">This plan is empty</div>
                <div className="s">No data rows were parsed from the upload. Check that the sheet matches the template.</div>
              </div>
            )}
            {selected && filtered.length === 0 && records.length > 0 && (
              <div className="ppl-empty">
                <div className="ppl-empty-ico"><Icon name="search" size={22}/></div>
                <div className="t">No rows match the filter</div>
                <div className="s">Try a different search term, or switch to a broader filter.</div>
              </div>
            )}
            {selected && filtered.length > 0 && (
              <table className="ppl-tbl">
                <thead>
                  <tr>
                    <th style={{ width: 48 }}>Row</th>
                    <th>Cell</th>
                    <th style={{ width: 150 }}>Site</th>
                    <th style={{ width: 130 }}>Latitude</th>
                    <th style={{ width: 130 }}>Longitude</th>
                    <th style={{ width: 90 }}>Height (m)</th>
                    <th style={{ width: 90 }}>Azimuth</th>
                    {showAntenna && <>
                      <th style={{ width: 90 }}>Mech tilt</th>
                      <th style={{ width: 90 }}>Elec tilt</th>
                      <th style={{ width: 130 }}>Antenna model</th>
                      <th style={{ width: 90 }}>Gain (dBi)</th>
                      <th style={{ width: 100 }}>Beamwidth (°)</th>
                      <th style={{ width: 100 }}>TX power (dBm)</th>
                    </>}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(r => (
                    <tr key={r.id} className={r.row_status === 'change' ? 'row-changed' : ''}>
                      <td className="row-num">{r.row_num}</td>
                      <td>
                        <div className="cell-id">{r.cell_id || <span style={{ color: 'var(--fg-4)' }}>—</span>}</div>
                        {r.live?.region && <div className="site">{r.live.region}</div>}
                      </td>
                      <td>{diffCell(r, 'site_name', 0)}</td>
                      <td>{diffCell(r, 'lat', 4)}</td>
                      <td>{diffCell(r, 'lng', 4)}</td>
                      <td>{diffCell(r, 'height_m', 1)}</td>
                      <td>{diffCell(r, 'azimuth', 0)}</td>
                      {showAntenna && <>
                        <td>{diffCell(r, 'mech_tilt', 1)}</td>
                        <td>{diffCell(r, 'elec_tilt', 1)}</td>
                        <td>{diffCell(r, 'antenna_model', 0)}</td>
                        <td>{diffCell(r, 'antenna_gain_dbi', 1)}</td>
                        <td>{diffCell(r, 'beamwidth_deg', 0)}</td>
                        <td>{diffCell(r, 'tx_power_dbm', 1)}</td>
                      </>}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {selected && records.length > 0 && (
            <div className="ppl-foot">
              <div className="ppl-foot-stat change">
                <span className="n">{changedCount}</span>
                <span className="l">cells to update</span>
              </div>
              <div className="ppl-foot-divider"/>
              <div className="ppl-foot-stat">
                <span className="n">{totalFieldChanges}</span>
                <span className="l">field changes</span>
              </div>
              <div className="ppl-foot-divider"/>
              <div className="ppl-foot-stat">
                <span className="n">{unchangedCount}</span>
                <span className="l">no-op</span>
              </div>
              {unknownCount > 0 && <>
                <div className="ppl-foot-divider"/>
                <div className="ppl-foot-stat error">
                  <span className="n">{unknownCount}</span>
                  <span className="l">unknown cells</span>
                </div>
              </>}
              {errorCount > 0 && <>
                <div className="ppl-foot-divider"/>
                <div className="ppl-foot-stat error">
                  <span className="n">{errorCount}</span>
                  <span className="l">errors</span>
                </div>
              </>}
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
                {applyResult ? (
                  <span style={{ color: 'var(--ok)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    ✓ {applyResult.applied_count} cell{applyResult.applied_count === 1 ? '' : 's'} configured to the live network
                    {applyResult.skipped_count ? ` · ${applyResult.skipped_count} skipped` : ''}
                  </span>
                ) : (
                  <span style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>
                    Ready · click <b style={{ color: 'var(--fg-2)' }}>Apply Config</b> to push to live network
                  </span>
                )}
              </div>
            </div>
          )}

          {applyResult && (applyResult.skipped_count > 0 || (applyResult.skipped && applyResult.skipped.length > 0)) && (
            <div style={{ padding: '0 22px 16px' }}>
              <div className="ppl-skipped">
                {(applyResult.skipped || []).map((s, i) => (
                  <div key={i}>
                    <span className="r">#{s.row}</span>
                    <span className="c">{s.cell_id || '—'}</span>
                    <span className="why">{s.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function PciReplanHistoryPanel() {
  const [replans, setReplans] = React.useState([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    try {
      const r = await fetch('/api/audit?per_page=200');
      const j = await r.json();
      const logs = (j.logs || []).filter(l =>
        l.pci_old != null && l.pci_new != null && l.pci_old !== l.pci_new
      );
      setReplans(logs.slice(0, 10));
    } catch (e) {  }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    load();

    if (window.subscribePCI) window.subscribePCI(() => load());
  }, [load]);

  const fmtTime = (iso) => window.formatTime
    ? window.formatTime(iso, { hour: '2-digit', minute: '2-digit', second: '2-digit', month: undefined, day: undefined })
    : (iso || '').slice(11, 19);

  const sourceLabel = (src) => {
    if (!src) return 'system';
    if (src === 'auto_detect' || src === 'auto-rapp' || src === 'system') return 'auto-rApp';
    if (src === 'operator') return 'operator';
    return src;
  };
  const sourceColor = (src) => {
    const lbl = sourceLabel(src);
    if (lbl === 'auto-rApp') return 'var(--accent)';
    if (lbl === 'operator') return 'var(--info)';
    return 'var(--fg-3)';
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="titles">
          <h3 className="panel-title">PCI Re-plan History</h3>
          <div className="panel-sub">{replans.length === 0 ? 'No PCI swaps yet' : `${replans.length} recent swap${replans.length === 1 ? '' : 's'}`}</div>
        </div>
        <button className="btn-sm" onClick={load} title="Refresh">
          <Icon name="refresh" size={12}/>
        </button>
      </div>
      {loading && replans.length === 0 && (
        <div style={{ padding: '14px 0', color: 'var(--fg-3)', fontSize: 13 }}>Loading…</div>
      )}
      {!loading && replans.length === 0 && (
        <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
          <Icon name="activity" size={22} style={{ opacity: 0.4, marginBottom: 6 }}/>
          <div>No PCI re-plans logged.</div>
          <div style={{ fontSize: 11.5, marginTop: 4 }}>Re-plan a cell from the Cell Map to populate this list.</div>
        </div>
      )}
      {replans.map(l => (
        <div key={l.id} className="row-h" style={{ justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px dashed var(--line)', gap: 10 }}>
          <span style={{ minWidth: 0, flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 13 }}>
              <span className="mono" style={{ color: 'var(--fg)', fontWeight: 600 }}>{l.cell_id || '—'}</span>
              <span className="mono" style={{ color: 'var(--fg-3)', fontSize: 12 }}>
                PCI <span style={{ color: 'var(--fg-2)' }}>{l.pci_old}</span>
                <span style={{ margin: '0 4px' }}>→</span>
                <span style={{ color: 'var(--accent)' }}>{l.pci_new}</span>
              </span>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--fg-3)', marginTop: 3 }}>{fmtTime(l.timestamp)}</div>
          </span>
          <span className="mono" style={{
            fontSize: 11, padding: '3px 8px', borderRadius: 999,
            color: sourceColor(l.source),
            background: `color-mix(in oklch, ${sourceColor(l.source)} 12%, transparent)`,
            border: `1px solid color-mix(in oklch, ${sourceColor(l.source)} 30%, transparent)`,
            textTransform: 'uppercase', letterSpacing: '0.04em',
            whiteSpace: 'nowrap', flex: '0 0 auto',
          }}>{sourceLabel(l.source)}</span>
        </div>
      ))}
    </div>
  );
}

const SETTINGS_DEFAULTS = {
  prb_warning: '80',

  theme_mode: 'light',

  account_name: 'Operator',
  account_timezone: 'Asia/Kolkata',

  notif_desktop: 'on',
  notif_sound_critical: 'on',
  notif_sound_minor: 'off',
  notif_quiet_start: '',
  notif_quiet_end: '',
};


const SETTINGS_SECTIONS = [
  { id: 'thresholds',  icon: 'activity', label: 'Thresholds',    title: 'Thresholds & Detection',   sub: 'When the incident feed raises a congestion alert' },
  { id: 'appearance',  icon: 'sun',      label: 'Appearance',    title: 'Theme & Appearance',       sub: 'Visual treatment applied across the dashboard' },
  { id: 'account',     icon: 'settings', label: 'Account',       title: 'Account & Profile',        sub: 'Identity recorded in the activity log' },
  { id: 'notifications', icon: 'bell',   label: 'Notifications', title: 'Notifications & Sounds',   sub: 'Alert delivery, sound and quiet hours' },
];


function SettingsView({ setTheme }) {
  const [s, setS] = React.useState(() => ({ ...SETTINGS_DEFAULTS, ...(window.PCI_SETTINGS || {}) }));
  const savedRef = React.useRef(s);
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [savedAt, setSavedAt] = React.useState(null);
  const [err, setErr] = React.useState(null);
  const [activeSection, setActiveSection] = React.useState(SETTINGS_SECTIONS[0].id);
  const sectionRefs = React.useRef({});


  React.useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then(remote => {
        const next = { ...SETTINGS_DEFAULTS };
        Object.keys(SETTINGS_DEFAULTS).forEach(k => { if (remote[k] != null) next[k] = remote[k]; });
        savedRef.current = next;
        setS(next);
      })
      .catch(() => {  });
  }, []);


  React.useEffect(() => {
    const obs = new IntersectionObserver((entries) => {
      const visible = entries.filter(e => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (visible[0]) setActiveSection(visible[0].target.id);
    }, { rootMargin: '-100px 0px -55% 0px', threshold: [0.1, 0.5, 1] });
    SETTINGS_SECTIONS.forEach(sec => {
      const el = sectionRefs.current[sec.id];
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, []);

  const update = (key, val) => { setS(p => ({ ...p, [key]: val })); setDirty(true); };

  const save = async () => {
    setSaving(true); setErr(null);
    try {
      const body = {};
      Object.keys(SETTINGS_DEFAULTS).forEach(k => { body[k] = s[k]; });
      const r = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      savedRef.current = { ...s };
      if (window.applySettings) window.applySettings(body);
      window.reloadPciData && window.reloadPciData(undefined, { quiet: true });
      if (typeof setTheme === 'function') setTheme(s.theme_mode);
      setDirty(false);
      setSavedAt(new Date().toLocaleTimeString('en-GB', {
        timeZone: (window.PCI_SETTINGS || {}).account_timezone || undefined,
        hour12: false,
      }));
    } catch (e) { setErr(e.message || 'Failed to save'); }
    setSaving(false);
  };

  const reset = () => { setS(savedRef.current); setDirty(false); };

  const scrollTo = (id) => {
    const el = sectionRefs.current[id];
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setActiveSection(id);
  };


  const Switch = ({ value, onChange }) => (
    <button className="stg-switch" data-on={value === 'on' ? 1 : 0} aria-pressed={value === 'on'}
      onClick={() => onChange(value === 'on' ? 'off' : 'on')}/>
  );
  const Seg = ({ value, options, onChange }) => (
    <span className="stg-seg">
      {options.map(([k, label]) => (
        <button key={k} data-on={value === k ? 1 : 0} onClick={() => onChange(k)}>{label}</button>
      ))}
    </span>
  );
  const Row = ({ label, hint, stack, children }) => (
    <div className={`stg-row ${stack ? 'stg-row-stack' : ''}`}>
      <div className="stg-row-label">
        <span className="l">{label}</span>
        {hint && <span className="h">{hint}</span>}
      </div>
      <div className="stg-row-control">{children}</div>
    </div>
  );


  const initials = (s.account_name || 'M M').split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();

  const renderSection = (id) => {
    switch (id) {
      case 'thresholds': return (
        <>
          <Row label="PRB congestion warning" hint="A cell above this DL PRB utilisation raises a PRB Congestion incident (major at +10 points).">
            <input className="stg-input" type="number" min="1" max="100" step="1" style={{ width: 90 }}
              value={s.prb_warning}
              onChange={(e) => update('prb_warning', e.target.value)}/>
            <span className="stg-unit">%</span>
          </Row>
          <Row label="PCI conflicts" hint="Collision, confusion and mod-N detection follow the rApp config (configs/config.yaml → scoring, shadow_nrt); they are not toggled per user.">
            <span style={{ fontSize: 13, color: 'var(--fg-3)' }}>always on</span>
          </Row>
        </>
      );

      case 'appearance': return (
        <>
          <Row label="Theme mode" hint="Light is best for daytime ops, dark suits NOC walls and overnight shifts.">
            <Seg value={s.theme_mode}
              options={[['light','Light'],['dark','Dark']]}
              onChange={(v) => update('theme_mode', v)}/>
          </Row>
        </>
      );

      case 'account': return (
        <>
          <div style={{ padding: '14px 24px 0' }}>
            <div className="stg-profile-card">
              <div className="stg-profile-avatar">{initials}</div>
              <div className="stg-profile-meta">
                <div className="n">{s.account_name || '—'}</div>
              </div>
            </div>
          </div>
          <Row label="Display name" hint="Recorded as the actor on every sign-in, re-plan, import and settings change in the activity log." stack>
            <input className="stg-input text" value={s.account_name}
              onChange={(e) => update('account_name', e.target.value)}/>
          </Row>
          <Row label="Timezone" hint="Timestamps and quiet hours are shown in this zone.">
            <select className="stg-select" value={s.account_timezone}
              onChange={(e) => update('account_timezone', e.target.value)}>
              <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
              <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
              <option value="Europe/London">Europe/London (GMT)</option>
              <option value="Europe/Berlin">Europe/Berlin (CET)</option>
              <option value="America/New_York">America/New_York (EST)</option>
              <option value="UTC">UTC</option>
            </select>
          </Row>
        </>
      );

      case 'notifications': return (
        <>
          <Row label="Desktop notifications" hint="Browser pop-up notifications for new critical and major alerts.">
            <Switch value={s.notif_desktop} onChange={(v) => update('notif_desktop', v)}/>
          </Row>
          <Row label="Sound on critical" hint="Two-tone audio cue when a critical alert fires.">
            <Switch value={s.notif_sound_critical} onChange={(v) => update('notif_sound_critical', v)}/>
          </Row>
          <Row label="Sound on minor" hint="Single chime for minor / informational alerts.">
            <Switch value={s.notif_sound_minor} onChange={(v) => update('notif_sound_minor', v)}/>
          </Row>
          <Row label="Quiet hours" hint="Suppress sound and desktop popups during this window. Critical alerts still surface in-app.">
            <input className="stg-input stg-input-time" type="time" value={s.notif_quiet_start}
              onChange={(e) => update('notif_quiet_start', e.target.value)}/>
            <span className="stg-unit" style={{ padding: '0 4px' }}>to</span>
            <input className="stg-input stg-input-time" type="time" value={s.notif_quiet_end}
              onChange={(e) => update('notif_quiet_end', e.target.value)}/>
          </Row>
        </>
      );

      default: return null;
    }
  };

  const savebarMsg = (() => {
    if (err)   return { cls: 'err',   text: <>Failed to save · <b>{err}</b></> };
    if (saving) return { cls: 'dirty', text: <>Saving changes…</> };
    if (dirty) return { cls: 'dirty', text: <><b>Unsaved changes</b> · review and click <b>Save</b> to apply across the dashboard.</> };
    return { cls: '', text: 'All changes are applied automatically when you save.' };
  })();

  return (
    <>
      <SectionHead title="Settings" subtitle={navSub('settings')}/>

      <div className="stg-shell">
        <aside className="stg-nav">
          <div className="stg-nav-head">Sections</div>
          {SETTINGS_SECTIONS.map(sec => (
            <button key={sec.id} className="stg-nav-item" data-on={activeSection === sec.id ? 1 : 0}
              onClick={() => scrollTo(sec.id)}>
              <Icon name={sec.icon} size={15} className="ico"/>
              <span>{sec.label}</span>
            </button>
          ))}
        </aside>

        <div className="stg-content">
          {SETTINGS_SECTIONS.map(sec => (
            <section key={sec.id} id={sec.id} className="stg-section"
              ref={(el) => { sectionRefs.current[sec.id] = el; }}>
              <div className="stg-section-head">
                <div className="stg-section-ico"><Icon name={sec.icon} size={18}/></div>
                <div className="stg-section-titles">
                  <h3>{sec.title}</h3>
                  <p>{sec.sub}</p>
                </div>
              </div>
              {renderSection(sec.id)}
            </section>
          ))}

          <div className={`stg-savebar ${dirty || err ? '' : 'idle'}`}>
            <div className={`stg-savebar-msg ${savebarMsg.cls}`}>{savebarMsg.text}</div>
            <button className="btn-sm" onClick={reset} disabled={saving || !dirty}>Discard</button>
            <button className="btn-sm primary" onClick={save} disabled={!dirty || saving}>
              {saving ? 'Saving…' : (dirty ? 'Save changes' : 'Saved')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}


function App() {
  const [theme, setTheme] = useTheme();
  const [section, setSection] = React.useState('overview');

  const [planningTab, setPlanningTab] = React.useState('plan');
  const [selectedCell, setSelectedCell] = React.useState(null);
  const [notifOpen, setNotifOpen] = React.useState(false);
  const settings = useSettings();


  const [, setTick] = React.useState(0);
  React.useEffect(() => {
    if (window.subscribePCI) window.subscribePCI(() => setTick(n => n + 1));
  }, []);


  React.useEffect(() => {
    const onApplyZoom = () => {
      setSection('cell-map');
      setSelectedCell(null);
      window.scrollTo({ top: 0 });
    };
    window.addEventListener('pci-apply-zoom', onApplyZoom);
    return () => window.removeEventListener('pci-apply-zoom', onApplyZoom);
  }, []);


  const seenAlertIds = React.useRef(new Set());
  const audioCtxRef = React.useRef(null);
  React.useEffect(() => {

    const init = window.PCI_DATA?.ALERTS || [];
    init.forEach(a => seenAlertIds.current.add(a.id));

    if (window.subscribeSettings) {
      window.subscribeSettings((s) => {
        if (s.notif_desktop === 'on' && typeof Notification !== 'undefined' && Notification.permission === 'default') {
          Notification.requestPermission().catch(() => {});
        }
      });
    }
    if (!window.subscribePCI) return;
    window.subscribePCI((state) => {
      const alerts = state.ALERTS || window.PCI_DATA?.ALERTS || [];
      const s = window.PCI_SETTINGS || {};

      const inQuietHours = (() => {
        const qs = s.notif_quiet_start, qe = s.notif_quiet_end;
        if (!qs || !qe) return false;
        const tz = s.account_timezone || undefined;
        const nowStr = new Date().toLocaleString('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false });
        const cur = nowStr;
        return qs <= qe ? (cur >= qs && cur < qe) : (cur >= qs || cur < qe);
      })();
      const quiet = !!window.__PCI_QUIET_INGEST;
      alerts.forEach(a => {
        if (seenAlertIds.current.has(a.id)) return;
        seenAlertIds.current.add(a.id);
        if (inQuietHours || quiet) return;
        const isCritical = a.sev === 'critical' || a.sev === 'major';
        const isMinor = a.sev === 'minor' || a.sev === 'info';

        if (isCritical && s.notif_desktop === 'on' && typeof Notification !== 'undefined' && Notification.permission === 'granted') {
          try {
            new Notification(`${a.sev?.toUpperCase() || 'ALERT'} · ${a.kind || 'PCI rApp'}${a.cell && a.cell !== '—' ? ` · ${a.cell}` : ''}`, {
              body: a.msg || 'New alert',
              tag: a.id,
              silent: true,
            });
          } catch (e) {  }
        }

        const playBeep = (freq, durMs) => {
          try {
            if (!audioCtxRef.current) {
              const Ctx = window.AudioContext || window.webkitAudioContext;
              if (!Ctx) return;
              audioCtxRef.current = new Ctx();
            }
            const ctx = audioCtxRef.current;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.0001, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + durMs / 1000);
            osc.connect(gain).connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + durMs / 1000 + 0.02);
          } catch (e) {  }
        };
        if (isCritical && s.notif_sound_critical === 'on') { playBeep(880, 220); setTimeout(() => playBeep(660, 220), 260); }
        else if (isMinor && s.notif_sound_minor === 'on')  { playBeep(540, 180); }
      });
    });
  }, []);


  const _settingsSynced = React.useRef(false);
  React.useEffect(() => {
    if (!settings || !settings.theme_mode || _settingsSynced.current) return;
    _settingsSynced.current = true;
    let persisted = null;
    try { persisted = localStorage.getItem('pci-theme'); } catch (e) {}
    if (!persisted && settings.theme_mode !== theme) setTheme(settings.theme_mode);
  }, [settings.theme_mode]);

  React.useEffect(() => {
    const html = document.documentElement;
    [...html.classList].forEach(c => { if (c.startsWith('theme-')) html.classList.remove(c); });
    html.classList.add('theme-' + theme);
  }, [theme]);

  const rootCls = `app theme-${theme}`;
  const current = NAV.find(n => n.k === section) || NAV[0];

  return (
    <div className={rootCls}>
      <Sidebar
        active={section}
        onSelect={(k) => { setSection(k); setSelectedCell(null); window.scrollTo({ top: 0 }); }}
        onOpenNotifications={() => setNotifOpen(true)}
      />

      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar
          theme={theme}
          sectionTitle={current.title}
          onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          onSelectCell={setSelectedCell}
          onNavigate={(k) => { setSection(k); setSelectedCell(null); window.scrollTo({ top: 0 }); }}
        />

        <main className="main">
          {section === 'overview'     && <OverviewView    onSelectCell={setSelectedCell} selectedCell={selectedCell} onNavigate={(k) => { setSection(k); setSelectedCell(null); window.scrollTo({ top: 0 }); }}/>}
          {section === 'cell-map'     && <CellMapView     onSelectCell={setSelectedCell} selectedCell={selectedCell}/>}
          {section === 'pci-planning' && <PciPlanningView initialTab={planningTab} onTabChange={setPlanningTab}/>}
          {section === 'settings'     && <SettingsView    setTheme={setTheme}/>}
          {settings.brand_footer && (
            <div style={{ marginTop: 32, padding: '14px 0', borderTop: '1px solid var(--bd)', color: 'var(--fg-3)', fontSize: 12, textAlign: 'center', letterSpacing: '0.02em' }}>
              {settings.brand_footer}
            </div>
          )}
        </main>
      </div>

      <DrilldownDrawer
        cell={selectedCell}
        onClose={() => setSelectedCell(null)}
        onShowOnMap={(c) => {
          if (!c || !c.id) return;
          window.dispatchEvent(new CustomEvent('pci-apply-zoom', { detail: { cellIds: [c.id] } }));
        }}
      />
      <NotificationsDrawer
        open={notifOpen}
        onClose={() => setNotifOpen(false)}
        onJumpToAudit={() => { setPlanningTab('activity'); setSection('pci-planning'); window.scrollTo({ top: 0 }); }}
      />

    </div>
  );
}


function __mountPciApp() {
  ReactDOM.createRoot(document.getElementById('root')).render(<App />);
}
if (window.__PCI_BOOT && window.__PCI_BOOT.then) {
  window.__PCI_BOOT.then(__mountPciApp).catch(__mountPciApp);
} else {
  __mountPciApp();
}
