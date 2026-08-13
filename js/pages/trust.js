(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;
  const store = B.store;
  const ui = B.ui;
  const pageCache = new Map();
  const trustNames = new Set(['help.html', 'responsible.html', 'privacy.html', 'terms.html']);
  let controlAssetsPromise = null;
  let initialized = false;
  let helpUnsubscribe = null;

  function initHelp() {
    const container = document.getElementById('faq-container');
    if (!container) {
      if (helpUnsubscribe) {
        helpUnsubscribe();
        helpUnsubscribe = null;
      }
      return;
    }
    if (container.dataset.helpReady) return;
    if (helpUnsubscribe) {
      helpUnsubscribe();
      helpUnsubscribe = null;
    }
    container.dataset.helpReady = '1';
    let activeCategory = 'all';
    const render = () => {
      const lang = store.getState().lang;
      const query = (document.getElementById('faq-search')?.value || '').trim().toLowerCase();
      const categories = activeCategory === 'all' ? Object.keys(C.faq) : [activeCategory];
      let total = 0;
      const html = categories.map(category => {
        const items = (C.faq[category] || []).filter(item => !query ||
          `${item['q_' + lang]} ${item['a_' + lang]}`.toLowerCase().includes(query));
        if (!items.length) return '';
        total += items.length;
        return `<div class="faq-section"><div class="faq-section-title">${ui.escapeHTML(ui.t('help_' + category))}</div>${items.map((item, index) => `<div class="faq-item"><button class="faq-q" type="button" data-faq-toggle aria-expanded="false" aria-controls="faq-answer-${category}-${index}">${ui.escapeHTML(item['q_' + lang])}<span class="faq-arrow">v</span></button><div class="faq-a" id="faq-answer-${category}-${index}">${ui.escapeHTML(item['a_' + lang])}</div></div>`).join('')}</div>`;
      }).join('');
      container.innerHTML = total ? html : `<div class="no-results"><div class="no-results-icon">?</div><p>${ui.t('help_no_results')}</p></div>`;
    };
    document.querySelectorAll('.help-cat').forEach(button => button.addEventListener('click', () => {
      activeCategory = button.dataset.cat || 'all';
      document.querySelectorAll('.help-cat').forEach(item => {
        const active = item === button;
        item.classList.toggle('active', active);
        item.setAttribute('aria-selected', String(active));
      });
      const search = document.getElementById('faq-search');
      if (search) search.value = '';
      render();
    }));
    document.getElementById('faq-search')?.addEventListener('input', render);
    document.getElementById('btn-search')?.addEventListener('click', render);
    container.addEventListener('click', event => {
      const toggle = event.target.closest('[data-faq-toggle]');
      if (!toggle) return;
      const answer = toggle.nextElementSibling;
      const open = answer.classList.contains('open');
      container.querySelectorAll('.faq-a.open').forEach(item => item.classList.remove('open'));
      container.querySelectorAll('.faq-q.open').forEach(item => {
        item.classList.remove('open');
        item.setAttribute('aria-expanded', 'false');
      });
      if (!open) {
        answer.classList.add('open');
        toggle.classList.add('open');
        toggle.setAttribute('aria-expanded', 'true');
      }
    });
    helpUnsubscribe = store.subscribe(render);
    render();
  }

  function isTrustUrl(url) {
    return url.origin === location.origin && trustNames.has(url.pathname.split('/').pop());
  }

  function fetchPage(url) {
    const key = url.pathname;
    if (!pageCache.has(key)) {
      pageCache.set(key, fetch(url.href, { credentials: 'same-origin' }).then(response => {
        if (!response.ok) throw new Error('trust_page_unavailable');
        return response.text();
      }));
    }
    return pageCache.get(key);
  }

  function ensureControlAssets() {
    if (B.gameControl) return Promise.resolve();
    if (controlAssetsPromise) return controlAssetsPromise;

    const styleHref = new URL('../css/pages/responsible.css?v=game-control-v2', location.href).href;
    if (!document.querySelector('link[data-game-control-style]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = styleHref;
      link.dataset.gameControlStyle = '1';
      document.head.appendChild(link);
    }

    controlAssetsPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = new URL('../js/pages/responsible.js?v=game-control-v2', location.href).href;
      script.dataset.gameControlScript = '1';
      script.onload = resolve;
      script.onerror = reject;
      document.body.appendChild(script);
    });
    return controlAssetsPromise;
  }

  function warmPages() {
    document.querySelectorAll('.trust-section-link[href]').forEach(link => {
      const url = new URL(link.href, location.href);
      if (isTrustUrl(url) && url.pathname !== location.pathname) fetchPage(url).catch(() => {});
    });
    const warmControl = () => ensureControlAssets().catch(() => {});
    if ('requestIdleCallback' in global) global.requestIdleCallback(warmControl, { timeout: 1400 });
    else global.setTimeout(warmControl, 500);
  }

  async function navigate(url, push) {
    document.body.classList.add('is-trust-navigating');
    try {
      const html = await fetchPage(url);
      const parsed = new DOMParser().parseFromString(html, 'text/html');
      const nextMain = parsed.querySelector('main.trust-page');
      const currentMain = document.querySelector('main.trust-page');
      if (!nextMain || !currentMain) throw new Error('trust_page_invalid');
      if (nextMain.querySelector('#gameControlTerminal')) await ensureControlAssets();
      currentMain.replaceWith(document.importNode(nextMain, true));
      document.body.classList.add('trust-page-swapped');
      document.body.dataset.page = parsed.body.dataset.page || '';
      document.title = parsed.title || document.title;
      if (push) history.pushState({ trust: true }, '', url.href);
      B.ui?.applyLang(document.querySelector('main.trust-page'));
      initHelp();
      if (document.getElementById('gameControlTerminal')) B.gameControl?.init?.();
      global.scrollTo({ top: 0, behavior: 'auto' });
      warmPages();
    } catch (err) {
      location.href = url.href;
      return;
    } finally {
      global.requestAnimationFrame(() => document.body.classList.remove('is-trust-navigating'));
    }
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('.trust-section-link[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, location.href);
    if (!isTrustUrl(url) || url.pathname === location.pathname) return;
    event.preventDefault();
    document.querySelectorAll('.trust-section-link').forEach(item => item.classList.toggle('active', item === link));
    navigate(url, true);
  });

  global.addEventListener('popstate', () => {
    const url = new URL(location.href);
    if (isTrustUrl(url)) navigate(url, false);
  });

  async function init() {
    if (initialized) return;
    initialized = true;
    initHelp();
    if (document.getElementById('gameControlTerminal')) {
      await ensureControlAssets().catch(() => {});
      B.gameControl?.init?.();
    }
    warmPages();
  }

  B.trust = { init };
})(window);
