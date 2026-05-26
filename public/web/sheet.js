/* SHEET — Self · members down, tasks across.
   Adds: session login (HttpOnly cookie), opt-in passwords, mobile stack
   layout, Stock/Danger statuses, localStorage UI state, performance pill. */

const _LOCAL = ['127.0.0.1', 'localhost'].includes(location.hostname);
const API = {
  team:   _LOCAL ? 'http://127.0.0.1:8011' : '/api/team',
  netdef: _LOCAL ? 'http://127.0.0.1:8012' : '/api/netdef',
  money:  _LOCAL ? 'http://127.0.0.1:8013' : '/api/money',
  judge:  _LOCAL ? 'http://127.0.0.1:8014' : '/api/judge',
};

const MEMBERS = [
  'Ari', 'Misheel', 'Temuulen', 'Avidikhuu', 'Ojii',
  'Erkhemee', 'Nyamka', 'Sodbayar', 'Obama', '— add —',
];

const TASKS = [
  { name: 'Marketing campaign', sub: 'Campaign',  icon: 'M' },
  { name: 'Social media',        sub: 'Channels',  icon: 'S' },
  { name: 'Sells / amount',      sub: 'Revenue',   icon: '$' },
  { name: 'IT / performance',    sub: 'Infra',     icon: 'I' },
  { name: 'KPI rate',            sub: 'KPI',       icon: 'K' },
  { name: 'Salary',              sub: 'Payroll',   icon: 'P' },
  { name: 'Rate / weight',       sub: 'Weight',    icon: 'W' },
];

const STATUS_GLYPH = {
  open:        '◯',
  in_progress: '▸',
  done:        '■',
  cancelled:   '✕',
  stock:       '●',   // green via CSS data-status
  danger:      '▲',   // amber via CSS data-status
};
const STATUS_ORDER = ['open', 'in_progress', 'done', 'cancelled', 'stock', 'danger'];

const LS_ACTING = 'sheet.acting';
const LS_LAST_CELL = 'sheet.lastCell';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

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

function toast(msg, ms = 2200) {
  const root = $('#toastRoot');
  root.innerHTML = `<div class="toast">${msg}</div>`;
  setTimeout(() => { if ($('.toast', root)) root.innerHTML = ''; }, ms);
}

const state = {
  session: null,          // {worker_id, name, handle, is_admin} or null
  acting: null,           // worker id (must be: own session id, or password-less, or admin acting)
  workers: [],
  members: [],            // [{name, id|null, placeholder, has_password}]
  projects: [],
  tasks: {},
  taskMeta: {},
  performance: {},        // {worker_id: {score, components, period}} - computed lazily
  commentsByTask: {},
};

/* ── session ────────────────────────────────────────────────────── */
async function checkSession() {
  try {
    const me = await api('team', '/auth/whoami');
    state.session = me.authenticated ? me : null;
  } catch {
    state.session = null;
  }
  return state.session;
}

async function login(handle, password) {
  return api('team', '/auth/login', { body: { handle, password } });
}
async function logout() {
  try { await api('team', '/auth/logout', { method: 'POST' }); } catch {}
  state.session = null;
}

/* ── boot ──────────────────────────────────────────────────────── */
async function boot() {
  await checkSession();

  if (!state.session) {
    showLoginOverlay({ allowSkip: true });
    return;   // continueAfterLogin() will resume
  }
  await loadAll();
}

function showLoginOverlay({ allowSkip = false, error = '' } = {}) {
  $('#loginOverlay').classList.remove('hidden');
  $('#skipLoginBtn').classList.toggle('hidden', !allowSkip);
  const errEl = $('#loginErr');
  if (error) { errEl.textContent = error; errEl.classList.remove('hidden'); }
  else { errEl.classList.add('hidden'); }
}
function hideLoginOverlay() { $('#loginOverlay').classList.add('hidden'); }

