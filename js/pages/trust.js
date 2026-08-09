(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const pageCache = new Map();
  const trustNames = new Set(['help.html', 'responsible.html', 'privacy.html', 'terms.html']);
  let controlAssetsPromise = null;

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
      B.ui?.initHelp?.();
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

  document.addEventListener('DOMContentLoaded', async () => {
    if (document.getElementById('gameControlTerminal')) {
      await ensureControlAssets().catch(() => {});
      B.gameControl?.init?.();
    }
    warmPages();
  });
})(window);
