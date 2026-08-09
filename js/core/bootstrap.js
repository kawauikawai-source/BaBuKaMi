(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;
  const store = B.store;
  const ui = B.ui;
  let liveJitterTimer = null;
  let homeInitialized = false;
  let backendOnline = false;
  let heroLoreSelection = null;
  let heroReactionTimer = null;
  const heroConditionOptions = [
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 14, 18],
    [1, 7, 10, 17],
    [1, 2, 3, 4, 5, 9, 16, 18],
    [1, 3, 7, 9, 15],
    [7, 13, 15],
    [1, 2, 3, 4, 7, 9, 13],
    [1, 8, 16, 18],
    [1, 2, 5, 8, 9],
    [12],
    [11],
    [15, 16, 17],
    [6, 14, 17],
    [3, 7, 13, 15],
    [2, 9, 10],
    [17, 20],
    [19, 23],
    [21, 23],
    [13, 22]
  ];
  const heroProtocolOptions = [
    [0, 1, 2, 3, 4, 5, 6, 7],
    [0, 10, 11, 13],
    [0, 2, 3, 8, 12, 13],
    [2, 3, 6, 13],
    [7, 10, 12, 13],
    [0, 2, 4, 5, 6],
    [8, 9, 10, 11, 12],
    [0, 2, 3, 4, 5],
    [3, 10, 12],
    [10, 11, 12, 13],
    [8, 10, 11, 12],
    [8, 9, 10, 11],
    [7, 10, 12, 13],
    [0, 3, 10, 12],
    [11, 15],
    [13, 14],
    [13, 16],
    [13, 17]
  ];
  function pickHeroProtocol(stateIndex) {
    const options = heroProtocolOptions[stateIndex] || heroProtocolOptions[0];
    return options[Math.floor(Math.random() * options.length)];
  }
  function pickHeroKawauiState(excludedState) {
    const regularStateCount = 14;
    const anomalyStartIndex = regularStateCount;
    let candidate;
    do {
      const anomalyRoll = Math.random() < 0.05;
      candidate = anomalyRoll
        ? anomalyStartIndex + Math.floor(Math.random() * (heroConditionOptions.length - anomalyStartIndex))
        : Math.floor(Math.random() * regularStateCount);
    } while (candidate === excludedState);
    return candidate;
  }
  const heroKawauiRoll = pickHeroKawauiState(-1);
  const heroCompatibleConditions = heroConditionOptions[heroKawauiRoll];
  const heroLoreState = {
    kawaui: heroKawauiRoll,
    condition: heroCompatibleConditions[Math.floor(Math.random() * heroCompatibleConditions.length)],
    protocol: pickHeroProtocol(heroKawauiRoll)
  };
  const vipClickerGoals = {
    bronze: 25,
    silver: 50,
    gold: 100,
    platinum: 250
  };
  const vipClickerStorageKey = 'bk_vip_clicker_progress';
  const vipClickerState = {
    tier: null,
    clicksByTier: {},
    versionByTier: {},
    pendingByTier: {},
    pendingActionAtByTier: {},
    flushTimerByTier: {},
    loadedForUserId: null
  };
  const prefersReducedMotion = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const apiBaseUrl = (C.api && C.api.baseUrl) || 'http://127.0.0.1:8000/api';
  const staticCacheVersion = 'offline-i18n-v1';

  function rollHeroLoreState() {
    const nextKawaui = pickHeroKawauiState(heroLoreState.kawaui);
    const compatible = heroConditionOptions[nextKawaui];
    heroLoreState.kawaui = nextKawaui;
    heroLoreState.condition = compatible[Math.floor(Math.random() * compatible.length)];
    heroLoreState.protocol = pickHeroProtocol(nextKawaui);
  }

  function fetchJson(url) {
    return fetch(url, { cache: 'no-store' }).then(response => {
      if (!response.ok) throw new Error('Cannot load ' + url);
      return response.json();
    });
  }

  function fetchStaticJson(url, name) {
    const versionedUrl = `${url}${url.includes('?') ? '&' : '?'}v=${encodeURIComponent(staticCacheVersion)}`;
    return fetch(versionedUrl, { cache: 'no-cache' }).then(response => {
      if (!response.ok) throw new Error('Cannot load ' + versionedUrl);
      return response.json();
    });
  }

  async function loadApiData() {
    const result = await Promise.all([
      fetchJson(apiBaseUrl + '/games'),
      fetchJson(apiBaseUrl + '/bonuses'),
      fetchJson(apiBaseUrl + '/vip/tiers')
    ]);
    return Object.assign({}, result[0], {
      bonuses: result[1],
      vip_tiers: result[2]
    });
  }

  async function loadStaticData() {
    const result = await Promise.allSettled([
      fetchStaticJson(ui.path('dataGames'), 'games'),
      fetchStaticJson(ui.path('dataI18n'), 'i18n')
    ]);
    return [
      result[0].status === 'fulfilled' ? result[0].value : C.fallbackGames,
      result[1].status === 'fulfilled' ? result[1].value : C.fallbackI18n
    ];
  }

  async function refreshApiData() {
    try {
      const remoteGames = await loadApiData();
      const current = store.getState().data || {};
      const staticGames = current.games || {};
      backendOnline = true;
      store.setApiStatus?.('online');
      store.setData(Object.assign({}, remoteGames, {
        slots: staticGames.slots || remoteGames.slots,
        table: staticGames.table || remoteGames.table
      }), current.i18n || C.fallbackI18n);
    } catch (err) {
      backendOnline = false;
      store.setApiStatus?.('offline');
    }
  }

  async function loadData() {
    if (location.protocol === 'file:') {
      backendOnline = false;
      store.setApiStatus?.('offline');
      store.setData(C.fallbackGames, C.fallbackI18n);
      return;
    }
    const result = await loadStaticData();
    store.setData(result[0], result[1]);
    refreshApiData();
  }

  function renderTicker() {
    const inner = document.querySelector('.ticker-inner');
    if (!inner) return;
    const messages = [];
    for (let i = 1; i <= 7; i++) messages.push(ui.t('ticker_' + i));
    const html = messages.map(msg => `<span>${ui.escapeHTML(msg)}</span>`).join('');
    inner.innerHTML = html + html;
  }

  function renderHeroActions() {
    const mount = document.getElementById('heroActions');
    if (!mount) return;
    const user = store.getState().currentUser;
    mount.innerHTML = user
      ? `<a class="btn btn-primary hero-partner-link" href="pages/partner.html">${ui.escapeHTML(ui.t('hero_cta_partner'))}</a>`
      : `<button class="btn btn-primary" type="button" data-modal="register">${ui.escapeHTML(ui.t('hero_cta_register'))}</button>`;
  }

  function renderGames(type) {
    const grid = document.getElementById('gamesGrid');
    if (!grid) return;
    const state = store.getState();
    const lang = state.lang;
    const data = state.data.games || C.fallbackGames;
    const items = type === 'table' ? data.table : data.slots;
    const nameKey = 'name_' + lang;
    const volKey = 'volatility_' + lang;
    const typeKey = 'type_' + lang;

    grid.innerHTML = (items || []).map(game => {
      const gameName = game[nameKey] || game.name_en || game.name_ru || '';
      const slug = String(game.slug || '');
      const isRoulette = slug === 'european-roulette' || String(game.id) === '7' || /european roulette|европейская рулетка/i.test(gameName);
      const isLuckyBamboo = slug === 'lucky-bamboo' || String(game.id) === '3' || /lucky bamboo|счастливый бамбук/i.test(gameName);
      const isDragonCrash = slug === 'dragons-fortune' || String(game.id) === '1' || /dragon's fortune|удача дракона|kawaui fortune|удача кавая/i.test(gameName);
      const isSolarMines = slug === 'solar-wilds' || String(game.id) === '4' || /solar wilds|солнечные вайлды|eclipse hunt|охота затмения/i.test(gameName);
      const isMidnightVault = slug === 'midnight-vault' || String(game.id) === '5' || /midnight vault/i.test(gameName);
      const isArcticProtocol = slug === 'arctic-protocol' || String(game.id) === '6' || /arctic protocol|арктический протокол/i.test(gameName);
      const isNeonPyramids = slug === 'neon-pyramids' || String(game.id) === '2' || /neon pyramids|неоновые пирамиды/i.test(gameName);
      const isTexasHoldem = slug === 'texas-holdem' || String(game.id) === '8' || /texas hold'?em|техасский холдем/i.test(gameName);
      const gameUrl = isRoulette
        ? 'pages/game.html?id=european-roulette&v=roulette-advanced-panel-smooth-v1'
        : (isLuckyBamboo ? 'pages/slot.html?id=lucky-bamboo&v=lucky-bamboo-rtp96-v1' : (isDragonCrash ? 'pages/crash.html?id=dragons-fortune&v=kawaui-fortune-rtp96-v1' : (isSolarMines ? 'pages/mines.html?id=solar-wilds&v=eclipse-hunt-recent-v1' : (isMidnightVault ? 'pages/plinko.html?id=midnight-vault&v=midnight-vault-panel-v1' : (isArcticProtocol ? 'pages/survival.html?id=arctic-protocol&v=arctic-protocol-command-v5' : (isNeonPyramids ? 'pages/blocks.html?id=neon-pyramids&v=neon-pyramids-pressure-v1' : (isTexasHoldem ? 'pages/holdem.html?id=texas-holdem&v=texas-holdem-dom-v1' : (game.url || ''))))))));
      const isFuture = Boolean(game.future);
      return `
      <div class="game-card${isFuture ? ' is-coming-soon' : ''}">
        <span class="game-emoji">${ui.escapeHTML(game.emoji)}</span>
        ${game.tag ? `<span class="game-tag ${game.tag.toLowerCase()}">${ui.escapeHTML(game.tag)}</span>` : ''}
        <span class="game-name">${ui.escapeHTML(gameName)}</span>
        ${game.rtp
          ? `<span class="game-meta">RTP ${ui.escapeHTML(game.rtp)} · ${ui.escapeHTML(game[volKey] || game.volatility_en || '')}</span>`
          : `<span class="game-meta">${ui.escapeHTML(game[typeKey] || game.type_en || '')}</span>`}
        <span class="game-players">${isFuture ? ui.t('game_in_development') : `${ui.formatNumber(game.players)} ${ui.t('game_playing')}`}</span>
        ${isFuture
          ? `<button class="game-play" type="button" disabled>${ui.t('game_coming_soon')}</button>`
          : gameUrl
          ? `<a class="game-play" href="${ui.escapeHTML(gameUrl)}" data-game-id="${ui.escapeHTML(game.id)}" data-game="${ui.escapeHTML(gameName)}" data-game-url="${ui.escapeHTML(gameUrl)}">${ui.t('game_play_btn')}</a>`
          : `<button class="game-play" type="button" data-game-id="${ui.escapeHTML(game.id)}" data-game="${ui.escapeHTML(gameName)}">${ui.t('game_play_btn')}</button>`}
      </div>
    `;
    }).join('');
  }

  function renderBonuses() {
    const grid = document.getElementById('bonusesGrid');
    if (!grid) return;
    const state = store.getState();
    const lang = state.lang;
    const data = state.data.games || C.fallbackGames;
    grid.innerHTML = (data.bonuses || []).map(item => {
      const promoCode = String(item.promo_code || '').trim().toUpperCase();
      const isFuture = Boolean(item.future);
      const target = promoCode
        ? `${ui.path('deposit')}?method=promo&promo=${encodeURIComponent(promoCode)}`
        : (Number(item.id) === 3 ? '#vip' : '#games');
      const scrollTarget = promoCode ? '' : ` data-scroll-target="${target}"`;
      const tag = isFuture ? 'article' : 'a';
      const href = isFuture ? '' : ` href="${ui.escapeHTML(target)}"${scrollTarget}`;
      const ctaKey = isFuture
        ? 'bonus_coming_soon'
        : (promoCode ? 'bonus_use_code' : (Number(item.id) === 3 ? 'bonus_view_tiers' : 'bonus_claim'));
      return `
      <${tag} class="bonus-card${promoCode ? ' is-promo' : ''}${isFuture ? ' is-future' : ''}"${href}>
        <div class="bonus-icon">${ui.escapeHTML(item.icon)}</div>
        <span class="bonus-badge">${ui.escapeHTML(item['badge_' + lang] || item.badge_en)}</span>
        <div class="bonus-amount">${ui.escapeHTML(item.amount)}</div>
        <div class="bonus-title">${ui.escapeHTML(item['title_' + lang] || item.title_en)}</div>
        <p class="bonus-desc">${ui.escapeHTML(item['desc_' + lang] || item.desc_en)}</p>
        <span class="bonus-cta">${ui.escapeHTML(ui.t(ctaKey))}</span>
      </${tag}>
    `;
    }).join('');
  }

  function renderVip() {
    const grid = document.getElementById('vipGrid');
    if (!grid) return;
    const state = store.getState();
    const lang = state.lang;
    const data = state.data.games || C.fallbackGames;
    const icons = { Bronze: 'B', Silver: 'S', Gold: 'G', Platinum: 'P' };
    grid.innerHTML = (data.vip_tiers || []).map(tier => {
      const tierName = String(tier.name || '');
      const tierClass = tierName.toLowerCase();
      const tierMark = icons[tierName] || tier.level || tierName.charAt(0);
      const clicks = vipClickerState.clicksByTier[tierClass] || 0;
      const goal = vipTierGoal(tierClass);
      const progress = vipTierProgress(tierClass);
      const isComplete = progress >= 100;
      return `
      <article class="vip-card vip-tier-${ui.escapeHTML(tierClass)}${isComplete ? ' is-complete' : ''}" data-vip-tier="${ui.escapeHTML(tierClass)}" data-vip-name="${ui.escapeHTML(tierName)}" data-vip-mark="${ui.escapeHTML(tierMark)}">
        <div class="vip-material-plate">
          <span class="vip-plate-mark" aria-hidden="true"><b>${ui.escapeHTML(tierMark)}</b></span>
          <span class="vip-card-rank">${ui.escapeHTML(tierName)}</span>
        </div>
        <div class="vip-card-body">
          <div class="vip-pts">${ui.escapeHTML(tier['points_' + lang] || tier.points_en)}</div>
          <ul class="vip-perks">
            ${(tier['perks_' + lang] || tier.perks_en || []).map(perk => `<li>${ui.escapeHTML(perk)}</li>`).join('')}
          </ul>
          <div class="vip-inline-clicker">
            <div class="vip-inline-clicker-meta">
              <span>CLICKS</span>
              <strong data-vip-inline-count>${ui.formatNumber(clicks)} / ${ui.formatNumber(goal)}</strong>
            </div>
            <button class="vip-inline-clicker-button" type="button" data-vip-inline-click aria-label="${ui.escapeHTML(tierName)} VIP clicker">
              <span aria-hidden="true">${ui.escapeHTML(tierMark)}</span>
              <b>CLICK</b>
            </button>
            <div class="vip-prog-bar" aria-hidden="true"><div class="vip-prog-fill" data-vip-inline-progress style="width:${progress}%"></div></div>
            <button class="vip-inline-reset" type="button" data-vip-inline-reset>${ui.escapeHTML(ui.t('vip_clicker_reset'))}</button>
          </div>
        </div>
      </article>
    `;
    }).join('');
    updateVipCardsCompletion();
  }

  function getVipClickerElements() {
    return {
      overlay: document.getElementById('vipClickerOverlay'),
      modal: document.querySelector('.vip-clicker-modal'),
      button: document.getElementById('vipClickerButton'),
      title: document.getElementById('vipClickerTitle'),
      sub: document.getElementById('vipClickerSub'),
      mark: document.getElementById('vipClickerMark'),
      count: document.getElementById('vipClickerCount'),
      progress: document.getElementById('vipClickerProgress'),
      progressText: document.getElementById('vipClickerProgressText')
    };
  }

  function getVipTierPayload(source) {
    const tierClass = String(source.dataset.vipTier || 'bronze').toLowerCase();
    return {
      tierClass,
      name: source.dataset.vipName || tierClass.charAt(0).toUpperCase() + tierClass.slice(1),
      mark: source.dataset.vipMark || tierClass.charAt(0).toUpperCase()
    };
  }

  function vipTierGoal(tierClass) {
    return vipClickerGoals[tierClass] || vipClickerGoals.bronze;
  }

  function vipTierProgress(tierClass) {
    const clicks = vipClickerState.clicksByTier[tierClass] || 0;
    return Math.min(100, Math.round((clicks / vipTierGoal(tierClass)) * 100));
  }

  function updateVipCardsCompletion() {
    document.querySelectorAll('[data-vip-tier]').forEach(card => {
      const tierClass = String(card.dataset.vipTier || 'bronze').toLowerCase();
      const clicks = vipClickerState.clicksByTier[tierClass] || 0;
      const progress = vipTierProgress(tierClass);
      card.classList.toggle('is-complete', progress >= 100);
      const count = card.querySelector('[data-vip-inline-count]');
      const bar = card.querySelector('[data-vip-inline-progress]');
      if (count) count.textContent = ui.formatNumber(clicks) + ' / ' + ui.formatNumber(vipTierGoal(tierClass));
      if (bar) bar.style.width = progress + '%';
    });
  }

  function vipTierVersion(tierClass) {
    return Number(vipClickerState.versionByTier[tierClass]) || 0;
  }

  function bumpVipTierVersion(tierClass) {
    const next = vipTierVersion(tierClass) + 1;
    vipClickerState.versionByTier[tierClass] = next;
    return next;
  }

  function updateVipClicker(options) {
    const els = getVipClickerElements();
    if (!els.overlay || !vipClickerState.tier) {
      updateVipCardsCompletion();
      return;
    }
    const shouldOpen = Boolean(options && options.open);
    const isOpen = els.overlay.classList.contains('open');
    const tier = vipClickerState.tier;
    const clicks = vipClickerState.clicksByTier[tier.tierClass] || 0;
    const progress = vipTierProgress(tier.tierClass);
    const tierClass = 'vip-tier-' + tier.tierClass;

    els.overlay.className = 'vip-clicker-overlay ' + (shouldOpen || isOpen ? 'open ' : '') + tierClass + (progress >= 100 ? ' is-charged' : '');
    els.overlay.setAttribute('aria-hidden', shouldOpen || isOpen ? 'false' : 'true');
    if (els.button) els.button.className = 'vip-clicker-award ' + tierClass;
    if (els.title) els.title.textContent = tier.name + ' VIP';
    if (els.sub) els.sub.textContent = ui.t('vip_clicker_hint_' + tier.tierClass, { tier: tier.name });
    if (els.mark) els.mark.textContent = tier.mark;
    if (els.count) els.count.textContent = ui.formatNumber(clicks);
    if (els.progress) els.progress.style.width = progress + '%';
    if (els.progressText) els.progressText.textContent = progress + '%';
    updateVipCardsCompletion();
  }

  function currentApiUserId() {
    const user = store.getState().currentUser;
    return user && user.apiId ? String(user.apiId) : '';
  }

  function currentVipUserKey() {
    const user = store.getState().currentUser;
    const key = user ? String(user.apiId || user.id || user.email || '').trim().toLowerCase() : '';
    return key || 'guest';
  }

  function readVipClickerStorage() {
    try {
      return JSON.parse(localStorage.getItem(vipClickerStorageKey) || '{}') || {};
    } catch (err) {
      return {};
    }
  }

  function saveLocalVipClickerProgress() {
    const userKey = currentVipUserKey();
    if (!userKey) return;
    const stored = readVipClickerStorage();
    stored[userKey] = Object.keys(vipClickerGoals).reduce((next, tier) => {
      next[tier] = Math.max(0, Number(vipClickerState.clicksByTier[tier]) || 0);
      return next;
    }, {});
    try {
      localStorage.setItem(vipClickerStorageKey, JSON.stringify(stored));
    } catch (err) {
      // The backend save remains the source of truth when storage is unavailable.
    }
  }

  function applyLocalVipClickerProgress() {
    const userKey = currentVipUserKey();
    if (!userKey) return;
    const stored = readVipClickerStorage();
    if (userKey !== 'guest' && stored.guest && typeof stored.guest === 'object') {
      stored[userKey] = Object.keys(vipClickerGoals).reduce((next, tier) => {
        next[tier] = Math.max(
          Number(stored[userKey]?.[tier]) || 0,
          Number(stored.guest[tier]) || 0
        );
        return next;
      }, {});
      delete stored.guest;
      try {
        localStorage.setItem(vipClickerStorageKey, JSON.stringify(stored));
      } catch (err) {
        // The in-memory clicker still works if storage writes are blocked.
      }
    }
    const localTotals = stored[userKey];
    if (!localTotals || typeof localTotals !== 'object') return;
    Object.keys(vipClickerGoals).forEach(tier => {
      vipClickerState.clicksByTier[tier] = Math.max(0, Number(localTotals[tier]) || 0);
    });
    updateVipClicker();
    updateVipCardsCompletion();
  }

  function applyVipClickerProgress(payload, options) {
    if (!payload || !payload.totals) return;
    const mergeMax = Boolean(options && options.mergeMax);
    const onlyTier = options && options.onlyTier ? String(options.onlyTier).toLowerCase() : '';
    Object.keys(payload.totals).forEach(tier => {
      if (onlyTier && tier !== onlyTier) return;
      const value = Math.max(0, Number(payload.totals[tier]) || 0);
      vipClickerState.clicksByTier[tier] = mergeMax
        ? Math.max(vipClickerState.clicksByTier[tier] || 0, value)
        : value;
    });
    updateVipClicker();
    updateVipCardsCompletion();
    saveLocalVipClickerProgress();
  }

  async function loadVipClickerProgress(force) {
    const userId = currentApiUserId();
    applyLocalVipClickerProgress();
    if (!userId || !store.getVipClickerProgress) {
      vipClickerState.loadedForUserId = null;
      return;
    }
    if (!force && vipClickerState.loadedForUserId === userId) return;
    const result = await store.getVipClickerProgress();
    if (currentApiUserId() !== userId) return;
    vipClickerState.loadedForUserId = userId;
    applyVipClickerProgress(result, { mergeMax: true });
  }

  function openVipClicker(source) {
    const els = getVipClickerElements();
    if (!els.overlay) return;
    vipClickerState.tier = getVipTierPayload(source);
    updateVipClicker({ open: true });
    loadVipClickerProgress();
    if (els.button) els.button.focus();
  }

  function closeVipClicker() {
    const els = getVipClickerElements();
    if (!els.overlay) return;
    els.overlay.classList.remove('open', 'is-charged');
    els.overlay.setAttribute('aria-hidden', 'true');
  }

  function emitVipClickerParticles(button) {
    if (prefersReducedMotion || !button) return;
    for (let i = 0; i < 7; i++) {
      const particle = document.createElement('span');
      particle.className = 'vip-clicker-particle';
      particle.style.setProperty('--x', (Math.random() * 120 - 60).toFixed(0) + 'px');
      particle.style.setProperty('--y', (Math.random() * -92 - 16).toFixed(0) + 'px');
      particle.style.setProperty('--d', (Math.random() * 0.16).toFixed(2) + 's');
      button.appendChild(particle);
      setTimeout(() => particle.remove(), 780);
    }
  }

  async function clickVipAward() {
    const els = getVipClickerElements();
    if (!vipClickerState.tier || !els.button) return;
    const key = vipClickerState.tier.tierClass;
    const actionAt = new Date().toISOString();
    const version = bumpVipTierVersion(key);
    vipClickerState.clicksByTier[key] = (vipClickerState.clicksByTier[key] || 0) + 1;
    els.button.classList.remove('is-clicked');
    void els.button.offsetWidth;
    els.button.classList.add('is-clicked');
    emitVipClickerParticles(els.button);
    updateVipClicker();
    saveLocalVipClickerProgress();
    if (store.clickVipTier && currentApiUserId()) {
      const result = await store.clickVipTier(key, actionAt);
      if (result && result.error) {
        ui.showToast(ui.t(result.error), 'err');
        return;
      }
      if (vipTierVersion(key) === version) {
        applyVipClickerProgress(result, { mergeMax: true, onlyTier: key });
      }
    }
  }

  async function clickVipInline(button) {
    const card = button && button.closest('[data-vip-tier]');
    if (!card) return;
    const tier = getVipTierPayload(card);
    const key = tier.tierClass;
    vipClickerState.tier = tier;
    vipClickerState.clicksByTier[key] = (vipClickerState.clicksByTier[key] || 0) + 1;
    button.classList.remove('is-clicked');
    void button.offsetWidth;
    button.classList.add('is-clicked');
    updateVipCardsCompletion();
    saveLocalVipClickerProgress();
    queueVipClickSync(key);
  }

  async function flushVipClickSync(key) {
    const timer = vipClickerState.flushTimerByTier[key];
    if (timer) global.clearTimeout(timer);
    vipClickerState.flushTimerByTier[key] = null;
    const count = Math.min(25, Math.max(0, Number(vipClickerState.pendingByTier[key]) || 0));
    if (!count) return;
    const actionAt = vipClickerState.pendingActionAtByTier[key] || new Date().toISOString();
    vipClickerState.pendingByTier[key] -= count;
    if (vipClickerState.pendingByTier[key] <= 0) {
      vipClickerState.pendingByTier[key] = 0;
      vipClickerState.pendingActionAtByTier[key] = '';
    }
    if (!store.clickVipTier || !currentApiUserId()) return;
    const version = bumpVipTierVersion(key);
    const result = await store.clickVipTier(key, actionAt, count);
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    if (vipTierVersion(key) === version) {
      applyVipClickerProgress(result, { mergeMax: true, onlyTier: key });
    }
    if (vipClickerState.pendingByTier[key] > 0) queueVipClickSync(key);
  }

  function queueVipClickSync(key) {
    if (!store.clickVipTier || !currentApiUserId()) return;
    if (!vipClickerState.pendingByTier[key]) {
      vipClickerState.pendingByTier[key] = 0;
      vipClickerState.pendingActionAtByTier[key] = new Date().toISOString();
    }
    vipClickerState.pendingByTier[key] += 1;
    if (vipClickerState.pendingByTier[key] >= 25) {
      flushVipClickSync(key);
      return;
    }
    if (vipClickerState.flushTimerByTier[key]) global.clearTimeout(vipClickerState.flushTimerByTier[key]);
    vipClickerState.flushTimerByTier[key] = global.setTimeout(() => flushVipClickSync(key), 650);
  }

  async function resetVipClicker() {
    if (!vipClickerState.tier) return;
    const confirmed = await ui.confirmAction({
      title: ui.t('vip_clicker_reset_confirm_title'),
      message: ui.t('vip_clicker_reset_confirm_message', { tier: vipClickerState.tier.name }),
      okLabel: ui.t('vip_clicker_reset'),
      cancelLabel: ui.t('confirm_cancel')
    });
    if (!confirmed) return;
    const key = vipClickerState.tier.tierClass;
    if (vipClickerState.flushTimerByTier[key]) global.clearTimeout(vipClickerState.flushTimerByTier[key]);
    vipClickerState.flushTimerByTier[key] = null;
    vipClickerState.pendingByTier[key] = 0;
    vipClickerState.pendingActionAtByTier[key] = '';
    const version = bumpVipTierVersion(key);
    vipClickerState.clicksByTier[key] = 0;
    updateVipClicker();
    updateVipCardsCompletion();
    saveLocalVipClickerProgress();
    if (store.resetVipTier && currentApiUserId()) {
      const result = await store.resetVipTier(key);
      if (result && result.error) {
        ui.showToast(ui.t(result.error), 'err');
        return;
      }
      if (vipTierVersion(key) === version) {
        applyVipClickerProgress(result, { onlyTier: key });
      }
    }
  }

  function initVipClicker() {
    document.addEventListener('click', e => {
      const clickButton = e.target.closest('[data-vip-inline-click]');
      if (clickButton) {
        clickVipInline(clickButton);
        return;
      }
      const resetButton = e.target.closest('[data-vip-inline-reset]');
      if (resetButton) {
        const card = resetButton.closest('[data-vip-tier]');
        if (card) vipClickerState.tier = getVipTierPayload(card);
        resetVipClicker();
      }
    });
  }

  function animateCounters() {
    if (prefersReducedMotion) return;
    document.querySelectorAll('[data-count]').forEach(el => {
      const target = Number(el.dataset.count || 0);
      let value = 0;
      const step = () => {
        value += Math.ceil(target / 40);
        if (value >= target) value = target;
        el.textContent = ui.formatNumber(value);
        if (value < target) requestAnimationFrame(step);
      };
      step();
    });
  }

  function getHeroLoreEntry(type) {
    if (type === 'kawaui') {
      return {
        label: ui.t('hero_lore_kawaui_label'),
        title: ui.t(`hero_kawaui_state_${heroLoreState.kawaui + 1}`),
        text: ui.t(`hero_kawaui_log_${heroLoreState.kawaui + 1}`)
      };
    }
    if (type === 'condition') {
      return {
        label: ui.t('hero_entity_condition_label'),
        title: ui.t(`hero_entity_condition_${heroLoreState.condition}`),
        text: ui.t(`hero_condition_log_${heroLoreState.condition}`)
      };
    }
    if (type === 'protocol') {
      return {
        label: ui.t('hero_protocol_label'),
        title: ui.t(`hero_protocol_state_${heroLoreState.protocol + 1}`),
        text: ui.t(`hero_protocol_log_${heroLoreState.protocol + 1}`)
      };
    }
    return {
      label: ui.t('hero_entity_status_label'),
      title: ui.t('hero_entity_status_value'),
      text: ui.t('hero_entity_status_log')
    };
  }

  function renderHeroLore() {
    const consolePanel = document.getElementById('heroLoreConsole');
    if (!consolePanel) return;
    const isOpen = Boolean(heroLoreSelection);
    const entry = getHeroLoreEntry(heroLoreSelection || 'kawaui');
    const label = document.getElementById('heroLoreLabel');
    const title = document.getElementById('heroLoreTitle');
    const text = document.getElementById('heroLoreText');
    if (label) label.textContent = entry.label;
    if (title) title.textContent = entry.title;
    if (text) text.textContent = entry.text;
    consolePanel.classList.toggle('is-open', isOpen);
    consolePanel.dataset.loreType = heroLoreSelection || '';
    consolePanel.dataset.kawauiState = String(heroLoreState.kawaui + 1);
    consolePanel.dataset.condition = String(heroLoreState.condition);
    document.querySelectorAll('[data-hero-lore]').forEach(item => {
      const active = item.dataset.heroLore === heroLoreSelection;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-expanded', active ? 'true' : 'false');
    });
  }

  function setHeroDiagnosticState() {
    const kawauiDiagnostic = document.getElementById('heroKawauiDiagnostic');
    const conditionDiagnostic = document.getElementById('heroConditionDiagnostic');
    const protocolDiagnostic = document.getElementById('heroProtocolDiagnostic');
    if (kawauiDiagnostic) {
      const stateClasses = [
        'is-alive', 'is-warning', 'is-awake', 'is-watching', 'is-outside',
        'is-connected', 'is-madness', 'is-pleased', 'is-sleeping', 'is-critical',
        'is-unfamiliar', 'is-feeding', 'is-distorted', 'is-returning',
        'is-bloodied', 'is-halo', 'is-levitating', 'is-double-shadow'
      ];
      kawauiDiagnostic.classList.remove(...stateClasses);
      kawauiDiagnostic.classList.add(stateClasses[heroLoreState.kawaui]);
      kawauiDiagnostic.dataset.kawauiState = String(heroLoreState.kawaui + 1);
    }
    if (conditionDiagnostic) conditionDiagnostic.dataset.condition = String(heroLoreState.condition);
    if (protocolDiagnostic) protocolDiagnostic.dataset.protocol = String(heroLoreState.protocol + 1);
  }

  function renderHeroStats() {
    const stats = (store.getState().data.games.stats || C.fallbackGames.stats);
    const apiStatus = store.getApiStatus ? store.getApiStatus() : (backendOnline ? 'online' : 'offline');
    backendOnline = apiStatus === 'online';
    document.querySelectorAll('[data-stat]').forEach(el => {
      const key = el.dataset.stat;
      if (stats[key] !== undefined) el.dataset.count = stats[key];
      el.textContent = ui.formatNumber(el.dataset.count);
    });
    const badge = document.getElementById('heroBackendBadge');
    const status = document.getElementById('heroBackendStatus');
    const live = document.getElementById('liveCount');
    const separator = document.getElementById('heroLiveSeparator');
    const players = document.getElementById('heroPlayersLabel');
    if (badge) {
      badge.classList.toggle('is-offline', apiStatus === 'offline');
      badge.classList.toggle('is-checking', apiStatus === 'checking');
    }
    if (status) status.textContent = apiStatus === 'checking' ? ui.t('hero_badge_checking') : (backendOnline ? ui.t('hero_badge') : ui.t('hero_badge_offline'));
    if (separator) separator.hidden = true;
    if (live) {
      live.hidden = true;
      live.textContent = '';
    }
    if (players) players.hidden = true;
    const kawauiState = document.getElementById('heroKawauiState');
    const entityCondition = document.getElementById('heroEntityCondition');
    const protocolState = document.getElementById('heroProtocolState');
    if (kawauiState) kawauiState.textContent = ui.t(`hero_kawaui_state_${heroLoreState.kawaui + 1}`);
    if (entityCondition) entityCondition.textContent = ui.t(`hero_entity_condition_${heroLoreState.condition}`);
    if (protocolState) protocolState.textContent = ui.t(`hero_protocol_state_${heroLoreState.protocol + 1}`);
    setHeroDiagnosticState();
    renderHeroLore();
  }

  function animateJackpot() {
    const el = document.getElementById('jackpotCounter');
    if (!el) return;
    const target = (store.getState().data.games.stats || C.fallbackGames.stats).jackpot_start;
    el.textContent = ui.formatMoney(target);
  }

  function startLiveJitter() {
    return;
  }

  function initHome() {
    if ((document.body.dataset.page || 'home') !== 'home' || homeInitialized) return;
    homeInitialized = true;
    let activeTab = 'slots';
    const renderAll = () => {
      renderHeroStats();
      renderHeroActions();
      renderTicker();
      renderGames(activeTab);
      renderBonuses();
      renderVip();
      animateJackpot();
    };

    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        activeTab = btn.dataset.tab === 'table' ? 'table' : 'slots';
        document.querySelectorAll('.tab-btn').forEach(item => {
          const active = item === btn;
          item.classList.toggle('active', active);
          item.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        const switcher = btn.closest('.game-category-switch');
        if (switcher) switcher.dataset.active = activeTab;
        renderGames(activeTab);
      });
    });
    document.querySelectorAll('[data-hero-lore]').forEach(item => {
      item.addEventListener('click', () => {
        const nextSelection = item.dataset.heroLore || 'kawaui';
        heroLoreSelection = heroLoreSelection === nextSelection ? null : nextSelection;
        document.querySelectorAll('[data-hero-lore]').forEach(node => node.classList.remove('is-reacting'));
        if (heroLoreSelection) {
          item.classList.add('is-reacting');
          if (heroReactionTimer) global.clearTimeout(heroReactionTimer);
          heroReactionTimer = global.setTimeout(() => item.classList.remove('is-reacting'), 720);
        }
        renderHeroLore();
      });
      item.addEventListener('pointermove', event => {
        const bounds = item.getBoundingClientRect();
        item.style.setProperty('--hero-pointer-x', `${event.clientX - bounds.left}px`);
        item.style.setProperty('--hero-pointer-y', `${event.clientY - bounds.top}px`);
      });
      item.addEventListener('pointerleave', () => {
        item.style.removeProperty('--hero-pointer-x');
        item.style.removeProperty('--hero-pointer-y');
      });
    });
    const newSignalButton = document.getElementById('heroNewSignal');
    if (newSignalButton) {
      newSignalButton.addEventListener('click', () => {
        rollHeroLoreState();
        if (!heroLoreSelection) heroLoreSelection = 'kawaui';
        const diagnostics = document.querySelector('.hero-diagnostics');
        if (diagnostics) {
          diagnostics.classList.remove('is-refreshing');
          void diagnostics.offsetWidth;
          diagnostics.classList.add('is-refreshing');
          global.setTimeout(() => diagnostics.classList.remove('is-refreshing'), 560);
        }
        renderHeroStats();
      });
    }
    document.addEventListener('click', e => {
      const game = e.target.closest('[data-game]');
      if (!game) return;
      const gameUrl = game.dataset.gameUrl || '';
      if (gameUrl) {
        if (game.tagName !== 'A') location.href = gameUrl;
        return;
      }
      ui.showToast(ui.t('toast_game', { name: game.dataset.game }));
    });
    store.subscribe((next, prev, action) => {
      if (next.lang !== prev.lang || action === 'data:set' || action === 'api:status') {
        renderAll();
        updateVipClicker();
      }
      const nextUserId = next.currentUser && next.currentUser.apiId ? String(next.currentUser.apiId) : '';
      const prevUserId = prev.currentUser && prev.currentUser.apiId ? String(prev.currentUser.apiId) : '';
      if (nextUserId !== prevUserId) {
        renderHeroActions();
        Object.values(vipClickerState.flushTimerByTier).forEach(timer => {
          if (timer) global.clearTimeout(timer);
        });
        vipClickerState.clicksByTier = {};
        vipClickerState.versionByTier = {};
        vipClickerState.pendingByTier = {};
        vipClickerState.pendingActionAtByTier = {};
        vipClickerState.flushTimerByTier = {};
        vipClickerState.loadedForUserId = null;
        updateVipClicker();
        loadVipClickerProgress(true);
      }
    });
    initVipClicker();
    renderAll();
    loadVipClickerProgress();
    animateCounters();
    startLiveJitter();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    try {
      await Promise.allSettled([
        loadData(),
        store.restoreSession ? store.restoreSession() : Promise.resolve()
      ]);
      bootstrapFeatures();
    } finally {
      global.requestAnimationFrame(() => {
        document.body.classList.remove('is-app-booting');
        document.body.classList.add('is-app-ready');
      });
    }
  });

  function bootstrapFeatures() {
    ui.initCommon();
    B.auth?.init();
    initHome();
    B.profile?.init();
    B.cashier?.init();
    B.admin?.init();
    B.game?.init();
    B.slot?.init();
    B.crash?.init();
    B.mines?.init();
    B.blocks?.init();
    B.holdem?.init();
    ui.initHelp();
    ui.applyLang();
  }
})(window);
