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

// Basemap. Blank by default, so the dashboard makes no third-party request,
// works in an air-gapped cluster, and does not hand a tile host the operator's
// map viewport. Set a style URL, your own tile server or a public basemap, for
// street detail.
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

