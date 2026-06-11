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


