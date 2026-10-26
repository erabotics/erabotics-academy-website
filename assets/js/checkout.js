// ERABOTICS Store checkout — sends the order to /api/order, which checks prices
// on the server, saves the order and notifies the team.
// No payment is taken online: the team confirms by phone (cash on delivery / InstaPay).
(function () {
  const $ = (id) => document.getElementById(id);


  document.addEventListener('DOMContentLoaded', async () => {
    const form = $('checkout-form');
    if (!form || !window.ErCart) return;
    const cart = window.ErCart;
    const submit = form.querySelector('button[type="submit"]');
    const error = $('co-error');

    const render = () => {
      cart.renderLines($('co-lines'), { compact: true });
      $('co-total').textContent = cart.money(cart.total());
      submit.disabled = cart.count() === 0;
    };
    document.addEventListener('cart:change', render);
    render();

    // Refresh cart prices from the current catalog before the customer orders
    try {
      const r = await fetch('assets/data/catalog.json');
      if (r.ok) {
        const data = await r.json();
        if (cart.reprice(new Map(data.products.map((p) => [p.id, p])))) {
          error.textContent = 'Some prices in your cart were updated to the latest catalog prices.';
          error.hidden = false;
        }
      }
    } catch (e) { /* keep the prices already in the cart */ }

    // Address is only needed for delivery
    const fulfil = $('co-fulfil');
    const deliveryRow = form.querySelector('[data-delivery]');
    const syncDelivery = () => {
      const deliver = fulfil.value === 'Delivery';
      deliveryRow.hidden = !deliver;
      deliveryRow.querySelectorAll('input').forEach((i) => { i.required = deliver; });
    };
    fulfil.addEventListener('change', syncDelivery);
    syncDelivery();

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      error.hidden = true;
      if (!cart.count()) {
        error.textContent = 'Your cart is empty — add parts from the Store first.';
        error.hidden = false;
        return;
      }
      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }

      const items = cart.items().map((i) => ({ id: i.id, qty: i.qty }));
      const fields = Object.fromEntries(new FormData(form));
      const label = submit.textContent;
      submit.disabled = true;
      submit.textContent = 'Sending order…';
      let ok = false;
      let data = {};
      try {
        // Only product IDs and quantities are sent — the server looks up the
        // real prices from the catalog and creates the order reference.
        const r = await fetch(form.action, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ ...fields, items }),
          credentials: 'same-origin'
        });
        data = await r.json().catch(() => ({}));
        ok = r.ok && data.ok;
      } catch (err) { ok = false; }
      const id = data.ref;

      if (ok) {
        cart.clear();
        $('co-ref').textContent = id;
        $('checkout-form-wrap').hidden = true;
        const done = $('checkout-done');
        done.hidden = false;
        done.focus();
      } else {
        error.textContent = data.error || 'Your order could not be sent. Please try again, or send it on WhatsApp: +20 101 539 7943.';
        error.hidden = false;
        submit.disabled = false;
        submit.textContent = label;
      }
    });
  });
})();