$('#loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const handle = $('#loginHandle').value.trim();
  const pass   = $('#loginPass').value;
  try {
    await login(handle, pass);
    await checkSession();
    hideLoginOverlay();
    await loadAll();
  } catch (err) {
    const msg = err.status === 401 ? 'invalid handle or password' : `error ${err.status}`;
    showLoginOverlay({ allowSkip: true, error: msg });
  }
});

$('#skipLoginBtn').addEventListener('click', async () => {
  hideLoginOverlay();
  await loadAll();
});

$('#signInBtn').addEventListener('click', () => showLoginOverlay({ allowSkip: true }));
$('#signOutBtn').addEventListener('click', async () => {
  await logout();
  location.reload();
});

/* ── data load ─────────────────────────────────────────────────── */
async function loadAll() {
  try {
    state.workers = await api('team', '/workers');
  } catch (err) {
    if (err.status === 401) { showLoginOverlay({ allowSkip: true }); return; }
    throw err;
  }

  // Resolve / fetch sheet structure. Bootstrap requires admin; if we're not
  // admin, fetch /projects + /projects/{id}/tasks and reconstruct the
  // (project,member)→task_id map ourselves.
  if (state.session?.is_admin) {
    const realMembers = MEMBERS.filter(n => !n.startsWith('—'));
    try {
      const res = await api('team', '/sheet/bootstrap', { body: { members: realMembers } });
      const byName = Object.fromEntries(res.members.map(m => [m.name, m.id]));
      state.members = MEMBERS.map(n => ({
        name: n,
        id: n.startsWith('—') ? null : byName[n],
        placeholder: n.startsWith('—'),
      }));
      state.projects = res.projects;
      state.tasks    = res.tasks;
    } catch (err) {
      toast(`bootstrap failed · ${err.status || ''}`);
      return;
    }
  } else {
    // guest / non-admin: read-only reconstruction
    state.projects = await api('team', '/projects');
    state.members = MEMBERS.map(n => ({
      name: n,
      id: n.startsWith('—') ? null : state.workers.find(w => w.name === n)?.id ?? null,
      placeholder: n.startsWith('—'),
    }));
    state.tasks = {};
    const lists = await Promise.all(
      state.projects.map(p => api('team', `/projects/${p.id}/tasks`).then(ts => [p.id, ts]))
    );
    for (const [pid, ts] of lists) {
      state.tasks[pid] = {};
      for (const t of ts) if (t.assignee_id) state.tasks[pid][t.assignee_id] = t.id;
    }
  }

  // Annotate password-protected members
  for (const m of state.members) {
    if (!m.id) continue;
    const w = state.workers.find(x => x.id === m.id);
    m.has_password = !!w?.password_hash;   // safe: API leaks no hash; we infer via /workers payload? actually password_hash isn't returned. Treat false unless API says otherwise.
  }
  // /workers doesn't currently return password_hash flag for privacy; ask the server.
  // We'll infer locked-ness lazily on click instead.

  // Refresh tasks meta from any project list call above
  await refreshTaskMeta();
  populateIdentityUI();
  populatePicker();
  await refreshPerformanceCacheLazy();
  render();
}

async function refreshTaskMeta() {
  const all = Object.keys(state.tasks)
    .map(pid => api('team', `/projects/${pid}/tasks`).catch(() => []));
  const lists = await Promise.all(all);
  state.taskMeta = {};
  for (const list of lists) for (const t of list) state.taskMeta[t.id] = t;
}

async function refreshPerformanceCacheLazy() {
  // Best-effort: this hits a write endpoint that admins can call; non-admins
  // would 401 today. Compute only when allowed.
  if (!state.session?.is_admin) return;
  const period = new Date().toISOString().slice(0, 7);
  const promises = state.members
    .filter(m => m.id)
    .map(m => api('team', `/workers/${m.id}/performance?period=${period}`)
      .then(r => [m.id, r]).catch(() => null));
  const rs = (await Promise.all(promises)).filter(Boolean);
  for (const [wid, r] of rs) state.performance[wid] = r;
}

