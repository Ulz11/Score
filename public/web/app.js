/* SCORING — vanilla JS glue for the 4 services. */

const _LOCAL = ['127.0.0.1', 'localhost'].includes(location.hostname);
const API = {
  team:   _LOCAL ? 'http://127.0.0.1:8011' : '/api/team',
  netdef: _LOCAL ? 'http://127.0.0.1:8012' : '/api/netdef',
  money:  _LOCAL ? 'http://127.0.0.1:8013' : '/api/money',
  judge:  _LOCAL ? 'http://127.0.0.1:8014' : '/api/judge',
};

// ─────────────────────────── helpers ───────────────────────────
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

async function api(svc, path, opts = {}) {
  const init = {
    method: opts.method || 'GET',
    headers: { ...(opts.headers || {}) },
    credentials: 'include',
  };
  if (opts.body !== undefined) {
    init.method = opts.method || 'POST';
    init.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
    init.headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(API[svc] + path, init);
  const text = await res.text();
  let data; try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw { status: res.status, data };
  return data;
}

async function ensureSignedIn() {
  try {
    const me = await api('team', '/auth/whoami');
    if (me.authenticated) return me;
  } catch {}
  const handle = prompt('Admin sign-in · handle:');
  if (!handle) return null;
  const password = prompt('password:');
  if (!password) return null;
  try {
    return await api('team', '/auth/login', { body: { handle, password } });
  } catch (err) {
    alert(err.status === 401 ? 'invalid handle or password' : `error ${err.status}`);
    return null;
  }
}

function readForm(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    let v = el.value;
    if (v === '') continue;
    if (el.type === 'number') v = Number(v);
    out[el.name] = v;
  }
  return out;
}

function showResult(boxId, label, data) {
  const box = document.getElementById(boxId);
  const stamp = new Date().toLocaleTimeString();
  const body = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  const block = `┌─ ${stamp}  ${label}\n${body}\n└────\n`;
  if (box.querySelector('.empty')) box.textContent = '';
  box.textContent = block + box.textContent;
}

function showError(boxId, label, err) {
  showResult(boxId, `${label} — ERROR ${err.status}`, err.data);
}

function fillSelect(sel, items, valKey, labelFn, includeBlank = false) {
  const cur = sel.value;
  sel.innerHTML = '';
  if (includeBlank) {
    const o = document.createElement('option');
    o.value = ''; o.textContent = '— none —';
    sel.appendChild(o);
  }
  for (const it of items) {
    const o = document.createElement('option');
    o.value = it[valKey];
    o.textContent = labelFn(it);
    sel.appendChild(o);
  }
  if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
}

// ─────────────────────────── tab switcher ───────────────────────────
function setActiveTab(name) {
  $$('[data-section]').forEach(s => { s.hidden = s.dataset.section !== name; });
  $$('[data-tab]').forEach(b => b.classList.toggle('is-active', b.dataset.tab === name));
}
$$('[data-tab]').forEach(b => b.addEventListener('click', () => setActiveTab(b.dataset.tab)));
document.addEventListener('keydown', e => {
  if (e.target.matches('input, textarea, select')) return;
  const map = { '1': 'team', '2': 'netdef', '3': 'money', '4': 'judge' };
  if (map[e.key]) setActiveTab(map[e.key]);
  if (e.key.toLowerCase() === 'r') refreshWitness();
});

// ─────────────────────────── shared state ───────────────────────────
const state = {
  workers: [], projects: [], tasks: [], meetings: [], transactions: [], votes: [],
};

async function refreshAll() {
  await Promise.all([
    refreshWorkers(),
    refreshProjects(),
    refreshTasks(),
    refreshChain(),
    refreshWitness(),
  ]);
}

