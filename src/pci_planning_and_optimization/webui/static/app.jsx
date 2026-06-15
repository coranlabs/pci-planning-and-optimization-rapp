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


