// Theme toggle (dark/light)
(() => {
  const stored = (() => {
    try { return localStorage.getItem('erabotics-theme'); } catch (e) { return null; }
  })();
  const theme = stored || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.classList.add('js');
})();

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('erabotics-theme', theme); } catch (e) { /* ignore */ }
}

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

document.addEventListener('DOMContentLoaded', () => {
  const themeToggle = document.querySelector('.theme-toggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
      setTheme(current === 'light' ? 'dark' : 'light');
    });
  }

  // Mobile nav toggle
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.nav');
  if (toggle && nav) {
    const setOpen = (open) => {
      nav.classList.toggle('open', open);
      document.body.classList.toggle('nav-locked', open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    };
    toggle.addEventListener('click', () => setOpen(!nav.classList.contains('open')));
    nav.querySelectorAll('.nav-links a').forEach((link) => {
      link.addEventListener('click', () => setOpen(false));
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && nav.classList.contains('open')) { setOpen(false); toggle.focus(); }
    });
    window.matchMedia('(min-width: 1081px)').addEventListener('change', (e) => { if (e.matches) setOpen(false); });
  }

  // FAQ accordion
  document.querySelectorAll('.faq-item').forEach((item) => {
    const q = item.querySelector('.faq-q');
    if (!q) return;
    q.setAttribute('aria-expanded', String(item.classList.contains('open')));
    q.addEventListener('click', () => {
      const isOpen = item.classList.contains('open');
      item.closest('.faq-list')?.querySelectorAll('.faq-item').forEach((i) => {
        i.classList.remove('open');
        i.querySelector('.faq-q')?.setAttribute('aria-expanded', 'false');
      });
      if (!isOpen) {
        item.classList.add('open');
        q.setAttribute('aria-expanded', 'true');
      }
    });
  });

  // Store filter chips
  const chips = document.querySelectorAll('.filter-chip');
  const products = document.querySelectorAll('[data-category]');
  if (chips.length && products.length) {
    chips.forEach((chip) => {
      chip.setAttribute('aria-pressed', String(chip.classList.contains('active')));
      chip.addEventListener('click', () => {
        chips.forEach((c) => { c.classList.remove('active'); c.setAttribute('aria-pressed', 'false'); });
        chip.classList.add('active');
        chip.setAttribute('aria-pressed', 'true');
        const cat = chip.dataset.filter;
        products.forEach((p) => {
          p.hidden = !(cat === 'all' || p.dataset.category === cat);
        });
      });
    });
  }

  // Header background on scroll
  const header = document.querySelector('.site-header');
  if (header) {
    const onScroll = () => header.classList.toggle('is-scrolled', window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  // Contact / lead forms: submit to Formspree (email) and, if the form has
  // a data-sheet URL, log a copy to a Google Sheet in parallel
  document.querySelectorAll('form[data-form]').forEach((form) => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      const original = btn ? btn.textContent : '';
      if (btn) {
        btn.textContent = 'Sending…';
        btn.disabled = true;
      }

      const emailSend = fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { Accept: 'application/json' }
      }).then((r) => r.ok).catch(() => false);

      const sheetUrl = form.dataset.sheet;
      const sheetSend = sheetUrl
        ? fetch(sheetUrl, { method: 'POST', mode: 'no-cors', body: new FormData(form) }).catch(() => {})
        : Promise.resolve();

      const [ok] = await Promise.all([emailSend, sheetSend]);

      if (btn) {
        btn.textContent = ok ? 'Sent — we’ll be in touch' : 'Something went wrong — try again';
      }
      if (ok) form.reset();

      setTimeout(() => {
        if (btn) { btn.textContent = original; btn.disabled = false; }
      }, 4000);
    });
  });

  // Apply buttons on the Adult Courses page: scroll to the application
  // form and pre-select the course
  document.querySelectorAll('[data-apply]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const course = btn.getAttribute('data-apply');
      const target = document.getElementById('apply');
      const select = document.getElementById('course');
      if (select) {
        const match = [...select.options].find((o) => o.value === course);
        if (match) select.value = course;
      }
      if (target) target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    });
  });

  // Set active nav link based on current page (also lights up the
  // Academy parent when the current page is one of its dropdown tracks).
  // Works with clean URLs (/academy) and file URLs (academy.html).
  const normalize = (p) => p.replace(/\/+$/, '').split('/').pop().replace(/\.html$/, '').replace(/^index$/, '');
  const current = normalize(window.location.pathname);
  document.querySelectorAll('.nav-links a, .dropdown a').forEach((a) => {
    const href = a.getAttribute('href');
    // Section links (/#how-it-works) are highlighted by the scroll-spy below instead
    if (!href || href.startsWith('http') || href.includes('#')) return;
    if (normalize(href.split('#')[0]) === current) {
      a.classList.add('active');
      a.setAttribute('aria-current', 'page');
      const parentItem = a.closest('.has-dropdown');
      if (parentItem) {
        const parentLink = parentItem.querySelector(':scope > a');
        if (parentLink) parentLink.classList.add('active');
      }
    }
  });

  // Scroll reveal
  const revealEls = document.querySelectorAll('[data-reveal], [data-reveal-group]');
  if (!('IntersectionObserver' in window) || reduceMotion) {
    revealEls.forEach((el) => el.classList.add('is-visible'));
  } else {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.12 });
    revealEls.forEach((el) => io.observe(el));
  }

  // Hero: subtle depth on pointer move (fine pointers only)
  const visual = document.querySelector('.hero-visual');
  if (visual && !reduceMotion && window.matchMedia('(pointer: fine)').matches) {
    const layers = visual.querySelectorAll('[data-depth]');
    let frame = null;
    visual.closest('.hero').addEventListener('pointermove', (e) => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        const r = visual.getBoundingClientRect();
        const x = (e.clientX - (r.left + r.width / 2)) / r.width;
        const y = (e.clientY - (r.top + r.height / 2)) / r.height;
        layers.forEach((l) => {
          const d = parseFloat(l.dataset.depth) * 6;
          l.style.transform = `translate3d(${(-x * d).toFixed(2)}px, ${(-y * d).toFixed(2)}px, 0)`;
        });
        frame = null;
      });
    });
  }

  // Hero: live-looking telemetry (decorative)
  const coords = document.querySelector('[data-coords]');
  const dist = document.querySelector('[data-tele="dist"]');
  const motor = document.querySelector('[data-tele="motor"]');
  if (dist && !reduceMotion) {
    let t = 0;
    setInterval(() => {
      if (document.hidden) return;
      t += 1;
      dist.textContent = `${(24 + Math.sin(t / 3) * 6 + Math.random()).toFixed(1)} cm`;
      const l = Math.round(60 + Math.sin(t / 4) * 8);
      motor.textContent = `${l}% / ${l - 4 + Math.round(Math.random() * 3)}%`;
      if (coords) coords.textContent = `X ${(120 + Math.cos(t / 5) * 40).toFixed(1).padStart(5, '0')} · Y ${(80 + Math.sin(t / 5) * 30).toFixed(1).padStart(5, '0')}`;
    }, 900);
  }

  // Pathway: five-stage journey (accessible tabs)
  const journey = document.querySelector('[data-journey]');
  if (journey) {
    const tabs = [...journey.querySelectorAll('[role="tab"]')];
    const panels = tabs.map((t) => document.getElementById(t.getAttribute('aria-controls')));
    const select = (i, focus) => {
      tabs.forEach((t, j) => {
        const on = j === i;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        t.classList.toggle('is-past', j < i);
        panels[j].hidden = !on;
        if (on && !reduceMotion) {
          panels[j].classList.remove('is-entering');
          void panels[j].offsetWidth;
          panels[j].classList.add('is-entering');
        }
      });
      journey.style.setProperty('--step', i);
      if (focus) tabs[i].focus();
      const rail = tabs[i].parentElement;
      if (rail.scrollWidth > rail.clientWidth) rail.scrollTo({ left: tabs[i].offsetLeft - 8, behavior: reduceMotion ? 'auto' : 'smooth' });
    };
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => select(i));
      t.addEventListener('keydown', (e) => {
        const k = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (k) { e.preventDefault(); select((i + k + tabs.length) % tabs.length, true); }
        if (e.key === 'Home') { e.preventDefault(); select(0, true); }
        if (e.key === 'End') { e.preventDefault(); select(tabs.length - 1, true); }
      });
    });
    select(0);
  }

  // How it works: step counter follows the scroll
  const howSteps = [...document.querySelectorAll('[data-how-step]')];
  const howNum = document.querySelector('[data-how-num]');
  const howBars = [...document.querySelectorAll('.how-progress i')];
  if (howSteps.length && 'IntersectionObserver' in window) {
    const setStep = (i) => {
      howSteps.forEach((s, j) => s.classList.toggle('is-active', j === i));
      howBars.forEach((b, j) => b.classList.toggle('on', j <= i));
      if (howNum) howNum.textContent = String(i + 1).padStart(2, '0');
    };
    const sio = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) setStep(Number(en.target.dataset.howStep)); });
    }, { rootMargin: '-45% 0px -45% 0px' });
    howSteps.forEach((s) => sio.observe(s));
    setStep(0);
  }

  // Project gallery: prev/next + counter
  const gallery = document.querySelector('[data-gallery]');
  if (gallery) {
    const items = [...gallery.children];
    const prev = document.querySelector('[data-gallery-prev]');
    const next = document.querySelector('[data-gallery-next]');
    const count = document.querySelector('[data-gallery-count]');
    const step = () => items[1] ? items[1].offsetLeft - items[0].offsetLeft : gallery.clientWidth;
    const index = () => Math.round(gallery.scrollLeft / step());
    const update = () => {
      const i = Math.min(items.length - 1, index());
      const atEnd = gallery.scrollLeft + gallery.clientWidth >= gallery.scrollWidth - 4;
      if (count) count.textContent = `${String(atEnd ? items.length : i + 1).padStart(2, '0')} / ${String(items.length).padStart(2, '0')}`;
      if (prev) prev.disabled = gallery.scrollLeft <= 4;
      if (next) next.disabled = atEnd;
    };
    const go = (d) => gallery.scrollBy({ left: d * step(), behavior: reduceMotion ? 'auto' : 'smooth' });
    prev?.addEventListener('click', () => go(-1));
    next?.addEventListener('click', () => go(1));
    gallery.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
    });
    gallery.addEventListener('scroll', () => requestAnimationFrame(update), { passive: true });
    window.addEventListener('resize', update);
    update();
    if ('IntersectionObserver' in window && !reduceMotion) {
      const gio = new IntersectionObserver(([en]) => { if (en.isIntersecting) { gallery.classList.add('is-visible'); gio.disconnect(); } }, { threshold: 0.2 });
      gio.observe(gallery);
    } else {
      gallery.classList.add('is-visible');
    }
  }

  // Scroll-spy: highlight "How It Works" while that section is on screen
  const spyLink = document.querySelector('.nav-links a[data-section]');
  const spyTarget = spyLink && document.getElementById(spyLink.dataset.section);
  if (spyTarget && 'IntersectionObserver' in window) {
    new IntersectionObserver(([en]) => spyLink.classList.toggle('active', en.isIntersecting), { rootMargin: '-40% 0px -55% 0px' }).observe(spyTarget);
  }
});

