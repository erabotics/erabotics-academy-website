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

  // Contact / lead forms: submit to Formspree (email) and log a row to
  // Google Sheets in parallel, show real result
  const SHEETS_WEBHOOK = 'https://script.google.com/macros/s/AKfycbxMVs1V1PjSnPmYh-KaWnmqgCGjYRC5kY_jtf6qNRXT5Xw5QcZqEjclfsoe9K-PfPHe/exec';

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

      const sheetSend = fetch(SHEETS_WEBHOOK, {
        method: 'POST',
        mode: 'no-cors',
        body: new FormData(form)
      }).catch(() => {});

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
      '<button class="chat-fab" aria-label="Ask a question about ERABOTICS">' +
        '<svg class="chat-fab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>' +
        '<svg class="chat-fab-close" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"></path></svg>' +
      '</button>' +
      '<div class="chat-panel">' +
        '<div class="chat-header"><span>Ask ERABOTICS</span><span class="chat-header-sub">Quick answers, instantly</span></div>' +
        '<div class="chat-body">' +
          '<div class="chat-messages"><div class="chat-msg chat-msg-bot">Hi! Pick a question below and I’ll answer right away.</div></div>' +
          '<div class="chat-questions"></div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(widget);

    const messagesEl = widget.querySelector('.chat-messages');
    const questionsEl = widget.querySelector('.chat-questions');
    const bodyEl = widget.querySelector('.chat-body');

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

    widget.querySelector('.chat-fab').addEventListener('click', () => {
      widget.classList.toggle('open');
    });
  });
})();
