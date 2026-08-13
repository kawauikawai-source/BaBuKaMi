(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  let settings = null;
  let selectedReminder = 30;
  let unlimited = true;
  let timer = null;
  let reminderShownFor = 0;
  const sessionKey = 'bk_game_control_session_started';

  function el(id) { return document.getElementById(id); }
  function t(key, vars) { return B.ui?.t(key, vars) || key; }
  function stateUser() { return B.store?.getState?.().currentUser || null; }
  function money(cents) { return B.ui?.formatMoney((Number(cents) || 0) / 100) || '€0.00'; }

  function sessionStartedAt() {
    let value = Number(sessionStorage.getItem(sessionKey));
    if (!Number.isFinite(value) || value <= 0) {
      value = Date.now();
      sessionStorage.setItem(sessionKey, String(value));
    }
    return value;
  }

  function formatDuration(ms) {
    const seconds = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return [hours, minutes, rest].map(value => String(value).padStart(2, '0')).join(':');
  }

  function setBusy(busy) {
    document.querySelectorAll('#gameControlTerminal button,#gameControlTerminal input').forEach(control => {
      if (!control.closest('#gameControlGate')) control.disabled = busy;
    });
    if (!busy && unlimited && el('gameControlLimit')) el('gameControlLimit').disabled = true;
  }

  function render() {
    const root = el('gameControlTerminal');
    if (!root) return;
    const user = stateUser();
    const gate = el('gameControlGate');
    if (gate) gate.hidden = Boolean(user);
    root.classList.toggle('is-guest', !user);
    if (!user) {
      el('gameControlConnection').textContent = t('game_control_local');
      el('gameControlMode').textContent = t('game_control_login_required');
      el('gameControlHeadline').textContent = t('game_control_gate_title');
      el('gameControlSummary').textContent = t('game_control_gate_text');
      return;
    }
    if (!settings) return;

    const paused = Boolean(settings.is_paused);
    root.classList.toggle('is-paused', paused);
    el('gameControlConnection').textContent = t('game_control_synced');
    el('gameControlMode').textContent = paused ? t('game_control_paused') : t('game_control_active');
    el('gameControlHeadline').textContent = paused ? t('game_control_pause_active_title') : t('game_control_normal_title');
    el('gameControlSummary').textContent = paused
      ? t('game_control_pause_active_text', { time: new Date(settings.paused_until).toLocaleString(B.store.getState().lang === 'ru' ? 'ru-RU' : 'en-GB') })
      : t('game_control_normal_text');

    const spent = Number(settings.daily_bet_spent_cents) || 0;
    const limit = settings.daily_bet_limit_cents == null ? null : Number(settings.daily_bet_limit_cents);
    const percent = limit ? Math.min(100, spent / limit * 100) : 0;
    el('gameControlUsageValue').textContent = limit == null ? money(spent) : `${money(spent)} / ${money(limit)}`;
    el('gameControlUsageFill').style.width = `${percent}%`;
    el('gameControlRemaining').textContent = limit == null
      ? t('game_control_no_limit_status')
      : t('game_control_remaining', { amount: money(Math.max(limit - spent, 0)) });
    el('gameControlResume').hidden = !paused;
  }

  function renderInputs() {
    if (!settings) return;
    unlimited = settings.daily_bet_limit_cents == null;
    selectedReminder = Number(settings.reminder_minutes) || 0;
    const input = el('gameControlLimit');
    if (input) {
      input.value = unlimited ? '' : String(Number(settings.daily_bet_limit_cents) / 100);
      input.disabled = unlimited;
    }
    el('gameControlUnlimited')?.classList.toggle('active', unlimited);
    document.querySelectorAll('#gameControlReminder [data-minutes]').forEach(button => {
      button.classList.toggle('active', Number(button.dataset.minutes) === selectedReminder);
    });
  }

  async function load() {
    if (!el('gameControlTerminal')) return;
    if (!stateUser()) {
      settings = null;
      render();
      return;
    }
    setBusy(true);
    const result = await B.store.getGameControl();
    setBusy(false);
    if (!result || result.ok === false) {
      el('gameControlConnection').textContent = t('state_error_title');
      el('gameControlHeadline').textContent = t('game_control_error_title');
      el('gameControlSummary').textContent = t(result?.error || 'err_api_unavailable');
      return;
    }
    settings = result;
    renderInputs();
    render();
  }

  async function save(event) {
    event.preventDefault();
    const value = Number(el('gameControlLimit')?.value);
    if (!unlimited && (!Number.isFinite(value) || value < 5)) {
      B.ui.showToast(t('game_control_limit_invalid'), 'err');
      return;
    }
    setBusy(true);
    const result = await B.store.updateGameControl({
      daily_bet_limit_cents: unlimited ? null : Math.round(value * 100),
      reminder_minutes: selectedReminder
    });
    setBusy(false);
    if (!result || result.ok === false) {
      B.ui.showToast(t(result?.error || 'err_api_unavailable'), 'err');
      return;
    }
    settings = result;
    renderInputs();
    render();
    const state = el('gameControlSaveState');
    if (state) state.textContent = t('game_control_saved');
    B.ui.showToast(t('game_control_saved'));
  }

  async function pause(minutes) {
    const confirmed = await B.ui.confirmAction({
      title: t('game_control_pause_confirm_title'),
      message: t('game_control_pause_confirm_text', { duration: t(`game_control_duration_${minutes}`) }),
      cancelLabel: t('confirm_cancel'),
      okLabel: t('game_control_pause_confirm')
    });
    if (!confirmed) return;
    setBusy(true);
    const result = await B.store.pauseGameControl(minutes);
    setBusy(false);
    if (!result || result.ok === false) return B.ui.showToast(t(result?.error || 'err_api_unavailable'), 'err');
    settings = result;
    render();
    B.ui.showToast(t('game_control_pause_enabled'));
  }

  async function resume() {
    setBusy(true);
    const result = await B.store.resumeGameControl();
    setBusy(false);
    if (!result || result.ok === false) return B.ui.showToast(t(result?.error || 'err_api_unavailable'), 'err');
    settings = result;
    render();
    B.ui.showToast(t('game_control_pause_disabled'));
  }

  function bind(root) {
    if (!root || root.dataset.controlBound === '1') return;
    root.dataset.controlBound = '1';
    el('gameControlSettings')?.addEventListener('submit', save);
    el('gameControlUnlimited')?.addEventListener('click', () => {
      unlimited = !unlimited;
      el('gameControlLimit').disabled = unlimited;
      el('gameControlUnlimited').classList.toggle('active', unlimited);
      if (!unlimited) el('gameControlLimit').focus();
    });
    el('gameControlReminder')?.addEventListener('click', event => {
      const button = event.target.closest('[data-minutes]');
      if (!button) return;
      selectedReminder = Number(button.dataset.minutes);
      document.querySelectorAll('#gameControlReminder [data-minutes]').forEach(item => item.classList.toggle('active', item === button));
    });
    el('gameControlPauseActions')?.addEventListener('click', event => {
      const button = event.target.closest('[data-pause]');
      if (button) pause(Number(button.dataset.pause));
    });
    el('gameControlResume')?.addEventListener('click', resume);
  }

  function tick() {
    if (!el('gameControlTerminal')) return;
    const elapsed = Date.now() - sessionStartedAt();
    el('gameControlSession').textContent = formatDuration(elapsed);
    el('gameControlClock').textContent = new Date().toLocaleTimeString(B.store.getState().lang === 'ru' ? 'ru-RU' : 'en-GB');
    if (settings && selectedReminder > 0) {
      const interval = selectedReminder * 60 * 1000;
      const marker = Math.floor(elapsed / interval);
      if (marker > 0 && marker !== reminderShownFor) {
        reminderShownFor = marker;
        B.ui.showToast(t('game_control_break_reminder'));
      }
    }
  }

  function init() {
    const root = el('gameControlTerminal');
    if (!root) return;
    bind(root);
    load();
    if (!timer) timer = global.setInterval(tick, 1000);
    tick();
  }

  B.gameControl = { init, reload: load };
  B.store?.subscribe?.((next, prev) => {
    const nextId = next.currentUser?.apiId || '';
    const prevId = prev.currentUser?.apiId || '';
    if (nextId !== prevId) load();
    if (next.lang !== prev.lang) render();
  });
})(window);