// ─────────────────────────── TEAM ───────────────────────────
async function refreshWorkers() {
  try {
    state.workers = await api('team', '/workers');
  } catch (e) { showError('teamOut', 'GET /workers', e); return; }

  // table
  const tbody = $('#workersTable tbody');
  tbody.innerHTML = '';
  for (const w of state.workers) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="mono">${w.id}</td>
                    <td class="mono">@${w.handle}</td>
                    <td>${w.name}</td>
                    <td><span class="tag">${w.type}</span></td>
                    <td class="tabular">${w.base_salary.toFixed(2)} ${w.salary_currency}</td>
                    <td>${w.active ? '●' : '○'}</td>`;
    tbody.appendChild(tr);
  }
  $('#workersCounter').textContent = String(state.workers.length).padStart(3, '0');

  // sidebar roster
  const roster = $('#rosterBox');
  if (state.workers.length === 0) {
    roster.innerHTML = '<span class="empty">no workers yet.</span>';
  } else {
    roster.textContent = state.workers
      .map(w => `#${w.id}  @${w.handle.padEnd(8)} ${w.name}`)
      .join('\n');
  }
  $('#rosterCounter').textContent = String(state.workers.length).padStart(3, '0');

  // option lists everywhere
  const lbl = w => `#${w.id} ${w.name} (@${w.handle})`;
  ['#taskFormAssignee', '#taskFormCreator', '#perfWorker', '#peerScorer',
   '#commentAuthor', '#inboxWorker', '#ballotVoter']
    .forEach(sel => {
      const el = $(sel);
      if (!el) return;
      const blank = ['#taskFormAssignee', '#taskFormCreator'].includes(sel);
      fillSelect(el, state.workers, 'id', lbl, blank);
    });
}

async function refreshProjects() {
  try {
    // No GET /projects endpoint exists — we keep what we created locally
    // by re-using whatever the worker list told us. Project rows that
    // already exist server-side won't be visible unless created here.
    // (Acceptable for a one-screen demo.)
  } catch (e) { /* noop */ }

  const tbody = $('#projectsTable tbody');
  tbody.innerHTML = '';
  for (const p of state.projects) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="mono">${p.id}</td>
                    <td>${p.name}</td>
                    <td><span class="tag">${p.status}</span></td>
                    <td class="mono">${p.started_at}</td>`;
    tbody.appendChild(tr);
  }
  $('#projectsCounter').textContent = String(state.projects.length).padStart(3, '0');

  const lbl = p => `#${p.id} ${p.name}`;
  fillSelect($('#taskFormProject'), state.projects, 'id', lbl);
  fillSelect($('#taskProjectFilter'), state.projects, 'id', lbl, true);
  $('#taskProjectFilter').firstElementChild.textContent = '— all —';
}

async function refreshTasks() {
  // No bulk GET /tasks either — keep what we created locally.
  const filter = $('#taskProjectFilter').value;
  const tbody = $('#tasksTable tbody');
  tbody.innerHTML = '';
  const rows = filter ? state.tasks.filter(t => String(t.project_id) === filter) : state.tasks;
  for (const t of rows) {
    const wa = state.workers.find(w => w.id === t.assignee_id);
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="mono">${t.id}</td>
                    <td class="mono">${t.project_id}</td>
                    <td>${t.title}</td>
                    <td class="tabular">${t.weight}</td>
                    <td>${wa ? '@' + wa.handle : '—'}</td>
                    <td><span class="tag">${t.status}</span></td>
                    <td><div class="cluster" style="gap:4px;">
                      <button class="btn btn--ghost" data-task-status="${t.id}" data-status="in_progress">start</button>
                      <button class="btn btn--ghost" data-task-status="${t.id}" data-status="done">done</button>
                      <button class="btn btn--ghost" data-task-status="${t.id}" data-status="stock">stock</button>
                      <button class="btn btn--ghost" data-task-status="${t.id}" data-status="danger">danger</button>
                      <button class="btn btn--ghost" data-task-status="${t.id}" data-status="cancelled">cancel</button>
                    </div></td>`;
    tbody.appendChild(tr);
  }
  $('#tasksCounter').textContent = String(rows.length).padStart(3, '0');

  fillSelect($('#peerTask'), state.tasks, 'id', t => `#${t.id} ${t.title} (proj ${t.project_id})`);
  fillSelect($('#taskScoresTask'), state.tasks, 'id', t => `#${t.id} ${t.title}`);
}

// ─── team form handlers
$('#workerForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('team', '/workers', { body });
    showResult('teamOut', 'POST /workers', r);
    e.target.reset();
    refreshWorkers(); refreshChain(); refreshWitness();
  } catch (err) { showError('teamOut', 'POST /workers', err); }
});

