(function (global) {
  'use strict';
  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;
  const store = B.store;
  let lastModalOpener = null;
  const numberFormatters = new Map();
  const currencyFormatters = new Map();
  const authNextKey = 'bk_auth_next';
  const audioMutedKey = 'bk_audio_muted';
  const protectedPages = new Set(['profile', 'deposit', 'game', 'slot', 'crash', 'mines', 'blocks', 'holdem', 'plinko', 'survival', 'admin']);
  const protectedRoutes = new Set(['profile', 'deposit', 'withdraw', 'admin']);
  const gameRulePages = {
    game: { title: 'rules_roulette_title', intro: 'rules_roulette_intro', rows: ['rules_roulette_bets', 'rules_roulette_balance', 'rules_server_result'] },
    slot: { title: 'rules_slot_title', intro: 'rules_slot_intro', rows: ['rules_slot_bets', 'rules_slot_lines', 'rules_server_result'] },
    crash: { title: 'rules_crash_title', intro: 'rules_crash_intro', rows: ['rules_crash_start', 'rules_crash_cashout', 'rules_server_result'] },
    mines: { title: 'rules_mines_title', intro: 'rules_mines_intro', rows: ['rules_mines_reveal', 'rules_mines_cashout', 'rules_server_result'] },
    blocks: { title: 'rules_blocks_title', intro: 'rules_blocks_intro', rows: ['rules_blocks_place', 'rules_blocks_cashout', 'rules_server_result'] },
    plinko: { title: 'rules_plinko_title', intro: 'rules_plinko_intro', rows: ['rules_plinko_modes', 'rules_plinko_balance', 'rules_server_result'] },
    survival: { title: 'rules_survival_title', intro: 'rules_survival_intro', rows: ['rules_survival_flow', 'rules_survival_timer', 'rules_survival_payout', 'rules_server_result'] },
    holdem: { title: 'rules_holdem_title', intro: 'rules_holdem_intro', rows: ['rules_holdem_ante', 'rules_holdem_call_fold', 'rules_holdem_dealer', 'rules_server_result'] }
  };
  function readState() {
    return store.peekState ? store.peekState() : store.getState();
  }
  const audio = (() => {
    let ctx = null;
    let master = null;
    let muted = false;
    let volume = 0.75;
    let unlocked = false;
    try {
      muted = localStorage.getItem(audioMutedKey) === '1';
      const savedVolume = Number(localStorage.getItem('bk_audio_volume'));
      if (Number.isFinite(savedVolume) && savedVolume >= 0 && savedVolume <= 1) volume = savedVolume;
    } catch (err) {
      muted = false;
    }
    function now() {
      return ctx ? ctx.currentTime : 0;
    }
    function ensure() {
      if (muted) return null;
      const AudioContext = global.AudioContext || global.webkitAudioContext;
      if (!AudioContext) return null;
      if (!ctx) ctx = new AudioContext();
      if (!master) {
        master = ctx.createGain();
        master.gain.value = volume;
        master.connect(ctx.destination);
      }
      if (ctx.state === 'suspended') ctx.resume().catch(() => {});
      return ctx;
    }
    function unlock() {
      if (muted) return false;
      const audioCtx = ensure();
      if (!audioCtx) return false;
      try {
        const buffer = audioCtx.createBuffer(1, 1, audioCtx.sampleRate);
        const src = audioCtx.createBufferSource();
        src.buffer = buffer;
        src.connect(master || audioCtx.destination);
        src.start(0);
        unlocked = true;
        syncAudioToggles();
        return true;
      } catch (err) {
        return false;
      }
    }
    function envelope(gain, start, duration, peak) {
      gain.gain.cancelScheduledValues(start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, peak), start + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    }
    function tone(freq, duration, type, peak, delay, slideTo) {
      const audioCtx = ensure();
      if (!audioCtx) return;
      const start = now() + Number(delay || 0);
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = type || 'sine';
      osc.frequency.setValueAtTime(freq, start);
      if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, start + duration);
      envelope(gain, start, duration, peak || 0.08);
      osc.connect(gain).connect(master || audioCtx.destination);
      osc.start(start);
      osc.stop(start + duration + 0.04);
    }
    function noise(duration, peak, delay, filterFreq) {
      const audioCtx = ensure();
      if (!audioCtx) return;
      const start = now() + Number(delay || 0);
      const length = Math.max(1, Math.floor(audioCtx.sampleRate * duration));
      const buffer = audioCtx.createBuffer(1, length, audioCtx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 1.6);
      const src = audioCtx.createBufferSource();
      const gain = audioCtx.createGain();
      const filter = audioCtx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.value = filterFreq || 1200;
      filter.Q.value = 0.8;
      envelope(gain, start, duration, peak || 0.045);
      src.buffer = buffer;
      src.connect(filter).connect(gain).connect(master || audioCtx.destination);
      src.start(start);
      src.stop(start + duration + 0.04);
    }
    function play(name) {
      if (muted) return;
      switch (name) {
        case 'chip':
          tone(420, 0.05, 'triangle', 0.07);
          tone(720, 0.04, 'sine', 0.035, 0.018);
          break;
        case 'card':
          noise(0.08, 0.035, 0, 1800);
          tone(360, 0.045, 'triangle', 0.03, 0.012, 260);
          break;
        case 'flip':
          noise(0.07, 0.03, 0, 2300);
          tone(620, 0.07, 'sine', 0.04, 0.025, 980);
          break;
        case 'spin':
          tone(180, 0.18, 'sawtooth', 0.035, 0, 280);
          noise(0.16, 0.025, 0.03, 900);
          break;
        case 'drop':
          tone(540, 0.08, 'triangle', 0.055, 0, 320);
          noise(0.08, 0.025, 0.02, 1500);
          break;
        case 'coin-drop':
          tone(760, 0.07, 'triangle', 0.055, 0, 410);
          tone(480, 0.09, 'sine', 0.04, 0.035, 350);
          break;
        case 'coin-hit':
          tone(980, 0.035, 'triangle', 0.024, 0, 720);
          noise(0.035, 0.012, 0, 2400);
          break;
        case 'ice-crack':
          noise(0.28, 0.055, 0, 2100);
          tone(260, 0.22, 'sawtooth', 0.035, 0.015, 92);
          tone(1280, 0.08, 'triangle', 0.03, 0.11, 560);
          break;
        case 'cashout':
          tone(620, 0.08, 'sine', 0.06);
          tone(930, 0.1, 'sine', 0.055, 0.055);
          tone(1240, 0.12, 'triangle', 0.045, 0.12);
          break;
        case 'win':
          tone(520, 0.09, 'sine', 0.05);
          tone(780, 0.1, 'sine', 0.055, 0.08);
          tone(1040, 0.16, 'triangle', 0.05, 0.17);
          break;
        case 'loss':
          tone(190, 0.18, 'sawtooth', 0.04, 0, 95);
          noise(0.11, 0.025, 0.02, 430);
          break;
        case 'push':
          tone(330, 0.08, 'triangle', 0.035);
          tone(330, 0.08, 'triangle', 0.025, 0.08);
          break;
        case 'error':
          tone(160, 0.08, 'square', 0.035);
          tone(130, 0.08, 'square', 0.03, 0.08);
          break;
        case 'click':
        default:
          tone(680, 0.035, 'triangle', 0.035);
          break;
      }
    }
    function isMuted() {
      return muted;
    }
    function setMuted(nextMuted) {
      muted = Boolean(nextMuted);
      try {
        localStorage.setItem(audioMutedKey, muted ? '1' : '0');
      } catch (err) {
      }
      if (!muted) unlock();
      syncAudioToggles();
      return muted;
    }
    function toggle() {
      return setMuted(!muted);
    }
    function status() {
      return {
        muted,
        unlocked,
        contextState: ctx ? ctx.state : 'none',
        supported: Boolean(global.AudioContext || global.webkitAudioContext)
      };
    }
    return { play, unlock, isMuted, setMuted, toggle, status };
  })();
  B.audio = audio;
  function isInnerPage() {
    return /\/pages\//.test(location.pathname.replace(/\\/g, '/'));
  }
  function path(route, suffix) {
    const inner = isInnerPage();
    const routes = {
      home: inner ? '../index.html' : '#hero',
      games: inner ? '../index.html#games' : '#games',
      bonuses: inner ? '../index.html#bonuses' : '#bonuses',
      vip: inner ? '../index.html#vip' : '#vip',
      profile: inner ? 'profile.html' : 'pages/profile.html',
      admin: inner ? 'admin.html' : 'pages/admin.html',
      deposit: inner ? 'deposit.html' : 'pages/deposit.html',
      withdraw: inner ? 'deposit.html?mode=withdraw' : 'pages/deposit.html?mode=withdraw',
      help: inner ? 'help.html' : 'pages/help.html',
      privacy: inner ? 'privacy.html' : 'pages/privacy.html',
      terms: inner ? 'terms.html' : 'pages/terms.html',
      responsible: inner ? 'responsible.html' : 'pages/responsible.html',
      dataGames: inner ? '../data/games.json?v=catalog-soon-v1' : 'data/games.json?v=catalog-soon-v1',
      dataI18n: inner ? '../data/i18n.json?v=20260811-player-rules-v2' : 'data/i18n.json?v=20260811-player-rules-v2',
      css: inner ? '../css/core/base.css' : 'css/core/base.css'
    };
    return (routes[route] || route) + (suffix || '');
  }
  function sameOriginPath(value) {
    if (!value) return '';
    try {
      const url = new URL(value, location.href);
      if (url.origin !== location.origin) return '';
      return url.pathname + url.search + url.hash;
    } catch (err) {
      return '';
    }
  }
  function currentPath() {
    return location.pathname + location.search + location.hash;
  }
  function homeAuthUrl(tab, nextPath) {
    const home = isInnerPage() ? '../index.html' : 'index.html';
    const params = new URLSearchParams({ auth: tab === 'register' ? 'register' : 'login' });
    if (nextPath) params.set('next', nextPath);
    return `${home}?${params.toString()}`;
  }
  function homeLoginUrl(nextPath) {
    return homeAuthUrl('login', nextPath);
  }
  function rememberAuthNext(nextPath) {
    const safeNext = sameOriginPath(nextPath);
    if (!safeNext) return;
    try {
      sessionStorage.setItem(authNextKey, safeNext);
    } catch (err) {
    }
  }
  function consumeAuthNext() {
    try {
      const stored = sessionStorage.getItem(authNextKey) || '';
      sessionStorage.removeItem(authNextKey);
      return sameOriginPath(stored);
    } catch (err) {
      return '';
    }
  }
  function hasCurrentUser() {
    return Boolean(readState().currentUser);
  }
  function requireAuth(nextPath) {
    if (hasCurrentUser()) return true;
    const safeNext = sameOriginPath(nextPath || currentPath());
    rememberAuthNext(safeNext);
    showToast(t('auth_login_required'), 'err');
    if (document.getElementById('modalOverlay')) {
      openModal('login');
    } else {
      location.href = homeLoginUrl(safeNext);
    }
    return false;
  }
  function removeAuthGate() {
    document.body.classList.remove('auth-gated');
    document.getElementById('authGate')?.remove();
  }
  function renderAuthGate() {
    const page = document.body.dataset.page || '';
    if (!protectedPages.has(page) || hasCurrentUser()) {
      removeAuthGate();
      return false;
    }
    const safeNext = sameOriginPath(currentPath());
    rememberAuthNext(safeNext);
    const main = document.querySelector('main');
    if (!main) return false;
    document.body.classList.add('auth-gated');
    let gate = document.getElementById('authGate');
    if (!gate) {
      gate = document.createElement('section');
      gate.id = 'authGate';
      gate.className = 'auth-gate trust-card';
      main.prepend(gate);
    }
    gate.innerHTML = `
      <p class="label">${escapeHTML(t('auth_gate_label'))}</p>
      <h1>${escapeHTML(t('auth_gate_title'))}</h1>
      <p>${escapeHTML(t('auth_gate_text'))}</p>
      <div class="trust-actions">
        <a class="btn btn-primary" href="${escapeHTML(homeAuthUrl('login', safeNext))}">${escapeHTML(t('nav_signin'))}</a>
        <a class="btn btn-outline" href="${escapeHTML(homeAuthUrl('register', safeNext))}">${escapeHTML(t('nav_join'))}</a>
      </div>
    `;
    return true;
  }
  function shouldProtectHref(href) {
    const safe = sameOriginPath(href);
    if (!safe) return false;
    return /\/pages\/(profile|deposit|game|slot|crash|mines|blocks|holdem|plinko|survival|admin)\.html/i.test(safe);
  }
  function replaceVars(text, vars) {
    return String(text || '').replace(/\{\{(\w+)\}\}/g, (match, key) => vars && vars[key] !== undefined ? vars[key] : match);
  }
  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }
  function setValue(id, value) {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) el.value = value == null ? '' : value;
  }
  function renderPaymentTags(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-payment-tags]').forEach(mount => {
      mount.innerHTML = C.cashier.paymentTags.map(tag => `<span class="pay-tag">${escapeHTML(tag)}</span>`).join('');
    });
  }
  function syncAudioToggles() {
    document.querySelectorAll('[data-audio-toggle]').forEach(button => {
      const muted = B.audio?.isMuted?.();
      button.classList.toggle('is-muted', Boolean(muted));
      button.setAttribute('aria-pressed', muted ? 'false' : 'true');
      button.setAttribute('aria-label', muted ? t('audio_enable') : t('audio_disable'));
      button.title = muted ? t('audio_enable') : t('audio_disable');
      button.textContent = muted ? 'SND OFF' : 'SND ON';
      const status = B.audio?.status?.();
      if (status) button.dataset.audioState = status.contextState;
    });
  }
  function initAudioToggle() {
    document.querySelectorAll('.nav-actions').forEach(actions => {
      if (actions.querySelector('[data-audio-toggle]')) return;
      const button = document.createElement('button');
      button.className = 'audio-toggle';
      button.type = 'button';
      button.setAttribute('data-audio-toggle', '');
      const authNav = actions.querySelector('[data-auth-nav]');
      actions.insertBefore(button, authNav || null);
    });
    syncAudioToggles();
  }
  function t(key, vars) {
    const state = readState();
    const langPack = (state.data.i18n && state.data.i18n[state.lang]) || C.fallbackI18n[state.lang] || C.fallbackI18n.ru;
    const raw = langPack[key] || key;
    return replaceVars(raw, Object.assign({
      termsUrl: path('terms'),
      privacyUrl: path('privacy'),
      supportEmail: C.links.supportEmail,
      partnersEmail: C.links.partnersEmail,
      privacyEmail: C.links.privacyEmail,
      legalEmail: C.links.legalEmail,
      responsibleGaming: C.links.responsibleGaming
    }, vars || {}));
  }
  function escapeHTML(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    })[ch]);
  }
  function sanitizeRichText(raw) {
    const template = document.createElement('template');
    template.innerHTML = String(raw || '');
    const allowed = new Set(['A', 'STRONG', 'EM', 'BR']);
    const nodes = template.content.querySelectorAll('*');
    nodes.forEach(node => {
      if (!allowed.has(node.tagName)) {
        node.replaceWith(document.createTextNode(node.textContent || ''));
        return;
      }
      if (node.tagName === 'A') {
        const href = node.getAttribute('href') || '#';
        node.setAttribute('href', href);
        if (node.getAttribute('target') === '_blank') {
          node.setAttribute('rel', 'noopener noreferrer');
        }
      }
      Array.from(node.attributes).forEach(attr => {
        if (node.tagName === 'A' && ['href', 'target', 'rel'].includes(attr.name)) return;
        node.removeAttribute(attr.name);
      });
    });
    return template.innerHTML;
  }
  function stateDefaults(type) {
    const safeType = ['loading', 'empty', 'error', 'offline'].includes(type) ? type : 'empty';
    return {
      icon: safeType === 'loading' ? '...' : safeType === 'offline' ? 'OFF' : safeType === 'error' ? '!' : '-',
      titleKey: safeType === 'loading' ? 'state_loading_title' : safeType === 'offline' ? 'state_offline_title' : safeType === 'error' ? 'state_error_title' : 'state_empty_title',
      textKey: safeType === 'loading' ? 'state_loading_text' : safeType === 'offline' ? 'state_offline_text' : safeType === 'error' ? 'state_error_text' : 'state_empty_text'
    };
  }
  function renderState(type, options) {
    const defaults = stateDefaults(type);
    const opts = Object.assign({}, defaults, options || {});
    const action = opts.actionLabel ? `<button class="btn btn-outline btn-sm" type="button" ${opts.actionAttr || 'data-state-retry'}>${escapeHTML(opts.actionLabel)}</button>` : '';
    return `
      <div class="trust-card state-card state-${escapeHTML(type || 'empty')}">
        <div class="state-icon">${escapeHTML(opts.icon)}</div>
        <div>
          <strong>${escapeHTML(opts.title || t(opts.titleKey))}</strong>
          <p>${escapeHTML(opts.text || t(opts.textKey))}</p>
          ${action}
        </div>
      </div>
    `;
  }
  function tableStateRow(colspan, type, options) {
    return `<tr><td colspan="${Number(colspan || 1)}" class="state-cell">${renderState(type, options)}</td></tr>`;
  }
  function renderGameHistory(mountId, items, emptyText, options) {
    const mount = typeof mountId === 'string' ? document.getElementById(mountId) : mountId;
    if (!mount) return;
    const opts = options || {};
    const history = Array.isArray(items) ? items : [];
    mount.classList.add('game-history-strip');
    if (!history.length) {
      mount.innerHTML = `<span class="game-history-empty">${escapeHTML(emptyText || t('state_empty_title'))}</span>`;
      return;
    }
    mount.innerHTML = history.map(item => {
      const state = item.state || (item.win ? 'win' : 'loss');
      const label = item.label || '';
      const title = item.title ? `<strong>${escapeHTML(item.title)}</strong>` : '';
      const meta = item.meta ? `<small>${escapeHTML(item.meta)}</small>` : '';
      return `
        <span class="game-history-item ${escapeHTML(state)} ${opts.compact ? 'is-compact' : ''}">
          ${title}
          <span>${escapeHTML(label)}</span>
          ${meta}
        </span>
      `;
    }).join('');
  }
  function formatNumber(value) {
    const lang = readState().lang;
    const locale = C.getLocale ? C.getLocale(lang) : (C.defaults.locale[lang] || 'en-US');
    let formatter = numberFormatters.get(locale);
    if (!formatter) {
      formatter = new Intl.NumberFormat(locale);
      numberFormatters.set(locale, formatter);
    }
    return formatter.format(Number(value || 0));
  }
  function getCurrency() {
    const state = readState();
    const user = state.currentUser || {};
    return user.currency || C.defaults.currency;
  }
  function formatMoney(value, currency) {
    const lang = readState().lang;
    const locale = C.getLocale ? C.getLocale(lang) : (C.defaults.locale[lang] || 'en-US');
    const nextCurrency = currency || getCurrency();
    const key = locale + '::' + nextCurrency;
    let formatter = currencyFormatters.get(key);
    if (!formatter) {
      formatter = new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: nextCurrency,
        minimumFractionDigits: 2
      });
      currencyFormatters.set(key, formatter);
    }
    return formatter.format(Number(value || 0));
  }
  function methodLabel(method) {
    if (!method) return t('tx_unknown_method');
    const lang = readState().lang;
    return method['label_' + lang] || method.label || method.id;
  }
  function applyRoutes(root) {
    (root || document).querySelectorAll('[data-route]').forEach(el => {
      el.setAttribute('href', path(el.dataset.route));
    });
  }
  const datePickerLabels = {
    ru: {
      months: ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'],
      weekdays: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'],
      open: 'Открыть календарь'
    },
    en: {
      months: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
      weekdays: ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
      open: 'Open calendar'
    }
  };
  const datePickerState = { input: null, view: null, popover: null };
  function isoDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
  function parseIsoDate(value) {
    const parts = String(value || '').split('-').map(Number);
    if (parts.length !== 3 || !parts.every(Number.isFinite)) return null;
    const date = new Date(parts[0], parts[1] - 1, parts[2]);
    return date.getFullYear() === parts[0] && date.getMonth() === parts[1] - 1 && date.getDate() === parts[2] ? date : null;
  }
  function datePickerLimits(input) {
    const today = new Date();
    const maxAge = Number(input.dataset.dateMaxAge || 0);
    const calculatedMax = new Date(today.getFullYear() - maxAge, today.getMonth(), today.getDate());
    const min = parseIsoDate(input.min) || new Date(1900, 0, 1);
    const max = parseIsoDate(input.max) || calculatedMax;
    return { min, max };
  }
  function positionDatePicker() {
    const input = datePickerState.input;
    const popover = datePickerState.popover;
    if (!input || !popover || !popover.classList.contains('is-open')) return;
    const rect = input.getBoundingClientRect();
    const width = Math.min(340, global.innerWidth - 24);
    const height = popover.offsetHeight || 390;
    const below = rect.bottom + 8;
    const top = below + height <= global.innerHeight - 12 ? below : Math.max(12, rect.top - height - 8);
    const left = Math.max(12, Math.min(rect.left, global.innerWidth - width - 12));
    popover.style.top = `${top}px`;
    popover.style.left = `${left}px`;
    popover.style.width = `${width}px`;
  }
  function renderDatePicker() {
    const input = datePickerState.input;
    const popover = datePickerState.popover;
    if (!input || !popover) return;
    const lang = readState().lang === 'ru' ? 'ru' : 'en';
    const labels = datePickerLabels[lang];
    const limits = datePickerLimits(input);
    const selected = parseIsoDate(input.value);
    const view = datePickerState.view || selected || limits.max;
    const viewYear = view.getFullYear();
    const viewMonth = view.getMonth();
    const first = new Date(viewYear, viewMonth, 1);
    const gridStart = new Date(viewYear, viewMonth, 1 - ((first.getDay() + 6) % 7));
    const todayIso = isoDate(new Date());
    const selectedIso = selected ? isoDate(selected) : '';
    const days = [];
    for (let index = 0; index < 42; index += 1) {
      const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
      const value = isoDate(date);
      const outside = date.getMonth() !== viewMonth;
      const disabled = date < limits.min || date > limits.max;
      days.push(`<button class="site-date-day${outside ? ' is-muted' : ''}${value === todayIso ? ' is-today' : ''}${value === selectedIso ? ' is-selected' : ''}" type="button" data-site-date-value="${value}"${disabled ? ' disabled' : ''}>${date.getDate()}</button>`);
    }
    const years = [];
    for (let year = limits.max.getFullYear(); year >= limits.min.getFullYear(); year -= 1) {
      years.push(`<option value="${year}"${year === viewYear ? ' selected' : ''}>${year}</option>`);
    }
    popover.innerHTML = `
      <div class="site-date-head">
        <button class="site-date-nav" type="button" data-site-date-nav="-1" aria-label="Previous month">‹</button>
        <select class="site-date-select" data-site-date-month aria-label="Month">
          ${labels.months.map((month, index) => `<option value="${index}"${index === viewMonth ? ' selected' : ''}>${escapeHTML(month)}</option>`).join('')}
        </select>
        <select class="site-date-select" data-site-date-year aria-label="Year">${years.join('')}</select>
        <button class="site-date-nav" type="button" data-site-date-nav="1" aria-label="Next month">›</button>
      </div>
      <div class="site-date-week">${labels.weekdays.map(day => `<span>${day}</span>`).join('')}</div>
      <div class="site-date-grid">${days.join('')}</div>
      <button class="site-date-clear" type="button" data-site-date-clear>${escapeHTML(t('admin_calendar_clear'))}</button>
    `;
    global.requestAnimationFrame(positionDatePicker);
  }
  function closeDatePicker() {
    const input = datePickerState.input;
    datePickerState.popover?.classList.remove('is-open');
    input?.closest('.site-date-field')?.classList.remove('is-open');
    datePickerState.input = null;
    datePickerState.view = null;
  }
  function openDatePicker(input) {
    if (!input || input.disabled) return;
    const limits = datePickerLimits(input);
    datePickerState.input?.closest('.site-date-field')?.classList.remove('is-open');
    datePickerState.input = input;
    datePickerState.view = parseIsoDate(input.value) || limits.max;
    input.closest('.site-date-field')?.classList.add('is-open');
    datePickerState.popover.classList.add('is-open');
    renderDatePicker();
  }
  function ensureDatePickerPopover() {
    if (datePickerState.popover) return datePickerState.popover;
    const popover = document.createElement('div');
    popover.className = 'site-date-popover';
    popover.setAttribute('role', 'dialog');
    popover.setAttribute('aria-label', 'Calendar');
    document.body.appendChild(popover);
    datePickerState.popover = popover;
    document.addEventListener('click', event => {
      if (!datePickerState.input) return;
      if (popover.contains(event.target) || event.target.closest('.site-date-field')) return;
      closeDatePicker();
    });
    global.addEventListener('resize', positionDatePicker);
    document.addEventListener('scroll', positionDatePicker, true);
    popover.addEventListener('click', event => {
      const valueButton = event.target.closest('[data-site-date-value]');
      if (valueButton && datePickerState.input) {
        datePickerState.input.value = valueButton.dataset.siteDateValue;
        datePickerState.input.classList.remove('error');
        datePickerState.input.dispatchEvent(new Event('input', { bubbles: true }));
        datePickerState.input.dispatchEvent(new Event('change', { bubbles: true }));
        closeDatePicker();
        return;
      }
      const nav = event.target.closest('[data-site-date-nav]');
      if (nav && datePickerState.view) {
        datePickerState.view = new Date(datePickerState.view.getFullYear(), datePickerState.view.getMonth() + Number(nav.dataset.siteDateNav), 1);
        renderDatePicker();
        return;
      }
      if (event.target.closest('[data-site-date-clear]') && datePickerState.input) {
        datePickerState.input.value = '';
        datePickerState.input.dispatchEvent(new Event('input', { bubbles: true }));
        datePickerState.input.dispatchEvent(new Event('change', { bubbles: true }));
        closeDatePicker();
      }
    });
    popover.addEventListener('change', event => {
      if (!datePickerState.view) return;
      const month = popover.querySelector('[data-site-date-month]');
      const year = popover.querySelector('[data-site-date-year]');
      if (event.target === month || event.target === year) {
        datePickerState.view = new Date(Number(year.value), Number(month.value), 1);
        renderDatePicker();
      }
    });
    return popover;
  }
  function initDatePickers(root) {
    ensureDatePickerPopover();
    (root || document).querySelectorAll('[data-site-date-picker]').forEach(input => {
      if (input.dataset.datePickerReady === '1') return;
      input.dataset.datePickerReady = '1';
      input.type = 'text';
      input.readOnly = true;
      input.placeholder = 'YYYY-MM-DD';
      const field = document.createElement('div');
      field.className = 'site-date-field';
      input.parentNode.insertBefore(field, input);
      field.appendChild(input);
      const trigger = document.createElement('button');
      trigger.className = 'site-date-trigger';
      trigger.type = 'button';
      trigger.setAttribute('aria-label', datePickerLabels[readState().lang === 'ru' ? 'ru' : 'en'].open);
      field.appendChild(trigger);
      input.addEventListener('click', () => openDatePicker(input));
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
          event.preventDefault();
          openDatePicker(input);
        }
      });
      trigger.addEventListener('click', () => openDatePicker(input));
      document.querySelector(`label[for="${input.id}"]`)?.addEventListener('click', event => {
        event.preventDefault();
        openDatePicker(input);
      });
    });
  }
  function applyLang(root) {
    const scope = root || document;
    const lang = readState().lang;
    document.documentElement.lang = lang;
    scope.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = t(el.dataset.i18n);
    });
    scope.querySelectorAll('[data-i18n-html]').forEach(el => {
      el.innerHTML = sanitizeRichText(t(el.dataset.i18nHtml));
    });
    scope.querySelectorAll('[data-i18n-ph]').forEach(el => {
      el.setAttribute('placeholder', t(el.dataset.i18nPh));
    });
    scope.querySelectorAll('[data-lang-content]').forEach(el => {
      el.hidden = el.dataset.langContent !== lang;
    });
    scope.querySelectorAll('.lang-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.lang === lang);
    });
    scope.querySelectorAll('[data-game-rules-open]').forEach(btn => {
      btn.textContent = t('rules_button');
    });
    scope.querySelectorAll('.site-date-trigger').forEach(button => {
      button.setAttribute('aria-label', datePickerLabels[lang === 'ru' ? 'ru' : 'en'].open);
    });
    if (datePickerState.input) renderDatePicker();
    renderConfiguredBlocks(scope);
    applyRoutes(scope);
    updateAuthNav();
  }
  function renderConfiguredBlocks(root) {
    const scope = root || document;
    renderPaymentTags(scope);
    scope.querySelectorAll('[data-social-providers]').forEach(mount => {
      mount.innerHTML = C.socialProviders.map(provider => `
        <button type="button" class="f-social" data-provider="${escapeHTML(provider.id)}">${escapeHTML(t(provider.i18nKey))}</button>
      `).join('');
    });
  }
  function apiBaseUrl() {
    return (C.api && C.api.baseUrl) || 'http://127.0.0.1:8000/api';
  }
  function showToast(message, type) {
    if (type === 'err') B.audio?.play?.('error');
    let container = document.querySelector('.toasts');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toasts';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'toast' + (type ? ' ' + type : '');
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.transition = 'opacity .3s';
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }
  function ensureConfirmDialog() {
    let overlay = document.getElementById('siteConfirmOverlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'site-confirm-overlay';
    overlay.id = 'siteConfirmOverlay';
    overlay.innerHTML = `
      <div class="site-confirm" role="dialog" aria-modal="true" aria-labelledby="siteConfirmTitle">
        <p class="label" id="siteConfirmTitle"></p>
        <strong class="site-confirm-message" id="siteConfirmMessage"></strong>
        <div class="site-confirm-actions">
          <button class="btn btn-outline" type="button" data-site-confirm="cancel"></button>
          <button class="btn btn-primary" type="button" data-site-confirm="ok"></button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
  }
  function confirmDialog(options) {
    const overlay = ensureConfirmDialog();
    const title = overlay.querySelector('#siteConfirmTitle');
    const message = overlay.querySelector('#siteConfirmMessage');
    const cancel = overlay.querySelector('[data-site-confirm="cancel"]');
    const ok = overlay.querySelector('[data-site-confirm="ok"]');
    title.textContent = options.title || '';
    message.textContent = options.message || '';
    cancel.textContent = options.cancelLabel || t('confirm_cancel');
    ok.textContent = options.okLabel || t('nav_logout');
    overlay.classList.add('open');
    return new Promise(resolve => {
      let settled = false;
      const finish = value => {
        if (settled) return;
        settled = true;
        overlay.classList.remove('open');
        overlay.removeEventListener('click', onClick);
        document.removeEventListener('keydown', onKeydown);
        resolve(value);
      };
      const onClick = event => {
        if (event.target === overlay || event.target.closest('[data-site-confirm="cancel"]')) {
          finish(false);
          return;
        }
        if (event.target.closest('[data-site-confirm="ok"]')) {
          finish(true);
        }
      };
      const onKeydown = event => {
        if (event.key === 'Escape') finish(false);
      };
      overlay.addEventListener('click', onClick);
      document.addEventListener('keydown', onKeydown);
      window.setTimeout(() => ok.focus(), 20);
    });
  }
  function ensureApiStatusBanner() {
    let banner = document.getElementById('apiStatusBanner');
    if (banner) return banner;
    banner = document.createElement('div');
    banner.id = 'apiStatusBanner';
    banner.className = 'api-status-banner';
    banner.setAttribute('role', 'status');
    document.body.appendChild(banner);
    return banner;
  }
  function updateApiStatusBanner() {
    const status = readState().apiStatus || 'checking';
    const banner = ensureApiStatusBanner();
    banner.classList.toggle('show', status === 'offline');
    banner.innerHTML = `
      <strong>${escapeHTML(t('state_offline_title'))}</strong>
      <span>${escapeHTML(t('state_offline_text'))}</span>
      <button class="btn btn-outline btn-sm" type="button" data-api-retry>${escapeHTML(t('state_retry'))}</button>
    `;
  }
  function ensureGameRulesModal() {
    let overlay = document.getElementById('gameRulesOverlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'gameRulesOverlay';
    overlay.className = 'game-rules-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML = `
      <div class="game-rules-modal" role="dialog" aria-modal="true" aria-labelledby="gameRulesTitle">
        <div class="admin-section-head">
          <div>
            <p class="label">${escapeHTML(t('rules_label'))}</p>
            <h2 id="gameRulesTitle"></h2>
          </div>
          <button class="btn btn-outline btn-sm" type="button" data-game-rules-close>${escapeHTML(t('vip_clicker_close'))}</button>
        </div>
        <p class="game-rules-intro" id="gameRulesIntro"></p>
        <div class="game-rules-list" id="gameRulesList"></div>
      </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
  }
  function openGameRules(page) {
    const config = gameRulePages[page || document.body.dataset.page || ''];
    if (!config) return;
    const overlay = ensureGameRulesModal();
    overlay.dataset.gameRulesPage = page || document.body.dataset.page || '';
    overlay.querySelector('#gameRulesTitle').textContent = t(config.title);
    overlay.querySelector('#gameRulesIntro').textContent = t(config.intro);
    overlay.querySelector('#gameRulesList').innerHTML = config.rows.map(key => `
      <div class="game-rule-row">
        <span>${escapeHTML(t(key + '_label'))}</span>
        <p>${escapeHTML(t(key + '_text'))}</p>
      </div>
    `).join('');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.documentElement.classList.add('game-rules-locked');
    document.body.classList.add('game-rules-locked');
  }
  function closeGameRules() {
    const overlay = document.getElementById('gameRulesOverlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    document.documentElement.classList.remove('game-rules-locked');
    document.body.classList.remove('game-rules-locked');
  }
  function initGameRules() {
    const page = document.body.dataset.page || '';
    const config = gameRulePages[page];
    if (!config) return;
    const existing = document.getElementById('holdemRulesOpen');
    if (page === 'holdem' && existing && document.getElementById('holdemRulesOverlay')) return;
    if (existing) existing.setAttribute('data-game-rules-open', page);
    const panel = document.querySelector('.roulette-panel,.slot-panel,.crash-panel,.mines-panel,.blocks-panel,.plinko-panel,.survival-panel,.holdem-panel');
    if (panel && !panel.querySelector('[data-game-rules-open]')) {
      const button = document.createElement('button');
      button.className = 'btn btn-outline game-rules-open';
      button.type = 'button';
      button.setAttribute('data-game-rules-open', page);
      button.textContent = t('rules_button');
      panel.appendChild(button);
    }
    document.addEventListener('click', event => {
      const opener = event.target.closest('[data-game-rules-open]');
      if (opener) {
        event.preventDefault();
        event.stopImmediatePropagation();
        openGameRules(opener.dataset.gameRulesOpen || page);
        return;
      }
      if (event.target.closest('[data-game-rules-close]') || event.target.id === 'gameRulesOverlay') {
        closeGameRules();
      }
    }, true);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeGameRules();
    });
  }
  function initNavbar() {
    const nav = document.getElementById('navbar');
    if (nav && !document.getElementById('navBurger')) {
      const navInner = nav.querySelector('.nav-inner');
      const navActions = navInner?.querySelector('.nav-actions');
      if (navInner && navActions) {
        const burger = document.createElement('button');
        burger.className = 'nav-burger';
        burger.id = 'navBurger';
        burger.type = 'button';
        burger.setAttribute('aria-label', 'Menu');
        burger.setAttribute('aria-controls', 'mobNav');
        burger.setAttribute('aria-expanded', 'false');
        burger.innerHTML = '<span></span><span></span><span></span>';
        navInner.appendChild(burger);
        const mobileNav = document.createElement('div');
        mobileNav.className = 'mob-nav';
        mobileNav.id = 'mobNav';
        mobileNav.setAttribute('aria-hidden', 'true');
        mobileNav.innerHTML = `
          <div class="mob-nav-head">
            <a class="mob-nav-brand" href="${path('home')}">Bambi<span>ku</span></a>
            <button class="mob-nav-close" type="button" data-mobile-nav-close aria-label="Close">&times;</button>
          </div>
          <a href="${path('home')}#games" data-route="games">${t('nav_games')}</a>
          <a href="${path('home')}#bonuses" data-route="bonuses">${t('nav_bonuses')}</a>
          <a href="${path('home')}#vip" data-route="vip">${t('nav_vip')}</a>
          <div class="mob-nav-auth" data-mobile-auth-nav></div>
        `;
        nav.insertAdjacentElement('afterend', mobileNav);
      }
    }
    if (nav) {
      const onScroll = () => nav.classList.toggle('scrolled', global.scrollY > 38);
      global.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
    }
    const burger = document.getElementById('navBurger');
    const mob = document.getElementById('mobNav');
    if (burger && mob) {
      const setMobileOpen = open => {
        mob.classList.toggle('open', open);
        mob.setAttribute('aria-hidden', open ? 'false' : 'true');
        burger.setAttribute('aria-expanded', open ? 'true' : 'false');
        document.body.style.overflow = open ? 'hidden' : '';
      };
      burger.addEventListener('click', () => {
        setMobileOpen(!mob.classList.contains('open'));
      });
      mob.addEventListener('click', e => {
        if (e.target === mob || e.target.closest('a,button,[data-mobile-nav-close]')) {
          setMobileOpen(false);
        }
      });
      document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && mob.classList.contains('open')) setMobileOpen(false);
      });
    }
    document.addEventListener('click', e => {
      B.audio?.unlock?.();
      const audioToggle = e.target.closest('[data-audio-toggle]');
      if (audioToggle) {
        const muted = B.audio?.toggle?.();
        if (!muted) B.audio?.play?.('cashout');
        return;
      }
      if (e.target.closest('.chip-btn,[data-chip],[data-slot-bet],[data-crash-bet],[data-mines-bet],[data-blocks-bet],[data-plinko-bet],[data-survival-bet],[data-holdem-ante]')) {
        B.audio?.play?.('chip');
      } else if (e.target.closest('button,a')) {
        B.audio?.play?.('click');
      }
      const link = e.target.closest('[data-scroll-target]');
      if (!link) return;
      const target = document.querySelector(link.dataset.scrollTarget);
      if (target) target.scrollIntoView({ behavior: 'smooth' });
    });
  }
  function initScrollSpy() {
    const secs = document.querySelectorAll('section[id]');
    const links = document.querySelectorAll('.nav-links a, .mob-nav a');
    if (!secs.length || !links.length || !('IntersectionObserver' in global)) return;
    const obs = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          links.forEach(link => {
            link.classList.toggle('active', link.getAttribute('href') === '#' + entry.target.id);
          });
        }
      });
    }, { threshold: 0.35 });
    secs.forEach(sec => obs.observe(sec));
  }
  function initLanguageSwitcher() {
    document.addEventListener('click', e => {
      const btn = e.target.closest('.lang-btn[data-lang]');
      if (!btn) return;
      store.setLang(btn.dataset.lang);
    });
  }
  function cleanAuthQuery() {
    try {
      const url = new URL(location.href);
      url.searchParams.delete('auth');
      url.searchParams.delete('next');
      history.replaceState(null, '', url.toString());
    } catch (err) {
    }
  }
  function handleOAuthErrorQuery() {
    try {
      const url = new URL(location.href);
      const error = url.searchParams.get('auth_error');
      if (!error) return;
      url.searchParams.delete('auth_error');
      url.searchParams.delete('auth_reason');
      history.replaceState(null, '', url.toString());
      showToast(t(error), 'err');
    } catch (err) {
    }
  }
  function handleAuthQuery() {
    try {
      const url = new URL(location.href);
      const authTab = url.searchParams.get('auth');
      if (!['login', 'register'].includes(authTab)) return;
      const next = sameOriginPath(url.searchParams.get('next'));
      if (next) rememberAuthNext(next);
      cleanAuthQuery();
      if (hasCurrentUser()) {
        redirectAfterAuth();
      } else if (document.getElementById('modalOverlay')) {
        window.setTimeout(() => openModal(authTab), 0);
      }
    } catch (err) {
    }
  }
  function guardCurrentPage() {
    renderAuthGate();
  }
  function guardProtectedNavigation(event) {
    if (hasCurrentUser()) return;
    const game = event.target.closest('[data-game-url]');
    if (game && game.dataset.gameUrl) {
      event.preventDefault();
      event.stopImmediatePropagation();
      requireAuth(game.dataset.gameUrl);
      return;
    }
    const routeLink = event.target.closest('[data-route]');
    if (routeLink && protectedRoutes.has(routeLink.dataset.route)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      requireAuth(routeLink.getAttribute('href') || path(routeLink.dataset.route));
      return;
    }
    const link = event.target.closest('a[href]');
    if (link && shouldProtectHref(link.getAttribute('href'))) {
      event.preventDefault();
      event.stopImmediatePropagation();
      requireAuth(link.getAttribute('href'));
    }
  }
  function initAuthGuard() {
    guardCurrentPage();
    handleOAuthErrorQuery();
    handleAuthQuery();
    if (hasCurrentUser()) redirectAfterAuth();
    document.addEventListener('click', guardProtectedNavigation, true);
  }
  function redirectAfterAuth() {
    const next = consumeAuthNext();
    if (!next || next === currentPath()) return false;
    location.href = next;
    return true;
  }
  function updateAuthNav() {
    const user = readState().currentUser;
    document.querySelectorAll('[data-footer-auth-link]').forEach(link => {
      link.hidden = Boolean(user);
    });
    const mounts = document.querySelectorAll('[data-auth-nav]');
    const mobileMounts = document.querySelectorAll('[data-mobile-auth-nav]');
    if (!mounts.length && !mobileMounts.length) return;
    const hasModal = Boolean(document.getElementById('modalOverlay'));
    mounts.forEach(mount => {
      if (user) {
        mount.innerHTML = `
          <a href="${path('deposit')}" class="btn btn-ghost btn-sm nav-balance">${formatMoney(user.balance, user.currency)}</a>
          <a href="${path('profile')}" class="btn btn-outline btn-sm nav-user-link">${escapeHTML(user.name.split(' ')[0] || user.email)}</a>
          <button class="btn btn-ghost btn-sm" data-auth-action="logout">${t('nav_logout')}</button>
        `;
      } else if (hasModal) {
        mount.innerHTML = `
          <button class="btn btn-ghost" data-modal="login">${t('nav_signin')}</button>
          <button class="btn btn-primary btn-sm" data-modal="register">${t('nav_join')}</button>
        `;
      } else {
        mount.innerHTML = `
          <a href="${path('profile')}" class="btn btn-outline btn-sm" data-route="profile">${t('nav_profile')}</a>
          <a href="${path('home')}" class="btn btn-outline btn-sm" data-route="home">${t('nav_home')}</a>
        `;
      }
    });
    mobileMounts.forEach(mount => {
      if (user) {
        mount.innerHTML = `
          <a href="${path('profile')}" data-route="profile">${t('nav_profile')}</a>
          <a href="${path('deposit')}" data-route="deposit">${t('nav_deposit')}</a>
          <button class="mob-nav-logout" type="button" data-auth-action="logout">${t('nav_logout')}</button>
        `;
      } else if (hasModal) {
        mount.innerHTML = `
          <button class="btn btn-outline" type="button" data-modal="login">${t('nav_signin')}</button>
          <button class="btn btn-primary" type="button" data-modal="register">${t('nav_join')}</button>
        `;
      } else {
        mount.innerHTML = '';
      }
    });
  }
  function initModal() {
    const overlay = document.getElementById('modalOverlay');
    if (!overlay) return;
    document.addEventListener('click', e => {
      const opener = e.target.closest('[data-modal]');
      if (opener) {
        if (opener.tagName === 'A') e.preventDefault();
        openModal(opener.dataset.modal || 'login', opener);
      }
      const closer = e.target.closest('[data-modal-close]');
      if (closer) closeModal();
    });
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeModal();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeModal();
      if (e.key === 'Tab' && overlay.classList.contains('open')) {
        const focusable = overlay.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });
    document.querySelectorAll('.m-tab').forEach(tab => {
      tab.addEventListener('click', () => switchModalTab(tab.dataset.tab));
    });
  }
  function openModal(tab, opener) {
    const overlay = document.getElementById('modalOverlay');
    if (!overlay) return;
    lastModalOpener = opener || document.activeElement;
    switchModalTab(tab || 'login');
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
    const initial = overlay.querySelector('#registerFormWrap:not([hidden]) input, #loginFormWrap:not([hidden]) input, [data-modal-close]');
    if (initial) initial.focus();
  }
  function closeModal() {
    const overlay = document.getElementById('modalOverlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    document.body.style.overflow = '';
    if (lastModalOpener && typeof lastModalOpener.focus === 'function') lastModalOpener.focus();
  }
  function switchModalTab(tab) {
    const nextTab = tab === 'register' ? 'register' : 'login';
    const authModal = document.querySelector('#modalOverlay .auth-modal');
    if (authModal) authModal.classList.toggle('is-register', nextTab === 'register');
    document.querySelectorAll('.m-tab').forEach(item => {
      const active = item.dataset.tab === nextTab;
      item.classList.toggle('active', active);
      item.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    const login = document.getElementById('loginFormWrap');
    const register = document.getElementById('registerFormWrap');
    if (login) login.hidden = nextTab !== 'login';
    if (register) register.hidden = nextTab !== 'register';
    const sub = document.getElementById('modalSub');
    if (sub) sub.textContent = t(nextTab === 'login' ? 'modal_sub_login' : 'modal_sub_register');
  }
  function initCookieBanner() {
    const banner = document.getElementById('cookieBanner');
    if (!banner) return;
    let hasChoice = false;
    try {
      hasChoice = Boolean(localStorage.getItem(C.storage.cookie));
    } catch (err) {
      hasChoice = true;
    }
    if (!hasChoice) {
      setTimeout(() => banner.classList.add('show'), 900);
    }
    banner.addEventListener('click', e => {
      const btn = e.target.closest('[data-cookie-choice]');
      if (!btn) return;
      try {
        localStorage.setItem(C.storage.cookie, btn.dataset.cookieChoice);
      } catch (err) {
      }
      banner.style.transition = 'opacity .3s';
      banner.style.opacity = '0';
      setTimeout(() => banner.remove(), 300);
    });
  }
  function initReveal() {
    if (!('IntersectionObserver' in global)) {
      document.querySelectorAll('.reveal').forEach(el => el.classList.add('on'));
      return;
    }
    const obs = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('on');
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
  }
  function initHelp() {
    const container = document.getElementById('faq-container');
    if (!container) return;
    let activeCategory = 'all';
    const render = () => {
      const lang = readState().lang;
      const q = (document.getElementById('faq-search')?.value || '').trim().toLowerCase();
      const categories = activeCategory === 'all' ? Object.keys(C.faq) : [activeCategory];
      let total = 0;
      const html = categories.map(cat => {
        const items = (C.faq[cat] || []).filter(item => {
          if (!q) return true;
          return (item['q_' + lang] + ' ' + item['a_' + lang]).toLowerCase().includes(q);
        });
        if (!items.length) return '';
        total += items.length;
        return `
          <div class="faq-section">
            <div class="faq-section-title">${escapeHTML(t('help_' + cat))}</div>
            ${items.map((item, idx) => `
              <div class="faq-item">
                <button class="faq-q" type="button" data-faq-toggle aria-expanded="false" aria-controls="faq-answer-${cat}-${idx}">
                  ${escapeHTML(item['q_' + lang])}
                  <span class="faq-arrow">v</span>
                </button>
                <div class="faq-a" id="faq-answer-${cat}-${idx}">${escapeHTML(item['a_' + lang])}</div>
              </div>
            `).join('')}
          </div>
        `;
      }).join('');
      container.innerHTML = total ? html : `<div class="no-results"><div class="no-results-icon">?</div><p>${t('help_no_results')}</p></div>`;
    };
    document.querySelectorAll('.help-cat').forEach(btn => {
      btn.addEventListener('click', () => {
        activeCategory = btn.dataset.cat || 'all';
        document.querySelectorAll('.help-cat').forEach(item => {
          const active = item === btn;
          item.classList.toggle('active', active);
          item.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        const search = document.getElementById('faq-search');
        if (search) search.value = '';
        render();
      });
    });
    document.getElementById('faq-search')?.addEventListener('input', render);
    document.getElementById('btn-search')?.addEventListener('click', render);
    container.addEventListener('click', e => {
      const toggle = e.target.closest('[data-faq-toggle]');
      if (!toggle) return;
      const answer = toggle.nextElementSibling;
      const open = answer.classList.contains('open');
      container.querySelectorAll('.faq-a.open').forEach(el => el.classList.remove('open'));
      container.querySelectorAll('.faq-q.open').forEach(el => {
        el.classList.remove('open');
        el.setAttribute('aria-expanded', 'false');
      });
      if (!open) {
        answer.classList.add('open');
        toggle.classList.add('open');
        toggle.setAttribute('aria-expanded', 'true');
      }
    });
    store.subscribe(render);
    render();
  }
  function initCommon() {
    initNavbar();
    initAudioToggle();
    initScrollSpy();
    initLanguageSwitcher();
    initModal();
    initDatePickers();
    initAuthGuard();
    initGameRules();
    initCookieBanner();
    initReveal();
    store.startApiStatusPolling?.(30000);
    document.addEventListener('click', async e => {
      const retry = e.target.closest('[data-api-retry]');
      if (retry) {
        retry.disabled = true;
        await store.checkApiHealth?.();
        retry.disabled = false;
        return;
      }
      const logout = e.target.closest('[data-auth-action="logout"]');
      if (!logout) return;
      const confirmed = await confirmDialog({
        title: t('confirm_logout_title'),
        message: t('confirm_logout_message'),
        cancelLabel: t('confirm_cancel'),
        okLabel: t('nav_logout')
      });
      if (!confirmed) return;
      store.logout();
      showToast(t('toast_logout'));
    });
    document.addEventListener('click', e => {
      const provider = e.target.closest('[data-provider]');
      if (!provider) return;
      if (provider.dataset.provider === 'google') {
        location.href = apiBaseUrl() + '/auth/google/login';
        return;
      }
      if (provider.dataset.provider === 'telegram') {
        location.href = apiBaseUrl() + '/auth/telegram/login';
        return;
      }
      showToast(t('err_api_unavailable'), 'err');
    });
    store.subscribe((next, prev, action) => {
      if (next.lang !== prev.lang) {
        applyLang();
        updateAuthNav();
        renderAuthGate();
        updateApiStatusBanner();
        return;
      }
      const balanceChanged = Number(next.balance || 0) !== Number(prev.balance || 0);
      const currentUserChanged = (next.currentUser && next.currentUser.id) !== (prev.currentUser && prev.currentUser.id);
      if (
        balanceChanged ||
        currentUserChanged ||
        String(action || '').startsWith('auth:') ||
        String(action || '').startsWith('user:') ||
        String(action || '').startsWith('demo:') ||
        String(action || '').startsWith('cashier:') ||
        String(action || '').startsWith('game:') ||
        String(action || '').startsWith('wallet:') ||
        String(action || '').startsWith('transactions:')
      ) {
        updateAuthNav();
        renderAuthGate();
      }
      if (next.apiStatus !== prev.apiStatus || action === 'api:status') {
        updateApiStatusBanner();
      }
    });
    applyLang();
    renderAuthGate();
    updateApiStatusBanner();
  }
  B.ui = {
    path,
    t,
    escapeHTML,
    formatNumber,
    formatMoney,
    methodLabel,
    setText,
    setValue,
    renderPaymentTags,
    applyLang,
    renderState,
    tableStateRow,
    renderGameHistory,
    showToast,
    confirmAction: confirmDialog,
    openModal,
    closeModal,
    redirectAfterAuth,
    requireAuth,
    requireAuthGate: renderAuthGate,
    initCommon,
    initHelp
  };
})(window);