// ---------- FAQ chat widget (pre-written Q&A, no external AI) ----------
(function () {
  const FAQS = [
    {
      q: 'How much do the courses cost?',
      a: "Most stages are <strong>3,500 EGP</strong> per 8-week course (Robot Builders, AI Innovators, Future Engineers, or Global Pathway). <strong>Little Explorers</strong> (ages 4–6) is 4,500 EGP and includes a LEGO / ZMROBO kit your child keeps. Full-track bundles and discounts are available too — see <a href=\"programs.html\">Programs &amp; Pricing</a>."
    },
    {
      q: 'What is ERABOTICS?',
      a: 'ERABOTICS Academy is a robotics and STEM education center founded by engineers. We teach robotics, coding, and AI through hands-on, project-based learning — delivered on-site at partner schools.'
    },
    {
      q: 'What courses do you offer?',
      a: 'One clear pathway across five age stages: <strong>Little Explorers</strong> (4–6), <strong>Robot Builders</strong> (7–10), <strong>AI Innovators</strong> (11+), <strong>Future Engineers</strong> (12+), and <strong>Global Pathway</strong> (15–18). Every stage runs 8 weeks with a finished project every week. See <a href="programs.html">Programs &amp; Courses</a>.'
    },
    {
      q: 'Why choose this academy?',
      a: 'Our founders bring 5+ years leading youth robotics programs (iSchool, Engineeius, BigHero, IEEE). Every course includes a finished project every week, a Demo Day for parents, weekly progress updates, a certificate at every level, and a competition path for top students.'
    },
    {
      q: 'How do I enroll my child?',
      a: 'Choose the right age track, then reach out so we can confirm your place — <a href="mailto:academy@eraboticseg.com">academy@eraboticseg.com</a> or +20 101 539 7943 / +20 111 333 7137. Or visit our <a href="contact.html">Contact page</a>.'
    },
    {
      q: 'Where are classes held?',
      a: "Courses run on-site, at your school — no extra commute. If ERABOTICS isn't at your school yet, see <a href=\"partners.html\">Schools &amp; Partners</a> about bringing us there."
    },
    {
      q: 'Who teaches the courses?',
      a: 'Kareem (Co-Founder &amp; Tech Lead, Communication &amp; Electronics Engineer) and Adham (Co-Founder &amp; Hardware Lead, Electronics &amp; Robotics Engineer) — both with 5 years mentoring youth in robotics and electronics. See <a href="about.html">About</a>.'
    },
    {
      q: 'Do you offer any discounts?',
      a: 'Yes — <strong>Sibling 10%</strong> off for a second child, <strong>Referral 10%</strong> for bringing a friend who enrolls, and <strong>Early Bird 5%</strong> for registering early. Discounts can be combined.'
    }
  ];

  document.addEventListener('DOMContentLoaded', () => {
    const widget = document.createElement('div');
    widget.className = 'chat-widget';
    widget.innerHTML =
      '<button class="chat-fab" type="button" aria-label="Ask a question about ERABOTICS" aria-expanded="false" aria-controls="chat-panel">' +
        '<svg class="chat-fab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>' +
        '<svg class="chat-fab-close" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"></path></svg>' +
      '</button>' +
      '<div class="chat-panel" id="chat-panel" role="dialog" aria-label="Quick answers about ERABOTICS">' +
        '<div class="chat-header"><span>Ask ERABOTICS</span><span class="chat-header-sub">Quick answers, instantly</span></div>' +
        '<div class="chat-body">' +
          '<div class="chat-messages" aria-live="polite"><div class="chat-msg chat-msg-bot">Hi! Pick a question below and I’ll answer right away.</div></div>' +
          '<div class="chat-questions"></div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(widget);

    const messagesEl = widget.querySelector('.chat-messages');
    const questionsEl = widget.querySelector('.chat-questions');
    const bodyEl = widget.querySelector('.chat-body');
    const fab = widget.querySelector('.chat-fab');

    FAQS.forEach((item) => {
      const chip = document.createElement('button');
      chip.className = 'chat-question-chip';
      chip.type = 'button';
      chip.textContent = item.q;
      chip.addEventListener('click', () => {
        const userMsg = document.createElement('div');
        userMsg.className = 'chat-msg chat-msg-user';
        userMsg.textContent = item.q;
        messagesEl.appendChild(userMsg);

        const botMsg = document.createElement('div');
        botMsg.className = 'chat-msg chat-msg-bot';
        botMsg.innerHTML = item.a;
        messagesEl.appendChild(botMsg);

        chip.classList.add('asked');
        bodyEl.scrollTop = bodyEl.scrollHeight;
      });
      questionsEl.appendChild(chip);
    });

    const setOpen = (open) => {
      widget.classList.toggle('open', open);
      fab.setAttribute('aria-expanded', String(open));
    };
    fab.addEventListener('click', () => setOpen(!widget.classList.contains('open')));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && widget.classList.contains('open')) { setOpen(false); fab.focus(); }
    });
  });
})();