$('#projectForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('team', '/projects', { body });
    showResult('teamOut', 'POST /projects', r);
    state.projects.push(r);
    e.target.reset();
    refreshProjects(); refreshChain(); refreshWitness();
  } catch (err) { showError('teamOut', 'POST /projects', err); }
});

$('#taskForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  const pid = body.project_id; delete body.project_id;
  try {
    const r = await api('team', `/projects/${pid}/tasks`, { body });
    showResult('teamOut', `POST /projects/${pid}/tasks`, r);
    state.tasks.push(r);
    e.target.reset();
    refreshTasks(); refreshChain(); refreshWitness();
  } catch (err) { showError('teamOut', `POST /projects/${pid}/tasks`, err); }
});

$('#refreshTasks').addEventListener('click', refreshTasks);
$('#taskProjectFilter').addEventListener('change', refreshTasks);

document.addEventListener('click', async e => {
  const b = e.target.closest('[data-task-status]');
  if (!b) return;
  const tid = b.dataset.taskStatus;
  const status = b.dataset.status;
  try {
    const r = await api('team', `/tasks/${tid}/status`, { body: { status } });
    showResult('teamOut', `POST /tasks/${tid}/status`, r);
    const idx = state.tasks.findIndex(t => t.id === Number(tid));
    if (idx !== -1) state.tasks[idx] = r;
    refreshTasks(); refreshChain(); refreshWitness();
  } catch (err) { showError('teamOut', `POST /tasks/${tid}/status`, err); }
});

$('#kpiForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('team', '/kpis', { body });
    showResult('teamOut', 'POST /kpis', r);
    refreshChain(); refreshWitness();
  } catch (err) { showError('teamOut', 'POST /kpis', err); }
});

$('#perfForm').addEventListener('submit', async e => {
  e.preventDefault();
  const f = readForm(e.target);
  try {
    const r = await api('team', `/workers/${f.worker_id}/performance?period=${encodeURIComponent(f.period)}`);
    showResult('teamOut', `GET /workers/${f.worker_id}/performance`, r);
    refreshChain(); refreshWitness();
  } catch (err) { showError('teamOut', 'performance', err); }
});

// ─────────────────────────── NETDEF ───────────────────────────
$('#peerForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('netdef', '/peer-scores', { body });
    showResult('netdefOut', 'POST /peer-scores', r);
    e.target.reset();
    refreshChain(); refreshWitness();
  } catch (err) { showError('netdefOut', 'POST /peer-scores', err); }
});

$('#commentForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('netdef', '/comments', { body });
    showResult('netdefOut', 'POST /comments', r);
    e.target.reset();
    refreshChain(); refreshWitness();
  } catch (err) { showError('netdefOut', 'POST /comments', err); }
});

$('#inboxForm').addEventListener('submit', async e => {
  e.preventDefault();
  const wid = readForm(e.target).worker_id;
  try {
    const r = await api('netdef', `/workers/${wid}/inbox`);
    showResult('netdefOut', `GET /workers/${wid}/inbox`, r);
  } catch (err) { showError('netdefOut', 'inbox', err); }
});

$('#taskScoresForm').addEventListener('submit', async e => {
  e.preventDefault();
  const tid = readForm(e.target).task_id;
  try {
    const r = await api('netdef', `/tasks/${tid}/peer-scores`);
    showResult('netdefOut', `GET /tasks/${tid}/peer-scores`, r);
  } catch (err) { showError('netdefOut', 'task peer-scores', err); }
});

// ─────────────────────────── MONEY ───────────────────────────
function renderMeetings() {
  const tbody = $('#meetingsTable tbody');
  tbody.innerHTML = '';
  for (const m of state.meetings) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="mono">${m.id}</td>
                    <td>${m.title}</td>
                    <td class="mono">${m.scheduled_at}</td>
                    <td><span class="tag">${m.status}</span></td>`;
    tbody.appendChild(tr);
  }
  $('#meetingsCounter').textContent = String(state.meetings.length).padStart(3, '0');
  fillSelect($('#voteMeeting'), state.meetings, 'id', m => `#${m.id} ${m.title}`);
}

