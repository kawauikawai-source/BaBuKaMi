(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;
  const store = B.store;
  const ui = B.ui;
  const HISTORY_PAGE_SIZE = 15;
  let historyFilter = 'all';
  let historyGameFilter = 'all';
  let historyVisible = HISTORY_PAGE_SIZE;

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
        <div class="vip-tier-mini ${item.name === tier.name ? 'current' : ''} ${next && item.name === next.name && vip.canBuy ? 'unlockable' : ''} ${item.level > tier.level && (!next || item.name !== next.name || !vip.canBuy) ? 'locked' : ''}">
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

  function init() {
    if (document.body.dataset.page !== 'profile') return;
    initTabs();
    document.getElementById('btn-save-personal')?.addEventListener('click', savePersonal);
    document.getElementById('profileManagerButton')?.addEventListener('click', () => {
      ui.showToast(ui.t('profile_manager_coming_soon'));
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
    store.subscribe(render);
    render();
  }

  B.profile = { init };
})(window);
