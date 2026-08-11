(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  let activeStatus = 'pending';
  let activePromoStatus = 'active';
  let activeSupportStatus = 'open';
  let activeTab = 'overview';
  let activeUserPanel = 'profile';
  let selectedUser = null;
  let selectedPromo = null;
  let selectedSupportTicket = null;
  let usersPageIndex = 0;
  let withdrawalsLoading = false;
  let usersLoading = false;
  let overviewLoading = false;
  let auditLoading = false;
  let promosLoading = false;
  let supportLoading = false;
  let userSearchTimer = 0;
  let auditSearchTimer = 0;
  let lastUsers = [];
  let lastWithdrawals = [];
  const PAGE_SIZE = 20;
  const COMPACT_PAGE_SIZE = 15;
  const HISTORY_PAGE_SIZE = 5;
  const paging = {
    users: { offset: 0, hasMore: false, items: [] },
    withdrawals: { offset: 0, hasMore: false, items: [] },
    promos: { offset: 0, hasMore: false, items: [] },
    audit: { offset: 0, hasMore: false, items: [] },
    transactions: { offset: 0, hasMore: false, items: [] },
    rounds: { offset: 0, hasMore: false, items: [] },
    promoRedemptions: { offset: 0, hasMore: false, items: [] },
    promoDetailRedemptions: { offset: 0, hasMore: false, items: [] },
    support: { offset: 0, hasMore: false, items: [] }
  };
  const calendarLabels = {
    ru: {
      months: ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'],
      weekdays: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    },
    en: {
      months: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
      weekdays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    }
  };

  function statusClass(status) {
    if (status === 'completed') return 'ok';
    if (status === 'active') return 'ok';
    if (status === 'rejected') return 'bad';
    if (status === 'expired' || status === 'inactive') return 'bad';
    if (status === 'scheduled') return 'pending';
    return 'pending';
  }

  function statusLabel(status) {
    const value = String(status || '').toLowerCase();
    if (value === 'completed') return ui.t('admin_status_completed');
    if (value === 'rejected') return ui.t('admin_status_rejected');
    if (value === 'active') return ui.t('admin_tx_status_active');
    if (value === 'lost') return ui.t('admin_tx_status_lost');
    if (value === 'pending') return ui.t('admin_status_pending');
    return value ? titleCaseValue(value) : '-';
  }

  function transactionStatusLabel(status) {
    const value = String(status || '').toLowerCase();
    if (value === 'completed') return ui.t('admin_tx_status_completed');
    if (value === 'rejected') return ui.t('admin_tx_status_rejected');
    if (value === 'pending') return ui.t('admin_tx_status_pending');
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : '-';
  }

  function transactionTypeLabel(type) {
    const value = String(type || '').toLowerCase();
    if (value === 'deposit') return ui.t('tx_deposit');
    if (value === 'withdraw') return ui.t('tx_withdraw');
    if (value === 'game') return ui.t('tx_game');
    if (value === 'win') return ui.t('tx_win');
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : '-';
  }

  function promoStatusLabel(status) {
    const value = String(status || '').toLowerCase();
    if (value === 'active') return ui.t('admin_status_active');
    if (value === 'inactive') return ui.t('admin_status_inactive');
    if (value === 'expired') return ui.t('admin_status_expired');
    if (value === 'scheduled') return ui.t('admin_status_scheduled');
    return value ? titleCaseValue(value) : '-';
  }

  function numberValue(id) {
    const value = Number(document.getElementById(id)?.value || 0);
    return Number.isFinite(value) ? value : 0;
  }

  function centsToMoney(cents) {
    return ui.formatMoney(Number(cents || 0) / 100);
  }

  function renderPromoPreview(prefix) {
    const base = prefix || 'adminPromo';
    const mount = document.getElementById(base === 'adminPromoEdit' ? 'adminPromoEditPreview' : 'adminPromoPreview');
    if (!mount) return;
    const rewardType = document.getElementById(base + 'RewardType')?.value || 'fixed';
    if (rewardType === 'percent') {
      const percent = numberValue(base + 'Percent');
      const maxBonus = numberValue(base + 'MaxBonus');
      const minDeposit = numberValue(base + 'MinDeposit');
      const sampleDeposit = minDeposit || 20;
      const bonus = Math.min(sampleDeposit * (percent / 100), maxBonus || Infinity);
      mount.textContent = percent && maxBonus
        ? ui.t('admin_promo_preview_percent', {
          percent: ui.formatNumber(percent),
          deposit: ui.formatMoney(sampleDeposit),
          bonus: ui.formatMoney(bonus),
          max: ui.formatMoney(maxBonus)
        })
        : ui.t('admin_promo_preview_empty');
      return;
    }
    const amount = numberValue(base + 'Amount');
    mount.textContent = amount
      ? ui.t('admin_promo_preview_fixed', { amount: ui.formatMoney(amount) })
      : ui.t('admin_promo_preview_empty');
  }

  function dateTimeValue(id) {
    const input = document.getElementById(id);
    const value = input?.dataset.value || input?.value || '';
    return value ? new Date(value + 'T00:00:00').toISOString() : null;
  }

  function syncPromoRewardFields(prefix) {
    const base = prefix || 'adminPromo';
    const editMode = base === 'adminPromoEdit';
    const rewardType = document.getElementById(base + 'RewardType')?.value || 'fixed';
    const percentMode = rewardType === 'percent';
    document.querySelectorAll(editMode ? '[data-promo-edit-percent]' : '[data-promo-percent]').forEach(el => {
      el.hidden = !percentMode;
      el.querySelectorAll('input').forEach(input => {
        input.disabled = !percentMode;
      });
    });
    const amountInput = document.getElementById(base + 'Amount');
    if (amountInput) {
      amountInput.disabled = percentMode;
      amountInput.closest('div').hidden = percentMode;
    }
    renderPromoPreview(base);
  }

  function titleCaseValue(value) {
    return String(value || '')
      .split(/([\s_-]+)/)
      .map(part => /^[\s_-]+$/.test(part) ? part : part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join('');
  }

  function formatDate(value) {
    if (!value) return '';
    try {
      return new Intl.DateTimeFormat(store.getState().lang === 'ru' ? 'ru-RU' : 'en-US', {
        dateStyle: 'medium',
        timeStyle: 'short'
      }).format(new Date(value));
    } catch (err) {
      return String(value);
    }
  }

  function padDatePart(value) {
    return String(value).padStart(2, '0');
  }

  function dateToIso(date) {
    return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;
  }

  function parseIsoDate(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    if (
      date.getFullYear() !== Number(match[1]) ||
      date.getMonth() !== Number(match[2]) - 1 ||
      date.getDate() !== Number(match[3])
    ) {
      return null;
    }
    return date;
  }

  function formatDateInput(value) {
    const date = parseIsoDate(value);
    if (!date) return '';
    const locale = store.getState().lang === 'ru' ? 'ru-RU' : 'en-US';
    return new Intl.DateTimeFormat(locale, { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
  }

  function getDateValue(id) {
    const input = document.getElementById(id);
    return input?.dataset.value || '';
  }

  function getAuditDateValue(id) {
    return getDateValue(id);
  }

  function closeCalendars(exceptField) {
    document.querySelectorAll('.admin-date-field.is-open').forEach(field => {
      if (field !== exceptField) field.classList.remove('is-open');
    });
  }

  function setDateInput(input, isoDate) {
    if (!input) return;
    input.dataset.value = isoDate || '';
    input.value = formatDateInput(isoDate);
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function renderCalendar(field) {
    const input = field?.querySelector('[data-admin-date]');
    const calendar = field?.querySelector('.admin-calendar');
    if (!input || !calendar) return;
    const selected = parseIsoDate(input.dataset.value);
    const today = new Date();
    const viewYear = Number(input.dataset.viewYear || (selected ? selected.getFullYear() : today.getFullYear()));
    const viewMonth = Number(input.dataset.viewMonth || (selected ? selected.getMonth() : today.getMonth()));
    input.dataset.viewYear = String(viewYear);
    input.dataset.viewMonth = String(viewMonth);

    const lang = store.getState().lang === 'ru' ? 'ru' : 'en';
    const labels = calendarLabels[lang];
    const firstDay = new Date(viewYear, viewMonth, 1);
    const startOffset = (firstDay.getDay() + 6) % 7;
    const gridStart = new Date(viewYear, viewMonth, 1 - startOffset);
    const selectedIso = input.dataset.value || '';
    const todayIso = dateToIso(today);
    const cells = [];
    for (let index = 0; index < 42; index += 1) {
      const cellDate = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
      const iso = dateToIso(cellDate);
      const muted = cellDate.getMonth() !== viewMonth ? ' is-muted' : '';
      const active = iso === selectedIso ? ' is-selected' : '';
      const current = iso === todayIso ? ' is-today' : '';
      cells.push(`<button class="admin-calendar-day${muted}${active}${current}" type="button" data-admin-date-value="${iso}">${cellDate.getDate()}</button>`);
    }

    calendar.innerHTML = `
      <div class="admin-calendar-head">
        <button class="admin-calendar-nav" type="button" data-admin-date-action="prev" aria-label="Previous month"></button>
        <strong>${ui.escapeHTML(labels.months[viewMonth])} ${viewYear}</strong>
        <button class="admin-calendar-nav next" type="button" data-admin-date-action="next" aria-label="Next month"></button>
      </div>
      <div class="admin-calendar-week">${labels.weekdays.map(day => `<span>${ui.escapeHTML(day)}</span>`).join('')}</div>
      <div class="admin-calendar-grid">${cells.join('')}</div>
      <button class="admin-calendar-clear" type="button" data-admin-date-action="clear">${ui.t('admin_calendar_clear')}</button>
    `;
  }

  function openCalendar(field) {
    const input = field?.querySelector('[data-admin-date]');
    const selected = parseIsoDate(input?.dataset.value);
    const today = new Date();
    if (input && !input.dataset.viewYear) {
      input.dataset.viewYear = String(selected ? selected.getFullYear() : today.getFullYear());
      input.dataset.viewMonth = String(selected ? selected.getMonth() : today.getMonth());
    }
    closeCalendars(field);
    renderCalendar(field);
    field?.classList.add('is-open');
  }

  function moveCalendarMonth(input, delta) {
    const today = new Date();
    const year = Number(input.dataset.viewYear || today.getFullYear());
    const month = Number(input.dataset.viewMonth || today.getMonth());
    const next = new Date(year, month + delta, 1);
    input.dataset.viewYear = String(next.getFullYear());
    input.dataset.viewMonth = String(next.getMonth());
  }

  function handleCalendarClick(event, field) {
    const input = field.querySelector('[data-admin-date]');
    const action = event.target.closest('[data-admin-date-action]');
    const day = event.target.closest('[data-admin-date-value]');
    if (action) {
      event.preventDefault();
      if (action.dataset.adminDateAction === 'clear') {
        setDateInput(input, '');
        field.classList.remove('is-open');
        return;
      }
      moveCalendarMonth(input, action.dataset.adminDateAction === 'next' ? 1 : -1);
      renderCalendar(field);
      return;
    }
    if (day) {
      event.preventDefault();
      setDateInput(input, day.dataset.adminDateValue);
      field.classList.remove('is-open');
      return;
    }
    if (event.target.closest('[data-admin-date], [data-admin-date-toggle]')) {
      event.preventDefault();
      if (field.classList.contains('is-open')) {
        field.classList.remove('is-open');
      } else {
        openCalendar(field);
      }
    }
  }

  function setupDateInputs() {
    document.querySelectorAll('.admin-date-field').forEach(field => {
      if (!field.querySelector('.admin-calendar')) {
        const calendar = document.createElement('div');
        calendar.className = 'admin-calendar';
        field.appendChild(calendar);
      }
      const input = field.querySelector('[data-admin-date]');
      if (input) input.value = formatDateInput(input.dataset.value);
    });
  }

  function syncDateInputs() {
    document.querySelectorAll('[data-admin-date]').forEach(input => {
      input.value = formatDateInput(input.dataset.value);
    });
    document.querySelectorAll('.admin-date-field.is-open').forEach(renderCalendar);
  }

  function renderSelectedUser() {
    const label = document.getElementById('adminSelectedUser');
    if (!label) return;
    label.textContent = selectedUser
      ? `${selectedUser.name || selectedUser.email} - ${ui.formatMoney(selectedUser.balance, selectedUser.currency)}`
      : ui.t('admin_no_user_selected');
  }

  function switchUserPanel(nextPanel) {
    activeUserPanel = nextPanel || 'profile';
    document.querySelectorAll('[data-admin-user-tab]').forEach(button => {
      const active = button.dataset.adminUserTab === activeUserPanel;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.querySelectorAll('[data-admin-user-panel]').forEach(panel => {
      const active = panel.dataset.adminUserPanel === activeUserPanel;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
  }

  function ensureConfirmModal() {
    let overlay = document.getElementById('adminConfirmOverlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'admin-confirm-overlay';
    overlay.id = 'adminConfirmOverlay';
    overlay.innerHTML = `
      <div class="admin-confirm" role="dialog" aria-modal="true" aria-labelledby="adminConfirmTitle">
        <p class="label" id="adminConfirmTitle"></p>
        <strong class="admin-confirm-message" id="adminConfirmMessage"></strong>
        <div class="admin-confirm-actions">
          <button class="btn btn-outline" type="button" data-admin-confirm="cancel"></button>
          <button class="btn btn-primary" type="button" data-admin-confirm="ok"></button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
  }

  function confirmAction(message, confirmLabel, tone) {
    const overlay = ensureConfirmModal();
    const title = overlay.querySelector('#adminConfirmTitle');
    const body = overlay.querySelector('#adminConfirmMessage');
    const cancel = overlay.querySelector('[data-admin-confirm="cancel"]');
    const ok = overlay.querySelector('[data-admin-confirm="ok"]');
    title.textContent = ui.t('admin_confirm_title');
    body.textContent = message;
    cancel.textContent = ui.t('admin_confirm_cancel');
    ok.textContent = confirmLabel;
    ok.classList.toggle('is-danger', tone === 'danger');
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
        if (event.target === overlay || event.target.closest('[data-admin-confirm="cancel"]')) {
          finish(false);
          return;
        }
        if (event.target.closest('[data-admin-confirm="ok"]')) {
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

  function renderOverview(users, withdrawals) {
    const list = Array.isArray(withdrawals) ? withdrawals : [];
    ui.setText('adminOverviewUsers', ui.formatNumber((users || []).length));
    ui.setText('adminOverviewPending', ui.formatNumber(list.filter(item => item.transaction?.status === 'pending').length));
    ui.setText('adminOverviewCompleted', ui.formatNumber(list.filter(item => item.transaction?.status === 'completed').length));
    ui.setText('adminOverviewRejected', ui.formatNumber(list.filter(item => item.transaction?.status === 'rejected').length));
  }

  function emptyRow(colspan, key) {
    return ui.tableStateRow ? ui.tableStateRow(colspan, 'empty', { text: ui.t(key || 'admin_empty') }) : `<tr><td colspan="${colspan}" class="admin-empty">${ui.t(key || 'admin_empty')}</td></tr>`;
  }

  function updateLoadMore(kind, loading) {
    const button = document.querySelector(`[data-admin-load-more="${kind}"]`);
    const state = paging[kind];
    if (!button || !state) return;
    button.hidden = !state.hasMore;
    button.disabled = Boolean(loading);
    button.textContent = ui.t(loading ? 'admin_loading' : 'admin_show_more');
  }

  function updateUserPager(loading) {
    const prev = document.getElementById('adminUsersPrev');
    const next = document.getElementById('adminUsersNext');
    const label = document.getElementById('adminUsersPage');
    const state = paging.users;
    if (prev) prev.disabled = Boolean(loading) || usersPageIndex <= 0;
    if (next) next.disabled = Boolean(loading) || !state.hasMore;
    if (label) label.textContent = ui.t('admin_page_number', { page: usersPageIndex + 1 });
  }

  function resetPage(kind) {
    if (!paging[kind]) return;
    if (kind === 'users') usersPageIndex = 0;
    paging[kind].offset = 0;
    paging[kind].hasMore = false;
    paging[kind].items = [];
    updateLoadMore(kind, false);
    if (kind === 'users') updateUserPager(false);
  }

  function resetAllPages() {
    Object.keys(paging).forEach(resetPage);
  }

  function setPageResult(kind, items, append) {
    const state = paging[kind];
    if (!state) return Array.isArray(items) ? items : [];
    const list = Array.isArray(items) ? items : [];
    state.items = append ? state.items.concat(list) : list;
    state.offset = state.items.length;
    state.hasMore = list.length === pageSize(kind);
    updateLoadMore(kind, false);
    return state.items;
  }

  function pageSize(kind) {
    if (kind === 'users') return COMPACT_PAGE_SIZE;
    if (kind === 'transactions' || kind === 'rounds' || kind === 'promoRedemptions' || kind === 'promoDetailRedemptions') return HISTORY_PAGE_SIZE;
    return PAGE_SIZE;
  }

  function switchTab(nextTab) {
    activeTab = nextTab || 'overview';
    document.querySelectorAll('[data-admin-tab]').forEach(button => {
      const active = button.dataset.adminTab === activeTab;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.querySelectorAll('[data-admin-panel]').forEach(panel => {
      const active = panel.dataset.adminPanel === activeTab;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
    refreshActiveTab();
  }

  function withdrawalRowHtml(item) {
    const tx = item.transaction || {};
    const user = item.user || {};
    const amount = tx.amount !== undefined ? tx.amount : Number(tx.amount_cents || 0) / 100;
    const pending = tx.status === 'pending';
    const userLabel = user.name || user.email || ('#' + user.id);
    const method = String(tx.method_id || '-').toUpperCase();
    return `
      <article class="admin-withdrawal-card ${pending ? 'is-pending' : ''}">
        <div class="admin-card-main">
          <span class="profile-balance-label">${ui.t('admin_user')}</span>
          <strong>${ui.escapeHTML(userLabel)}</strong>
          <small>${ui.escapeHTML(user.email || '')}</small>
        </div>
        <div class="admin-card-metric">
          <span>${ui.t('admin_amount')}</span>
          <strong>${ui.formatMoney(Math.abs(Number(amount || 0)), tx.currency || user.currency)}</strong>
          ${Number(tx.payout_cents || 0) > 0 ? `<small>${ui.t('cashier_payout_amount')}: ${ui.formatMoney(Number(tx.payout_cents) / 100, tx.currency || user.currency)}</small>` : ''}
        </div>
        <div class="admin-card-metric">
          <span>${ui.t('admin_method')}</span>
          <strong>${ui.escapeHTML(method)}</strong>
        </div>
        <div class="admin-card-metric">
          <span>${ui.t('admin_created')}</span>
          <strong>${ui.escapeHTML(formatDate(tx.created_at))}</strong>
        </div>
        <div class="admin-card-status">
          <span class="admin-pill ${statusClass(tx.status)}">${ui.escapeHTML(statusLabel(tx.status))}</span>
        </div>
        <div class="admin-card-actions">
          ${pending ? `
            <button class="btn btn-primary btn-sm" type="button" data-admin-action="approve" data-withdrawal-id="${ui.escapeHTML(tx.id)}">${ui.t('admin_approve')}</button>
            <button class="btn btn-outline btn-sm" type="button" data-admin-action="reject" data-withdrawal-id="${ui.escapeHTML(tx.id)}">${ui.t('admin_reject')}</button>
          ` : `<span class="admin-muted-note">#${ui.escapeHTML(tx.id || '-')}</span>`}
        </div>
      </article>
    `;
  }

  function promoRewardLabel(promo) {
    if (promo.reward_type === 'percent') {
      const percent = Number(promo.percent !== undefined ? promo.percent : Number(promo.percent_bps || 0) / 100);
      const maxBonus = Number(promo.max_bonus !== undefined ? promo.max_bonus : Number(promo.max_bonus_cents || 0) / 100);
      const minDeposit = Number(promo.min_deposit !== undefined ? promo.min_deposit : Number(promo.min_deposit_cents || 0) / 100);
      return `${ui.formatNumber(percent)}% · max ${ui.formatMoney(maxBonus)} · min ${ui.formatMoney(minDeposit)}`;
    }
    const amount = Number(promo.amount !== undefined ? promo.amount : Number(promo.amount_cents || 0) / 100);
    return ui.formatMoney(amount);
  }

  function promoRowHtml(promo) {
    const active = promo.status === 'active' && promo.is_active;
    const selected = selectedPromo && String(selectedPromo.id) === String(promo.id);
    return `
      <tr class="${selected ? 'is-selected' : ''}" data-admin-promo-id="${ui.escapeHTML(promo.id)}">
        <td>
          <strong>${ui.escapeHTML(promo.code || '')}</strong>
          <span>${ui.escapeHTML(promo.title || '')}</span>
        </td>
        <td>${ui.escapeHTML(promoRewardLabel(promo))}</td>
        <td><span class="admin-pill ${statusClass(promo.status)}">${ui.escapeHTML(promoStatusLabel(promo.status))}</span></td>
        <td>${ui.escapeHTML(ui.formatNumber(promo.used_count || 0))} / ${ui.escapeHTML(ui.formatNumber(promo.usage_limit || 0))}</td>
        <td>
          <button class="btn btn-outline btn-sm" type="button" data-admin-promo-edit="${ui.escapeHTML(promo.id)}">${ui.t('admin_promo_edit')}</button>
          ${active ? `<button class="btn btn-outline btn-sm" type="button" data-admin-promo-disable="${ui.escapeHTML(promo.id)}">${ui.t('admin_promo_disable')}</button>` : ''}
        </td>
      </tr>
    `;
  }

  function userRowHtml(user) {
    const isSelected = selectedUser && selectedUser.id === user.id;
    return `
      <button class="admin-user-card ${isSelected ? 'active' : ''}" type="button" data-admin-user-id="${ui.escapeHTML(user.id)}">
        <span class="admin-user-card-main">
          <strong>${ui.escapeHTML(user.name || user.email || ('#' + user.id))}</strong>
          <span>${ui.escapeHTML(user.email || '')}</span>
        </span>
        <span class="admin-user-card-side">
          <strong>${ui.formatMoney(user.balance, user.currency)}</strong>
          <span>${ui.escapeHTML(titleCaseValue(user.vip_tier || 'bronze'))}</span>
        </span>
      </button>
    `;
  }

  function txRowHtml(tx) {
    const amount = tx.amount !== undefined ? Number(tx.amount) : Number(tx.amount_cents || 0) / 100;
    return `
      <tr>
        <td>${ui.escapeHTML(formatDate(tx.created_at))}</td>
        <td><span class="admin-type-pill">${ui.escapeHTML(transactionTypeLabel(tx.type))}</span></td>
        <td><span class="admin-pill ${statusClass(tx.status)}">${ui.escapeHTML(transactionStatusLabel(tx.status))}</span></td>
        <td class="${amount >= 0 ? 'amount-pos' : 'amount-neg'}">${ui.formatMoney(amount, tx.currency)}</td>
      </tr>
    `;
  }

  function roundRowHtml(round) {
    const net = round.net !== undefined ? Number(round.net) : Number(round.net_cents || 0) / 100;
    const result = round.result || {};
    const winningLines = Array.isArray(result.winning_lines) ? result.winning_lines.length : 0;
    let resultLabel = `${round.result_number == null ? '-' : round.result_number} ${round.result_color || ''}`.trim();
    if (round.game_id === 'lucky-bamboo') {
      resultLabel = `${ui.t('slot_round_summary')}: ${winningLines}`;
    } else if (round.game_id === 'solar-wilds') {
      const summary = result.summary || {};
      const opened = summary.opened !== undefined ? summary.opened : (Array.isArray(result.revealed_cells) ? result.revealed_cells.length : 0);
      resultLabel = summary.status === 'lost'
        ? `${ui.t('mines_round_summary')}: ${opened} opened, lost`
        : `${ui.t('mines_round_summary')}: ${opened} opened, ${summary.multiplier || '-'}x`;
    } else if (round.game_id === 'dragons-fortune') {
      const summary = result.summary || {};
      resultLabel = summary.status === 'cashed_out'
        ? `Cashed out at ${summary.cashout_multiplier || '-'}x`
        : `Crashed at ${summary.crash_multiplier || '-'}x`;
    } else if (round.game_id === 'neon-pyramids') {
      const summary = result.summary || {};
      const difficulty = summary.difficulty ? `, ${summary.difficulty}` : '';
      resultLabel = `${ui.t('blocks_round_summary')}: ${summary.lines || 0} lines, ${summary.multiplier || '-'}x, score ${summary.score || 0}${difficulty}`;
    } else if (round.game_id === 'midnight-vault') {
      const summary = result.summary || {};
      const balls = summary.balls || result.ball_count || 1;
      const best = summary.best_multiplier_cents ? `${(Number(summary.best_multiplier_cents) / 100).toFixed(2)}x` : '-';
      resultLabel = `${ui.t('plinko_round_summary')}: ${balls} balls, ${summary.risk || '-'}, best ${best}`;
    } else if (round.game_id === 'arctic-protocol') {
      const summary = result.summary || {};
      const survived = Number(summary.survived_stages ?? result.stage_index ?? 0);
      const category = summary.category_label || summary.category || result.category || '-';
      resultLabel = `${ui.t('survival_round_summary')}: ${category}, ${survived}/6`;
    } else if (round.game_id === 'arctic-cash') {
      const summary = result.summary || {};
      const multiplier = summary.multiplier_cents !== undefined
        ? `${(Number(summary.multiplier_cents) / 100).toFixed(2)}x`
        : '0.00x';
      resultLabel = `${ui.t('pusher_round_summary')}: ${multiplier}, ${summary.mode || 'classic'}`;
    }
    return `
      <tr>
        <td>${ui.escapeHTML(formatDate(round.created_at))}</td>
        <td>${ui.escapeHTML(round.game_id || '')}</td>
        <td><span class="admin-pill ${statusClass(round.status)}">${ui.escapeHTML(statusLabel(round.status))}</span></td>
        <td>${ui.escapeHTML(resultLabel)}</td>
        <td class="${net >= 0 ? 'amount-pos' : 'amount-neg'}">${ui.formatMoney(net)}</td>
      </tr>
    `;
  }

  function auditRowHtml(item) {
    const amount = item.amount !== null && item.amount !== undefined
      ? Number(item.amount)
      : item.amount_cents !== null && item.amount_cents !== undefined ? Number(item.amount_cents) / 100 : null;
    const before = item.before_balance_cents !== null && item.before_balance_cents !== undefined ? Number(item.before_balance_cents) / 100 : null;
    const after = item.after_balance_cents !== null && item.after_balance_cents !== undefined ? Number(item.after_balance_cents) / 100 : null;
    const metadata = item.metadata || {};
    const chips = ['transaction_id', 'round_id', 'method_id', 'game_id']
      .filter(key => metadata[key] !== undefined && metadata[key] !== null && metadata[key] !== '')
      .map(key => `<span>${ui.escapeHTML(titleCaseValue(key.replace(/_/g, ' ')))}: ${ui.escapeHTML(metadata[key])}</span>`)
      .join('');
    const balanceLabel = before === null || after === null ? '-' : `${ui.formatMoney(before)} -> ${ui.formatMoney(after)}`;
    const amountClass = amount !== null && amount < 0 ? 'amount-neg' : 'amount-pos';
    return `
      <article class="admin-audit-card">
        <div class="admin-card-main">
          <span class="profile-balance-label">${ui.escapeHTML(formatDate(item.created_at))}</span>
          <strong>${ui.escapeHTML(titleCaseValue(item.action || ''))}</strong>
          <small>#${ui.escapeHTML(item.id)}</small>
        </div>
        <div class="admin-card-metric compact">
          <span>${ui.t('admin_actor')}</span>
          <strong>${ui.escapeHTML(item.actor_user_id || '-')}</strong>
        </div>
        <div class="admin-card-metric compact">
          <span>${ui.t('admin_target')}</span>
          <strong>${ui.escapeHTML(item.target_user_id || '-')}</strong>
        </div>
        <div class="admin-card-metric">
          <span>${ui.t('admin_amount')}</span>
          <strong class="${amountClass}">${amount === null ? '-' : ui.formatMoney(amount)}</strong>
        </div>
        <div class="admin-card-metric">
          <span>${ui.t('admin_balance')}</span>
          <strong>${ui.escapeHTML(balanceLabel)}</strong>
        </div>
        <div class="admin-card-meta">
          <span>${ui.t('admin_metadata')}</span>
          <div class="admin-metadata">${chips || '<em>-</em>'}</div>
        </div>
      </article>
    `;
  }

  function renderUserProfile(user) {
    const mount = document.getElementById('adminUserProfile');
    const panel = document.getElementById('adminUserDetail');
    const tabs = document.getElementById('adminUserSubtabs');
    if (!mount || !panel) return;
    panel.hidden = !user;
    if (tabs) tabs.hidden = !user;
    if (!user) {
      mount.className = 'admin-detail-list';
      mount.innerHTML = '';
      return;
    }
    const displayName = user.name || user.email || `#${user.id}`;
    const initials = String(displayName).trim().slice(0, 1).toUpperCase() || '#';
    mount.className = 'admin-user-profile-card';
    mount.innerHTML = `
      <div class="admin-user-profile-head">
        <div class="admin-user-avatar">${ui.escapeHTML(initials)}</div>
        <div class="admin-user-identity">
          <span>${ui.escapeHTML(ui.t('admin_selected_user'))} #${ui.escapeHTML(user.id)}</span>
          <strong>${ui.escapeHTML(displayName)}</strong>
          <small>${ui.escapeHTML(user.email || '')}</small>
        </div>
        <div class="admin-user-balance">
          <span>${ui.escapeHTML(ui.t('profile_balance'))}</span>
          <strong>${ui.formatMoney(user.balance, user.currency)}</strong>
        </div>
      </div>
      <div class="admin-user-profile-meta">
        <div><span>ID</span><strong>#${ui.escapeHTML(user.id)}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('admin_provider'))}</span><strong>${ui.escapeHTML(titleCaseValue(user.provider || 'local'))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('profile_currency'))}</span><strong>${ui.escapeHTML(user.currency || 'EUR')}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('profile_vip_status'))}</span><strong>${ui.escapeHTML(titleCaseValue(user.vip_tier || 'bronze'))}</strong></div>
        <div><span>VIP Points</span><strong>${ui.escapeHTML(ui.formatNumber(user.vip_points || 0))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('profile_games_played'))}</span><strong>${ui.escapeHTML(ui.formatNumber(user.games_played || 0))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('profile_total_won'))}</span><strong>${ui.formatMoney(user.total_won, user.currency)}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('studio_balance'))}</span><strong>${ui.formatMoney(Number(user.studio_balance || 0), 'EUR')}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('admin_email_verified'))}</span><strong>${ui.escapeHTML(user.email_verified ? ui.t('yes') : ui.t('no'))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('admin_flag_admin'))}</span><strong>${ui.escapeHTML(user.is_admin ? ui.t('yes') : ui.t('no'))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('admin_created'))}</span><strong>${ui.escapeHTML(formatDate(user.created_at))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('admin_last_login'))}</span><strong>${ui.escapeHTML(user.last_login_at ? formatDate(user.last_login_at) : '-')}</strong></div>
      </div>
    `;
    switchUserPanel(activeUserPanel);
  }

  function renderUserTransactions(items) {
    const body = document.getElementById('adminUserTransactions');
    if (!body) return;
    body.innerHTML = items.length ? items.map(txRowHtml).join('') : emptyRow(4, 'profile_no_history');
  }

  function renderUserRounds(items) {
    const body = document.getElementById('adminUserRounds');
    if (!body) return;
    body.innerHTML = items.length ? items.map(roundRowHtml).join('') : emptyRow(5, 'profile_no_history');
  }

  function promoRedemptionRowHtml(item) {
    const bonus = item.bonus !== undefined ? Number(item.bonus) : Number(item.bonus_cents || 0) / 100;
    const deposit = item.deposit !== undefined ? Number(item.deposit) : Number(item.deposit_cents || 0) / 100;
    return `
      <tr>
        <td>${ui.escapeHTML(formatDate(item.created_at))}</td>
        <td><strong>${ui.escapeHTML(item.promo_code || '')}</strong><span>${ui.escapeHTML(item.promo_title || '')}</span></td>
        <td class="amount-pos">${ui.formatMoney(bonus)}</td>
        <td>${deposit ? ui.formatMoney(deposit) : '-'}</td>
        <td>#${ui.escapeHTML(item.transaction_id || '-')}</td>
      </tr>
    `;
  }

  function renderUserPromoRedemptions(items) {
    const body = document.getElementById('adminUserPromoRedemptions');
    if (!body) return;
    body.innerHTML = items.length ? items.map(promoRedemptionRowHtml).join('') : emptyRow(5, 'profile_no_history');
  }

  function renderAudit(items) {
    const body = document.getElementById('adminAuditBody');
    if (!body) return;
    body.innerHTML = items.length ? items.map(auditRowHtml).join('') : (ui.renderState ? ui.renderState('empty', { text: ui.t('admin_empty') }) : `<div class="admin-empty">${ui.t('admin_empty')}</div>`);
  }

  function renderPromos(items) {
    const body = document.getElementById('adminPromosBody');
    if (!body) return;
    body.innerHTML = items.length ? items.map(promoRowHtml).join('') : emptyRow(5, 'admin_empty');
  }

  function renderPromoStats(stats) {
    const mount = document.getElementById('adminPromoStats');
    if (!mount || !stats || stats.error) return;
    const values = [
      ['admin_status_active', stats.active],
      ['admin_status_scheduled', stats.scheduled],
      ['admin_status_inactive', stats.inactive],
      ['admin_status_expired', stats.expired],
      ['admin_status_all', stats.total]
    ];
    const statuses = ['active', 'scheduled', 'inactive', 'expired', 'all'];
    mount.innerHTML = values.map(([key, value], index) => `
      <button class="admin-promo-stat-card ${statuses[index] === activePromoStatus ? 'active' : ''}" type="button" data-admin-promo-status="${statuses[index]}">
        <span>${ui.escapeHTML(ui.t(key))}</span>
        <strong>${ui.escapeHTML(ui.formatNumber(value || 0))}</strong>
      </button>
    `).join('');
  }

  function promoDetailMetric(labelKey, value) {
    return `<div><span>${ui.escapeHTML(ui.t(labelKey))}</span><strong>${ui.escapeHTML(value || '-')}</strong></div>`;
  }

  function renderPromoDetail(detail) {
    const panel = document.getElementById('adminPromoDetail');
    const title = document.getElementById('adminPromoDetailTitle');
    const grid = document.getElementById('adminPromoDetailGrid');
    const disableButton = document.getElementById('adminPromoDetailDisableBtn');
    const editButton = document.getElementById('adminPromoEditBtn');
    if (!panel || !title || !grid) return;
    const promo = detail && detail.promo ? detail.promo : selectedPromo;
    panel.hidden = !promo;
    if (!promo) return;
    selectedPromo = promo;
    title.textContent = `${promo.code || '-'} · ${promo.title || '-'}`;
    const used = `${ui.formatNumber(promo.used_count || 0)} / ${ui.formatNumber(promo.usage_limit || 0)}`;
    const dates = `${promo.starts_at ? formatDate(promo.starts_at) : '-'} → ${promo.expires_at ? formatDate(promo.expires_at) : '-'}`;
    grid.innerHTML = [
      promoDetailMetric('admin_promo_code', promo.code),
      promoDetailMetric('admin_promo_title', promo.title),
      promoDetailMetric('admin_promo_reward_type', promoStatusLabel(promo.reward_type)),
      promoDetailMetric('admin_promo_reward', promoRewardLabel(promo)),
      promoDetailMetric('admin_promo_used', used),
      promoDetailMetric('admin_status', promoStatusLabel(promo.status)),
      promoDetailMetric('admin_promo_per_user_limit', ui.formatNumber(promo.per_user_limit || 0)),
      promoDetailMetric('admin_promo_dates', dates)
    ].join('');
    if (disableButton) {
      disableButton.hidden = !(promo.status === 'active' && promo.is_active);
      disableButton.dataset.adminPromoDisable = promo.id;
    }
    if (editButton) editButton.dataset.adminPromoEdit = promo.id;
    renderPromoDetailRedemptions(detail && detail.redemptions ? detail.redemptions : []);
    renderPromoAuditSnippet(detail && detail.audit ? detail.audit : []);
    renderPromos(paging.promos.items);
  }

  function promoDetailRedemptionRowHtml(item) {
    const userLabel = item.user_name || item.user_email || ('#' + item.user_id);
    const bonus = item.bonus !== undefined ? Number(item.bonus) : Number(item.bonus_cents || 0) / 100;
    const deposit = item.deposit !== undefined ? Number(item.deposit) : Number(item.deposit_cents || 0) / 100;
    return `
      <tr>
        <td><strong>${ui.escapeHTML(userLabel)}</strong><span>${ui.escapeHTML(item.user_email || '')}</span></td>
        <td class="amount-pos">${ui.formatMoney(bonus)}</td>
        <td>${deposit ? ui.formatMoney(deposit) : '-'}</td>
        <td>#${ui.escapeHTML(item.transaction_id || '-')}</td>
        <td>${ui.escapeHTML(formatDate(item.created_at))}</td>
      </tr>
    `;
  }

  function renderPromoDetailRedemptions(items) {
    const body = document.getElementById('adminPromoDetailRedemptions');
    if (!body) return;
    body.innerHTML = items.length ? items.map(promoDetailRedemptionRowHtml).join('') : emptyRow(5, 'profile_no_history');
  }

  function auditSnippetRowHtml(item) {
    const metadata = item.metadata || {};
    const chips = ['promo_id', 'promo_code', 'reward_type', 'bonus_cents', 'deposit_cents', 'transaction_id']
      .filter(key => metadata[key] !== undefined && metadata[key] !== null && metadata[key] !== '')
      .map(key => `<span>${ui.escapeHTML(titleCaseValue(key.replace(/_/g, ' ')))}: ${ui.escapeHTML(metadata[key])}</span>`)
      .join('');
    return `
      <tr>
        <td>${ui.escapeHTML(formatDate(item.created_at))}</td>
        <td><strong>${ui.escapeHTML(item.action || '')}</strong><span>#${ui.escapeHTML(item.id || '')}</span></td>
        <td><div class="admin-metadata">${chips || '-'}</div></td>
      </tr>
    `;
  }

  function renderPromoAuditSnippet(items) {
    const body = document.getElementById('adminPromoDetailAudit');
    if (!body) return;
    body.innerHTML = items.length ? items.map(auditSnippetRowHtml).join('') : emptyRow(3, 'admin_empty');
  }

  function renderWithdrawals(items) {
    const body = document.getElementById('adminWithdrawalsBody');
    if (!body) return;
    body.innerHTML = items.length ? items.map(withdrawalRowHtml).join('') : (ui.renderState ? ui.renderState('empty', { text: ui.t('admin_empty') }) : `<div class="admin-empty">${ui.t('admin_empty')}</div>`);
  }

  function renderUsers(items) {
    const body = document.getElementById('adminUsersBody');
    if (!body) return;
    lastUsers = Array.isArray(items) ? items : [];
    body.dataset.users = JSON.stringify(items || []);
    body.innerHTML = items.length ? items.map(userRowHtml).join('') : `<div class="admin-empty">${ui.t('admin_no_users')}</div>`;
    renderSelectedUser();
  }

  function canUseAdmin() {
    const user = store.getState().currentUser;
    if (!user) {
      ui.showToast(ui.t('err_auth_required'), 'err');
      resetAllPages();
      renderWithdrawals([]);
      renderUsers([]);
      renderPromos([]);
      renderUserPromoRedemptions([]);
      return false;
    }
    if (!user.isAdmin) {
      ui.showToast(ui.t('err_admin_required'), 'err');
      resetAllPages();
      renderWithdrawals([]);
      renderUsers([]);
      renderPromos([]);
      renderUserPromoRedemptions([]);
      return false;
    }
    return true;
  }

  async function loadWithdrawals(append) {
    if (withdrawalsLoading || !canUseAdmin()) return;
    if (!append) resetPage('withdrawals');
    withdrawalsLoading = true;
    updateLoadMore('withdrawals', true);
    const result = await store.adminListWithdrawals(activeStatus, { limit: PAGE_SIZE, offset: append ? paging.withdrawals.offset : 0 });
    withdrawalsLoading = false;
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      renderWithdrawals([]);
      resetPage('withdrawals');
      return;
    }
    const withdrawals = setPageResult('withdrawals', result, append);
    renderWithdrawals(withdrawals);
    if (activeStatus === 'all') lastWithdrawals = withdrawals;
  }

  async function loadUsers(pageDelta) {
    if (usersLoading || !canUseAdmin()) return;
    const delta = Number(pageDelta || 0);
    if (delta) {
      usersPageIndex = Math.max(0, usersPageIndex + delta);
    } else {
      resetPage('users');
    }
    usersLoading = true;
    updateUserPager(true);
    const limit = pageSize('users');
    const result = await store.adminListUsers(document.getElementById('adminUserSearch')?.value || '', { limit: limit + 1, offset: usersPageIndex * limit });
    usersLoading = false;
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      renderUsers([]);
      resetPage('users');
      return;
    }
    const rows = Array.isArray(result) ? result : [];
    const users = rows.slice(0, limit);
    paging.users.items = users;
    paging.users.offset = usersPageIndex * limit + users.length;
    paging.users.hasMore = rows.length > limit;
    if (selectedUser) {
      selectedUser = users.find(user => user.id === selectedUser.id) || selectedUser;
    }
    renderUsers(users);
    updateUserPager(false);
  }

  async function loadSelectedUserDetail(options) {
    const opts = options || {};
    const appendTransactions = Boolean(opts.appendTransactions);
    const appendRounds = Boolean(opts.appendRounds);
    const appendPromoRedemptions = Boolean(opts.appendPromoRedemptions);
    const loadTransactions = opts.transactions !== false && !appendRounds && !appendPromoRedemptions;
    const loadRounds = opts.rounds !== false && !appendTransactions && !appendPromoRedemptions;
    const loadPromoRedemptions = opts.promoRedemptions !== false && !appendTransactions && !appendRounds;
    const refreshDetail = !appendTransactions && !appendRounds && !appendPromoRedemptions;
    if (!selectedUser || !canUseAdmin()) {
      renderUserProfile(null);
      renderUserTransactions([]);
      renderUserRounds([]);
      renderUserPromoRedemptions([]);
      resetPage('transactions');
      resetPage('rounds');
      resetPage('promoRedemptions');
      return;
    }
    if (loadTransactions && !appendTransactions) resetPage('transactions');
    if (loadRounds && !appendRounds) resetPage('rounds');
    if (loadPromoRedemptions && !appendPromoRedemptions) resetPage('promoRedemptions');
    if (appendTransactions) updateLoadMore('transactions', true);
    if (appendRounds) updateLoadMore('rounds', true);
    if (appendPromoRedemptions) updateLoadMore('promoRedemptions', true);
    const txFilters = {
      type: document.getElementById('adminTxType')?.value || '',
      status: document.getElementById('adminTxStatus')?.value || '',
      date_from: getDateValue('adminTxFrom'),
      date_to: getDateValue('adminTxTo'),
      limit: pageSize('transactions'),
      offset: appendTransactions ? paging.transactions.offset : 0
    };
    const roundFilters = {
      game_id: document.getElementById('adminRoundGame')?.value || '',
      status: document.getElementById('adminRoundStatus')?.value || '',
      date_from: getDateValue('adminRoundFrom'),
      date_to: getDateValue('adminRoundTo'),
      limit: pageSize('rounds'),
      offset: appendRounds ? paging.rounds.offset : 0
    };
    Object.keys(txFilters).forEach(key => {
      if (!txFilters[key]) delete txFilters[key];
    });
    Object.keys(roundFilters).forEach(key => {
      if (!roundFilters[key]) delete roundFilters[key];
    });
    const promoPaging = {
      limit: pageSize('promoRedemptions'),
      offset: appendPromoRedemptions ? paging.promoRedemptions.offset : 0
    };
    const [detail, transactions, rounds, promoRedemptions] = await Promise.all([
      refreshDetail ? store.adminGetUser(selectedUser.id) : Promise.resolve(selectedUser),
      loadTransactions ? store.adminGetUserTransactions(selectedUser.id, txFilters) : Promise.resolve(null),
      loadRounds ? store.adminGetUserGameRounds(selectedUser.id, roundFilters) : Promise.resolve(null),
      loadPromoRedemptions ? store.adminGetUserPromoRedemptions(selectedUser.id, promoPaging) : Promise.resolve(null)
    ]);
    if (detail && detail.error) {
      ui.showToast(ui.t(detail.error), 'err');
      return;
    }
    selectedUser = detail || selectedUser;
    renderSelectedUser();
    renderUserProfile(detail);
    if (transactions && transactions.error) {
      ui.showToast(ui.t(transactions.error), 'err');
      if (!appendTransactions) renderUserTransactions([]);
      resetPage('transactions');
    } else if (loadTransactions) {
      renderUserTransactions(setPageResult('transactions', transactions, appendTransactions));
    }
    if (rounds && rounds.error) {
      ui.showToast(ui.t(rounds.error), 'err');
      if (!appendRounds) renderUserRounds([]);
      resetPage('rounds');
    } else if (loadRounds) {
      renderUserRounds(setPageResult('rounds', rounds, appendRounds));
    }
    if (promoRedemptions && promoRedemptions.error) {
      ui.showToast(ui.t(promoRedemptions.error), 'err');
      if (!appendPromoRedemptions) renderUserPromoRedemptions([]);
      resetPage('promoRedemptions');
    } else if (loadPromoRedemptions) {
      renderUserPromoRedemptions(setPageResult('promoRedemptions', promoRedemptions, appendPromoRedemptions));
    }
  }

  async function loadOverview() {
    if (overviewLoading || !canUseAdmin()) return;
    overviewLoading = true;
    const usersResult = await store.adminListUsers('', { limit: 100, offset: 0 });
    const withdrawalsResult = await store.adminListWithdrawals('all', { limit: 100, offset: 0 });
    overviewLoading = false;
    if (usersResult && usersResult.error) {
      ui.showToast(ui.t(usersResult.error), 'err');
      renderOverview([], []);
      return;
    }
    if (withdrawalsResult && withdrawalsResult.error) {
      ui.showToast(ui.t(withdrawalsResult.error), 'err');
      renderOverview(Array.isArray(usersResult) ? usersResult : [], []);
      return;
    }
    lastUsers = Array.isArray(usersResult) ? usersResult : [];
    lastWithdrawals = Array.isArray(withdrawalsResult) ? withdrawalsResult : [];
    renderOverview(lastUsers, lastWithdrawals);
  }

  async function loadAudit(append) {
    if (auditLoading || !canUseAdmin()) return;
    if (!append) resetPage('audit');
    auditLoading = true;
    updateLoadMore('audit', true);
    const filters = {
      action: document.getElementById('adminAuditAction')?.value || '',
      actor_user_id: document.getElementById('adminAuditActor')?.value || '',
      target_user_id: document.getElementById('adminAuditTarget')?.value || '',
      date_from: getAuditDateValue('adminAuditFrom'),
      date_to: getAuditDateValue('adminAuditTo'),
      limit: PAGE_SIZE,
      offset: append ? paging.audit.offset : 0
    };
    Object.keys(filters).forEach(key => {
      if (!filters[key]) delete filters[key];
    });
    const result = await store.adminListAudit(filters);
    auditLoading = false;
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      renderAudit([]);
      resetPage('audit');
      return;
    }
    renderAudit(setPageResult('audit', result, append));
  }

  async function loadPromos(append) {
    if (promosLoading || !canUseAdmin()) return;
    if (!append) resetPage('promos');
    promosLoading = true;
    updateLoadMore('promos', true);
    if (!append) {
      const stats = await store.adminPromoStats();
      renderPromoStats(stats);
    }
    const result = await store.adminListPromos(activePromoStatus, { limit: PAGE_SIZE, offset: append ? paging.promos.offset : 0 });
    promosLoading = false;
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      renderPromos([]);
      resetPage('promos');
      return;
    }
    renderPromos(setPageResult('promos', result, append));
  }

  async function selectPromo(id) {
    if (!id || !canUseAdmin()) return;
    resetPage('promoDetailRedemptions');
    const detail = await store.adminGetPromo(id);
    if (detail && detail.error) {
      ui.showToast(ui.t(detail.error), 'err');
      return;
    }
    selectedPromo = detail.promo;
    paging.promoDetailRedemptions.items = Array.isArray(detail.redemptions) ? detail.redemptions : [];
    paging.promoDetailRedemptions.offset = paging.promoDetailRedemptions.items.length;
    paging.promoDetailRedemptions.hasMore = paging.promoDetailRedemptions.items.length === pageSize('promoDetailRedemptions');
    updateLoadMore('promoDetailRedemptions', false);
    renderPromoDetail(detail);
  }

  async function loadPromoDetailRedemptions(append) {
    if (!selectedPromo || !canUseAdmin()) return;
    if (!append) resetPage('promoDetailRedemptions');
    updateLoadMore('promoDetailRedemptions', true);
    const result = await store.adminGetPromoRedemptions(selectedPromo.id, {
      limit: pageSize('promoDetailRedemptions'),
      offset: append ? paging.promoDetailRedemptions.offset : 0
    });
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      if (!append) renderPromoDetailRedemptions([]);
      resetPage('promoDetailRedemptions');
      return;
    }
    renderPromoDetailRedemptions(setPageResult('promoDetailRedemptions', result, append));
  }

  function resetPromoForm() {
    const form = document.getElementById('adminPromoForm');
    if (!form) return;
    form.reset();
    const usage = document.getElementById('adminPromoUsageLimit');
    const perUser = document.getElementById('adminPromoPerUserLimit');
    const active = document.getElementById('adminPromoActive');
    if (usage) usage.value = '100';
    if (perUser) perUser.value = '1';
    if (active) active.checked = true;
    ['adminPromoStartsAt', 'adminPromoExpiresAt'].forEach(id => {
      const input = document.getElementById(id);
      if (input) {
        input.dataset.value = '';
        input.value = '';
      }
    });
    syncPromoRewardFields();
  }

  function promoFormPayload(prefix, includeCode) {
    const base = prefix || 'adminPromo';
    const rewardType = document.getElementById(base + 'RewardType')?.value || 'fixed';
    const payload = {
      title: (document.getElementById(base + (base === 'adminPromoEdit' ? 'Name' : 'Title'))?.value || '').trim(),
      reward_type: rewardType,
      usage_limit: Math.max(0, Math.floor(numberValue(base + 'UsageLimit') || 0)),
      per_user_limit: Math.max(0, Math.floor(numberValue(base + 'PerUserLimit') || 0)),
      is_active: Boolean(document.getElementById(base + 'Active')?.checked)
    };
    if (includeCode) payload.code = (document.getElementById(base + 'Code')?.value || '').trim().toUpperCase();
    const startsAt = dateTimeValue(base + 'StartsAt');
    const expiresAt = dateTimeValue(base + 'ExpiresAt');
    if (includeCode) {
      if (startsAt) payload.starts_at = startsAt;
      if (expiresAt) payload.expires_at = expiresAt;
    } else {
      payload.starts_at = startsAt || null;
      payload.expires_at = expiresAt || null;
    }
    if (rewardType === 'percent') {
      payload.percent = numberValue(base + 'Percent');
      payload.max_bonus = numberValue(base + 'MaxBonus');
      payload.min_deposit = numberValue(base + 'MinDeposit');
    } else {
      payload.amount = numberValue(base + 'Amount');
    }
    return payload;
  }

  function setPromoEditDate(id, value) {
    const input = document.getElementById(id);
    if (!input) return;
    setDateInput(input, value ? String(value).slice(0, 10) : '');
  }

  function openPromoEdit(id) {
    const promo = paging.promos.items.find(item => String(item.id) === String(id)) || selectedPromo;
    if (!promo) return;
    selectedPromo = promo;
    const overlay = document.getElementById('adminPromoEditOverlay');
    document.getElementById('adminPromoEditTitle').textContent = `${promo.code || '-'} · ${promo.title || ''}`;
    document.getElementById('adminPromoEditName').value = promo.title || '';
    document.getElementById('adminPromoEditRewardType').value = promo.reward_type || 'fixed';
    document.getElementById('adminPromoEditAmount').value = promo.amount !== undefined ? promo.amount : Number(promo.amount_cents || 0) / 100 || '';
    document.getElementById('adminPromoEditPercent').value = promo.percent !== undefined ? promo.percent : Number(promo.percent_bps || 0) / 100 || '';
    document.getElementById('adminPromoEditMaxBonus').value = promo.max_bonus !== undefined ? promo.max_bonus : Number(promo.max_bonus_cents || 0) / 100 || '';
    document.getElementById('adminPromoEditMinDeposit').value = promo.min_deposit !== undefined ? promo.min_deposit : Number(promo.min_deposit_cents || 0) / 100 || '';
    document.getElementById('adminPromoEditUsageLimit').value = promo.usage_limit || 0;
    document.getElementById('adminPromoEditPerUserLimit').value = promo.per_user_limit || 0;
    document.getElementById('adminPromoEditActive').checked = Boolean(promo.is_active);
    setPromoEditDate('adminPromoEditStartsAt', promo.starts_at);
    setPromoEditDate('adminPromoEditExpiresAt', promo.expires_at);
    syncPromoRewardFields('adminPromoEdit');
    overlay?.classList.add('open');
    overlay?.setAttribute('aria-hidden', 'false');
  }

  function closePromoEdit() {
    const overlay = document.getElementById('adminPromoEditOverlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden', 'true');
  }

  async function createPromo(event) {
    event.preventDefault();
    const payload = promoFormPayload('adminPromo', true);
    if (!payload.code || payload.code.length < 3) {
      ui.showToast(ui.t('err_promo_invalid'), 'err');
      return;
    }
    if (payload.reward_type === 'percent' && (!payload.percent || !payload.max_bonus)) {
      ui.showToast(ui.t('err_promo_config'), 'err');
      return;
    }
    if (payload.reward_type === 'fixed' && !payload.amount) {
      ui.showToast(ui.t('err_promo_config'), 'err');
      return;
    }
    const result = await store.adminCreatePromo(payload);
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    ui.showToast(ui.t('admin_promo_created'));
    resetPromoForm();
    await loadPromos(false);
    await loadAudit(false);
  }

  async function savePromoEdit(event) {
    event.preventDefault();
    if (!selectedPromo) return;
    const payload = promoFormPayload('adminPromoEdit', false);
    if (!payload.title) {
      ui.showToast(ui.t('err_promo_config'), 'err');
      return;
    }
    if (payload.reward_type === 'percent' && (!payload.percent || !payload.max_bonus)) {
      ui.showToast(ui.t('err_promo_config'), 'err');
      return;
    }
    if (payload.reward_type === 'fixed' && !payload.amount) {
      ui.showToast(ui.t('err_promo_config'), 'err');
      return;
    }
    const message = `${ui.t('admin_confirm_update_promo')}\n${selectedPromo.code || ('#' + selectedPromo.id)}`;
    if (!await confirmAction(message, ui.t('admin_promo_save'))) return;
    const result = await store.adminUpdatePromo(selectedPromo.id, payload);
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    selectedPromo = result;
    closePromoEdit();
    ui.showToast(ui.t('admin_promo_updated'));
    await loadPromos(false);
    await selectPromo(result.id || selectedPromo.id);
    await loadAudit(false);
  }

  async function disablePromo(id) {
    const promo = paging.promos.items.find(item => String(item.id) === String(id)) || {};
    const message = `${ui.t('admin_confirm_disable_promo')}\n${promo.code ? promo.code + ' #' + id : '#' + id}`;
    if (!await confirmAction(message, ui.t('admin_promo_disable'), 'danger')) return;
    const result = await store.adminDisablePromo(id);
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    ui.showToast(ui.t('admin_promo_disabled'));
    await loadPromos(false);
    if (selectedPromo && String(selectedPromo.id) === String(id)) await selectPromo(id);
    await loadAudit(false);
  }

  function managerTicketStatusLabel(value) {
    const status = String(value || '').toLowerCase();
    const key = {
      open: 'admin_support_open',
      in_progress: 'admin_support_progress',
      resolved: 'admin_support_resolved',
      rejected: 'admin_support_rejected',
      closed: 'admin_support_closed'
    }[status];
    return key ? ui.t(key) : titleCaseValue(status);
  }

  function managerTicketCategoryLabel(value) {
    const category = String(value || '').toLowerCase();
    if (category === 'bet_exception') return ui.t('admin_support_bet_exception');
    if (category === 'technical') return ui.t('admin_support_technical');
    return titleCaseValue(category);
  }

  function renderSupportTickets(items) {
    const mount = document.getElementById('adminSupportTickets');
    if (!mount) return;
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      mount.innerHTML = `<div class="admin-empty">${ui.escapeHTML(ui.t('admin_support_empty'))}</div>`;
      return;
    }
    mount.innerHTML = list.map(ticket => {
      const selected = String(selectedSupportTicket?.id || '') === String(ticket.id);
      return `
        <button class="admin-support-ticket ${selected ? 'is-selected' : ''}" type="button" data-manager-ticket-id="${ui.escapeHTML(ticket.id)}">
          <span class="admin-support-ticket-top">
            <strong>#${ui.escapeHTML(ticket.id)} · ${ui.escapeHTML(ticket.user_name || ticket.user_email || ('User ' + ticket.user_id))}</strong>
            <span class="admin-pill ${statusClass(ticket.status)}">${ui.escapeHTML(managerTicketStatusLabel(ticket.status))}</span>
          </span>
          <span class="admin-support-ticket-subject">${ui.escapeHTML(ticket.subject || '-')}</span>
          <span class="admin-support-ticket-meta">
            <span>${ui.escapeHTML(managerTicketCategoryLabel(ticket.category))}</span>
            <time>${ui.escapeHTML(formatDate(ticket.created_at))}</time>
          </span>
        </button>
      `;
    }).join('');
  }

  function renderSupportDetail(detail) {
    const mount = document.getElementById('adminSupportDetail');
    if (!mount) return;
    if (!detail || detail.error || !detail.ticket) {
      mount.innerHTML = `<div class="admin-empty admin-support-placeholder"><strong>${ui.escapeHTML(ui.t('admin_support_select_title'))}</strong><span>${ui.escapeHTML(ui.t('admin_support_select_text'))}</span></div>`;
      return;
    }
    const ticket = detail.ticket;
    const user = detail.user || {};
    const messages = Array.isArray(detail.messages) ? detail.messages : [];
    const request = ticket.payload || {};
    const betTicket = ticket.category === 'bet_exception';
    const requestedEuros = Number(request.bet_cents || 0) / 100;
    const finalStatus = ['resolved', 'rejected', 'closed'].includes(ticket.status);
    mount.innerHTML = `
      <div class="admin-support-detail-head">
        <div>
          <p class="label">${ui.escapeHTML(managerTicketCategoryLabel(ticket.category))} // #${ui.escapeHTML(ticket.id)}</p>
          <h2>${ui.escapeHTML(ticket.subject || '-')}</h2>
          <p>${ui.escapeHTML(ticket.user_name || user.name || '-')} · ${ui.escapeHTML(ticket.user_email || user.email || '')}</p>
        </div>
        <span class="admin-pill ${statusClass(ticket.status)}">${ui.escapeHTML(managerTicketStatusLabel(ticket.status))}</span>
      </div>
      <div class="admin-support-user-strip">
        <div><span>${ui.escapeHTML(ui.t('admin_balance'))}</span><strong>${ui.escapeHTML(centsToMoney(user.balance_cents))}</strong></div>
        <div><span>VIP</span><strong>${ui.escapeHTML(titleCaseValue(user.vip_tier || 'bronze'))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('profile_games_played'))}</span><strong>${ui.escapeHTML(ui.formatNumber(user.games_played || 0))}</strong></div>
        <div><span>${ui.escapeHTML(ui.t('admin_created'))}</span><strong>${ui.escapeHTML(formatDate(ticket.created_at))}</strong></div>
      </div>
      <div class="admin-support-chat" id="adminSupportChat">
        ${messages.length ? messages.map(message => `
          <article class="admin-support-message is-${ui.escapeHTML(message.role || 'operator')}">
            <span>${ui.escapeHTML(message.role === 'user' ? (ticket.user_name || ui.t('admin_user')) : message.role === 'admin' ? ui.t('admin_support_management') : 'Operator 08')}</span>
            <p>${ui.escapeHTML(message.text || '')}</p>
            <time>${ui.escapeHTML(formatDate(message.created_at))}</time>
          </article>
        `).join('') : `<div class="admin-empty">${ui.escapeHTML(ui.t('admin_support_no_messages'))}</div>`}
      </div>
      <form class="admin-support-resolution" id="adminSupportResolution">
        ${betTicket ? `
          <div class="admin-support-bet-request">
            <label><span>${ui.escapeHTML(ui.t('admin_support_game'))}</span><strong>${ui.escapeHTML(request.game_id || '-')}</strong></label>
            <label><span>${ui.escapeHTML(ui.t('admin_support_requested_bet'))}</span><strong>${ui.escapeHTML(ui.formatMoney(requestedEuros))}</strong></label>
            <label for="adminSupportApprovedBet"><span>${ui.escapeHTML(ui.t('admin_support_approved_bet'))}</span><input class="f-input" id="adminSupportApprovedBet" type="number" min="105" max="500" step="5" value="${ui.escapeHTML(requestedEuros || '')}" ${finalStatus ? 'disabled' : ''}/></label>
          </div>
        ` : ''}
        <label class="admin-support-response" for="adminSupportResponse">
          <span class="f-label">${ui.escapeHTML(ui.t('admin_support_response'))}</span>
          <textarea class="f-input" id="adminSupportResponse" rows="3" maxlength="2000" ${finalStatus ? 'disabled' : ''}>${ui.escapeHTML(ticket.admin_response || '')}</textarea>
        </label>
        <div class="admin-support-actions">
          ${finalStatus ? `<span class="admin-muted-note">${ui.escapeHTML(ui.t('admin_support_settled'))}</span>` : `
            <button class="btn btn-outline btn-sm" type="button" data-manager-ticket-action="in_progress">${ui.escapeHTML(ui.t('admin_support_take'))}</button>
            <button class="btn btn-primary btn-sm" type="button" data-manager-ticket-action="resolved">${ui.escapeHTML(ui.t('admin_support_resolve'))}</button>
            <button class="btn btn-outline btn-sm is-danger" type="button" data-manager-ticket-action="rejected">${ui.escapeHTML(ui.t('admin_support_reject'))}</button>
            <button class="btn btn-outline btn-sm" type="button" data-manager-ticket-action="closed">${ui.escapeHTML(ui.t('admin_support_close'))}</button>
          `}
        </div>
      </form>
    `;
    window.setTimeout(() => {
      const chat = document.getElementById('adminSupportChat');
      if (chat) chat.scrollTop = chat.scrollHeight;
    }, 0);
  }

  async function loadSupport(append) {
    if (supportLoading) return;
    supportLoading = true;
    if (!append) resetPage('support');
    updateLoadMore('support', true);
    const category = document.getElementById('adminSupportCategory')?.value || '';
    const result = await store.adminListManagerTickets(activeSupportStatus, {
      category,
      limit: pageSize('support'),
      offset: paging.support.offset
    });
    supportLoading = false;
    if (result && result.error) {
      updateLoadMore('support', false);
      ui.showToast(ui.t(result.error), 'err');
      renderSupportTickets([]);
      return;
    }
    const items = setPageResult('support', result, Boolean(append));
    renderSupportTickets(items);
  }

  async function selectSupportTicket(id) {
    const ticket = paging.support.items.find(item => String(item.id) === String(id));
    selectedSupportTicket = ticket || { id: Number(id) };
    renderSupportTickets(paging.support.items);
    const mount = document.getElementById('adminSupportDetail');
    if (mount) mount.innerHTML = `<div class="admin-empty">${ui.escapeHTML(ui.t('admin_loading'))}</div>`;
    const detail = await store.adminGetManagerTicket(id);
    if (detail && detail.error) {
      ui.showToast(ui.t(detail.error), 'err');
      renderSupportDetail(null);
      return;
    }
    selectedSupportTicket = detail.ticket;
    renderSupportDetail(detail);
  }

  async function updateSupportTicket(status) {
    if (!selectedSupportTicket) return;
    const response = document.getElementById('adminSupportResponse')?.value.trim() || '';
    const payload = { status, response };
    if (selectedSupportTicket.category === 'bet_exception' && status === 'resolved') {
      const amount = Number(document.getElementById('adminSupportApprovedBet')?.value || 0);
      if (!Number.isFinite(amount) || amount <= 100 || amount % 5) {
        ui.showToast(ui.t('err_manager_bet_exception_invalid'), 'err');
        return;
      }
      payload.approved_bet_cents = Math.round(amount * 100);
      payload.game_id = selectedSupportTicket.payload?.game_id || '';
    }
    const message = ui.t('admin_support_confirm', {
      id: selectedSupportTicket.id,
      status: managerTicketStatusLabel(status)
    });
    if (!await confirmAction(message, managerTicketStatusLabel(status), status === 'rejected' ? 'danger' : 'default')) return;
    const result = await store.adminUpdateManagerTicket(selectedSupportTicket.id, payload);
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    ui.showToast(ui.t('admin_support_updated'));
    await loadSupport(false);
    await selectSupportTicket(result.id || selectedSupportTicket.id);
  }

  function refreshActiveTab() {
    if (activeTab === 'withdrawals') {
      loadWithdrawals();
      return;
    }
    if (activeTab === 'audit') {
      loadAudit();
      return;
    }
    if (activeTab === 'promos') {
      loadPromos();
      return;
    }
    if (activeTab === 'support') {
      loadSupport();
      return;
    }
    loadOverview();
    loadUsers(false);
  }

  async function runWithdrawalAction(action, id) {
    const confirmKey = action === 'approve' ? 'admin_confirm_approve' : 'admin_confirm_reject';
    const confirmLabel = action === 'approve' ? ui.t('admin_approve') : ui.t('admin_reject');
    const item = paging.withdrawals.items.find(row => String(row.transaction?.id) === String(id)) || {};
    const tx = item.transaction || {};
    const user = item.user || {};
    const amount = tx.amount !== undefined ? Math.abs(Number(tx.amount || 0)) : Math.abs(Number(tx.amount_cents || 0) / 100);
    const userLabel = user.email || user.name || ('#' + (user.id || '-'));
    const message = `${ui.t(confirmKey)} ${userLabel} · ${ui.formatMoney(amount, tx.currency || user.currency)} · #${id}`;
    if (!await confirmAction(message, confirmLabel, action === 'reject' ? 'danger' : 'default')) return;
    const result = action === 'approve'
      ? await store.adminApproveWithdrawal(id)
      : await store.adminRejectWithdrawal(id);
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    ui.showToast(ui.t('admin_done'));
    await loadWithdrawals(false);
    await loadUsers(false);
  }

  function selectUser(id) {
    const body = document.getElementById('adminUsersBody');
    const users = JSON.parse(body?.dataset.users || '[]');
    selectedUser = users.find(user => String(user.id) === String(id)) || null;
    activeUserPanel = 'profile';
    renderUsers(users);
    loadSelectedUserDetail();
  }

  async function adjustBalance(mode) {
    if (!selectedUser) {
      ui.showToast(ui.t('admin_no_user_selected'), 'err');
      return;
    }
    const amountInput = document.getElementById('adminBalanceAmount');
    const noteInput = document.getElementById('adminBalanceNote');
    const rawAmount = Number(amountInput?.value || 0);
    if (!Number.isFinite(rawAmount) || rawAmount <= 0) {
      ui.showToast(ui.t('err_amount_invalid'), 'err');
      return;
    }
    const signedAmount = mode === 'debit' ? -rawAmount : rawAmount;
    const confirmKey = mode === 'debit' ? 'admin_confirm_debit' : 'admin_confirm_credit';
    const confirmLabel = mode === 'debit' ? ui.t('admin_debit') : ui.t('admin_credit');
    const userLabel = selectedUser.email || selectedUser.name || ('#' + selectedUser.id);
    const message = `${ui.t(confirmKey)} ${userLabel} · ${ui.formatMoney(Math.abs(signedAmount), selectedUser.currency)}`;
    if (!await confirmAction(message, confirmLabel, mode === 'debit' ? 'danger' : 'default')) return;
    const result = await store.adminAdjustBalance(selectedUser.id, signedAmount, noteInput?.value || '');
    if (result && result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    selectedUser = result.user || selectedUser;
    if (amountInput) amountInput.value = '';
    ui.showToast(ui.t(mode === 'debit' ? 'admin_debit_done' : 'admin_credit_done'));
    await loadUsers(false);
    await loadSelectedUserDetail();
    await loadOverview();
  }

  function loadMore(kind) {
    if (kind === 'users') return loadUsers(1);
    if (kind === 'withdrawals') return loadWithdrawals(true);
    if (kind === 'promos') return loadPromos(true);
    if (kind === 'audit') return loadAudit(true);
    if (kind === 'transactions') return loadSelectedUserDetail({ appendTransactions: true });
    if (kind === 'rounds') return loadSelectedUserDetail({ appendRounds: true });
    if (kind === 'promoRedemptions') return loadSelectedUserDetail({ appendPromoRedemptions: true });
    if (kind === 'promoDetailRedemptions') return loadPromoDetailRedemptions(true);
    if (kind === 'support') return loadSupport(true);
    return null;
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      const tab = event.target.closest('[data-admin-tab]');
      if (tab) {
        switchTab(tab.dataset.adminTab);
        return;
      }

      const dateField = event.target.closest('.admin-date-field');
      if (dateField) {
        handleCalendarClick(event, dateField);
        return;
      }
      closeCalendars();

      const status = event.target.closest('[data-admin-status]');
      if (status) {
        activeStatus = status.dataset.adminStatus || 'pending';
        document.querySelectorAll('[data-admin-status]').forEach(btn => btn.classList.toggle('active', btn === status));
        loadWithdrawals();
        return;
      }

      const promoStatus = event.target.closest('[data-admin-promo-status]');
      if (promoStatus) {
        activePromoStatus = promoStatus.dataset.adminPromoStatus || 'active';
        document.querySelectorAll('[data-admin-promo-status]').forEach(btn => btn.classList.toggle('active', btn === promoStatus));
        loadPromos();
        return;
      }

      const supportStatus = event.target.closest('[data-manager-ticket-status]');
      if (supportStatus) {
        activeSupportStatus = supportStatus.dataset.managerTicketStatus || 'open';
        document.querySelectorAll('[data-manager-ticket-status]').forEach(btn => btn.classList.toggle('active', btn === supportStatus));
        selectedSupportTicket = null;
        renderSupportDetail(null);
        loadSupport(false);
        return;
      }

      const supportTicket = event.target.closest('[data-manager-ticket-id]');
      if (supportTicket) {
        selectSupportTicket(supportTicket.dataset.managerTicketId);
        return;
      }

      const supportAction = event.target.closest('[data-manager-ticket-action]');
      if (supportAction) {
        updateSupportTicket(supportAction.dataset.managerTicketAction);
        return;
      }

      const promoEditClose = event.target.closest('[data-admin-promo-edit-close]');
      if (promoEditClose || event.target.id === 'adminPromoEditOverlay') {
        closePromoEdit();
        return;
      }

      const promoEdit = event.target.closest('[data-admin-promo-edit]');
      if (promoEdit) {
        openPromoEdit(promoEdit.dataset.adminPromoEdit);
        return;
      }

      const promoDisable = event.target.closest('[data-admin-promo-disable]');
      if (promoDisable) {
        disablePromo(promoDisable.dataset.adminPromoDisable);
        return;
      }

      const promoRow = event.target.closest('[data-admin-promo-id]');
      if (promoRow) {
        selectPromo(promoRow.dataset.adminPromoId);
        return;
      }

      const action = event.target.closest('[data-admin-action][data-withdrawal-id]');
      if (action) {
        runWithdrawalAction(action.dataset.adminAction, action.dataset.withdrawalId);
        return;
      }

      const userButton = event.target.closest('[data-admin-user-id]');
      if (userButton) {
        selectUser(userButton.dataset.adminUserId);
        return;
      }

      const userTab = event.target.closest('[data-admin-user-tab]');
      if (userTab) {
        switchUserPanel(userTab.dataset.adminUserTab);
        return;
      }

      const userPage = event.target.closest('[data-admin-user-page]');
      if (userPage) {
        loadUsers(Number(userPage.dataset.adminUserPage || 0));
        return;
      }

      const loadMoreButton = event.target.closest('[data-admin-load-more]');
      if (loadMoreButton) {
        loadMore(loadMoreButton.dataset.adminLoadMore);
      }
    });

    document.getElementById('adminRefreshAll')?.addEventListener('click', refreshActiveTab);
    document.getElementById('adminUsersRefresh')?.addEventListener('click', () => loadUsers(false));
    document.getElementById('adminUserSearch')?.addEventListener('input', () => {
      window.clearTimeout(userSearchTimer);
      userSearchTimer = window.setTimeout(() => loadUsers(false), 250);
    });
    document.getElementById('adminBalanceForm')?.addEventListener('submit', event => {
      event.preventDefault();
      adjustBalance(event.submitter?.dataset.adminBalance || 'credit');
    });
    document.getElementById('adminPromoForm')?.addEventListener('submit', createPromo);
    document.getElementById('adminPromoCode')?.addEventListener('input', event => {
      const next = event.target.value.toUpperCase().replace(/\s+/g, '');
      if (event.target.value !== next) event.target.value = next;
    });
    document.getElementById('adminPromoEditForm')?.addEventListener('submit', savePromoEdit);
    document.getElementById('adminPromoRewardType')?.addEventListener('change', () => syncPromoRewardFields('adminPromo'));
    document.getElementById('adminPromoEditRewardType')?.addEventListener('change', () => syncPromoRewardFields('adminPromoEdit'));
    ['adminPromoAmount', 'adminPromoPercent', 'adminPromoMaxBonus', 'adminPromoMinDeposit'].forEach(id => {
      document.getElementById(id)?.addEventListener('input', () => renderPromoPreview('adminPromo'));
    });
    ['adminPromoEditAmount', 'adminPromoEditPercent', 'adminPromoEditMaxBonus', 'adminPromoEditMinDeposit'].forEach(id => {
      document.getElementById(id)?.addEventListener('input', () => renderPromoPreview('adminPromoEdit'));
    });
    document.getElementById('adminPromoRedemptionsRefresh')?.addEventListener('click', () => loadPromoDetailRedemptions(false));
    document.getElementById('adminSupportRefresh')?.addEventListener('click', () => loadSupport(false));
    document.getElementById('adminSupportCategory')?.addEventListener('change', () => {
      selectedSupportTicket = null;
      renderSupportDetail(null);
      loadSupport(false);
    });
    document.getElementById('adminUserHistoryRefresh')?.addEventListener('click', () => loadSelectedUserDetail());
    ['adminTxType', 'adminTxStatus', 'adminTxFrom', 'adminTxTo'].forEach(id => {
      document.getElementById(id)?.addEventListener('change', () => loadSelectedUserDetail({ rounds: false, promoRedemptions: false }));
    });
    ['adminRoundGame', 'adminRoundStatus', 'adminRoundFrom', 'adminRoundTo'].forEach(id => {
      document.getElementById(id)?.addEventListener(id === 'adminRoundGame' ? 'input' : 'change', () => {
        window.clearTimeout(userSearchTimer);
        userSearchTimer = window.setTimeout(() => loadSelectedUserDetail({ transactions: false, promoRedemptions: false }), 250);
      });
    });
    document.getElementById('adminAuditRefresh')?.addEventListener('click', () => loadAudit(false));
    document.getElementById('adminAuditApply')?.addEventListener('click', () => loadAudit(false));
    document.getElementById('adminAuditReset')?.addEventListener('click', () => {
      ['adminAuditAction', 'adminAuditActor', 'adminAuditTarget'].forEach(id => {
        const input = document.getElementById(id);
        if (input) input.value = '';
      });
      ['adminAuditFrom', 'adminAuditTo'].forEach(id => setDateInput(document.getElementById(id), ''));
      loadAudit(false);
    });
    ['adminAuditAction', 'adminAuditActor', 'adminAuditTarget', 'adminAuditFrom', 'adminAuditTo'].forEach(id => {
      document.getElementById(id)?.addEventListener('input', () => {
        window.clearTimeout(auditSearchTimer);
        auditSearchTimer = window.setTimeout(() => loadAudit(false), 250);
      });
      document.getElementById(id)?.addEventListener('change', () => loadAudit(false));
    });
  }

  function init() {
    if (document.body.dataset.page !== 'admin') return;
    setupDateInputs();
    syncPromoRewardFields();
    bindEvents();
    store.subscribe((next, prev, action) => {
      if (next.lang !== prev.lang) {
        syncDateInputs();
        renderSelectedUser();
        if (selectedUser) renderUserProfile(selectedUser);
        renderUserTransactions(paging.transactions.items);
        renderUserRounds(paging.rounds.items);
        renderUserPromoRedemptions(paging.promoRedemptions.items);
        renderAudit(paging.audit.items);
        renderWithdrawals(paging.withdrawals.items);
        renderPromos(paging.promos.items);
        renderSupportTickets(paging.support.items);
        if (selectedSupportTicket) selectSupportTicket(selectedSupportTicket.id);
      }
      const nextUser = next.currentUser || {};
      const prevUser = prev.currentUser || {};
      if (nextUser.id !== prevUser.id || nextUser.isAdmin !== prevUser.isAdmin || action === 'auth:restore') {
        refreshActiveTab();
      }
    });
    switchTab(activeTab);
  }

  B.admin = { init };
})(window);