function renderTransactions() {
  const tbody = $('#txTable tbody');
  tbody.innerHTML = '';
  for (const t of state.transactions) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="mono">${t.id}</td>
                    <td class="mono">${t.occurred_at}</td>
                    <td class="tabular">${t.amount.toFixed(2)} ${t.currency}</td>
                    <td><span class="tag">${t.transaction_type}</span></td>
                    <td>${t.sender_party} → ${t.receiver_party}</td>
                    <td>${t.payment_method}</td>
                    <td><span class="tag">${t.status}</span></td>`;
    tbody.appendChild(tr);
  }
  $('#txCounter').textContent = String(state.transactions.length).padStart(3, '0');
  fillSelect($('#voteTx'), state.transactions.filter(t => t.status === 'pending_vote'),
             'id', t => `#${t.id} ${t.amount} ${t.currency} → ${t.receiver_party}`, true);
  $('#voteTx').firstElementChild.textContent = '— none —';
}

function renderVotes() {
  fillSelect($('#ballotVote'), state.votes.filter(v => v.status === 'open'),
             'id', v => `#${v.id} (meeting ${v.meeting_id})`);
  fillSelect($('#closeVoteVote'), state.votes.filter(v => v.status === 'open'),
             'id', v => `#${v.id} (meeting ${v.meeting_id})`);
}

$('#meetingForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('money', '/meetings', { body });
    showResult('moneyOut', 'POST /meetings', r);
    state.meetings.push(r);
    e.target.reset();
    renderMeetings(); refreshChain(); refreshWitness();
  } catch (err) { showError('moneyOut', 'POST /meetings', err); }
});

$('#txForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('money', '/transactions', { body });
    showResult('moneyOut', 'POST /transactions', r);
    state.transactions.push(r);
    e.target.reset();
    renderTransactions(); refreshChain(); refreshWitness();
  } catch (err) { showError('moneyOut', 'POST /transactions', err); }
});

$('#voteForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  const mid = body.meeting_id; delete body.meeting_id;
  if (body.linked_transaction_id === undefined) body.linked_transaction_id = null;
  try {
    const r = await api('money', `/meetings/${mid}/votes`, { body });
    showResult('moneyOut', `POST /meetings/${mid}/votes`, r);
    state.votes.push(r);
    // bump linked tx status visually (still pending_vote until close)
    e.target.reset();
    renderVotes(); refreshChain(); refreshWitness();
  } catch (err) { showError('moneyOut', `POST /meetings/${mid}/votes`, err); }
});

$('#ballotForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  const vid = body.vote_id; delete body.vote_id;
  try {
    const r = await api('money', `/votes/${vid}/ballots`, { body });
    showResult('moneyOut', `POST /votes/${vid}/ballots`, r);
    refreshChain(); refreshWitness();
  } catch (err) { showError('moneyOut', 'cast ballot', err); }
});

$('#closeVoteForm').addEventListener('submit', async e => {
  e.preventDefault();
  const vid = readForm(e.target).vote_id;
  try {
    const r = await api('money', `/votes/${vid}/close`, { method: 'POST', body: {} });
    showResult('moneyOut', `POST /votes/${vid}/close`, r);
    // update local state
    const v = state.votes.find(x => x.id === Number(vid));
    if (v) v.status = r.status;
    if (r.linked_transaction_id) {
      const t = state.transactions.find(x => x.id === r.linked_transaction_id);
      if (t && r.transaction_status) t.status = r.transaction_status;
    }
    renderVotes(); renderTransactions(); refreshChain(); refreshWitness();
  } catch (err) { showError('moneyOut', 'close vote', err); }
});

$('#reportForm').addEventListener('submit', async e => {
  e.preventDefault();
  const period = readForm(e.target).period;
  try {
    const r = await api('money', `/reports/spend?period=${encodeURIComponent(period)}`);
    showResult('moneyOut', `GET /reports/spend?period=${period}`, r);
    refreshChain(); refreshWitness();
  } catch (err) { showError('moneyOut', 'spend report', err); }
});

