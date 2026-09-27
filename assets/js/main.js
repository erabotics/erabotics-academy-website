// Theme toggle (dark/light)
(() => {
  const stored = (() => {
    try { return localStorage.getItem('erabotics-theme'); } catch (e) { return null; }
  })();
  const theme = stored || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  document.documentElement.setAttribute('data-theme', theme);
})();

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('erabotics-theme', theme); } catch (e) { /* ignore */ }
}

// Mobile nav toggle
document.addEventListener('DOMContentLoaded', () => {
  const themeToggle = document.querySelector('.theme-toggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
      setTheme(current === 'light' ? 'dark' : 'light');
    });
  }

  const toggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      nav.classList.toggle('open');
    });
    nav.querySelectorAll('.nav-links a').forEach((link) => {
      link.addEventListener('click', () => nav.classList.remove('open'));
    });
  }

  // FAQ accordion
  document.querySelectorAll('.faq-item').forEach((item) => {
    const q = item.querySelector('.faq-q');
    if (!q) return;
    q.addEventListener('click', () => {
      const isOpen = item.classList.contains('open');
      item.closest('.faq-list')?.querySelectorAll('.faq-item').forEach((i) => i.classList.remove('open'));
      if (!isOpen) item.classList.add('open');
    });
  });

  // Store filter chips
  const chips = document.querySelectorAll('.filter-chip');
  const products = document.querySelectorAll('[data-category]');
  if (chips.length && products.length) {
    chips.forEach((chip) => {
      chip.addEventListener('click', () => {
        chips.forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');
        const cat = chip.dataset.filter;
        products.forEach((p) => {
          p.style.display = cat === 'all' || p.dataset.category === cat ? '' : 'none';
        });
      });
    });
  }

  // Header shadow on scroll
  const header = document.querySelector('.site-header');
  if (header) {
    window.addEventListener('scroll', () => {
      header.style.boxShadow = window.scrollY > 10 ? '0 8px 24px -12px rgba(0,0,0,0.5)' : 'none';
    });
  }

  // Contact / lead forms: no backend yet, show confirmation
  document.querySelectorAll('form[data-form]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      const original = btn ? btn.textContent : '';
      if (btn) {
        btn.textContent = 'Sent — we’ll be in touch';
        btn.disabled = true;
      }
      form.reset();
      setTimeout(() => {
        if (btn) { btn.textContent = original; btn.disabled = false; }
      }, 3500);
    });
  });

  // Set active nav link based on current page (also lights up the
  // Academy parent when the current page is one of its dropdown tracks)
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a, .dropdown a').forEach((a) => {
    const href = a.getAttribute('href');
    if (href === path) {
      a.classList.add('active');
      const parentItem = a.closest('.has-dropdown');
      if (parentItem) {
        const parentLink = parentItem.querySelector(':scope > a');
        if (parentLink) parentLink.classList.add('active');
      }
    }
  });
});
