(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  const BETS = [5, 10, 25, 100];
  const MINE_COUNTS = [5, 7, 10, 12];
  const CELL_COUNT = 20;

  let selectedBet = 5;
  let selectedMineCount = 5;
  let activeRound = null;
  let busy = false;
  let restoring = false;
  let restoreAttempted = false;
  let lossHitCell = null;
  let recent = [];

  function currentBalance() {
    return Number(store.getDisplayUser().balance || 0);
  }

  function multiplierLabel(value) {
    return Number(value || 1).toFixed(2) + 'x';
  }

  function roundMines() {
    return activeRound && Array.isArray(activeRound.mines) ? activeRound.mines.map(Number) : [];
  }

  function roundRevealed() {
    return activeRound && Array.isArray(activeRound.revealed_cells) ? activeRound.revealed_cells.map(Number) : [];
  }

  function isSettled() {
    return activeRound && activeRound.status && activeRound.status !== 'active';
  }

  function isRoundActive() {
    return Boolean(activeRound && activeRound.status === 'active');
  }

  function isRoundWon() {
    return Boolean(activeRound && activeRound.status === 'completed');
  }

  function renderBalance() {
    const user = store.getDisplayUser();
    ui.setText('mines-balance', ui.formatMoney(user.balance, user.currency));
  }

  function renderBets() {
    const mount = document.getElementById('minesBets');
    if (!mount) return;
    mount.innerHTML = BETS.map(value => `
      <button class="chip-btn ${value === selectedBet ? 'selected' : ''}" type="button" data-mines-bet="${value}" ${isRoundActive() ? 'disabled' : ''}>
        ${ui.formatMoney(value)}
      </button>
    `).join('');
  }

  function renderCounts() {
    const mount = document.getElementById('minesCounts');
    if (!mount) return;
    mount.innerHTML = MINE_COUNTS.map(value => `
      <button class="mines-count ${value === selectedMineCount ? 'selected' : ''}" type="button" data-mines-count="${value}" ${isRoundActive() ? 'disabled' : ''}>
        ${value}
      </button>
    `).join('');
  }

  function renderStats() {
    const multiplier = activeRound ? Number(activeRound.current_multiplier || 1) : 1;
    const potential = activeRound ? Number(activeRound.potential_win || 0) : 0;
    ui.setText('minesMultiplier', multiplierLabel(multiplier));
    ui.setText('minesPotential', ui.formatMoney(potential));
    document.getElementById('minesMultiplier')?.closest('.mines-meter')?.classList.toggle('is-win', isRoundWon());
  }

  function cellClass(index, revealed, mines) {
    const classes = ['mines-cell'];
    if (revealed.includes(index)) classes.push('is-safe');
    if (mines.includes(index)) classes.push('is-mine');
    if (isRoundWon() && revealed.includes(index) && !mines.includes(index)) classes.push('is-cashed');
    if (activeRound && activeRound.status === 'lost' && index === lossHitCell) classes.push('is-hit');
    if (busy || isSettled() || !activeRound) classes.push('is-locked');
    return classes.join(' ');
  }

  function renderBoard() {
    const mount = document.getElementById('minesBoard');
    if (!mount) return;
    const isLoss = Boolean(activeRound && activeRound.status === 'lost');
    const isWin = isRoundWon();
    mount.classList.toggle('is-loss', isLoss);
    mount.classList.toggle('is-win', isWin);
    const shell = mount.closest('.mines-board-shell');
    shell?.classList.toggle('is-loss', isLoss);
    shell?.classList.toggle('is-win', isWin);
    const revealed = roundRevealed();
    const mines = roundMines();
    mount.innerHTML = Array.from({ length: CELL_COUNT }, (_, index) => `
      <button class="${cellClass(index, revealed, mines)}" type="button" data-mines-cell="${index}" style="--cell-order:${index}" aria-label="Cell ${index + 1}">
        <span></span>
      </button>
    `).join('');
  }

  function renderStatus() {
    const status = document.getElementById('minesStatus');
    if (!status) return;
    status.classList.toggle('win', Boolean(activeRound && activeRound.status === 'completed'));
    status.classList.toggle('loss', Boolean(activeRound && activeRound.status === 'lost'));

    if (!activeRound) {
      status.textContent = ui.t('mines_waiting');
      return;
    }
    if (activeRound.status === 'lost') {
      status.textContent = ui.t('mines_lost');
      return;
    }
    if (activeRound.status === 'completed') {
      status.textContent = ui.t('mines_win', {
        multiplier: multiplierLabel(activeRound.current_multiplier),
        amount: ui.formatMoney(Number(activeRound.total_win || 0))
      });
      return;
    }
    status.textContent = ui.t('mines_opened', {
      opened: roundRevealed().length,
      multiplier: multiplierLabel(activeRound.current_multiplier)
    });
  }

  function renderAction() {
    const button = document.getElementById('minesAction');
    if (!button) return;
    const canCashout = isRoundActive() && roundRevealed().length > 0;
    button.disabled = busy || (isRoundActive() && !canCashout);
    button.textContent = isRoundActive()
      ? ui.t('mines_cashout')
      : ui.t('mines_start');
  }

  function renderRecent() {
    ui.renderGameHistory?.('minesRecent', recent, ui.t('mines_recent_empty'));
  }

  function renderAll() {
    renderBalance();
    renderBets();
    renderCounts();
    renderStats();
    renderBoard();
    renderStatus();
    renderAction();
    renderRecent();
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error), 'err');
    return true;
  }

  function recordSettledRound(result) {
    const win = Number(result.net || 0) > 0;
    recent.unshift({
      state: win ? 'win' : 'loss',
      label: win ? '+' + ui.formatMoney(result.net) : ui.formatMoney(result.net || 0),
      meta: multiplierLabel(result.current_multiplier)
    });
    recent = recent.slice(0, 8);
  }

  async function restoreActiveRound(force) {
    if (restoring || (restoreAttempted && !force)) return;
    const user = store.getDisplayUser();
    if (!user || !user.apiId) return;
    restoring = true;
    restoreAttempted = true;
    const result = await store.getActiveSolarMinesRound();
    restoring = false;
    if (!result || result.error) {
      if (!result || result.error === 'err_auth_required' || result.error === 'err_mines_round_not_found') {
        activeRound = null;
        lossHitCell = null;
      }
      if (!result || result.error !== 'err_auth_required') renderAll();
      return;
    }
    if (result.status === 'active') {
      activeRound = result;
      lossHitCell = null;
      selectedBet = Number(result.total_bet || selectedBet);
      selectedMineCount = Number(result.mine_count || selectedMineCount);
      renderAll();
    }
  }

  async function startRound() {
    if (busy) return;
    if (selectedBet > currentBalance()) {
      ui.showToast(ui.t('err_mines_balance'), 'err');
      renderAll();
      return;
    }
    busy = true;
    renderAction();
    B.audio?.play?.('drop');
    const result = await store.startSolarMines(selectedBet, selectedMineCount);
    busy = false;
    if (result && result.error === 'err_mines_active_round') {
      await restoreActiveRound(true);
      renderAll();
      return;
    }
    if (showStoreError(result)) {
      renderAll();
      return;
    }
    activeRound = result;
    lossHitCell = null;
    renderAll();
  }

  async function revealCell(cell) {
    if (busy || !activeRound || activeRound.status !== 'active') return;
    const selectedCell = Number(cell);
    if (roundRevealed().includes(selectedCell)) return;
    busy = true;
    renderAction();
    B.audio?.play?.('click');
    const result = await store.revealSolarMinesCell(activeRound.round_id, selectedCell);
    busy = false;
    if (showStoreError(result)) {
      renderAll();
      return;
    }
    activeRound = result;
    lossHitCell = result.status === 'lost' ? selectedCell : null;
    if (result.status !== 'active') {
      store.commitGameWallet(result, 'game:mines:settled');
      recordSettledRound(result);
      B.audio?.play?.(result.status === 'lost' ? 'loss' : 'win');
    } else {
      B.audio?.play?.('chip');
    }
    renderAll();
  }

  async function cashoutRound() {
    if (busy || !activeRound || activeRound.status !== 'active') return;
    busy = true;
    renderAction();
    B.audio?.play?.('cashout');
    const result = await store.cashoutSolarMines(activeRound.round_id);
    busy = false;
    if (showStoreError(result)) {
      renderAll();
      return;
    }
    activeRound = result;
    lossHitCell = null;
    store.commitGameWallet(result, 'game:mines:settled');
    recordSettledRound(result);
    B.audio?.play?.(Number(result.net || 0) > 0 ? 'win' : 'push');
    renderAll();
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      const bet = event.target.closest('[data-mines-bet]');
      if (bet && !isRoundActive()) {
        selectedBet = Number(bet.dataset.minesBet || selectedBet);
        renderBets();
        return;
      }

      const count = event.target.closest('[data-mines-count]');
      if (count && !isRoundActive()) {
        selectedMineCount = Number(count.dataset.minesCount || selectedMineCount);
        renderCounts();
        return;
      }

      const cell = event.target.closest('[data-mines-cell]');
      if (cell) {
        revealCell(Number(cell.dataset.minesCell));
      }
    });
    document.getElementById('minesAction')?.addEventListener('click', () => {
      if (activeRound && activeRound.status === 'active') cashoutRound();
      else {
        activeRound = null;
        lossHitCell = null;
        renderAll();
        startRound();
      }
    });
  }

  function init() {
    if (document.body.dataset.page !== 'mines') return;
    renderAll();
    store.getManagerState?.().then(result => {
      if (!result?.error) {
        BETS.splice(0, BETS.length, ...store.getManagerBetOptions('solar-wilds'));
        if (selectedBet === 100) selectedBet = BETS[BETS.length - 1];
        renderBets();
      }
    });
    bindEvents();
    restoreActiveRound(false);
    store.subscribe(() => {
      restoreActiveRound(false);
      renderBalance();
    });
  }

  B.mines = { init };
})(window);