/* ── identity / picker ─────────────────────────────────────────── */
function populateIdentityUI() {
  const chip = $('#idChip');
  const signIn = $('#signInBtn');
  if (state.session) {
    chip.classList.remove('hidden');
    signIn.classList.add('hidden');
    $('#idChipName').textContent = state.session.name;
    $('#idChipBadge').textContent = state.session.is_admin ? 'admin' : 'signed-in';
    chip.classList.toggle('is-admin', !!state.session.is_admin);
  } else {
    chip.classList.add('hidden');
    signIn.classList.remove('hidden');
  }
}

function populatePicker() {
  const sel = $('#actingPicker');
  sel.innerHTML = '';
  for (const w of state.workers) {
    const o = document.createElement('option');
    o.value = w.id; o.textContent = w.name;
    sel.appendChild(o);
  }
  // If signed-in non-admin: forced to act as self
  const lockedToSelf = state.session && !state.session.is_admin;
  const wrap = $('#actingWrap');
  if (lockedToSelf) {
    state.acting = state.session.worker_id;
    sel.value = state.acting;
    sel.disabled = true;
    wrap.classList.add('is-disabled');
  } else {
    // default: localStorage > first listed member > first worker
    const saved = localStorage.getItem(LS_ACTING);
    const first = state.members.find(m => m.id)?.id ?? state.workers[0]?.id ?? null;
    state.acting = (saved && state.workers.some(w => w.id === saved)) ? saved : first;
    sel.value = state.acting;
    sel.disabled = false;
    wrap.classList.remove('is-disabled');
  }
  sel.onchange = () => {
    state.acting = sel.value;
    localStorage.setItem(LS_ACTING, state.acting);
    render();
  };
}

/* ── render: desktop grid + mobile stack ───────────────────────── */
function render() { renderDesktop(); renderMobile(); }

function renderDesktop() {
  const sheet = $('#sheet');
  sheet.innerHTML = '';
  sheet.appendChild(cellCorner());
  TASKS.forEach(t => sheet.appendChild(cellTaskHead(t)));
  state.members.forEach((m, mi) => {
    sheet.appendChild(cellMemberHead(m, mi));
    TASKS.forEach((t, ti) => {
      const project = state.projects[ti];
      if (m.placeholder || !project) sheet.appendChild(cellEmpty());
      else {
        const tid = state.tasks[project.id]?.[m.id];
        sheet.appendChild(cellTask(tid, m, project));
      }
    });
  });
}

function renderMobile() {
  const list = $('#stackList');
  list.innerHTML = '';
  state.members.forEach((m, mi) => {
    if (m.placeholder) return;   // skip empty slot on mobile to save space
    const card = document.createElement('section');
    card.className = 'stack-card';
    if (m.id === state.acting) card.classList.add('is-self');
    const w = state.workers.find(x => x.id === m.id);
    const perf = state.performance[m.id];
    card.innerHTML = `
      <header>
        <div>
          <div class="name">${m.name}</div>
          <div class="meta">@${w?.handle || '—'}</div>
        </div>
        <div class="meta">${perf ? `perf ${perf.score.toFixed(0)}` : ''}</div>
      </header>
      <div class="stack-chips" data-member="${m.id}"></div>`;
    const chipsEl = card.querySelector('.stack-chips');
    TASKS.forEach((t, ti) => {
      const project = state.projects[ti];
      if (!project) return;
      const tid = state.tasks[project.id]?.[m.id];
      const meta = state.taskMeta[tid];
      const status = meta?.status || 'open';
      const chip = document.createElement('button');
      chip.className = 'stack-chip';
      chip.dataset.status = status;
      chip.innerHTML = `
        <div class="label">${t.name}</div>
        <div class="status"><span class="glyph">${STATUS_GLYPH[status] || '·'}</span><span>${status.replace('_',' ')}</span></div>`;
      chip.addEventListener('click', () => openWidget(tid, m, project));
      chipsEl.appendChild(chip);
    });
    list.appendChild(card);
  });
}

