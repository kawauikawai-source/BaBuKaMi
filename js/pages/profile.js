(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;
  const store = B.store;
  const ui = B.ui;
  const HISTORY_PAGE_SIZE = 15;
  let initialized = false;
  let historyFilter = 'all';
  let historyGameFilter = 'all';
  let historyVisible = HISTORY_PAGE_SIZE;
  let studioBalanceCents = 0;
  let studioBalanceLoading = false;
  let studioBalanceLoadedFor = '';
  let studioBalanceRequestId = 0;
  let managerOpen = false;
  let managerLoading = false;
  let managerState = null;
  let managerMessages = [];

  async function loadStudioBalance() {
    const state = store.getState();
    const user = store.currentUser();
    const userKey = String(user && (user.apiId || user.id || user.email) || '');
    if (!userKey || state.apiStatus !== 'online' || studioBalanceLoading || studioBalanceLoadedFor === userKey) return;
    studioBalanceLoading = true;
    const requestId = ++studioBalanceRequestId;
    try {
      const result = await store.getStudioWallet();
      if (!result || result.error) return;
      const current = store.currentUser();
      const currentKey = String(current && (current.apiId || current.id || current.email) || '');
      if (requestId !== studioBalanceRequestId || currentKey !== userKey) return;
      studioBalanceCents = Number(result.wallet?.balance_cents || 0);
      studioBalanceLoadedFor = userKey;
      render();
    } catch (err) {
      // The global API status already communicates temporary backend failures.
    } finally {
      if (requestId === studioBalanceRequestId) studioBalanceLoading = false;
    }
  }

  function splitName(name) {
    const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    return { first: parts.shift() || '', last: parts.join(' ') };
  }

  function nextTierFor(tier) {
    return C.vipTiers.find(item => item.level === tier.level + 1) || null;
  }

  function tierKey(tier) {
    return String(tier && tier.name ? tier.name : tier || 'bronze').toLowerCase();
  }

  function tierPrice(next) {
    const prices = { silver: 10, gold: 25, platinum: 50 };
    return prices[tierKey(next)] || 0;
  }

  function tierRange(tier) {
    return ui.formatNumber(tier.min) + (tier.max === Infinity ? '+' : '-' + ui.formatNumber(tier.max));
  }

  function vipProgress(user) {
    const current = B.getVipTier(user.vipTier || 'bronze');
    const next = nextTierFor(current);
    const points = Math.max(0, Number(user.vipPoints) || 0);
    if (!next || current.max === Infinity) {
      return { current, next: null, points, progress: 100, missing: 0, canBuy: false };
    }
    const cap = Number(current.max);
    const floor = Number(current.min);
    const clamped = Math.max(floor, Math.min(points, cap));
    const span = Math.max(1, cap - floor);
    return {
      current,
      next,
      points,
      progress: Math.max(0, Math.min(100, ((clamped - floor) / span) * 100)),
      missing: Math.max(0, cap - points),
      canBuy: points >= cap
    };
  }

  function txClass(type) {
    return type === 'withdraw' || type === 'vip' ? 'tx-withdraw' : type === 'win' || type === 'game' ? 'tx-win' : 'tx-deposit';
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString(store.getState().lang === 'ru' ? 'ru-RU' : 'en-US', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function txTitle(item) {
    if (item.titleKey) {
      if (item.titleKey === 'tx_roulette_title') return ui.t('tx_roulette_title');
      if (item.titleKey === 'tx_vip_tier_purchase') return ui.t('tx_vip_tier_purchase', { tier: item.title || 'VIP' });
      if (item.type === 'game') return ui.t(item.titleKey);
      const kind = item.type === 'withdraw' ? 'withdraw' : 'deposit';
      const method = item.methodId ? store.cashierMethod(kind, item.methodId) : null;
      return ui.t(item.titleKey, { method: ui.methodLabel(method) });
    }
    return item.title || ui.t('tx_' + item.type);
  }

  function isGameTransaction(item) {
    return item.type === 'game' || item.type === 'win';
  }

  function isPromoTransaction(item) {
    return item.type === 'deposit' && String(item.methodId || '').toLowerCase() === 'promo';
  }

  function historyMatches(item, filter) {
    if (filter === 'games') return isGameTransaction(item);
    if (filter === 'deposits') return item.type === 'deposit' && !isPromoTransaction(item);
    if (filter === 'withdrawals') return item.type === 'withdraw';
    if (filter === 'promos') return isPromoTransaction(item);
    if (filter === 'vip') return item.type === 'vip';
    return true;
  }

  function gameTransactionKey(item) {
    return String(item.methodId || item.titleKey || item.title || 'game');
  }

  function statusLabel(status) {
    const value = String(status || 'completed').toLowerCase();
    const key = 'profile_history_status_' + value;
    const translated = ui.t(key);
    if (translated !== key) return translated;
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  function historyFilterLabel(filter) {
    return ui.t('profile_history_' + filter);
  }

  function renderHistoryTabs(history) {
    const counts = {
      all: history.length,
      games: history.filter(item => historyMatches(item, 'games')).length,
      deposits: history.filter(item => historyMatches(item, 'deposits')).length,
      withdrawals: history.filter(item => historyMatches(item, 'withdrawals')).length,
      promos: history.filter(item => historyMatches(item, 'promos')).length,
      vip: history.filter(item => historyMatches(item, 'vip')).length
    };
    Object.keys(counts).forEach(key => ui.setText('profile-history-count-' + key, ui.formatNumber(counts[key])));
    document.querySelectorAll('[data-history-filter]').forEach(button => {
      const active = button.dataset.historyFilter === historyFilter;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
  }

  function renderGameFilter(history) {
    const wrap = document.getElementById('profileHistoryGameFilterWrap');
    const select = document.getElementById('profileHistoryGameFilter');
    if (!wrap || !select) return;
    wrap.hidden = historyFilter !== 'games';
    if (historyFilter !== 'games') return;
    const games = new Map();
    history.filter(isGameTransaction).forEach(item => {
      const key = gameTransactionKey(item);
      if (!games.has(key)) games.set(key, txTitle(item));
    });
    if (historyGameFilter !== 'all' && !games.has(historyGameFilter)) historyGameFilter = 'all';
    select.innerHTML = `<option value="all">${ui.escapeHTML(ui.t('profile_history_all_games'))}</option>` +
      Array.from(games.entries()).map(([key, label]) => `<option value="${ui.escapeHTML(key)}">${ui.escapeHTML(label)}</option>`).join('');
    select.value = historyGameFilter;
  }

  function renderHistory(user) {
    const body = document.getElementById('historyRows');
    if (!body) return;
    const history = user.history || [];
    renderHistoryTabs(history);
    renderGameFilter(history);
    let filtered = history.filter(item => historyMatches(item, historyFilter));
    if (historyFilter === 'games' && historyGameFilter !== 'all') {
      filtered = filtered.filter(item => gameTransactionKey(item) === historyGameFilter);
    }
    ui.setText('profile-history-title', historyFilterLabel(historyFilter));
    ui.setText('profile-history-meta', ui.t('profile_history_found', { count: ui.formatNumber(filtered.length) }));
    if (!filtered.length) {
      body.innerHTML = `<tr><td class="empty-cell" colspan="5">${ui.t('profile_no_history_filter')}</td></tr>`;
      const more = document.getElementById('profileHistoryMore');
      if (more) more.hidden = true;
      return;
    }
    body.innerHTML = filtered.slice(0, historyVisible).map(item => `
      <tr>
        <td>${formatDate(item.createdAt || item.date)}</td>
        <td><span class="tx-type ${txClass(item.type)}">${ui.t('tx_' + item.type)}</span></td>
        <td>${ui.escapeHTML(txTitle(item))}</td>
        <td><span class="profile-history-status is-${ui.escapeHTML(String(item.status || 'completed').toLowerCase())}">${ui.escapeHTML(statusLabel(item.status))}</span></td>
        <td class="${Number(item.amount) >= 0 ? 'amount-pos' : 'amount-neg'}">${ui.formatMoney(item.amount, user.currency)}</td>
      </tr>
    `).join('');
    const more = document.getElementById('profileHistoryMore');
    if (more) more.hidden = historyVisible >= filtered.length;
  }

  function renderVipUpgrade(user) {
    const vip = vipProgress(user);
    const tier = vip.current;
    const next = vip.next;
    const currentTierKey = tierKey(tier);
    const vipPanel = document.querySelector('.overview-vip-panel');
    if (vipPanel) vipPanel.dataset.vipTier = currentTierKey;
    const currentTierMark = document.getElementById('profileCurrentTierMark');
    if (currentTierMark) currentTierMark.textContent = tier.icon;
    const currentTierName = document.getElementById('profileCurrentTierName');
    if (currentTierName) currentTierName.textContent = tier.name;
    const currentPerkCard = document.getElementById('profileCurrentPerkCard');
    if (currentPerkCard) currentPerkCard.hidden = false;
    const vipBar = document.getElementById('vip-bar');
    if (vipBar) vipBar.style.width = vip.progress + '%';

    const progressLabel = document.getElementById('profile-vip-progress-label');
    if (progressLabel) progressLabel.textContent = next ? ui.t('profile_progress_to', { tier: next.name }) : ui.t('profile_max_vip');
    const hint = document.getElementById('profile-vip-hint');
    if (hint) hint.textContent = next ? ui.t('profile_points_to_next', { points: ui.formatNumber(vip.missing) }) : ui.t('profile_max_vip');
    const purchase = document.getElementById('profile-vip-purchase');
    if (purchase) {
      purchase.hidden = !(next && vip.canBuy);
      purchase.dataset.vipPurchase = next ? tierKey(next) : '';
      purchase.textContent = next ? ui.t('vip_buy_tier', { tier: next.name, price: ui.formatMoney(tierPrice(next), user.currency) }) : '';
    }

    const tiers = document.getElementById('profileVipTiers');
    if (tiers) {
      tiers.innerHTML = C.vipTiers.map(item => `
        <div class="vip-tier-mini vip-tier-${tierKey(item)} ${item.name === tier.name ? 'current' : ''} ${next && item.name === next.name && vip.canBuy ? 'unlockable' : ''} ${item.level > tier.level && (!next || item.name !== next.name || !vip.canBuy) ? 'locked' : ''}">
          <div class="vip-tier-mini-icon">${ui.escapeHTML(item.icon)}</div>
          <div class="vip-tier-mini-name vip-tier-text-${item.name.toLowerCase()}">${ui.escapeHTML(item.name)}</div>
          <div class="vip-tier-mini-pts">${ui.formatNumber(item.min)}${item.max === Infinity ? '+' : '-' + ui.formatNumber(item.max)}</div>
        </div>
      `).join('');
    }

    const perks = document.getElementById('profileCurrentPerks');
    if (perks) {
      const lang = store.getState().lang;
      const vipData = (store.getState().data.games.vip_tiers || C.fallbackGames.vip_tiers).find(item => item.name === tier.name);
      const items = vipData ? (vipData['perks_' + lang] || vipData.perks_en || []) : [];
      perks.innerHTML = items.map(perk => `<li>${ui.escapeHTML(perk)}</li>`).join('');
    }
    const managerAccess = document.getElementById('profileManagerAccess');
    if (managerAccess) managerAccess.hidden = tier.level < 2;
    if (tier.level < 2 && managerOpen) setManagerOpen(false);
  }

  function renderSecurity(user) {
    const list = document.getElementById('securityRows');
    if (!list) return;
    const security = user.security || {};
    const kycStatus = security.kycStatus || 'not_started';
    const passwordDate = user.passwordChangedAt ? formatDate(user.passwordChangedAt) : ui.t('status_not_started');
    const rows = [
      {
        label: ui.t('profile_password'),
        meta: ui.t('profile_password_updated', { date: passwordDate }),
        status: '',
        statusClass: ''
      },
      {
        label: ui.t('profile_2fa'),
        meta: ui.t('profile_authenticator'),
        status: ui.t(security.twoFactor ? 'status_enabled' : 'status_disabled'),
        statusClass: security.twoFactor ? 'status-ok' : 'status-warn'
      },
      {
        label: ui.t('profile_email_verify'),
        meta: user.email,
        status: ui.t(security.emailVerified ? 'status_verified' : 'status_unverified'),
        statusClass: security.emailVerified ? 'status-ok' : 'status-warn'
      },
      {
        label: ui.t('profile_kyc'),
        meta: ui.t(kycStatus === 'pending' ? 'profile_kyc_pending_meta' : 'profile_kyc_meta'),
        status: ui.t(kycStatus === 'verified' ? 'status_verified' : kycStatus === 'pending' ? 'status_pending' : 'status_not_started'),
        statusClass: kycStatus === 'verified' ? 'status-ok' : 'status-warn',
        action: kycStatus === 'verified' ? '' : 'kyc',
        actionLabel: ui.t(kycStatus === 'pending' ? 'profile_kyc_retry' : 'profile_kyc_start')
      },
      {
        label: ui.t('nav_logout'),
        meta: ui.t('confirm_logout_message'),
        status: '',
        statusClass: '',
        action: 'logout',
        actionLabel: ui.t('nav_logout')
      },
      {
        label: ui.t('profile_logout_all'),
        meta: ui.t('profile_logout_all_meta'),
        status: '',
        statusClass: '',
        action: 'logout-all',
        actionLabel: ui.t('profile_logout_all_action')
      }
    ];
    list.innerHTML = rows.map(row => `
      <div class="security-row">
        <div>
          <strong>${ui.escapeHTML(row.label)}</strong>
          ${row.meta ? `<span>${ui.escapeHTML(row.meta)}</span>` : ''}
        </div>
        <div class="security-row-actions">
          ${row.status ? `<span class="${row.statusClass}">${ui.escapeHTML(row.status)}</span>` : ''}
          ${row.action === 'kyc' ? `<button class="btn btn-outline btn-sm security-action" type="button" data-kyc-open>${ui.escapeHTML(row.actionLabel)}</button>` : ''}
          ${row.action === 'logout' ? `<button class="btn btn-outline btn-sm security-action" type="button" data-profile-logout>${ui.escapeHTML(row.actionLabel)}</button>` : ''}
          ${row.action === 'logout-all' ? `<button class="btn btn-outline btn-sm security-action" type="button" data-logout-all>${ui.escapeHTML(row.actionLabel)}</button>` : ''}
        </div>
      </div>
    `).join('');
  }

  function renderProfileCompletion(user) {
    const completion = Math.max(0, Math.min(100, Number(user.profileCompletion) || 0));
    const missing = Array.isArray(user.profileMissingFields) ? user.profileMissingFields : [];
    ui.setText('profileCompletionValue', completion + '%');
    const bar = document.getElementById('profileCompletionBar');
    if (bar) bar.style.width = completion + '%';
    const text = document.getElementById('profileCompletionText');
    if (text) text.textContent = missing.length ? ui.t('profile_completion_safe') : ui.t('profile_completion_complete');
    const list = document.getElementById('profileCompletionMissing');
    if (list) {
      list.innerHTML = missing.map(key => `<span>${ui.escapeHTML(ui.t('profile_missing_' + key))}</span>`).join('');
      list.hidden = !missing.length;
    }
    document.getElementById('profileCompletion')?.classList.toggle('is-complete', completion === 100);
  }

  function setKycModalOpen(open) {
    const overlay = document.getElementById('kycOverlay');
    if (!overlay) return;
    overlay.hidden = !open;
    overlay.classList.toggle('open', open);
    overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (open) {
      const qr = overlay.querySelector('img[data-src]');
      if (qr && !qr.getAttribute('src')) qr.src = qr.dataset.src;
      const checkbox = document.getElementById('kyc-scan-check');
      if (checkbox) checkbox.checked = false;
      syncKycContinue();
      window.setTimeout(() => document.getElementById('kyc-scan-check')?.focus(), 30);
    }
  }

  function syncKycContinue() {
    const checkbox = document.getElementById('kyc-scan-check');
    const button = document.getElementById('kyc-continue');
    if (button) button.disabled = !checkbox?.checked;
  }

  function confirmKycScan() {
    const checkbox = document.getElementById('kyc-scan-check');
    if (!checkbox?.checked) {
      ui.showToast(ui.t('profile_kyc_scan_required'), 'err');
      return;
    }
    store.updateKycStatus('pending');
    setKycModalOpen(false);
    ui.showToast(ui.t('toast_kyc_started'));
  }

  async function logoutAllSessions() {
    const confirmed = await ui.confirmAction({
      title: ui.t('confirm_logout_all_title'),
      message: ui.t('confirm_logout_all_message'),
      cancelLabel: ui.t('confirm_cancel'),
      okLabel: ui.t('profile_logout_all_action')
    });
    if (!confirmed) return;
    const result = await store.logoutAll();
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    ui.showToast(ui.t('toast_logout_all'));
    location.href = '../index.html';
  }

  async function logoutCurrentSession() {
    const confirmed = await ui.confirmAction({
      title: ui.t('confirm_logout_title'),
      message: ui.t('confirm_logout_message'),
      cancelLabel: ui.t('confirm_cancel'),
      okLabel: ui.t('nav_logout')
    });
    if (!confirmed) return;
    store.logout();
    ui.showToast(ui.t('toast_logout'));
    location.href = '../index.html';
  }

  function render() {
    const user = store.getDisplayUser();
    const name = {
      first: user.firstName || splitName(user.name).first,
      last: user.lastName || splitName(user.name).last
    };
    const tier = B.getVipTier(user.vipTier || 'bronze');

    ui.setText('profile-name-display', user.name);
    ui.setText('profile-email-display', user.email);
    ui.setText('profile-vip-display', tier.name + ' VIP');
    ui.setText('profile-avatar-badge', tier.name);
    ui.setText('profile-balance-val', ui.formatMoney(user.balance, user.currency));
    ui.setText('stat-balance-proxy', ui.formatMoney(user.balance, user.currency));
    ui.setText('stat-games-played', ui.formatNumber(user.gamesPlayed));
    ui.setText('stat-total-won', ui.formatMoney(user.totalWon, user.currency));
    ui.setText('stat-vip-points', ui.formatNumber(user.vipPoints));
    ui.setText('stat-studio-balance', ui.formatMoney(studioBalanceCents / 100, 'EUR'));
    const adminLink = document.getElementById('profile-admin-link');
    if (adminLink) {
      adminLink.hidden = !user.isAdmin;
      adminLink.classList.toggle('is-visible', Boolean(user.isAdmin));
    }

    ui.setValue('inp-fname', name.first);
    ui.setValue('inp-lname', name.last);
    ui.setValue('inp-email', user.email);
    ui.setValue('inp-phone', user.phone);
    ui.setValue('inp-dob', user.dob);
    ui.setValue('inp-country', user.country);
    ui.setValue('inp-currency', user.currency);

    renderHistory(user);
    renderVipUpgrade(user);
    renderSecurity(user);
    renderProfileCompletion(user);
  }

  function initTabs() {
    const buttons = Array.from(document.querySelectorAll('.profile-nav-btn'));
    const sections = Array.from(document.querySelectorAll('.profile-section'));
    buttons.forEach(btn => {
      const sectionId = 'section-' + btn.dataset.section;
      btn.setAttribute('aria-controls', sectionId);
      btn.setAttribute('aria-selected', btn.classList.contains('active') ? 'true' : 'false');
    });
    sections.forEach(section => {
      section.hidden = !section.classList.contains('active');
    });
    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        buttons.forEach(item => {
          item.classList.remove('active');
          item.setAttribute('aria-selected', 'false');
        });
        sections.forEach(item => {
          item.classList.remove('active');
          item.hidden = true;
        });
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        const section = document.getElementById('section-' + btn.dataset.section);
        if (section) {
          section.classList.add('active');
          section.hidden = false;
        }
        if (btn.dataset.section === 'history' && store.getState().apiStatus === 'online' && store.refreshTransactions) {
          store.refreshTransactions('transactions:profile').catch(() => {
            ui.showToast(ui.t('state_error_text'), 'err');
          });
        }
      });
    });
  }

  function showError(id, key) {
    const error = document.getElementById(id);
    if (!error) return;
    error.textContent = key ? ui.t(key) : '';
    error.classList.toggle('visible', Boolean(key));
  }

  function setInputError(id, hasError) {
    const input = document.getElementById(id);
    if (!input) return;
    input.classList.toggle('error', Boolean(hasError));
    input.setAttribute('aria-invalid', hasError ? 'true' : 'false');
    if (id === 'inp-fname') input.setAttribute('aria-describedby', 'inp-name-err');
    if (id === 'inp-email') input.setAttribute('aria-describedby', 'inp-email-err');
  }

  function clearPersonalErrors() {
    ['inp-fname', 'inp-email'].forEach(id => setInputError(id, false));
    ['inp-name-err', 'inp-email-err'].forEach(id => showError(id, ''));
  }

  async function savePersonal() {
    clearPersonalErrors();
    const first = document.getElementById('inp-fname')?.value.trim() || '';
    const last = document.getElementById('inp-lname')?.value.trim() || '';
    const email = document.getElementById('inp-email')?.value.trim() || '';
    const result = await store.updateProfile({
      name: (first + ' ' + last).trim(),
      firstName: first,
      lastName: last,
      email,
      phone: document.getElementById('inp-phone')?.value.trim() || '',
      dob: document.getElementById('inp-dob')?.value || '',
      country: document.getElementById('inp-country')?.value.trim() || '',
      currency: document.getElementById('inp-currency')?.value || 'EUR'
    });

    if (result.error) {
      const isName = result.error === 'err_name_empty';
      const isEmail = result.error.startsWith('err_email') || result.error === 'err_profile_email_exists';
      if (isName) {
        setInputError('inp-fname', true);
        showError('inp-name-err', result.error);
      }
      if (isEmail) {
        setInputError('inp-email', true);
        showError('inp-email-err', result.error);
      }
      ui.showToast(ui.t(result.error), 'err');
      return;
    }

    ui.showToast(ui.t('toast_profile_saved'));
  }

  async function purchaseVip(event) {
    const button = event.target.closest('[data-vip-purchase]');
    if (!button) return;
    const tier = button.dataset.vipPurchase;
    if (!tier) return;
    button.disabled = true;
    const result = await store.purchaseVipTier(tier);
    button.disabled = false;
    if (result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    if (store.refreshTransactions) await store.refreshTransactions('transactions:vip');
    ui.showToast(ui.t('vip_purchase_success', { tier: B.getVipTier(tier).name }));
  }

  function managerLang() {
    return store.getState().lang === 'en' ? 'en' : 'ru';
  }

  function managerGameName(gameId) {
    const names = {
      'dragons-fortune': 'Kawaui Fortune',
      'lucky-bamboo': 'Lucky Bamboo',
      'solar-wilds': 'Eclipse Hunt',
      'neon-pyramids': 'Neon Pyramids',
      'midnight-vault': 'Midnight Vault',
      'texas-holdem': "Texas Hold'em",
      'arctic-protocol': 'Arctic Protocol',
      roulette: 'European Roulette'
    };
    return names[gameId] || gameId;
  }

  function renderManagerSummary() {
    const root = document.getElementById('managerSummary');
    if (!root) return;
    if (!managerState) {
      root.innerHTML = `<div><span>${ui.escapeHTML(ui.t('state_loading_title'))}</span><strong>...</strong></div>`;
      return;
    }
    root.innerHTML = [
      [ui.t('manager_summary_clearance'), String(managerState.vip_tier || '').toUpperCase()],
      [ui.t('manager_summary_limit'), ui.formatMoney(Number(managerState.max_bet_cents || 0) / 100)],
      [ui.t('manager_summary_presets'), `${(managerState.bet_presets || []).length} / ${managerState.max_games || 0}`],
      [ui.t('manager_summary_tickets'), String(managerState.open_tickets || 0)]
    ].map(item => `<div><span>${ui.escapeHTML(item[0])}</span><strong>${ui.escapeHTML(item[1])}</strong></div>`).join('');
  }

  function renderManagerMessages() {
    const root = document.getElementById('managerMessages');
    if (!root) return;
    if (managerLoading && !managerMessages.length) {
      root.innerHTML = `<div class="manager-message"><div><small>OPERATOR 08</small><p>${ui.escapeHTML(ui.t('state_loading_title'))}</p></div></div>`;
      return;
    }
    if (!managerMessages.length) {
      root.innerHTML = `<div class="manager-message"><div><small>OPERATOR 08</small><p>${ui.escapeHTML(ui.t('manager_welcome'))}</p></div></div>`;
      return;
    }
    root.innerHTML = managerMessages.map(message => {
      const role = String(message.role || 'operator');
      const metadata = message.metadata || {};
      const action = metadata.action;
      const canConfirm = action && action.status === 'pending';
      return `<article class="manager-message is-${ui.escapeHTML(role)}"><div>
        <small>${ui.escapeHTML(role === 'user' ? ui.t('manager_you') : role === 'admin' ? ui.t('manager_management') : 'OPERATOR 08')}</small>
        <p>${ui.escapeHTML(message.text || '')}</p>
        ${canConfirm ? `<div class="manager-message-action"><button type="button" data-manager-confirm="${ui.escapeHTML(action.id)}">${ui.escapeHTML(ui.t('manager_confirm'))}</button></div>` : ''}
      </div></article>`;
    }).join('');
    root.scrollTop = root.scrollHeight;
  }

  function renderManagerWorkbench(intent) {
    const root = document.getElementById('managerWorkbench');
    if (!root) return;
    root.hidden = false;
    if (intent === 'bets') {
      const options = ['dragons-fortune', 'lucky-bamboo', 'solar-wilds', 'neon-pyramids', 'midnight-vault', 'texas-holdem', 'arctic-protocol', 'roulette'];
      root.innerHTML = `<form class="manager-bet-form" data-manager-form="bet">
        <select name="game_id" aria-label="${ui.escapeHTML(ui.t('manager_game'))}">${options.map(id => `<option value="${id}">${ui.escapeHTML(managerGameName(id))}</option>`).join('')}</select>
        <input name="amount" type="number" min="105" step="5" placeholder="105" aria-label="${ui.escapeHTML(ui.t('manager_amount'))}"/>
        <button class="btn btn-primary" type="submit">${ui.escapeHTML(ui.t('manager_prepare'))}</button>
      </form>`;
      return;
    }
    if (intent === 'control') {
      root.innerHTML = `<div class="manager-control-grid">
        <button class="btn btn-outline" type="button" data-manager-command="pause" data-duration="15">${ui.escapeHTML(ui.t('manager_pause_15'))}</button>
        <button class="btn btn-outline" type="button" data-manager-command="pause" data-duration="60">${ui.escapeHTML(ui.t('manager_pause_60'))}</button>
        <button class="btn btn-outline" type="button" data-manager-command="reminder" data-duration="30">${ui.escapeHTML(ui.t('manager_reminder_30'))}</button>
      </div>
      <form class="manager-limit-form" data-manager-form="limit">
        <label for="managerDailyLimit">${ui.escapeHTML(ui.t('manager_daily_limit'))}</label>
        <div>
          <span>€</span>
          <input id="managerDailyLimit" name="amount" type="number" min="5" step="5" placeholder="100" required />
          <button class="btn btn-primary" type="submit">${ui.escapeHTML(ui.t('manager_prepare'))}</button>
        </div>
      </form>`;
      return;
    }
    root.hidden = true;
    root.innerHTML = '';
  }

  async function loadManager() {
    if (managerLoading) return;
    managerLoading = true;
    renderManagerMessages();
    const [stateResult, messagesResult] = await Promise.all([store.getManagerState(), store.getManagerMessages()]);
    managerLoading = false;
    if (stateResult.error || messagesResult.error) {
      ui.showToast(ui.t(stateResult.error || messagesResult.error), 'err');
      renderManagerMessages();
      return;
    }
    managerState = stateResult;
    managerMessages = Array.isArray(messagesResult) ? messagesResult : [];
    renderManagerSummary();
    renderManagerMessages();
  }

  async function sendManager(text, intent, payload) {
    if (!String(text || '').trim()) return;
    const send = document.getElementById('managerSend');
    if (send) send.disabled = true;
    const result = await store.sendManagerMessage(text, intent, payload, managerLang());
    if (send) send.disabled = false;
    if (result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    const operator = Object.assign({}, result.operator_message || {});
    if (result.action) {
      operator.metadata = Object.assign({}, operator.metadata || {}, { action: result.action });
    }
    managerMessages.push(result.user_message, operator);
    const input = document.getElementById('managerInput');
    if (input) {
      input.value = '';
      input.style.height = '';
    }
    renderManagerMessages();
    if (result.ticket || result.action) {
      managerState = await store.getManagerState();
      renderManagerSummary();
    }
  }

  async function confirmManagerAction(actionId, button) {
    if (button) button.disabled = true;
    const result = await store.confirmManagerAction(actionId);
    if (result.error) {
      if (button) button.disabled = false;
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    managerState = result.state;
    managerMessages.push(result.operator_message);
    managerMessages.forEach(message => {
      if (message.metadata?.action?.id === Number(actionId)) message.metadata.action.status = 'completed';
    });
    renderManagerSummary();
    renderManagerMessages();
  }

  function setManagerOpen(open) {
    managerOpen = Boolean(open);
    const terminal = document.getElementById('managerTerminal');
    if (terminal) terminal.hidden = !managerOpen;
    if (managerOpen) {
      terminal?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      loadManager();
    }
  }

  function resizeManagerInput(input) {
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = `${Math.min(Math.max(input.scrollHeight, 88), 180)}px`;
  }

  function init() {
    if (document.body.dataset.page !== 'profile' || initialized) return;
    initialized = true;
    initTabs();
    document.getElementById('btn-save-personal')?.addEventListener('click', savePersonal);
    document.getElementById('profileManagerButton')?.addEventListener('click', () => setManagerOpen(true));
    document.getElementById('managerClose')?.addEventListener('click', () => setManagerOpen(false));
    document.getElementById('managerComposer')?.addEventListener('submit', event => {
      event.preventDefault();
      sendManager(document.getElementById('managerInput')?.value, null, {});
    });
    const managerInput = document.getElementById('managerInput');
    managerInput?.addEventListener('input', () => resizeManagerInput(managerInput));
    managerInput?.addEventListener('keydown', event => {
      if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      document.getElementById('managerComposer')?.requestSubmit();
    });
    document.getElementById('managerTerminal')?.addEventListener('click', event => {
      const quick = event.target.closest('[data-manager-intent]');
      if (quick) {
        const intent = quick.dataset.managerIntent;
        document.querySelectorAll('[data-manager-intent]').forEach(item => item.classList.toggle('active', item === quick));
        if (intent === 'bets' || intent === 'control') renderManagerWorkbench(intent);
        else {
          renderManagerWorkbench('');
          sendManager(ui.t('manager_quick_' + intent), intent, {});
        }
      }
      const confirm = event.target.closest('[data-manager-confirm]');
      if (confirm) confirmManagerAction(confirm.dataset.managerConfirm, confirm);
      const command = event.target.closest('[data-manager-command]');
      if (command?.dataset.managerCommand === 'pause') sendManager(ui.t('manager_pause_request'), 'control', { kind: 'pause', duration_minutes: Number(command.dataset.duration) });
      if (command?.dataset.managerCommand === 'reminder') sendManager(ui.t('manager_reminder_request'), 'control', { kind: 'reminder', reminder_minutes: Number(command.dataset.duration) });
    });
    document.getElementById('managerWorkbench')?.addEventListener('submit', event => {
      const form = event.target.closest('[data-manager-form]');
      if (!form) return;
      event.preventDefault();
      const data = new FormData(form);
      const amount = Number(data.get('amount'));
      if (!Number.isFinite(amount) || amount <= 0) return;
      if (form.dataset.managerForm === 'limit') {
        sendManager(ui.t('manager_limit_request', { amount: amount.toFixed(2) }), 'control', {
          kind: 'daily_limit',
          daily_bet_limit_cents: Math.round(amount * 100)
        });
        return;
      }
      const gameId = String(data.get('game_id') || '');
      sendManager(`${managerGameName(gameId)} €${amount}`, 'set_bet', { game_id: gameId, amount_cents: Math.round(amount * 100) });
    });
    document.getElementById('section-overview')?.addEventListener('click', purchaseVip);
    document.getElementById('profileHistoryTabs')?.addEventListener('click', event => {
      const button = event.target.closest('[data-history-filter]');
      if (!button) return;
      historyFilter = button.dataset.historyFilter || 'all';
      historyGameFilter = 'all';
      historyVisible = HISTORY_PAGE_SIZE;
      renderHistory(store.getDisplayUser());
    });
    document.getElementById('profileHistoryGameFilter')?.addEventListener('change', event => {
      historyGameFilter = event.target.value || 'all';
      historyVisible = HISTORY_PAGE_SIZE;
      renderHistory(store.getDisplayUser());
    });
    document.getElementById('profileHistoryMore')?.addEventListener('click', () => {
      historyVisible += HISTORY_PAGE_SIZE;
      renderHistory(store.getDisplayUser());
    });
    document.getElementById('inp-email')?.addEventListener('input', clearPersonalErrors);
    document.getElementById('inp-fname')?.addEventListener('input', clearPersonalErrors);
    document.getElementById('securityRows')?.addEventListener('click', event => {
      if (event.target.closest('[data-kyc-open]')) setKycModalOpen(true);
      if (event.target.closest('[data-profile-logout]')) logoutCurrentSession();
      if (event.target.closest('[data-logout-all]')) logoutAllSessions();
    });
    document.getElementById('kycOverlay')?.addEventListener('click', event => {
      if (event.target === event.currentTarget || event.target.closest('[data-kyc-close]')) setKycModalOpen(false);
    });
    document.getElementById('kyc-scan-check')?.addEventListener('change', syncKycContinue);
    document.getElementById('kyc-continue')?.addEventListener('click', confirmKycScan);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && document.getElementById('kycOverlay')?.classList.contains('open')) setKycModalOpen(false);
    });
    store.subscribe((next, prev) => {
      const nextUser = next.currentUser || {};
      const prevUser = prev.currentUser || {};
      const nextKey = String(nextUser.apiId || nextUser.id || nextUser.email || '');
      const prevKey = String(prevUser.apiId || prevUser.id || prevUser.email || '');
      if (nextKey !== prevKey) {
        studioBalanceRequestId += 1;
        studioBalanceLoading = false;
        studioBalanceLoadedFor = '';
        studioBalanceCents = 0;
      }
      render();
      loadStudioBalance();
    });
    render();
    loadStudioBalance();
  }

  B.profile = { init };
})(window);
