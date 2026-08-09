(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  const BETS = [5, 10, 25, 100];
  const SYMBOLS = {
    bamboo: { icon: '🎋', name: 'Bamboo', className: 'bamboo' },
    panda: { icon: '🐼', name: 'Panda', className: 'panda' },
    coin: { icon: '🪙', name: 'Coin', className: 'coin' },
    lotus: { icon: '🪷', name: 'Lotus', className: 'lotus' },
    lantern: { icon: '🏮', name: 'Lantern', className: 'lantern' },
    jade: { icon: '💎', name: 'Jade', className: 'jade' }
  };
  const PAYTABLE = [
    ['bamboo', '730x', '160x', '36x'],
    ['panda', '455x', '110x', '27x'],
    ['coin', '320x', '82x', '23x'],
    ['lotus', '205x', '55x', '18x'],
    ['lantern', '128x', '41x', '14x'],
    ['jade', '82x', '27x', '9x']
  ];
  const EMPTY_GRID = [
    ['bamboo', 'panda', 'coin', 'lotus', 'lantern'],
    ['jade', 'bamboo', 'panda', 'coin', 'lotus'],
    ['lantern', 'jade', 'bamboo', 'panda', 'coin']
  ];

  let selectedBet = 5;
  let spinning = false;
  let slotState = '';
  let recent = [];

  function symbolMeta(id) {
    return SYMBOLS[id] || SYMBOLS.jade;
  }

  function currentBalance() {
    return Number(store.getDisplayUser().balance || 0);
  }

  function renderBalance() {
    const user = store.getDisplayUser();
    ui.setText('slot-balance', ui.formatMoney(user.balance, user.currency));
  }

  function renderBets() {
    const mount = document.getElementById('slotBets');
    if (!mount) return;
    mount.innerHTML = BETS.map(value => `
      <button class="chip-btn ${value === selectedBet ? 'selected' : ''}" type="button" data-slot-bet="${value}">
        ${ui.formatMoney(value)}
      </button>
    `).join('');
  }

  function applySlotState(state) {
    const nextState = state || '';
    const reels = document.getElementById('slotReels');
    const machine = document.getElementById('slotMachine');
    [reels, machine].forEach(element => {
      if (!element) return;
      element.classList.toggle('is-win', nextState === 'win');
      element.classList.toggle('is-loss', nextState === 'loss');
      element.classList.toggle('is-push', nextState === 'push');
    });
  }

  function resultState(result) {
    const net = Number(result && result.net || 0);
    if (net > 0) return 'win';
    if (net < 0) return 'loss';
    return 'push';
  }

  function resetResultUi() {
    slotState = '';
    applySlotState('');
    renderLineBreakdown([]);
    const box = document.getElementById('slotResult');
    if (!box) return;
    box.classList.remove('win', 'loss', 'push');
    box.textContent = ui.t('slot_result_empty');
  }

  function renderGrid(grid, winningLines, state) {
    const mount = document.getElementById('slotReels');
    if (!mount) return;
    if (state !== undefined) slotState = state || '';
    applySlotState(slotState);
    const hits = new Set();
    (winningLines || []).forEach(line => {
      (line.positions || []).forEach(pos => hits.add(pos.row + ':' + pos.reel));
    });
    mount.innerHTML = grid.map((row, rowIndex) => row.map((symbol, reelIndex) => {
      const meta = symbolMeta(symbol);
      const hit = hits.has(rowIndex + ':' + reelIndex);
      const order = reelIndex * 3 + rowIndex;
      return `
        <div class="slot-cell ${meta.className} ${hit ? 'is-hit' : ''}" data-row="${rowIndex}" data-reel="${reelIndex}" style="--cell-order:${order}">
          <span>${ui.escapeHTML(meta.icon)}</span>
          <small>${ui.escapeHTML(meta.name)}</small>
        </div>
      `;
    }).join('')).join('');
  }

  function renderPaytable() {
    const mount = document.getElementById('slotPaytable');
    if (!mount) return;
    mount.innerHTML = PAYTABLE.map(([id, five, four, three]) => {
      const meta = symbolMeta(id);
      return `
        <div class="slot-pay-row">
          <span class="slot-pay-symbol ${meta.className}">${ui.escapeHTML(meta.icon)}</span>
          <span>5=${ui.escapeHTML(five)}</span>
          <span>4=${ui.escapeHTML(four)}</span>
          <span>3=${ui.escapeHTML(three)}</span>
        </div>
      `;
    }).join('');
  }

  function renderRecent() {
    ui.renderGameHistory?.('slotRecent', recent, ui.t('slot_recent_empty'));
  }

  function renderLineBreakdown(winningLines) {
    const mount = document.getElementById('slotResultLines');
    if (!mount) return;
    mount.hidden = true;
    mount.innerHTML = '';
  }

  function setResult(result) {
    const box = document.getElementById('slotResult');
    if (!box) return;
    const net = Number(result.net || 0);
    const totalWin = Math.max(0, Number(result.total_win || 0));
    const netLabel = (net > 0 ? '+' : '') + ui.formatMoney(net);
    box.classList.toggle('win', net > 0);
    box.classList.toggle('loss', net < 0);
    box.classList.toggle('push', net === 0);
    if (totalWin > 0) {
      box.textContent = ui.t('slot_result_win', {
        amount: ui.formatMoney(totalWin),
        lines: result.winning_lines.length,
        net: netLabel
      });
    } else if (net === 0) {
      box.textContent = ui.t('slot_result_push');
    } else {
      box.textContent = ui.t('slot_result_loss', { amount: ui.formatMoney(Number(result.total_bet || Math.abs(net))) });
    }
    renderLineBreakdown(result.winning_lines);
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error), 'err');
    return true;
  }

  function animateSpin(finalGrid, winningLines, state) {
    const sequence = Object.keys(SYMBOLS);
    const started = performance.now();
    const duration = 1150;
    return new Promise(resolve => {
      function frame(now) {
        const progress = Math.min(1, (now - started) / duration);
        if (progress < 1) {
          const grid = EMPTY_GRID.map((row, rowIndex) => row.map((_, reelIndex) => {
            const offset = Math.floor((now / 72) + reelIndex * 2 + rowIndex);
            return sequence[offset % sequence.length];
          }));
          renderGrid(grid, [], '');
          requestAnimationFrame(frame);
          return;
        }
        renderGrid(finalGrid, winningLines, state);
        resolve();
      }
      requestAnimationFrame(frame);
    });
  }

  async function spin() {
    if (spinning) return;
    if (selectedBet > currentBalance()) {
      ui.showToast(ui.t('err_slot_balance'), 'err');
      return;
    }
    spinning = true;
    document.getElementById('slotSpin').disabled = true;
    resetResultUi();
    renderGrid(EMPTY_GRID, [], '');
    B.audio?.play?.('spin');

    const result = await store.playLuckyBamboo(selectedBet);
    if (showStoreError(result)) {
      spinning = false;
      document.getElementById('slotSpin').disabled = false;
      return;
    }

    await animateSpin(result.grid, result.winning_lines || [], resultState(result));
    setResult(result);
    store.commitGameWallet(result, 'game:slot:settled');
    B.audio?.play?.(Number(result.net || 0) > 0 ? 'win' : (Number(result.net || 0) < 0 ? 'loss' : 'push'));
    recent.unshift({
      state: resultState(result),
      label: Number(result.net || 0) > 0 ? '+' + ui.formatMoney(result.net) : ui.formatMoney(result.net)
    });
    recent = recent.slice(0, 8);
    renderRecent();
    renderBalance();
    spinning = false;
    document.getElementById('slotSpin').disabled = false;
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      const bet = event.target.closest('[data-slot-bet]');
      if (!bet || spinning) return;
      selectedBet = Number(bet.dataset.slotBet || selectedBet);
      renderBets();
    });
    document.getElementById('slotSpin')?.addEventListener('click', spin);
  }

  function init() {
    if (document.body.dataset.page !== 'slot') return;
    renderBalance();
    renderBets();
    renderGrid(EMPTY_GRID, []);
    renderPaytable();
    renderRecent();
    bindEvents();
    store.subscribe(() => {
      if (!spinning) renderBalance();
    });
  }

  B.slot = { init };
})(window);