function cellCorner() {
  const el = document.createElement('div');
  el.className = 'cell corner';
  el.innerHTML = `
    <span class="eyebrow">Sheet</span>
    <div class="corner-title">10 × 7</div>
    <span class="mono text-faint" style="font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;">members · tasks</span>`;
  return el;
}
function cellTaskHead(t) {
  const el = document.createElement('div');
  el.className = 'cell task-head';
  el.innerHTML = `
    <div class="cluster" style="gap: var(--space-2);">
      <span class="icon mono">${t.icon}</span>
      <span class="sub">${t.sub}</span>
    </div>
    <div class="label">${t.name}</div>`;
  return el;
}
function cellMemberHead(m) {
  const el = document.createElement('div');
  el.className = 'cell member-head';
  if (m.placeholder) {
    el.innerHTML = `
      <span class="placeholder-mark">${m.name}</span>
      <span class="handle">slot 10</span>`;
    return el;
  }
  if (m.id === state.acting) el.classList.add('is-self');
  const w = state.workers.find(x => x.id === m.id);
  const perf = state.performance[m.id];
  el.innerHTML = `
    <div class="name">${m.name}</div>
    <div class="handle">@${w?.handle || m.name.toLowerCase()}</div>
    <div class="perf">${perf ? `perf ${perf.score.toFixed(0)} / 100` : ''}</div>`;
  return el;
}
function cellEmpty() {
  const el = document.createElement('div');
  el.className = 'cell empty-member';
  el.textContent = '—';
  return el;
}
function cellTask(tid, member, project) {
  const el = document.createElement('div');
  el.className = 'cell task-cell';
  if (member.id === state.acting) el.classList.add('in-self-row');
  el.tabIndex = 0;
  el.setAttribute('role', 'button');
  el.setAttribute('aria-label', `${member.name} — ${project.name}`);

  const meta = state.taskMeta[tid];
  const status = meta?.status || 'open';
  const created = (meta?.created_at || '').slice(5, 16).replace('T', ' ');
  const weight = meta?.weight ?? '—';
  const cmtCount = state.commentsByTask[tid]?.length ?? 0;

  el.innerHTML = `
    <div class="meta">
      <span>${created || '—'}</span>
      <span>w${weight}</span>
    </div>
    <div class="status" data-status="${status}">
      <span class="glyph">${STATUS_GLYPH[status] || '·'}</span>
      <span>${status.replace('_', ' ')}</span>
    </div>
    <div class="bottom">
      <span>💬 ${cmtCount}</span>
    </div>`;

  el.addEventListener('click', () => openWidget(tid, member, project));
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openWidget(tid, member, project); }
  });
  return el;
}

