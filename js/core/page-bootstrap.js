(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;
  const store = B.store;
  const ui = B.ui;
  const apiBaseUrl = (C.api && C.api.baseUrl) || '/api';
  const staticCacheVersion = 'js-audit-v1';

  function fetchJson(url) {
    return fetch(url, { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error('api_data_unavailable');
      return response.json();
    });
  }

  async function refreshApiData() {
    try {
      const [games, bonuses, vipTiers] = await Promise.all([
        fetchJson(apiBaseUrl + '/games'),
        fetchJson(apiBaseUrl + '/bonuses'),
        fetchJson(apiBaseUrl + '/vip/tiers')
      ]);
      const current = store.getState().data || {};
      const staticGames = current.games || {};
      store.setData(Object.assign({}, games, {
        bonuses,
        vip_tiers: vipTiers,
        slots: staticGames.slots || games.slots,
        table: staticGames.table || games.table
      }), current.i18n || C.fallbackI18n);
      store.setApiStatus?.('online');
    } catch (err) {
      store.setApiStatus?.('offline');
    }
  }

  function fetchStaticJson(url, fallback) {
    const separator = url.includes('?') ? '&' : '?';
    return fetch(`${url}${separator}v=${staticCacheVersion}`, { cache: 'no-cache' })
      .then(response => response.ok ? response.json() : Promise.reject(new Error('static_data_unavailable')))
      .catch(() => fallback);
  }

  async function loadData() {
    if (location.protocol === 'file:') {
      store.setData(C.fallbackGames, C.fallbackI18n);
      store.setApiStatus?.('offline');
      return;
    }
    const [games, i18n] = await Promise.all([
      fetchStaticJson(ui.path('dataGames'), C.fallbackGames),
      fetchStaticJson(ui.path('dataI18n'), C.fallbackI18n)
    ]);
    store.setData(games, i18n);
    refreshApiData();
  }

  function initPage() {
    ui.initCommon();
    B.auth?.init();
    B.profile?.init();
    B.cashier?.init();
    B.admin?.init();
    B.game?.init();
    B.slot?.init();
    B.crash?.init();
    B.mines?.init();
    B.blocks?.init();
    B.holdem?.init();
    B.plinko?.init();
    B.survival?.init();
    B.partner?.init();
    B.trust?.init();
    B.gameControl?.init();
    ui.applyLang();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    try {
      await Promise.allSettled([
        loadData(),
        store.restoreSession ? store.restoreSession() : Promise.resolve()
      ]);
      initPage();
    } finally {
      global.requestAnimationFrame(() => {
        document.body.classList.remove('is-app-booting');
        document.body.classList.add('is-app-ready');
      });
    }
  }, { once: true });
})(window);
