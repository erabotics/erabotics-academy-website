// ERABOTICS admin panel.
// The session itself lives on the server (HttpOnly cookie + database row); this
// script only mirrors its timer, warns before it expires and keeps it alive while
// the person is actually working. Customer data is shown only in the page and is
// never written to localStorage, sessionStorage or the URL.
(function () {
  const $ = (id) => document.getElementById(id);
  const WARN_SECONDS = 120;          // show "Still there?" 2 minutes before sign-out
  const EXTEND_WHEN_LEFT = 300;      // refresh an active session when < 5 minutes remain
  const ACTIVE_WINDOW = 60;          // "active" = mouse/keyboard/touch in the last minute

  const ORDER_STATUSES = ['new', 'confirmed', 'delivered', 'cancelled'];
  const MESSAGE_STATUSES = ['new', 'handled'];

  let session = null;                // { user, expiresAt, idleTimeoutSeconds }
  let clockOffset = 0;               // server time − local time, in seconds
  let lastActivity = Date.now();
  let extending = false;
  let tab = 'orders';
  let rows = [];
  let ticker = null;
  const channel = 'BroadcastChannel' in window ? new BroadcastChannel('erabotics-admin') : null;

  const now = () => Date.now() / 1000 + clockOffset;
  const fmtTime = (s) => `${Math.floor(s / 60)}:${String(Math.max(0, Math.floor(s % 60))).padStart(2, '0')}`;
  const fmtDate = (t) => new Date(t * 1000).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
  const money = (n) => `${Number(n).toLocaleString('en-EG')} EGP`;
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null && text !== '') n.textContent = text;
    return n;
  };

  // ---------------------------------------------------------------- API
  async function api(path, { method = 'GET', body } = {}) {
    const r = await fetch(path, {
      method,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
      body: body ? JSON.stringify(body) : undefined
    });
    const data = await r.json().catch(() => ({}));
    if (r.status === 401) {
      signedOut('Your session has expired. Please sign in again.');
      throw new Error('unauthorised');
    }
    if (!r.ok || !data.ok) throw new Error(data.error || 'Request failed.');
    if (data.expiresAt) applySession(data);
    return data;
  }

  function applySession(data) {
    clockOffset = data.serverTime - Date.now() / 1000;
    session = { user: data.user, expiresAt: data.expiresAt, idleTimeoutSeconds: data.idleTimeoutSeconds };
    $('admin-user').textContent = data.user;
    $('idle-minutes').textContent = Math.round(data.idleTimeoutSeconds / 60);
  }

  // ---------------------------------------------------------------- views
  function showApp() {
    $('view-login').hidden = true;
    $('view-app').hidden = false;
    $('admin-session').hidden = false;
    startTicker();
    load();
  }

  function signedOut(notice) {
    session = null;
    rows = [];
    clearInterval(ticker);
    $('panel').replaceChildren();          // remove customer data from the page
    $('admin-count').textContent = '';
    $('view-app').hidden = true;
    $('admin-session').hidden = true;
    $('view-login').hidden = false;
    const dlg = $('timeout-dialog');
    if (dlg.open) dlg.close();
    const n = $('login-notice');
    n.textContent = notice || '';
    n.hidden = !notice;
    $('login-pass').value = '';
  }

  async function signOut(notice) {
    try { await fetch('/api/admin/logout', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' }); } catch (e) { /* offline: the server session still expires on its own */ }
    if (channel) channel.postMessage('signed-out');
    signedOut(notice);
  }

  // ---------------------------------------------------------------- session timer
  function startTicker() {
    clearInterval(ticker);
    ticker = setInterval(tick, 1000);
    tick();
  }

  async function extend() {
    if (extending) return;
    extending = true;
    try { await api('/api/admin/session', { method: 'POST', body: {} }); } catch (e) { /* 401 handled in api() */ }
    extending = false;
  }

  function tick() {
    if (!session) return;
    const left = session.expiresAt - now();
    const timer = $('admin-timer');
    timer.textContent = `Signs out in ${fmtTime(left)}`;
    timer.classList.toggle('is-warning', left <= WARN_SECONDS);

    if (left <= 0) {
      signOut(`You were signed out after ${Math.round(session.idleTimeoutSeconds / 60)} minutes of inactivity.`);
      return;
    }
    const active = (Date.now() - lastActivity) / 1000 < ACTIVE_WINDOW;
    const dlg = $('timeout-dialog');
    if (active && left < EXTEND_WHEN_LEFT && !dlg.open) {
      extend();
    } else if (!active && left <= WARN_SECONDS && !dlg.open) {
      dlg.showModal();
    }
    if (dlg.open) $('timeout-left').textContent = fmtTime(left);
  }

  // Browsers slow down timers in background tabs; catch up as soon as the tab
  // is visible again (the server enforces the limit either way).
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  window.addEventListener('focus', tick);

  ['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach((ev) =>
    window.addEventListener(ev, () => { lastActivity = Date.now(); }, { passive: true, capture: true }));

  $('stay-signed-in').addEventListener('click', async () => {
    lastActivity = Date.now();
    $('timeout-dialog').close();
    await extend();
  });
  $('timeout-logout').addEventListener('click', () => signOut());
  $('admin-logout').addEventListener('click', () => signOut());

  // Signing out in one tab signs out every open admin tab.
  if (channel) channel.onmessage = (e) => { if (e.data === 'signed-out' && session) signedOut('You signed out in another tab.'); };

  // ---------------------------------------------------------------- sign in
  $('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    if (!form.checkValidity()) { form.reportValidity(); return; }
    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = 'Signing in…';
    const notice = $('login-notice');
    try {
      const r = await fetch('/api/admin/login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ username: $('login-user').value, password: $('login-pass').value })
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.ok) throw new Error(data.error || 'Sign-in failed.');
      $('login-pass').value = '';
      notice.hidden = true;
      applySession(data);
      lastActivity = Date.now();
      showApp();
    } catch (err) {
      $('login-pass').value = '';
      notice.textContent = err.message;
      notice.hidden = false;
    }
    btn.disabled = false;
    btn.textContent = 'Sign in';
  });

  // ---------------------------------------------------------------- data
  function fillFilter() {
    const sel = $('status-filter');
    const statuses = tab === 'orders' ? ORDER_STATUSES : MESSAGE_STATUSES;
    sel.replaceChildren(new Option('All statuses', ''), ...statuses.map((s) => new Option(s[0].toUpperCase() + s.slice(1), s)));
  }

  async function load() {
    $('admin-count').textContent = 'Loading…';
    try {
      const data = await api(`/api/admin/${tab}`);
      rows = data.rows;
      render();
    } catch (err) {
      if (err.message !== 'unauthorised') $('admin-count').textContent = err.message;
    }
  }

  function statusSelect(current, statuses, onChange) {
    const sel = el('select', 'status-select');
    statuses.forEach((s) => sel.add(new Option(s[0].toUpperCase() + s.slice(1), s)));
    sel.value = current;
    sel.dataset.status = current;
    sel.setAttribute('aria-label', 'Status');
    sel.addEventListener('change', async () => {
      sel.disabled = true;
      try {
        await onChange(sel.value);
        sel.dataset.status = sel.value;
      } catch (err) {
        sel.value = sel.dataset.status;
        if (err.message !== 'unauthorised') alert(err.message);
      }
      sel.disabled = false;
    });
    return sel;
  }

  function kv(list, label, value, href) {
    if (!value) return;
    const dt = el('dt', 'mono', label);
    const dd = el('dd');
    if (href) {
      const a = el('a', 'text-link', value);
      a.href = href;
      dd.appendChild(a);
    } else {
      dd.textContent = value;
    }
    list.append(dt, dd);
  }

  function orderCard(o) {
    const card = el('article', 'admin-card');
    const head = el('div', 'admin-card-head');
    const title = el('div');
    title.append(el('strong', 'mono', o.ref), el('span', 'admin-date', fmtDate(o.created_at)));
    head.append(title, statusSelect(o.status, ORDER_STATUSES, async (status) => {
      await api('/api/admin/orders', { method: 'PATCH', body: { ref: o.ref, status } });
      o.status = status;
    }));
    const info = el('dl', 'admin-kv');
    kv(info, 'Customer', o.name);
    kv(info, 'Phone', o.phone, `tel:${o.phone.replace(/[^0-9+]/g, '')}`);
    kv(info, 'Email', o.email, o.email ? `mailto:${o.email}` : null);
    kv(info, 'Delivery', o.fulfilment === 'Delivery' ? [o.address, o.city].filter(Boolean).join(', ') : 'Pick up');
    kv(info, 'Payment', o.payment);
    kv(info, 'Notes', o.notes);
    const table = el('table', 'admin-items');
    const thead = el('thead');
    const hr = el('tr');
    ['Qty', 'Item', 'SKU', 'Price', 'Subtotal'].forEach((h) => hr.appendChild(el('th', 'mono', h)));
    thead.appendChild(hr);
    const tbody = el('tbody');
    o.items.forEach((i) => {
      const tr = el('tr');
      [String(i.qty), i.name, i.sku, money(i.price), money(i.subtotal)].forEach((v) => tr.appendChild(el('td', null, v)));
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    const total = el('p', 'admin-total');
    total.append('Total ', el('strong', null, money(o.total)));
    card.append(head, info, table, total);
    return card;
  }

  function messageCard(m) {
    const card = el('article', 'admin-card');
    const head = el('div', 'admin-card-head');
    const title = el('div');
    title.append(el('strong', 'mono', m.kind === 'adult_application' ? 'Adult course application' : 'Contact message'), el('span', 'admin-date', fmtDate(m.created_at)));
    head.append(title, statusSelect(m.status, MESSAGE_STATUSES, async (status) => {
      await api('/api/admin/messages', { method: 'PATCH', body: { id: m.id, status } });
      m.status = status;
    }));
    const info = el('dl', 'admin-kv');
    kv(info, 'Name', m.name);
    kv(info, 'Email', m.email, m.email ? `mailto:${m.email}` : null);
    kv(info, 'Phone', m.phone, m.phone ? `tel:${m.phone.replace(/[^0-9+]/g, '')}` : null);
    Object.entries(m.details || {}).forEach(([k, v]) => kv(info, k[0].toUpperCase() + k.slice(1), v));
    card.append(head, info);
    return card;
  }

  function render() {
    const filter = $('status-filter').value;
    const list = rows.filter((r) => !filter || r.status === filter);
    const panel = $('panel');
    panel.replaceChildren();
    if (!list.length) panel.appendChild(el('p', 'admin-empty', `No ${tab} ${filter ? `marked “${filter}”` : 'yet'}.`));
    list.forEach((r) => panel.appendChild(tab === 'orders' ? orderCard(r) : messageCard(r)));
    $('admin-count').textContent = `${list.length} ${tab}${filter ? ` · ${filter}` : ''}`;
  }

  ['orders', 'messages'].forEach((name) => {
    $(`tab-${name}`).addEventListener('click', () => {
      tab = name;
      $('tab-orders').setAttribute('aria-selected', String(name === 'orders'));
      $('tab-messages').setAttribute('aria-selected', String(name === 'messages'));
      fillFilter();
      load();
    });
  });
  $('status-filter').addEventListener('change', render);
  $('refresh').addEventListener('click', load);

  // ---------------------------------------------------------------- start
  fillFilter();
  (async () => {
    try {
      const r = await fetch('/api/admin/session', { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } });
      const data = await r.json().catch(() => ({}));
      if (r.ok && data.ok) {
        applySession(data);
        showApp();
      } else if (r.status === 503) {
        signedOut(data.error || 'The admin area is not configured yet.');
      } else {
        signedOut();
      }
    } catch (e) {
      signedOut('Cannot reach the server. Check your connection.');
    }
  })();
})();