/* ── widget modal ─────────────────────────────────────────────── */
async function openWidget(tid, member, project) {
  if (!tid) { toast('no task yet · ask admin to bootstrap'); return; }
  localStorage.setItem(LS_LAST_CELL, JSON.stringify({ tid, member: member.name, project: project.name }));

  const isSelf = member.id === state.acting;
  const meta = state.taskMeta[tid] || {};
  const actor = state.workers.find(w => w.id === state.acting);

  const root = $('#modalRoot');
  root.innerHTML = `
    <div class="modal-backdrop" id="mb">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">

        <div class="cluster" style="justify-content: space-between; align-items: flex-start; gap: var(--space-4);">
          <div>
            <span class="eyebrow">${isSelf ? 'self · update' : 'peer · comment'}</span>
            <h2 id="modalTitle">${member.name} <em>· ${project.name}</em></h2>
            <div class="sub" title="${tid}">task ${String(tid || '').slice(0, 8)} · weight ${meta.weight ?? '—'} · acting as ${actor?.name || 'guest'}</div>
          </div>
          <button class="btn btn--ghost" id="closeBtn" aria-label="Close">close</button>
        </div>

        <div class="group">
          <label class="field" style="margin-bottom: 6px;">status</label>
          <div class="seg" id="statusSeg">
            ${STATUS_ORDER.map(s =>
              `<button data-status="${s}" class="${meta.status === s ? 'is-active' : ''}">${s.replace('_',' ')}</button>`
            ).join('')}
          </div>
        </div>

        <div class="group">
          <label class="field" for="ideaInput">idea · text</label>
          <textarea id="ideaInput" placeholder="What's the move? Use @handle to mention."></textarea>
        </div>

        <div class="group row">
          <label class="field">link
            <input id="linkInput" type="text" placeholder="https://…">
          </label>
          <label class="field">peer score (0–100)
            <input id="perfInput" type="number" min="0" max="100" placeholder="e.g. 78">
          </label>
        </div>

        <div class="group">
          <label class="field" style="margin-bottom: 6px;">import file</label>
          <label class="file-zone" id="fileZone">
            <input type="file" id="fileInput">
            <span id="fileLabel"><strong>tap to attach</strong> · or drop here</span>
          </label>
        </div>

        <div class="cluster" style="justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-4);">
          <button class="btn btn--ghost" id="cancelBtn">cancel</button>
          <button class="btn btn--primary" id="submitBtn">post update</button>
        </div>

        <hr class="rule mt-6">
        <div class="section-head" style="margin-top: var(--space-4);">
          History <span class="counter" id="histCount">—</span>
        </div>
        <div class="history mt-2" id="history"><div class="history-empty">loading…</div></div>
      </div>
    </div>`;

  $('#mb').addEventListener('click', e => { if (e.target.id === 'mb') closeModal(); });
  $('#closeBtn').addEventListener('click', closeModal);
  $('#cancelBtn').addEventListener('click', closeModal);
  document.addEventListener('keydown', escClose);

  $$('#statusSeg button').forEach(b => b.addEventListener('click', async () => {
    const s = b.dataset.status;
    try {
      const r = await api('team', `/tasks/${tid}/status`, { body: { status: s } });
      state.taskMeta[tid] = r;
      $$('#statusSeg button').forEach(x => x.classList.toggle('is-active', x.dataset.status === s));
      toast(`status → ${s.replace('_',' ')}`);
      render();
    } catch (err) {
      const detail = err.data?.detail || err.status;
      toast(`status error · ${detail}`);
    }
  }));

  const fileInput = $('#fileInput');
  fileInput.addEventListener('change', () => {
    const f = fileInput.files[0];
    $('#fileLabel').innerHTML = f
      ? `<strong>${f.name}</strong> · ${(f.size / 1024).toFixed(1)} KB`
      : `<strong>tap to attach</strong> · or drop here`;
  });
  const fz = $('#fileZone');
  fz.addEventListener('dragover', e => { e.preventDefault(); fz.style.borderStyle = 'solid'; fz.style.borderColor = 'var(--ink)'; });
  fz.addEventListener('dragleave', () => { fz.style.borderStyle = ''; fz.style.borderColor = ''; });
  fz.addEventListener('drop', e => {
    e.preventDefault();
    fz.style.borderStyle = ''; fz.style.borderColor = '';
    if (e.dataTransfer.files[0]) { fileInput.files = e.dataTransfer.files; fileInput.dispatchEvent(new Event('change')); }
  });

  $('#submitBtn').addEventListener('click', () => submit(tid, member, project));

  await loadHistory(tid);
}

function escClose(e) { if (e.key === 'Escape') closeModal(); }
function closeModal() {
  $('#modalRoot').innerHTML = '';
  document.removeEventListener('keydown', escClose);
}

