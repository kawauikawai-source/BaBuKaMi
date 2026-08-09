(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  const BETS = [5, 10, 25, 100];
  const ACTIVE_ROUND_KEY = 'bk_kawaui_fortune_active_round';
  const CRASH_START_MULTIPLIER = 0.8;
  const CRASH_CASHOUT_MIN_MULTIPLIER = 1;
  const CRASH_CHART_MAX_MULTIPLIER = 50;
  const CRASH_GROWTH_SECONDS = 8;
  let selectedBet = 5;
  let activeRoundId = null;
  let flying = false;
  let pollTimer = null;
  let visualFrame = null;
  let visualDone = null;
  let visualTween = null;
  let visualMultiplier = 1;
  let targetMultiplier = 1;
  let visualStatus = '';
  let activeStartedAtMs = null;
  let recent = [];
  let settledRoundIds = new Set();
  let cashoutPending = false;
  let cashoutLocked = false;
  let pendingCashoutVisualMultiplier = null;
  let lastControlPaintAt = 0;

  function currentBalance() {
    return Number(store.getDisplayUser().balance || 0);
  }

  function multiplierValue(value) {
    const next = Number(value || CRASH_START_MULTIPLIER);
    return Number.isFinite(next) ? Math.max(CRASH_START_MULTIPLIER, next) : CRASH_START_MULTIPLIER;
  }

  function multiplierLabel(value) {
    return multiplierValue(value).toFixed(2);
  }

  function parseStartedAtMs(value) {
    const parsed = Date.parse(value || '');
    return Number.isFinite(parsed) ? parsed : null;
  }

  function liveActiveMultiplier() {
    if (!activeStartedAtMs) return visualMultiplier;
    const elapsedSeconds = Math.max(0, (Date.now() - activeStartedAtMs) / 1000);
    return Math.max(CRASH_START_MULTIPLIER, CRASH_START_MULTIPLIER * Math.exp(elapsedSeconds / CRASH_GROWTH_SECONDS));
  }

  function naturalFlightDurationMs(fromMultiplier, toMultiplier) {
    const from = multiplierValue(fromMultiplier);
    const to = multiplierValue(toMultiplier);
    if (to <= from) return 420;
    return Math.max(420, Math.log(to / from) * CRASH_GROWTH_SECONDS * 1000);
  }

  function persistActiveRound(roundId) {
    try {
      if (roundId) global.sessionStorage.setItem(ACTIVE_ROUND_KEY, String(roundId));
      else global.sessionStorage.removeItem(ACTIVE_ROUND_KEY);
    } catch (err) {
      // Session storage is a best-effort restore helper only.
    }
  }

  function storedActiveRound() {
    try {
      return global.sessionStorage.getItem(ACTIVE_ROUND_KEY);
    } catch (err) {
      return null;
    }
  }

  function renderBalance() {
    const user = store.getDisplayUser();
    ui.setText('crash-balance', ui.formatMoney(user.balance, user.currency));
  }

  function renderBets() {
    const mount = document.getElementById('crashBets');
    if (!mount) return;
    mount.innerHTML = BETS.map(value => `
      <button class="chip-btn ${value === selectedBet ? 'selected' : ''}" type="button" data-crash-bet="${value}">
        ${ui.formatMoney(value)}
      </button>
    `).join('');
    setControls();
  }

  function renderRecent() {
    ui.renderGameHistory?.('crashRecent', recent, ui.t('crash_recent_empty'));
  }

  function setResultMessage(message, state) {
    const resultBox = document.getElementById('crashResult');
    if (!resultBox) return;
    resultBox.classList.toggle('win', state === 'win');
    resultBox.classList.toggle('loss', state === 'loss');
    resultBox.textContent = message;
  }

  function setControls() {
    const action = document.getElementById('crashAction');
    if (action) {
      const multiplierLocked = flying && !cashoutLocked && multiplierValue(visualMultiplier) < CRASH_CASHOUT_MIN_MULTIPLIER;
      action.disabled = cashoutPending || cashoutLocked || multiplierLocked;
      action.classList.toggle('is-cashout', flying && !cashoutLocked && !multiplierLocked);
      action.classList.toggle('is-locked', cashoutLocked);
      let label = '';
      if (cashoutLocked) {
        label = ui.t('crash_cashout_locked_short');
      } else if (cashoutPending) {
        label = ui.t('crash_cashout_pending');
      } else if (multiplierLocked) {
        label = ui.t('crash_cashout_min', { multiplier: multiplierLabel(CRASH_CASHOUT_MIN_MULTIPLIER) });
      } else if (flying) {
        label = ui.t('crash_cashout_at', { multiplier: multiplierLabel(visualMultiplier) });
      } else {
        label = ui.t('crash_start_bet', { amount: ui.formatMoney(selectedBet) });
      }
      action.textContent = String(label || '').toUpperCase();
    }
    document.querySelectorAll('[data-crash-bet]').forEach(btn => {
      btn.disabled = flying || cashoutLocked;
    });
  }

  function drawVisual(multiplier, status) {
    const value = multiplierValue(multiplier);
    const progress = Math.min(1, Math.max(0, Math.log(value) / Math.log(CRASH_CHART_MAX_MULTIPLIER)));
    const chart = document.getElementById('crashChart');
    const line = document.getElementById('crashLinePath');
    const fill = document.getElementById('crashFillPath');
    const dot = document.getElementById('crashDot');
    const label = document.getElementById('crashMultiplier');
    if (label) label.textContent = multiplierLabel(value) + 'x';
    if (flying && !cashoutPending) {
      const now = Date.now();
      if (now - lastControlPaintAt > 120) {
        lastControlPaintAt = now;
        setControls();
      }
    }

    const startX = 80;
    const startY = 360;
    const maxX = 940;
    const maxY = 62;
    const drawnProgress = Math.max(0.018, progress);
    const curvePower = 1.58;
    const launchLift = 0.055;
    const pointCount = 80;
    const points = [];
    for (let index = 0; index <= pointCount; index += 1) {
      const t = drawnProgress * (index / pointCount);
      const x = startX + (maxX - startX) * t;
      const yProgress = launchLift * t + (1 - launchLift) * Math.pow(t, curvePower);
      const y = startY - (startY - maxY) * yProgress;
      points.push([x, y]);
    }
    const [endX, endY] = points[points.length - 1];
    const path = points.map(([x, y], index) => {
      const command = index === 0 ? 'M' : 'L';
      return `${command}${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(' ');

    if (line) line.setAttribute('d', path);
    if (fill) {
      fill.setAttribute(
        'd',
        `${path} L${endX.toFixed(1)} ${startY} L${startX} ${startY} Z`
      );
    }
    if (dot) {
      dot.setAttribute('cx', endX.toFixed(1));
      dot.setAttribute('cy', endY.toFixed(1));
    }
    if (chart) {
      chart.classList.toggle('is-flying', status === 'active');
      chart.classList.toggle('is-cashout-locked', status === 'cashout_locked');
      chart.classList.toggle('is-crashed', status === 'lost' || status === 'cashout_crashed');
      chart.classList.toggle('is-cashed', status === 'completed');
      chart.classList.toggle('is-cashed-crash', status === 'cashout_crashed');
      const isLive = status === 'active' || status === 'cashout_locked';
      chart.classList.toggle('is-overdrive-warmup', value >= 8 && value < 10 && isLive);
      chart.classList.toggle('is-overdrive', value >= 10 && isLive);
    }
  }

  function stopVisualLoop() {
    if (visualFrame) global.cancelAnimationFrame(visualFrame);
    visualFrame = null;
    visualDone = null;
    visualTween = null;
    activeStartedAtMs = null;
  }

  function freezeVisual(status) {
    if (visualStatus === 'active' && activeStartedAtMs) {
      visualMultiplier = liveActiveMultiplier();
    }
    if (visualFrame) global.cancelAnimationFrame(visualFrame);
    visualFrame = null;
    visualDone = null;
    visualTween = null;
    activeStartedAtMs = null;
    targetMultiplier = visualMultiplier;
    drawVisual(visualMultiplier, status || visualStatus);
  }

  function animateVisual(now) {
    if (visualStatus === 'active' && activeStartedAtMs && !visualTween) {
      visualMultiplier = liveActiveMultiplier();
      targetMultiplier = visualMultiplier;
      drawVisual(visualMultiplier, visualStatus);
      visualFrame = global.requestAnimationFrame(animateVisual);
      return;
    }

    if (visualTween) {
      const elapsed = Math.max(0, now - visualTween.startedAt);
      const progress = Math.min(1, elapsed / visualTween.duration);
      visualMultiplier = visualTween.mode === 'exponential' && visualTween.to > visualTween.from
        ? visualTween.from * Math.exp(Math.log(visualTween.to / visualTween.from) * progress)
        : visualTween.from + (visualTween.to - visualTween.from) * progress;
      if (progress >= 1) {
        visualMultiplier = visualTween.to;
        visualTween = null;
      }
      drawVisual(visualMultiplier, visualStatus);
      if (visualTween) {
        visualFrame = global.requestAnimationFrame(animateVisual);
        return;
      }
      visualFrame = null;
      if (visualDone) {
        const done = visualDone;
        visualDone = null;
        done();
      }
      return;
    }

    const delta = targetMultiplier - visualMultiplier;
    visualMultiplier += delta * 0.08;
    if (Math.abs(delta) < 0.004) visualMultiplier = targetMultiplier;
    drawVisual(visualMultiplier, visualStatus);
    if (visualMultiplier !== targetMultiplier || visualStatus === 'active') {
      visualFrame = global.requestAnimationFrame(animateVisual);
    } else {
      visualFrame = null;
      if (visualDone) {
        const done = visualDone;
        visualDone = null;
        done();
      }
    }
  }

  function setVisual(multiplier, status, options) {
    const value = multiplierValue(multiplier);
    const settings = options || {};
    visualStatus = status || '';
    if (visualStatus !== 'active') activeStartedAtMs = null;
    targetMultiplier = value;
    visualDone = typeof settings.onDone === 'function' ? settings.onDone : null;
    if (settings.snap) {
      stopVisualLoop();
      visualMultiplier = value;
      drawVisual(value, visualStatus);
      if (typeof settings.onDone === 'function') settings.onDone();
      return;
    }
    if (settings.duration) {
      if (visualFrame) global.cancelAnimationFrame(visualFrame);
      visualTween = {
        from: multiplierValue(settings.from || visualMultiplier),
        to: value,
        duration: Math.max(240, Number(settings.duration) || 900),
        startedAt: global.performance && global.performance.now ? global.performance.now() : Date.now(),
        mode: settings.mode || 'linear'
      };
      visualFrame = global.requestAnimationFrame(animateVisual);
      return;
    }
    if (!visualFrame) visualFrame = global.requestAnimationFrame(animateVisual);
  }

  function setActiveVisual(result, snap) {
    const startedAt = parseStartedAtMs(result && result.started_at);
    if (startedAt) activeStartedAtMs = startedAt;
    visualStatus = 'active';
    targetMultiplier = liveActiveMultiplier();
    if (snap) {
      if (visualFrame) global.cancelAnimationFrame(visualFrame);
      visualFrame = null;
      visualMultiplier = targetMultiplier;
      drawVisual(visualMultiplier, visualStatus);
    }
    if (!visualFrame) visualFrame = global.requestAnimationFrame(animateVisual);
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error), 'err');
    return true;
  }

  function stopPolling() {
    if (pollTimer) global.clearInterval(pollTimer);
    pollTimer = null;
  }

  function finishRound(result) {
    const roundId = String(result.round_id || activeRoundId || '');
    const alreadyRendered = roundId && settledRoundIds.has(roundId);
    stopPolling();
    flying = false;
    cashoutPending = false;
    cashoutLocked = false;
    activeRoundId = null;
    persistActiveRound(null);
    setControls();

    const status = result.status || 'lost';
    const multiplier = result.cashout_multiplier || result.crash_multiplier || result.current_multiplier || 1;
    const net = Number(result.net || 0);
    setResultMessage(
      status === 'completed'
        ? ui.t('crash_win', { multiplier: multiplierLabel(multiplier), amount: ui.formatMoney(Math.max(0, Number(result.total_win || 0))) })
        : ui.t('crash_lost', { multiplier: multiplierLabel(multiplier) }),
      status === 'completed' && net > 0 ? 'win' : (status === 'lost' ? 'loss' : '')
    );
    if (status === 'lost') {
      const lossMultiplier = Math.max(CRASH_CASHOUT_MIN_MULTIPLIER, multiplierValue(multiplier));
      setVisual(lossMultiplier, 'lost', { snap: true });
    } else {
      setVisual(multiplier, status);
    }
    store.commitGameWallet(result, 'game:crash:settled');
    B.audio?.play?.(status === 'completed' && net > 0 ? 'win' : 'loss');
    renderBalance();
    if (!alreadyRendered) {
      if (roundId) {
        settledRoundIds.add(roundId);
        if (settledRoundIds.size > 24) settledRoundIds = new Set(Array.from(settledRoundIds).slice(-12));
      }
      recent.unshift({
        state: status === 'completed' && net > 0 ? 'win' : 'loss',
        label: status === 'completed' && net > 0 ? '+' + ui.formatMoney(net) : ui.formatMoney(net),
        meta: status === 'completed' ? multiplierLabel(result.cashout_multiplier || multiplier) : multiplierLabel(multiplier)
      });
      recent = recent.slice(0, 8);
      renderRecent();
    }
  }

  function finishCashoutFlyout(result) {
    const cashoutMultiplier = result.cashout_multiplier || result.current_multiplier || 1;
    const crashMultiplier = result.crash_multiplier || cashoutMultiplier;
    const finalVisualMultiplier = Math.max(multiplierValue(crashMultiplier), multiplierValue(visualMultiplier));
    const net = Number(result.net || 0);
    const roundId = String(result.round_id || activeRoundId || '');
    const alreadyRendered = roundId && settledRoundIds.has(roundId);

    flying = false;
    cashoutPending = false;
    cashoutLocked = false;
    activeRoundId = null;
    persistActiveRound(null);
    setControls();
    setVisual(finalVisualMultiplier, 'cashout_crashed', { snap: true });
    setResultMessage(
      ui.t('crash_win_after_crash', {
        cashout: multiplierLabel(cashoutMultiplier),
        crash: multiplierLabel(crashMultiplier),
        amount: ui.formatMoney(Math.max(0, Number(result.total_win || 0)))
      }),
      net > 0 ? 'win' : ''
    );
    store.commitGameWallet(result, 'game:crash:settled');
    B.audio?.play?.(net > 0 ? 'win' : 'push');
    renderBalance();

    if (!alreadyRendered) {
      if (roundId) {
        settledRoundIds.add(roundId);
        if (settledRoundIds.size > 24) settledRoundIds = new Set(Array.from(settledRoundIds).slice(-12));
      }
      recent.unshift({
        state: net > 0 ? 'win' : 'loss',
        label: net > 0 ? '+' + ui.formatMoney(net) : ui.formatMoney(net),
        meta: multiplierLabel(cashoutMultiplier)
      });
      recent = recent.slice(0, 8);
      renderRecent();
    }
  }

  function playCashoutFlyout(result) {
    stopPolling();
    const cashoutMultiplier = result.cashout_multiplier || result.current_multiplier || 1;
    const crashMultiplier = result.crash_multiplier || cashoutMultiplier;
    const frozenMultiplier = pendingCashoutVisualMultiplier;
    pendingCashoutVisualMultiplier = null;
    cashoutPending = false;
    cashoutLocked = true;
    flying = true;
    setControls();
    setResultMessage(
      ui.t('crash_win_after_crash', {
        cashout: multiplierLabel(cashoutMultiplier),
        crash: multiplierLabel(crashMultiplier),
        amount: ui.formatMoney(Math.max(0, Number(result.total_win || 0)))
      }),
      'win'
    );

    const settle = () => {
      global.setTimeout(() => finishCashoutFlyout(result), 260);
    };
    const currentFlightMultiplier = multiplierValue(frozenMultiplier || visualMultiplier);
    const targetFlightMultiplier = Math.max(multiplierValue(crashMultiplier), currentFlightMultiplier);
    const flightDuration = naturalFlightDurationMs(currentFlightMultiplier, targetFlightMultiplier);
    setVisual(targetFlightMultiplier, 'cashout_locked', {
      from: currentFlightMultiplier,
      duration: flightDuration,
      mode: 'exponential',
      onDone: settle
    });

    global.setTimeout(() => {
      if (cashoutLocked && String(activeRoundId) === String(result.round_id)) finishCashoutFlyout(result);
    }, flightDuration + 900);
  }

  async function pollRound() {
    if (!activeRoundId) return;
    const result = await store.getDragonCrashRound(activeRoundId);
    if (showStoreError(result)) {
      stopPolling();
      stopVisualLoop();
      flying = false;
      cashoutPending = false;
      cashoutLocked = false;
      activeRoundId = null;
      setControls();
      return;
    }
    if (result.status === 'active') {
      setActiveVisual(result, false);
      setResultMessage(ui.t('crash_flying'), '');
      return;
    }
    finishRound(result);
  }

  function startPolling() {
    stopPolling();
    pollTimer = global.setInterval(pollRound, 300);
  }

  async function startRound() {
    if (flying) return;
    if (selectedBet > currentBalance()) {
      ui.showToast(ui.t('err_crash_balance'), 'err');
      return;
    }
    const result = await store.startDragonCrash(selectedBet);
    if (showStoreError(result)) return;
    B.audio?.play?.('drop');

    activeRoundId = result.round_id;
    persistActiveRound(activeRoundId);
    flying = true;
    cashoutPending = false;
    cashoutLocked = false;
    setControls();
    renderBalance();
    visualMultiplier = CRASH_START_MULTIPLIER;
    setActiveVisual(result, true);
    setResultMessage(ui.t('crash_flying'), '');
    startPolling();
  }

  async function cashout() {
    if (!flying || !activeRoundId || cashoutPending) return;
    if (multiplierValue(visualMultiplier) < CRASH_CASHOUT_MIN_MULTIPLIER) return;
    freezeVisual('cashout_locked');
    pendingCashoutVisualMultiplier = multiplierValue(visualMultiplier);
    cashoutPending = true;
    setControls();
    B.audio?.play?.('cashout');
    const result = await store.cashoutDragonCrash(activeRoundId);
    if (showStoreError(result)) {
      pendingCashoutVisualMultiplier = null;
      cashoutPending = false;
      setVisual(visualMultiplier, 'active');
      pollRound();
      setControls();
      return;
    }
    if (result.status === 'completed' && result.cashout_multiplier && result.crash_multiplier) {
      playCashoutFlyout(result);
      return;
    }
    finishRound(result);
  }

  async function restoreActiveRound() {
    const roundId = storedActiveRound();
    if (!roundId) return;
    activeRoundId = roundId;
    flying = true;
    cashoutPending = false;
    cashoutLocked = false;
    setControls();
    const result = await store.getDragonCrashRound(roundId);
    if (showStoreError(result)) {
      activeRoundId = null;
      flying = false;
      cashoutLocked = false;
      persistActiveRound(null);
      setControls();
      return;
    }
    if (result.status === 'active') {
      setActiveVisual(result, true);
      setResultMessage(ui.t('crash_flying'), '');
      startPolling();
      return;
    }
    finishRound(result);
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      const bet = event.target.closest('[data-crash-bet]');
      if (!bet || flying) return;
      selectedBet = Number(bet.dataset.crashBet || selectedBet);
      renderBets();
    });
    document.getElementById('crashAction')?.addEventListener('click', () => {
      if (flying) cashout();
      else startRound();
    });
  }

  function init() {
    if (document.body.dataset.page !== 'crash') return;
    renderBalance();
    renderBets();
    renderRecent();
    setVisual(CRASH_START_MULTIPLIER, '', { snap: true });
    setControls();
    bindEvents();
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        if (visualFrame) global.cancelAnimationFrame(visualFrame);
        visualFrame = null;
        return;
      }
      if (flying) {
        pollRound();
        if (!visualFrame) visualFrame = global.requestAnimationFrame(animateVisual);
      }
    });
    restoreActiveRound();
    store.subscribe(() => {
      if (!flying) renderBalance();
    });
    global.addEventListener('beforeunload', stopPolling);
    global.addEventListener('beforeunload', stopVisualLoop);
  }

  B.crash = { init };
})(window);