// ─────────────────────────── JUDGE ───────────────────────────
async function refreshChain() {
  const statusEl = $('#chainStatus');
  const dot = statusEl.querySelector('.status__dot');
  const label = statusEl.querySelector('span:last-child');
  try {
    const r = await api('judge', '/witness/verify');
    statusEl.classList.remove('is-success', 'is-warn');
    if (r.ok) {
      statusEl.classList.add('is-success');
      label.textContent = `chain ok · ${r.rows_checked} rows`;
    } else {
      statusEl.classList.add('is-warn');
      label.textContent = `BROKEN @ id=${r.broken_at_id}`;
    }
    $('#rowsCheckedTag').textContent = `rows: ${r.rows_checked}`;
  } catch (err) {
    statusEl.classList.remove('is-success'); statusEl.classList.add('is-warn');
    label.textContent = 'unreachable';
  }
}

function shortId(id) { return id ? String(id).slice(0, 8) : '—'; }

async function refreshWitness() {
  try {
    const rows = await api('judge', '/witness?limit=200');
    const feed = $('#witnessFeed');
    if (!rows.length) {
      feed.innerHTML = '<span class="empty">no events yet.</span>';
    } else {
      feed.innerHTML = '';
      // newest first
      for (const r of rows.slice().reverse()) {
        const row = document.createElement('div');
        row.className = 'feed-row';
        row.innerHTML = `<span class="idx" title="${r.id}">${shortId(r.id)}</span>
          <span><span class="act">${r.service}.${r.action}</span>
          <span class="meta"> · ${r.target_type}:${shortId(r.target_id)} · ${r.ts}</span></span>`;
        feed.appendChild(row);
      }
    }
    $('#witnessCounter').textContent = String(rows.length).padStart(4, '0');
  } catch (err) {
    $('#witnessFeed').innerHTML = `<span class="empty">witness unreachable.</span>`;
  }
}

$('#verifyChain').addEventListener('click', async () => {
  try {
    const r = await api('judge', '/witness/verify');
    showResult('judgeOut', 'GET /witness/verify', r);
    refreshChain();
  } catch (err) { showError('judgeOut', '/witness/verify', err); }
});
$('#refreshWitness').addEventListener('click', () => { refreshWitness(); refreshChain(); });

$$('[data-detector]').forEach(btn => btn.addEventListener('click', async () => {
  const d = btn.dataset.detector;
  const qs = d ? `?only=${encodeURIComponent(d)}` : '';
  try {
    const r = await api('judge', `/detectors/run${qs}`, { method: 'POST', body: {} });
    showResult('judgeOut', `POST /detectors/run${qs}`, r);
    loadAnomalies();
    refreshChain(); refreshWitness();
  } catch (err) { showError('judgeOut', 'detectors', err); }
}));

async function loadAnomalies(status = '') {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  try {
    const rows = await api('judge', `/anomalies${qs}`);
    const tbody = $('#anomTable tbody');
    tbody.innerHTML = '';
    for (const a of rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="mono">${a.id}</td>
                      <td class="mono">rule ${a.rule_id}</td>
                      <td><span class="tag">${a.severity}</span></td>
                      <td><span class="tag">${a.status}</span></td>
                      <td class="mono">${a.detected_at}</td>
                      <td class="mono" style="max-width:340px; word-break:break-all;">${a.evidence_json}</td>`;
      tbody.appendChild(tr);
    }
    $('#anomCounter').textContent = String(rows.length).padStart(3, '0');
  } catch (err) { showError('judgeOut', '/anomalies', err); }
}
$$('[data-anom-status]').forEach(b => b.addEventListener('click', () => loadAnomalies(b.dataset.anomStatus)));

$('#auditForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = readForm(e.target);
  try {
    const r = await api('judge', '/audits', { body });
    showResult('judgeOut', 'POST /audits', r);
    refreshChain(); refreshWitness();
  } catch (err) { showError('judgeOut', '/audits', err); }
});

// ─────────────────────────── boot ───────────────────────────
// pre-fill the spend-report period with current YYYY-MM
{
  const now = new Date();
  $('#reportForm input[name="period"]').value =
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

(async () => {
  await ensureSignedIn();   // admin page is admin-first; prompt if needed
  refreshAll();
  loadAnomalies();
  setInterval(() => { refreshChain(); refreshWitness(); }, 8000);
})();
