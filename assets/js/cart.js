// ERABOTICS Store cart — kept in this browser (localStorage), shared by every page.
// Exposes window.ErCart for the Store and Checkout pages.
(function () {
  const KEY = 'erabotics-cart';
  const MAX_QTY = 999;
  const SAFE_IMG = /^assets\/img\/(parts|products)\/[\w.-]+\.(svg|webp|jpe?g|png)$/;
  const fmt = new Intl.NumberFormat('en-EG');

  const read = () => {
    try {
      const items = JSON.parse(localStorage.getItem(KEY) || '[]');
      if (!Array.isArray(items)) return [];
      // Never trust stored data: keep only well-formed lines, with safe types and image URLs
      return items.slice(0, 200).filter((i) => i && Number.isInteger(i.id) && i.id > 0).map((i) => ({
        id: i.id,
        name: String(i.name || '').slice(0, 200),
        sku: String(i.sku || '').slice(0, 40),
        price: Math.max(0, Number(i.price) || 0),
        img: SAFE_IMG.test(String(i.img || '')) ? i.img : '',
        qty: Math.max(1, Math.min(MAX_QTY, Math.floor(Number(i.qty) || 1)))
      }));
    } catch (e) { return []; }
  };
  let items = read();

  const notify = () => document.dispatchEvent(new CustomEvent('cart:change', { detail: { items } }));
  const save = () => {
    try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) { /* private mode — cart lasts this page view */ }
    notify();
  };
  const clampQty = (q) => Math.max(1, Math.min(MAX_QTY, Math.floor(Number(q) || 1)));

  const ErCart = {
    items: () => items.slice(),
    count: () => items.reduce((n, i) => n + i.qty, 0),
    total: () => items.reduce((n, i) => n + i.qty * i.price, 0),
    money: (n) => `${fmt.format(n)} EGP`,
    add(product, qty = 1) {
      const existing = items.find((i) => i.id === product.id);
      if (existing) existing.qty = clampQty(existing.qty + qty);
      else items.push({ id: product.id, name: product.name, sku: product.sku, price: product.price, img: SAFE_IMG.test(product.img || '') ? product.img : '', qty: clampQty(qty) });
      save();
    },
    setQty(id, qty) {
      const it = items.find((i) => i.id === id);
      if (it) { it.qty = clampQty(qty); save(); }
    },
    remove(id) { items = items.filter((i) => i.id !== id); save(); },
    clear() { items = []; save(); },
    // Refresh names/prices from the latest catalog so orders use current prices
    reprice(byId) {
      let changed = false;
      let imagesChanged = false;
      items = items.filter((i) => {
        const p = byId.get(i.id);
        if (!p) { changed = true; return false; }
        if (p.p !== i.price || p.n !== i.name || (p.s || '') !== i.sku) { i.price = p.p; i.name = p.n; i.sku = p.s || ''; changed = true; }
        const img = p.img || `assets/img/parts/${p.ic || 'part'}.svg`;
        if (img !== i.img) { i.img = img; imagesChanged = true; }
        return true;
      });
      if (changed || imagesChanged) save();
      return changed; // only price/name changes are worth telling the customer about
    },
    open: () => openDrawer()
  };
  window.ErCart = ErCart;

  // Keep tabs in sync: re-read another tab's change, but never write it back
  // (writing here would let two open tabs overwrite each other's carts)
  window.addEventListener('storage', (e) => { if (e.key === KEY) { items = read(); notify(); } });

  // ---------- Header badge ----------
  const updateBadges = () => {
    const n = ErCart.count();
    document.querySelectorAll('.cart-link').forEach((link) => {
      const badge = link.querySelector('.cart-count');
      if (badge) { badge.textContent = n > 99 ? '99+' : String(n); badge.hidden = n === 0; }
      link.setAttribute('aria-label', `Cart, ${n} item${n === 1 ? '' : 's'}`);
    });
  };

  // ---------- Drawer ----------
  let drawer;
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const icon = (id) => {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(ns, 'use');
    use.setAttribute('href', `#icon-${id}`);
    svg.appendChild(use);
    return svg;
  };

  const buildDrawer = () => {
    drawer = document.createElement('dialog');
    drawer.className = 'cart-drawer';
    drawer.setAttribute('aria-labelledby', 'cart-title');
    // Built with DOM APIs (no innerHTML)
    const head = el('div', 'cd-head');
    const title = el('h2', null, 'Your cart');
    title.id = 'cart-title';
    const close = el('button', 'dialog-close');
    close.type = 'button';
    close.dataset.close = '';
    close.setAttribute('aria-label', 'Close cart');
    close.appendChild(icon('close'));
    head.append(title, close);

    const foot = el('div', 'cd-foot');
    const total = el('div', 'cd-total');
    total.append(el('span', null, 'Subtotal'), el('strong'));
    const checkout = el('a', 'btn btn-primary btn-block', 'Checkout ');
    checkout.href = '/checkout';
    checkout.appendChild(icon('arrow'));
    const keepShopping = el('button', 'btn btn-outline btn-block', 'Continue shopping');
    keepShopping.type = 'button';
    keepShopping.dataset.close = '';
    foot.append(total, el('p', 'fine-print', 'Prices in EGP. We confirm stock, delivery and the final total when we call you.'), checkout, keepShopping);

    drawer.append(head, el('div', 'cd-body'), foot);
    document.body.appendChild(drawer);
    drawer.addEventListener('click', (e) => {
      if (e.target === drawer || e.target.closest('[data-close]')) drawer.close();
    });
    drawer.addEventListener('close', () => document.body.classList.remove('nav-locked'));
  };

  const renderLines = (container, { compact = false } = {}) => {
    container.replaceChildren();
    if (!items.length) {
      const empty = el('div', 'cart-empty');
      empty.appendChild(icon('cart'));
      empty.appendChild(el('p', null, 'Your cart is empty.'));
      const a = el('a', 'btn btn-outline btn-sm', 'Browse the Store');
      a.href = '/store';
      empty.appendChild(a);
      container.appendChild(empty);
      return;
    }
    const list = el('ul', 'cart-lines');
    items.forEach((i) => {
      const li = el('li', 'cart-line');
      const thumb = el('div', 'cl-thumb');
      if (i.img) { const img = el('img'); img.src = i.img; img.alt = ''; img.loading = 'lazy'; thumb.appendChild(img); }
      else thumb.appendChild(icon('chip'));
      li.appendChild(thumb);

      const info = el('div', 'cl-info');
      info.appendChild(el('p', 'cl-name', i.name));
      info.appendChild(el('p', 'cl-meta mono', `${i.sku ? 'SKU ' + i.sku + ' · ' : ''}${ErCart.money(i.price)} each`));
      if (!compact) {
        const qty = el('div', 'qty qty-sm');
        qty.setAttribute('role', 'group');
        qty.setAttribute('aria-label', `Quantity for ${i.name}`);
        const minus = el('button', null, '−'); minus.type = 'button'; minus.setAttribute('aria-label', 'Decrease quantity');
        const input = el('input'); input.type = 'number'; input.min = '1'; input.value = i.qty; input.setAttribute('aria-label', 'Quantity'); input.inputMode = 'numeric';
        const plus = el('button', null, '+'); plus.type = 'button'; plus.setAttribute('aria-label', 'Increase quantity');
        minus.addEventListener('click', () => ErCart.setQty(i.id, i.qty - 1));
        plus.addEventListener('click', () => ErCart.setQty(i.id, i.qty + 1));
        input.addEventListener('change', () => ErCart.setQty(i.id, input.value));
        qty.append(minus, input, plus);
        const row = el('div', 'cl-row');
        row.appendChild(qty);
        const rm = el('button', 'cl-remove'); rm.type = 'button'; rm.setAttribute('aria-label', `Remove ${i.name}`);
        rm.appendChild(icon('trash'));
        rm.addEventListener('click', () => ErCart.remove(i.id));
        row.appendChild(rm);
        info.appendChild(row);
      } else {
        info.appendChild(el('p', 'cl-meta', `Qty ${i.qty}`));
      }
      li.appendChild(info);
      li.appendChild(el('strong', 'cl-sum', ErCart.money(i.qty * i.price)));
      list.appendChild(li);
    });
    container.appendChild(list);
  };
  ErCart.renderLines = renderLines;

  const renderDrawer = () => {
    if (!drawer) return;
    renderLines(drawer.querySelector('.cd-body'));
    drawer.querySelector('.cd-total strong').textContent = ErCart.money(ErCart.total());
    drawer.querySelector('.cd-foot').hidden = !items.length;
  };

  function openDrawer() {
    if (!drawer) buildDrawer();
    renderDrawer();
    if (!drawer.open) { drawer.showModal(); document.body.classList.add('nav-locked'); }
  }

  document.addEventListener('cart:change', () => { updateBadges(); renderDrawer(); });

  document.addEventListener('DOMContentLoaded', () => {
    updateBadges();
    const onCheckout = /\/checkout(\.html)?$/.test(location.pathname);
    document.querySelectorAll('.cart-link').forEach((link) => {
      link.addEventListener('click', (e) => {
        if (onCheckout || e.metaKey || e.ctrlKey) return;
        e.preventDefault();
        openDrawer();
      });
    });
  });
})();
