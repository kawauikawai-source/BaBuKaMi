(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  const ANTES = [5, 10, 25, 100];
  const SUIT_META = {
    S: { label: '&spades;', className: 'black' },
    C: { label: '&clubs;', className: 'black' },
    H: { label: '&hearts;', className: 'red' },
    D: { label: '&diams;', className: 'red' }
  };
  const HAND_RANK_EXAMPLES = [
    { key: 'holdem_hand_straight_flush', cards: ['AS', 'KS', 'QS', 'JS', 'TS'] },
    { key: 'holdem_hand_quads', cards: ['9S', '9H', '9D', '9C', 'AS'] },
    { key: 'holdem_hand_full_house', cards: ['AH', 'AD', 'AC', 'KD', 'KC'] },
    { key: 'holdem_hand_flush', cards: ['AS', 'JS', '8S', '5S', '2S'] },
    { key: 'holdem_hand_straight', cards: ['9S', '8H', '7D', '6C', '5S'] },
    { key: 'holdem_hand_trips', cards: ['QS', 'QH', 'QD', '8C', '3S'] },
    { key: 'holdem_hand_two_pair', cards: ['JS', 'JH', '4D', '4C', 'AS'] },
    { key: 'holdem_hand_pair', cards: ['KS', 'KH', '9D', '5C', '2S'] },
    { key: 'holdem_hand_high_card', cards: ['AS', 'QD', '9C', '6H', '3S'] }
  ];

  let selectedAnte = 5;
  let activeRound = null;
  let displayRound = null;
  let busy = false;
  let animating = false;
  let animationMode = '';
  let resultVisible = true;
  let cardAnimations = {};
  let recent = [];
  let initialized = false;

  function sleep(ms) {
    return new Promise(resolve => global.setTimeout(resolve, ms));
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value || null));
  }

  function roundForView() {
    return displayRound || activeRound;
  }

  function isActive() {
    return Boolean(activeRound && activeRound.status === 'active');
  }

  function money(value) {
    return ui.formatMoney(Number(value || 0));
  }

  function resultAmount(round) {
    return Number(round?.net || 0);
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error), 'err');
    return true;
  }

  function cardKey(id, index, hidden) {
    return id + ':' + index + ':' + (hidden ? 'hidden' : 'card');
  }

  function cardHTML(card, hidden, className, order) {
    const extra = className ? ' ' + className : '';
    const style = ` style="--card-order:${Number(order || 0)}"`;
    if (hidden) {
      return `<div class="holdem-card is-hidden${extra}"${style}><span></span><strong>B</strong><small></small></div>`;
    }
    const value = String(card || '').toUpperCase();
    const rank = value.slice(0, 1);
    const suit = value.slice(1, 2);
    const meta = SUIT_META[suit] || SUIT_META.S;
    return `
      <div class="holdem-card ${meta.className}${extra}"${style}>
        <span>${ui.escapeHTML(rank)}</span>
        <strong>${meta.label}</strong>
        <small>${ui.escapeHTML(rank)}</small>
      </div>
    `;
  }

  function miniCardHTML(card) {
    const value = String(card || '').toUpperCase();
    const rank = value.slice(0, 1);
    const suit = value.slice(1, 2);
    const meta = SUIT_META[suit] || SUIT_META.S;
    return `
      <span class="holdem-mini-card ${meta.className}">
        <span>${ui.escapeHTML(rank)}</span>
        <strong>${meta.label}</strong>
        <small>${ui.escapeHTML(rank)}</small>
      </span>
    `;
  }

  function renderRankGallery() {
    const mount = document.getElementById('holdemRankGrid');
    if (!mount) return;
    mount.innerHTML = HAND_RANK_EXAMPLES.map(example => `
      <div class="holdem-rank-row">
        <strong class="holdem-rank-name">${ui.escapeHTML(ui.t(example.key))}</strong>
        <div class="holdem-rank-cards">${example.cards.map(miniCardHTML).join('')}</div>
      </div>
    `).join('');
  }

  function cardsOf(cards, count) {
    return (Array.isArray(cards) ? cards : []).slice(0, count == null ? undefined : count).filter(Boolean);
  }

  function viewRound(source, overrides) {
    return Object.assign(clone(source) || {}, overrides || {});
  }

  function renderCards(id, cards, hiddenCount, expectedCount) {
    const mount = document.getElementById(id);
    if (!mount) return;
    const visible = Array.isArray(cards) ? cards : [];
    const hiddenTotal = Number(hiddenCount || 0);
    const hidden = Array.from({ length: hiddenTotal }, (_, index) => {
      const key = cardKey(id, index, true);
      return cardHTML('', true, cardAnimations[key] || '', visible.length + index);
    });
    const targetCount = Number(expectedCount || 0);
    const placeholders = Array.from({ length: Math.max(0, targetCount - visible.length - hidden.length) }, (_, index) => {
      const order = visible.length + hidden.length + index;
      return `<div class="holdem-card is-empty" style="--card-order:${order}"></div>`;
    });
    mount.innerHTML = visible.map((card, index) => {
      const key = cardKey(id, index, false);
      return cardHTML(card, false, cardAnimations[key] || '', index);
    }).concat(hidden, placeholders).join('');
  }

  function handLabel(hand) {
    if (!hand) return '';
    const key = hand.name_key || '';
    return key ? ui.t(key) : String(hand.name || '');
  }

  function renderBets() {
    const mount = document.getElementById('holdemBets');
    if (!mount) return;
    mount.innerHTML = ANTES.map(value => `
      <button class="chip-btn ${value === selectedAnte ? 'selected' : ''}" type="button" data-holdem-ante="${value}" ${isActive() || busy ? 'disabled' : ''}>
        <span>${money(value)}</span>
      </button>
    `).join('');
  }

  function renderBalance() {
    const user = store.getDisplayUser();
    const round = roundForView();
    ui.setText('holdem-balance', ui.formatMoney(user.balance, user.currency));
    ui.setText('holdemAnte', money(round ? Number(round.total_bet || selectedAnte) : selectedAnte));
    ui.setText('holdemCall', money(round ? Number(round.call_amount || selectedAnte * 2) : selectedAnte * 2));
  }

  function outcomeClass(round) {
    const outcome = String(round?.outcome || '');
    const net = resultAmount(round);
    if (outcome === 'push' || net === 0 && round && round.status !== 'active') return 'push';
    if (outcome === 'loss' || outcome === 'fold' || round?.status === 'lost' || net < 0) return 'loss';
    if (net > 0 || outcome === 'win' || outcome === 'dealer_not_qualified') return 'win';
    return '';
  }

  function setShellState(shell, round) {
    shell?.classList.remove('is-win', 'is-loss', 'is-push', 'is-active', 'is-dealing', 'is-showdown', 'is-folding');
    if (!shell) return;
    if (animationMode === 'deal') shell.classList.add('is-dealing');
    if (animationMode === 'showdown') shell.classList.add('is-showdown');
    if (animationMode === 'fold') shell.classList.add('is-folding');
    if (round && round.status === 'active') shell.classList.add('is-active');
    const cls = resultVisible ? outcomeClass(round) : '';
    if (cls) shell.classList.add('is-' + cls);
  }

  function renderResult() {
    const box = document.getElementById('holdemResult');
    const shell = document.getElementById('holdemTableShell');
    const round = roundForView();
    if (!box) return;
    box.className = 'holdem-result';
    setShellState(shell, round);

    if (!round) {
      box.textContent = ui.t('holdem_waiting');
      return;
    }
    if (!resultVisible) {
      box.textContent = animationMode === 'showdown'
        ? ui.t('holdem_showdown')
        : (animationMode === 'fold' ? ui.t('holdem_folding') : ui.t('holdem_dealing'));
      return;
    }
    if (round.status === 'active') {
      box.textContent = ui.t('holdem_decision', { call: money(round.call_amount || selectedAnte * 2) });
      return;
    }

    const cls = outcomeClass(round);
    if (cls) box.classList.add(cls);
    const vars = {
      amount: money(Math.abs(resultAmount(round))),
      player: handLabel(round.player_hand),
      dealer: handLabel(round.dealer_hand)
    };
    if (round.outcome === 'dealer_not_qualified') {
      box.textContent = ui.t('holdem_dealer_not_qualified', vars);
    } else if (cls === 'win') {
      box.textContent = ui.t('holdem_win', vars);
    } else if (cls === 'push') {
      box.textContent = ui.t('holdem_push', vars);
    } else if (round.outcome === 'fold') {
      box.textContent = ui.t('holdem_folded', vars);
    } else {
      box.textContent = ui.t('holdem_loss', vars);
    }
  }

  function renderRecent() {
    ui.renderGameHistory?.('holdemRecent', recent, ui.t('holdem_recent_empty'));
  }

  function renderActions() {
    const start = document.getElementById('holdemStart');
    const call = document.getElementById('holdemCallBtn');
    const fold = document.getElementById('holdemFoldBtn');
    if (!start || !call || !fold) return;
    const canAct = isActive() && !animating;
    start.hidden = isActive() || animating;
    call.hidden = !isActive() || animating;
    fold.hidden = !isActive() || animating;
    start.disabled = busy;
    call.disabled = busy || !canAct;
    fold.disabled = busy || !canAct;
    start.textContent = activeRound && activeRound.status !== 'active' ? ui.t('holdem_new_hand') : ui.t('holdem_start');
    call.textContent = ui.t('holdem_call_action', { amount: money(activeRound ? activeRound.call_amount : selectedAnte * 2) });
    fold.textContent = ui.t('holdem_fold_action');
  }

  function renderAll() {
    const round = roundForView();
    const dealerHidden = round ? Number(round.dealer_hidden_count || 0) : 0;
    renderCards('holdemDealerCards', round ? round.dealer_cards : [], dealerHidden, 2);
    renderCards('holdemCommunityCards', round ? round.community_cards : [], 0, 5);
    renderCards('holdemPlayerCards', round ? round.player_cards : [], 0, 2);
    ui.setText('holdemDealerHand', round && resultVisible && round.dealer_hand ? handLabel(round.dealer_hand) : '');
    ui.setText('holdemPlayerHand', round && resultVisible && round.player_hand ? handLabel(round.player_hand) : '');
    ui.setText('holdemPot', ui.t('holdem_pot', { amount: money(round ? round.total_bet : 0) }));
    renderBalance();
    renderBets();
    renderActions();
    renderResult();
    renderRecent();
    renderRankGallery();
  }

  function rememberRound(round) {
    const cls = outcomeClass(round);
    if (!round || round.status === 'active') return;
    recent.unshift({
      state: cls || 'push',
      label: cls === 'win'
        ? ui.t('holdem_recent_win', { amount: money(Math.max(0, resultAmount(round))) })
        : (cls === 'push' ? ui.t('holdem_recent_push') : ui.t('holdem_recent_loss', { amount: money(Math.abs(resultAmount(round))) }))
    });
    recent = recent.slice(0, 5);
  }

  function setCardAnimation(id, index, hidden, className) {
    cardAnimations[cardKey(id, index, hidden)] = className;
  }

  function renderStep(round, overrides, animation) {
    cardAnimations = {};
    if (animation) {
      setCardAnimation(animation.id, animation.index, animation.hidden, animation.className || 'is-dealt');
      B.audio?.play?.(String(animation.className || '').includes('is-flipped') ? 'flip' : 'card');
    }
    displayRound = viewRound(round, overrides);
    renderAll();
  }

  async function animateStartDeal(round) {
    animating = true;
    animationMode = 'deal';
    resultVisible = false;
    cardAnimations = {};
    const player = cardsOf(round.player_cards);
    const community = cardsOf(round.community_cards);
    renderStep(round, { player_cards: [], dealer_cards: [], dealer_hidden_count: 0, community_cards: [] });
    await sleep(120);

    renderStep(round, { player_cards: cardsOf(player, 1), dealer_cards: [], dealer_hidden_count: 0, community_cards: [] }, {
      id: 'holdemPlayerCards', index: 0, hidden: false
    });
    await sleep(185);
    renderStep(round, { player_cards: cardsOf(player, 1), dealer_cards: [], dealer_hidden_count: 1, community_cards: [] }, {
      id: 'holdemDealerCards', index: 0, hidden: true
    });
    await sleep(185);
    renderStep(round, { player_cards: cardsOf(player, 2), dealer_cards: [], dealer_hidden_count: 1, community_cards: [] }, {
      id: 'holdemPlayerCards', index: 1, hidden: false
    });
    await sleep(185);
    renderStep(round, { player_cards: cardsOf(player, 2), dealer_cards: [], dealer_hidden_count: 2, community_cards: [] }, {
      id: 'holdemDealerCards', index: 1, hidden: true
    });
    await sleep(230);
    for (let index = 0; index < Math.min(3, community.length); index++) {
      renderStep(round, { player_cards: cardsOf(player, 2), dealer_cards: [], dealer_hidden_count: 2, community_cards: cardsOf(community, index + 1) }, {
        id: 'holdemCommunityCards', index, hidden: false, className: index === 2 ? 'is-dealt is-river' : 'is-dealt'
      });
      await sleep(index === 2 ? 360 : 155);
    }

    displayRound = clone(round);
    animating = false;
    animationMode = '';
    resultVisible = true;
    cardAnimations = {};
    renderAll();
  }

  async function animateShowdown(previous, finalRound) {
    animating = true;
    animationMode = 'showdown';
    resultVisible = false;
    cardAnimations = {};
    const player = cardsOf(previous.player_cards);
    const community = cardsOf(finalRound.community_cards);
    renderStep(previous, {
      player_cards: cardsOf(player, 2),
      dealer_cards: [],
      dealer_hidden_count: 2,
      community_cards: cardsOf(community, 3)
    });
    await sleep(120);
    renderStep(previous, {
      player_cards: cardsOf(player, 2),
      dealer_cards: [],
      dealer_hidden_count: 2,
      community_cards: cardsOf(community, 4)
    }, { id: 'holdemCommunityCards', index: 3, hidden: false, className: 'is-dealt is-river' });
    await sleep(260);
    renderStep(previous, {
      player_cards: cardsOf(player, 2),
      dealer_cards: [],
      dealer_hidden_count: 2,
      community_cards: cardsOf(community, 5)
    }, { id: 'holdemCommunityCards', index: 4, hidden: false, className: 'is-dealt is-river' });
    await sleep(330);
    renderStep(finalRound, {}, { id: 'holdemDealerCards', index: 0, hidden: false, className: 'is-flipped' });
    setCardAnimation('holdemDealerCards', 1, false, 'is-flipped');
    renderAll();
    await sleep(660);

    displayRound = clone(finalRound);
    animating = false;
    animationMode = '';
    resultVisible = true;
    cardAnimations = {};
    rememberRound(finalRound);
    renderAll();
  }

  async function animateFold(finalRound) {
    animating = true;
    animationMode = 'fold';
    resultVisible = false;
    cardAnimations = {
      [cardKey('holdemPlayerCards', 0, false)]: 'is-folded',
      [cardKey('holdemPlayerCards', 1, false)]: 'is-folded'
    };
    displayRound = displayRound || activeRound;
    renderAll();
    await sleep(620);
    displayRound = clone(finalRound);
    animating = false;
    animationMode = '';
    resultVisible = true;
    cardAnimations = {};
    rememberRound(finalRound);
    renderAll();
  }

  async function restoreActiveRound() {
    const user = store.getDisplayUser();
    if (!user || !user.apiId || !store.getActiveTexasHoldemRound) return;
    const result = await store.getActiveTexasHoldemRound();
    if (result && !result.error) {
      activeRound = result;
      displayRound = result;
      resultVisible = true;
    } else {
      activeRound = null;
      displayRound = null;
      resultVisible = true;
    }
    renderAll();
  }

  async function startRound() {
    if (busy) return;
    busy = true;
    activeRound = null;
    displayRound = null;
    resultVisible = true;
    cardAnimations = {};
    renderAll();
    B.audio?.play?.('chip');
    const result = await store.startTexasHoldem(selectedAnte);
    if (showStoreError(result)) {
      busy = false;
      renderAll();
      return;
    }
    activeRound = result;
    await animateStartDeal(result);
    busy = false;
    renderAll();
  }

  async function decide(action) {
    if (busy || !isActive()) return;
    busy = true;
    const previous = clone(activeRound);
    renderAll();
    B.audio?.play?.(String(action).toLowerCase() === 'fold' ? 'loss' : 'chip');
    const result = await store.decideTexasHoldem(activeRound.round_id, action);
    if (showStoreError(result)) {
      busy = false;
      renderAll();
      return;
    }
    activeRound = result;
    if (String(action).toLowerCase() === 'fold') {
      await animateFold(result);
    } else {
      await animateShowdown(previous, result);
    }
    B.audio?.play?.(Number(result.net || 0) > 0 ? 'win' : (Number(result.net || 0) < 0 ? 'loss' : 'push'));
    busy = false;
    renderAll();
  }

  function openRules() {
    const overlay = document.getElementById('holdemRulesOverlay');
    if (!overlay) return;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    window.setTimeout(() => overlay.querySelector('[data-holdem-rules-close]')?.focus(), 20);
  }

  function closeRules() {
    const overlay = document.getElementById('holdemRulesOverlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  function initHoldem() {
    if (document.body.dataset.page !== 'holdem' || initialized) return;
    initialized = true;
    document.addEventListener('click', event => {
      const bet = event.target.closest('[data-holdem-ante]');
      if (bet && !isActive() && !busy) {
        selectedAnte = Number(bet.dataset.holdemAnte || selectedAnte);
        renderAll();
        return;
      }
      const rulesOverlay = document.getElementById('holdemRulesOverlay');
      if (event.target.closest('#holdemRulesOpen')) {
        openRules();
        return;
      }
      if (rulesOverlay && (event.target === rulesOverlay || event.target.closest('[data-holdem-rules-close]'))) {
        closeRules();
      }
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeRules();
    });
    document.getElementById('holdemStart')?.addEventListener('click', startRound);
    document.getElementById('holdemCallBtn')?.addEventListener('click', () => decide('call'));
    document.getElementById('holdemFoldBtn')?.addEventListener('click', () => decide('fold'));
    store.subscribe((next, prev, action) => {
      if (next.lang !== prev.lang || action === 'data:set' || String(action || '').startsWith('wallet:') || String(action || '').startsWith('game:')) {
        renderAll();
      }
      const nextUser = next.currentUser && next.currentUser.apiId ? String(next.currentUser.apiId) : '';
      const prevUser = prev.currentUser && prev.currentUser.apiId ? String(prev.currentUser.apiId) : '';
      if (nextUser !== prevUser) restoreActiveRound();
    });
    renderAll();
    store.getManagerState?.().then(result => {
      if (!result?.error) {
        ANTES.splice(0, ANTES.length, ...store.getManagerBetOptions('texas-holdem'));
        if (selectedAnte === 100) selectedAnte = ANTES[ANTES.length - 1];
        renderBets();
      }
    });
    restoreActiveRound();
  }

  B.holdem = { init: initHoldem };
})(window);