async function submit(tid, member, project) {
  const idea = $('#ideaInput').value.trim();
  const link = $('#linkInput').value.trim();
  const perf = $('#perfInput').value.trim();
  const file = $('#fileInput').files[0];

  if (!idea && !link && !perf && !file) {
    toast('add an idea, link, file, or score first');
    return;
  }
  const parts = [];
  if (idea) parts.push(idea);
  if (link) parts.push(`[link] ${link}`);
  if (file) parts.push(`[file] ${file.name} · ${(file.size / 1024).toFixed(1)} KB · ${file.type || 'application/octet-stream'}`);
  const body = parts.join('\n');

  try {
    if (body) {
      await api('netdef', '/comments', {
        body: { author_id: state.acting, target_type: 'task', target_id: tid, body },
      });
    }
    if (perf) {
      if (member.id === state.acting) {
        toast('peer score skipped · self-scoring not allowed');
      } else {
        await api('netdef', '/peer-scores', {
          body: { scorer_id: state.acting, target_task_id: tid,
                  score: Number(perf), notes: idea || null },
        });
      }
    }
    toast('posted');
    await loadHistory(tid);
    render();
    $('#ideaInput').value = ''; $('#linkInput').value = '';
    $('#perfInput').value = ''; $('#fileInput').value = '';
    $('#fileLabel').innerHTML = `<strong>tap to attach</strong> · or drop here`;
  } catch (err) {
    const detail = err.data?.detail || (typeof err.data === 'string' ? err.data : JSON.stringify(err.data));
    toast(`error ${err.status} · ${detail}`);
    if (err.status === 401) showLoginOverlay({ allowSkip: true, error: 'sign in required' });
  }
}

async function loadHistory(tid) {
  const histEl = $('#history');
  try {
    const [comments, peerScores] = await Promise.all([
      api('netdef', `/comments?target_type=task&target_id=${tid}`),
      api('netdef', `/tasks/${tid}/peer-scores`),
    ]);
    state.commentsByTask[tid] = comments;
    const items = [
      ...comments.map(c => ({ kind: 'comment', ts: c.created_at, data: c })),
      ...peerScores.map(p => ({ kind: 'score',   ts: p.created_at, data: p })),
    ].sort((a, b) => (a.ts < b.ts ? 1 : -1));
    $('#histCount').textContent = String(items.length).padStart(3, '0');

    if (!items.length) {
      histEl.innerHTML = `<div class="history-empty">no history yet · be the first to post.</div>`;
      return;
    }
    histEl.innerHTML = items.map(renderHistoryItem).join('');
  } catch (err) {
    histEl.innerHTML = `<div class="history-empty">could not load history (${err.status || '?'})</div>`;
  }
}

function renderHistoryItem(item) {
  const ts = (item.ts || '').replace('T', ' ').slice(0, 19);
  if (item.kind === 'comment') {
    const c = item.data;
    const author = c.author_name || `#${(c.author_id||'').slice(0,8)}`;
    const handle = c.author_handle ? `@${c.author_handle}` : '';
    return `<div class="history-item">
      <div class="meta"><span><span class="badge">comment</span><strong>${author}</strong> ${handle}</span><span>${ts}</span></div>
      <div class="body">${escapeAndLinkify(c.body)}</div>
    </div>`;
  } else {
    const s = item.data;
    const scorer = state.workers.find(w => w.id === s.scorer_id);
    return `<div class="history-item">
      <div class="meta"><span><span class="badge">peer score</span><strong>${scorer?.name || '#' + (s.scorer_id||'').slice(0,8)}</strong> · ${s.score}/100${s.was_unfinished ? ' · unfinished' : ''}</span><span>${ts}</span></div>
      ${s.notes ? `<div class="body">${escapeAndLinkify(s.notes)}</div>` : ''}
    </div>`;
  }
}

function escapeAndLinkify(s) {
  const escaped = (s || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escaped
    .replace(/\[link\]\s*(https?:\/\/[^\s]+)/g, '<span class="badge">link</span> <a href="$1" target="_blank" rel="noopener">$1</a>')
    .replace(/\[file\]\s*(.+)/g, '<span class="badge">file</span> $1')
    .replace(/@([a-zA-Z0-9_\-]+)/g, '<strong class="mention">@$1</strong>');
}

boot().catch(err => {
  console.error(err);
  document.body.innerHTML = `<pre style="padding:40px; font-family: ui-monospace, monospace;">boot failed · ${err.status || ''}\n${JSON.stringify(err.data, null, 2)}</pre>`;
});
