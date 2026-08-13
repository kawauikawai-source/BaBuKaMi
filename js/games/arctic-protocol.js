(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;
  const BETS = [5, 10, 25, 100];

  let selectedBet = 5;
  let activeRound = null;
  let initialized = false;
  let busy = false;
  let loading = true;
  let timerFrame = 0;
  let timeoutSending = false;
  let timerWarningPlayed = false;
  let briefingView = 'event';
  let transitionTimer = 0;
  const parameterAnimationFrames = new Set();
  let parameterAnimationTimers = [];

  function lang() {
    return store.getState().lang === 'en' ? 'en' : 'ru';
  }

  function currentUser() {
    return store.getState().currentUser || null;
  }

  function currentBalance() {
    return Number(store.getDisplayUser().balance || 0);
  }

  function isRoundActive() {
    return Boolean(activeRound && activeRound.status === 'active');
  }

  function isBriefing() {
    return Boolean(activeRound && activeRound.phase === 'briefing');
  }

  function transitionRender(update) {
    if (typeof update === 'function') update();
    renderAll();

    const terminal = document.querySelector('.survival-terminal');
    const reducedMotion = global.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (!terminal || reducedMotion) return;

    if (transitionTimer) global.clearTimeout(transitionTimer);
    terminal.classList.remove('is-phase-entering');
    void terminal.offsetWidth;
    terminal.classList.add('is-phase-entering');
    transitionTimer = global.setTimeout(() => {
      terminal.classList.remove('is-phase-entering');
      transitionTimer = 0;
    }, 420);
  }

  function showError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error), 'err');
    return true;
  }

  function setCause(active) {
    const root = document.getElementById('survivalCause');
    if (!root) return;
    const title = root.querySelector('strong');
    const text = root.querySelector('p');
    if (active && activeRound) {
      title.textContent = activeRound.category_label || '';
      text.textContent = activeRound.cause || '';
    } else {
      title.textContent = ui.t('survival_idle_title');
      text.textContent = ui.t('survival_idle_text');
    }
    root.hidden = Boolean(activeRound && (activeRound.phase !== 'briefing' || briefingView !== 'event'));
  }

  function renderBalance() {
    ui.setText('survivalBalance', ui.formatMoney(currentBalance()));
    ui.setText('survivalPotential', ui.formatMoney(selectedBet * 6));
  }

  function renderBets() {
    const root = document.getElementById('survivalBets');
    if (!root) return;
    const locked = busy || loading || isRoundActive();
    root.innerHTML = BETS.map(value => `
      <button class="chip-btn${selectedBet === value ? ' active' : ''}" type="button"
        data-survival-bet="${value}" ${locked ? 'disabled' : ''}>${ui.formatMoney(value)}</button>
    `).join('');
  }

  function clearTimer() {
    if (timerFrame) cancelAnimationFrame(timerFrame);
    timerFrame = 0;
    timerWarningPlayed = false;
    const timer = document.getElementById('survivalTimer');
    timer?.classList.remove('is-warning', 'is-expired');
    timer?.style.setProperty('--timer-progress', '1');
    if (timer) timer.hidden = activeRound?.phase !== 'awaiting_choice';
  }

  async function sendTimeout() {
    if (timeoutSending || busy || !activeRound || activeRound.phase !== 'awaiting_choice') return;
    timeoutSending = true;
    busy = true;
    renderAll();
    const result = await store.timeoutArcticProtocol(activeRound.round_id, lang());
    if (result?.error === 'err_survival_timeout_not_due') {
      await new Promise(resolve => setTimeout(resolve, 120));
      busy = false;
      timeoutSending = false;
      startTimer();
      return;
    }
    const hasError = showError(result);
    busy = false;
    timeoutSending = false;
    if (!hasError) {
      B.audio?.play?.('loss');
      transitionRender(() => {
        activeRound = result;
      });
    } else {
      renderAll();
    }
  }

  function startTimer() {
    clearTimer();
    if (!activeRound || activeRound.phase !== 'awaiting_choice' || !activeRound.deadline_at) return;
    const deadline = Date.parse(activeRound.deadline_at);
    if (!Number.isFinite(deadline)) return;
    const total = 30000;
    const timer = document.getElementById('survivalTimer');
    const value = document.getElementById('survivalTimerValue');
    if (timer) timer.hidden = false;

    const tick = () => {
      if (!activeRound || activeRound.phase !== 'awaiting_choice') return;
      if (document.hidden) {
        timerFrame = 0;
        return;
      }
      const remaining = Math.max(0, deadline - Date.now());
      const seconds = Math.max(0, Math.ceil(remaining / 1000));
      if (value) value.textContent = String(seconds);
      timer?.style.setProperty('--timer-progress', String(Math.max(0, Math.min(1, remaining / total))));
      timer?.classList.toggle('is-warning', remaining > 0 && remaining <= 5000);
      if (remaining <= 5000 && remaining > 0 && !timerWarningPlayed) {
        timerWarningPlayed = true;
        B.audio?.play?.('card');
      }
      if (remaining <= 0) {
        timer?.classList.add('is-expired');
        timerFrame = 0;
        sendTimeout();
        return;
      }
      timerFrame = requestAnimationFrame(tick);
    };
    timerFrame = requestAnimationFrame(tick);
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && activeRound?.phase === 'awaiting_choice' && !timerFrame) startTimer();
  });

  function clearParameterAnimations() {
    parameterAnimationFrames.forEach(frame => cancelAnimationFrame(frame));
    parameterAnimationFrames.clear();
    parameterAnimationTimers.forEach(timer => global.clearTimeout(timer));
    parameterAnimationTimers = [];
  }

  function metricParts(value) {
    const match = String(value || '').trim().match(/^(-?\d+(?:[.,]\d+)?)\s*(%|°C)?$/u);
    if (!match) return null;
    return {
      number: Number(match[1].replace(',', '.')),
      decimals: (match[1].split(/[.,]/)[1] || '').length,
      suffix: match[2] || ''
    };
  }

  function animateParameter(node, item, index) {
    const value = node.querySelector('strong');
    const targetText = String(item.resolved_value || '').trim();
    if (!value || !targetText || targetText === String(item.value || '').trim()) return;
    node.classList.add('has-resolution');
    if (global.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      value.textContent = targetText;
      node.classList.add('is-resolved');
      return;
    }

    const sourceMetric = metricParts(item.value);
    const targetMetric = metricParts(targetText);
    const delay = 180 + index * 110;
    const timer = global.setTimeout(() => {
      node.classList.add('is-changing');
      if (!sourceMetric || !targetMetric || sourceMetric.suffix !== targetMetric.suffix) {
        node.classList.add('is-text-changing');
        const swapTimer = global.setTimeout(() => {
          value.textContent = targetText;
          node.classList.remove('is-changing', 'is-text-changing');
          node.classList.add('is-resolved');
        }, 190);
        parameterAnimationTimers.push(swapTimer);
        return;
      }

      const startedAt = performance.now();
      const duration = 950;
      const decimals = Math.max(sourceMetric.decimals, targetMetric.decimals);
      node.classList.add('is-metric-running');
      const requestTick = () => {
        const frame = requestAnimationFrame(now => {
          parameterAnimationFrames.delete(frame);
          tick(now);
        });
        parameterAnimationFrames.add(frame);
      };
      const tick = now => {
        const progress = Math.min(1, (now - startedAt) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = sourceMetric.number + (targetMetric.number - sourceMetric.number) * eased;
        value.textContent = `${current.toFixed(decimals)}${targetMetric.suffix}`;
        if (progress < 1) {
          requestTick();
          return;
        }
        value.textContent = targetText;
        node.classList.remove('is-changing', 'is-metric-running');
        node.classList.add('is-resolved');
      };
      requestTick();
    }, delay);
    parameterAnimationTimers.push(timer);
  }

  function buildParameters(items) {
    const root = document.getElementById('survivalParameters');
    if (!root) return;
    const signature = JSON.stringify(items || []);
    if (root.dataset.signature === signature) return;
    clearParameterAnimations();
    root.dataset.signature = signature;
    root.replaceChildren();
    (items || []).forEach((item, index) => {
      const node = document.createElement('div');
      node.dataset.parameterKey = item.key || '';
      const label = document.createElement('span');
      const value = document.createElement('strong');
      label.textContent = item.label || '';
      value.textContent = item.value || '';
      node.append(label, value);
      root.appendChild(node);
      if (item.resolved_value) animateParameter(node, item, index);
    });
  }

  function buildChoices(question) {
    const root = document.getElementById('survivalChoices');
    if (!root) return;
    root.hidden = activeRound?.phase === 'briefing';
    const signature = JSON.stringify({
      choices: question?.choices || [],
      phase: activeRound?.phase || '',
      selected: activeRound?.selected_choice_id || '',
      correct: activeRound?.correct_choice_id || ''
    });
    if (root.dataset.signature === signature) {
      root.querySelectorAll('[data-survival-choice]').forEach(button => {
        button.disabled = busy || activeRound?.phase !== 'awaiting_choice';
      });
      return;
    }
    root.dataset.signature = signature;
    root.replaceChildren();
    (question?.choices || []).forEach((choice, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.survivalChoice = choice.id;
      button.disabled = busy || activeRound?.phase !== 'awaiting_choice';
      const marker = document.createElement('span');
      marker.textContent = String(index + 1).padStart(2, '0');
      const text = document.createElement('strong');
      text.textContent = choice.text || '';
      button.append(marker, text);
      if (activeRound?.phase !== 'awaiting_choice') {
        if (choice.id === activeRound.correct_choice_id) button.classList.add('is-correct');
        if (choice.id === activeRound.selected_choice_id && choice.id !== activeRound.correct_choice_id) {
          button.classList.add('is-wrong');
        }
      }
      root.appendChild(button);
    });
  }

  function renderQuestion() {
    const questionRoot = document.getElementById('survivalQuestion');
    const resolution = document.getElementById('survivalResolution');
    const lost = activeRound?.status === 'lost';
    if (lost) {
      if (questionRoot) questionRoot.hidden = true;
      if (resolution) resolution.hidden = true;
      return;
    }
    const showQuestion = Boolean(
      activeRound &&
      activeRound.question &&
      (activeRound.phase !== 'briefing' || briefingView === 'dossier')
    );
    if (!showQuestion) {
      if (questionRoot) questionRoot.hidden = true;
      if (resolution) resolution.hidden = true;
      return;
    }
    if (questionRoot) questionRoot.hidden = false;
    questionRoot?.classList.toggle('is-dossier', activeRound.phase === 'briefing');
    ui.setText('survivalStageLabel', activeRound.question.stage_label || '');
    ui.setText('survivalQuestionTitle', activeRound.question.title || '');
    ui.setText('survivalQuestionPrompt', activeRound.question.prompt || '');
    buildParameters(activeRound.question.parameters);
    buildChoices(activeRound.question);

    const resolved = !['briefing', 'awaiting_choice'].includes(activeRound.phase);
    const hasResolvedParameters = Boolean(
      resolved && activeRound.question.parameters?.some(item => item.resolved_value)
    );
    questionRoot?.classList.toggle('has-parameter-resolution', hasResolvedParameters);
    if (resolution) resolution.hidden = !resolved;
    if (resolved) {
      const won = activeRound.status === 'completed';
      const lost = activeRound.status === 'lost';
      ui.setText(
        'survivalResolutionKicker',
        won ? ui.t('survival_protocol_survived') : (lost ? ui.t('survival_protocol_failed') : ui.t('survival_choice_correct'))
      );
      ui.setText(
        'survivalResolutionTitle',
        won ? ui.t('survival_win_title') : (lost ? ui.t('survival_loss_title') : ui.t('survival_correct_title'))
      );
      ui.setText('survivalExplanation', activeRound.explanation || '');
    }
  }

  function choiceText(choiceId) {
    return activeRound?.question?.choices?.find(choice => choice.id === choiceId)?.text || '';
  }

  function deathCauseText() {
    const explanation = String(activeRound?.explanation || '').trim();
    const separator = lang() === 'ru' ? 'Верный протокол:' : 'Correct protocol:';
    const separatorIndex = explanation.indexOf(separator);
    return separatorIndex >= 0
      ? explanation.slice(0, separatorIndex).trim()
      : explanation;
  }

  function renderDeathScreen() {
    const root = document.getElementById('survivalDeathScreen');
    if (!root) return;
    const lost = activeRound?.status === 'lost';
    root.hidden = !lost;
    if (!lost) return;

    const completedStages = Math.max(0, Number(activeRound.stage || 1) - 1);
    const selected = choiceText(activeRound.selected_choice_id);
    const correct = choiceText(activeRound.correct_choice_id);
    ui.setText('survivalDeathStage', ui.t('survival_death_stage', {
      stage: activeRound.stage || 1,
      completed: completedStages
    }));
    ui.setText(
      'survivalDeathDecision',
      selected || ui.t(activeRound.outcome === 'timeout' ? 'survival_death_timeout' : 'survival_death_unknown')
    );
    ui.setText('survivalDeathCause', deathCauseText() || ui.t('survival_death_unknown'));
    ui.setText('survivalDeathProtocol', correct || ui.t('survival_death_protocol_unavailable'));
  }

  function renderProgress() {
    const stage = activeRound ? Number(activeRound.stage || 1) : 0;
    ui.setText('survivalStageValue', `${stage} / 6`);
    document.getElementById('survivalStageTrack')?.style.setProperty('width', `${stage / 6 * 100}%`);
    ui.setText(
      'survivalCategory',
      activeRound ? String(activeRound.category_label || '').toUpperCase() : ui.t('survival_waiting_category')
    );

    document.querySelectorAll('[data-survival-section]').forEach(button => {
      const section = button.dataset.survivalSection;
      const decisionOpen = Boolean(activeRound && activeRound.phase !== 'briefing');
      const reached = section === 'event' ||
        (section === 'dossier' && Boolean(activeRound)) ||
        (section === 'decision' && decisionOpen);
      const active = activeRound
        ? (activeRound.phase === 'briefing' ? briefingView === section : section === 'decision')
        : section === 'event';
      button.classList.toggle('is-reached', reached);
      button.classList.toggle('active', active);
      button.disabled = !activeRound || !reached || (section === 'decision' && !decisionOpen);
    });
  }

  function renderBriefing() {
    const footer = document.getElementById('survivalBriefingFooter');
    const button = document.getElementById('survivalBriefingAction');
    const briefing = isBriefing();
    if (footer) footer.hidden = !briefing;
    if (!button || !briefing) return;
    button.disabled = busy;
    button.textContent = busy
      ? ui.t('survival_processing')
      : (briefingView === 'event'
        ? ui.t('survival_open_stage', { stage: activeRound.stage })
        : ui.t('survival_open_choices'));
  }

  function renderResult() {
    const root = document.getElementById('survivalResult');
    if (!root) return;
    const won = activeRound?.status === 'completed';
    root.hidden = !won;
    root.className = 'survival-result';
    if (!won) {
      root.textContent = '';
      return;
    }
    root.classList.add('win');
    root.textContent = `6.00x · ${ui.formatMoney(activeRound.total_win || 0)}`;
  }

  function renderAction() {
    const button = document.getElementById('survivalAction');
    if (!button) return;
    button.disabled = busy || loading || (!isRoundActive() && selectedBet > currentBalance());
    button.hidden = Boolean(activeRound && ['briefing', 'awaiting_choice'].includes(activeRound.phase));
    if (busy || loading) {
      button.textContent = ui.t('survival_processing');
    } else if (activeRound?.phase === 'resolved') {
      button.textContent = ui.t('survival_continue').toUpperCase();
    } else if (activeRound && activeRound.status !== 'active') {
      button.textContent = ui.t('survival_new_protocol').toUpperCase();
    } else {
      button.textContent = 'START';
    }
  }

  function renderStageState() {
    const stage = document.getElementById('survivalStage');
    if (!stage) return;
    stage.className = 'survival-stage';
    const stageNumber = activeRound ? Number(activeRound.stage || 1) : 0;
    if (stageNumber) stage.classList.add(`stage-${stageNumber}`);
    if (activeRound?.phase === 'resolved') stage.classList.add('is-correct');
    if (activeRound?.phase === 'briefing') stage.classList.add('is-briefing');
    if (activeRound?.status === 'lost') stage.classList.add('is-loss');
    if (activeRound?.status === 'completed') stage.classList.add('is-win');
    if (busy) stage.classList.add('is-busy');
    stage.dataset.category = activeRound?.category_key || 'idle';
    stage.dataset.briefingView = isBriefing() ? briefingView : 'decision';
  }

  function renderAll() {
    renderBalance();
    renderBets();
    setCause(Boolean(activeRound));
    renderProgress();
    renderQuestion();
    renderDeathScreen();
    renderBriefing();
    renderResult();
    renderAction();
    renderStageState();
    if (activeRound?.phase === 'awaiting_choice' && !busy) startTimer();
    else clearTimer();
  }

  async function startRound() {
    if (busy || loading || isRoundActive()) return;
    if (selectedBet > currentBalance()) {
      ui.showToast(ui.t('err_survival_balance'), 'err');
      return;
    }
    busy = true;
    renderAll();
    const result = await store.startArcticProtocol(selectedBet, lang());
    busy = false;
    if (showError(result)) {
      renderAll();
      return;
    }
    B.audio?.play?.('drop');
    transitionRender(() => {
      activeRound = result;
      briefingView = 'event';
    });
  }

  async function openBriefing() {
    if (busy || !isBriefing()) return;
    if (briefingView === 'event') {
      B.audio?.play?.('card');
      transitionRender(() => {
        briefingView = 'dossier';
      });
      return;
    }
    busy = true;
    renderAll();
    const result = await store.readyArcticProtocol(activeRound.round_id, lang());
    busy = false;
    if (showError(result)) {
      renderAll();
      return;
    }
    B.audio?.play?.('card');
    transitionRender(() => {
      activeRound = result;
      briefingView = 'decision';
    });
  }

  async function choose(choiceId) {
    if (busy || !activeRound || activeRound.phase !== 'awaiting_choice') return;
    busy = true;
    clearTimer();
    renderAll();
    const result = await store.chooseArcticProtocol(activeRound.round_id, choiceId, lang());
    busy = false;
    if (showError(result)) {
      renderAll();
      return;
    }
    if (result.status === 'completed') B.audio?.play?.('win');
    else if (result.status === 'lost') B.audio?.play?.('loss');
    else B.audio?.play?.('cashout');
    transitionRender(() => {
      activeRound = result;
    });
  }

  async function continueRound() {
    if (busy || !activeRound || activeRound.phase !== 'resolved') return;
    busy = true;
    renderAll();
    const result = await store.continueArcticProtocol(activeRound.round_id, lang());
    busy = false;
    if (showError(result)) {
      renderAll();
      return;
    }
    B.audio?.play?.('card');
    transitionRender(() => {
      activeRound = result;
      if (result.phase === 'briefing') briefingView = 'event';
    });
  }

  async function loadActive(options) {
    if (!currentUser()) return;
    loading = true;
    if (!(options && options.silent)) renderAll();
    const result = await store.getActiveArcticProtocol(lang());
    loading = false;
    if (showError(result)) {
      renderAll();
      return;
    }
    activeRound = result || null;
    if (activeRound?.phase === 'briefing') briefingView = 'event';
    if (activeRound && activeRound.status !== 'active') {
      store.commitGameWallet(activeRound, 'game:survival:restored');
    }
    renderAll();
  }

  function bindEvents() {
    document.getElementById('survivalBets')?.addEventListener('click', event => {
      const button = event.target.closest('[data-survival-bet]');
      if (!button || busy || loading || isRoundActive()) return;
      selectedBet = Number(button.dataset.survivalBet || selectedBet);
      renderAll();
      B.audio?.play?.('chip');
    });
    document.getElementById('survivalChoices')?.addEventListener('click', event => {
      const button = event.target.closest('[data-survival-choice]');
      if (button) choose(button.dataset.survivalChoice);
    });
    document.getElementById('survivalAction')?.addEventListener('click', () => {
      if (activeRound?.phase === 'resolved') continueRound();
      else startRound();
    });
    document.getElementById('survivalBriefingAction')?.addEventListener('click', openBriefing);
    document.getElementById('survivalBriefingNav')?.addEventListener('click', event => {
      const button = event.target.closest('[data-survival-section]');
      if (!button || !isBriefing() || button.disabled) return;
      const section = button.dataset.survivalSection;
      if (section === 'event' || section === 'dossier') {
        transitionRender(() => {
          briefingView = section;
        });
      }
    });
    document.addEventListener('keydown', event => {
      if (event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
      if (activeRound?.phase === 'awaiting_choice' && ['1', '2', '3'].includes(event.key)) {
        const choice = activeRound.question?.choices?.[Number(event.key) - 1];
        if (choice) choose(choice.id);
      }
      if (event.key === 'Enter' && activeRound?.phase === 'resolved') continueRound();
      else if (event.key === 'Enter' && isBriefing()) openBriefing();
    });
  }

  async function refreshLanguage() {
    if (!activeRound) {
      renderAll();
      return;
    }
    const result = await store.getArcticProtocolRound(activeRound.round_id, lang());
    if (!showError(result)) activeRound = result;
    renderAll();
  }

  async function init() {
    if (document.body.dataset.page !== 'survival' || initialized) return;
    initialized = true;
    renderAll();
    bindEvents();
    if (!currentUser()) {
      loading = false;
      renderAll();
      return;
    }
    const managerState = await store.getManagerState?.();
    if (managerState && !managerState.error) {
      BETS.splice(0, BETS.length, ...store.getManagerBetOptions('arctic-protocol'));
      if (selectedBet === 100) selectedBet = BETS[BETS.length - 1];
      renderBets();
    }
    await loadActive();
    store.subscribe((next, previous, action) => {
      if (action === 'lang:set' || next.lang !== previous.lang) {
        refreshLanguage();
        return;
      }
      if (!busy && Number(next.balance || 0) !== Number(previous.balance || 0)) {
        renderBalance();
        renderAction();
      }
    });
  }

  B.survival = { init };
})(window);
