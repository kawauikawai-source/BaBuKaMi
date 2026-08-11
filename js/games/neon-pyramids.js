(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  const WIDTH = 10;
  const DEFAULT_HEIGHT = 15;
  const BETS = [5, 10, 25, 100];
  const CONTROLS_SEEN_KEY = 'bk_blocks_controls_seen';
  const DIFFICULTIES = {
    level1: { height: 15, tickMs: 650, start: 0.1 },
    level2: { height: 15, tickMs: 520, start: 0.25 },
    level3: { height: 15, tickMs: 430, start: 0.4 }
  };
  const SHAPES = {
    I: [
      [[0, 0], [0, 1], [0, 2], [0, 3]],
      [[0, 0], [1, 0], [2, 0], [3, 0]],
      [[0, 0], [0, 1], [0, 2], [0, 3]],
      [[0, 0], [1, 0], [2, 0], [3, 0]]
    ],
    J: [
      [[0, 0], [0, 1], [1, 1], [2, 1]],
      [[1, 0], [2, 0], [1, 1], [1, 2]],
      [[0, 0], [1, 0], [2, 0], [2, 1]],
      [[1, 0], [1, 1], [0, 2], [1, 2]]
    ],
    L: [
      [[2, 0], [0, 1], [1, 1], [2, 1]],
      [[1, 0], [1, 1], [1, 2], [2, 2]],
      [[0, 0], [1, 0], [2, 0], [0, 1]],
      [[0, 0], [1, 0], [1, 1], [1, 2]]
    ],
    O: [
      [[0, 0], [1, 0], [0, 1], [1, 1]],
      [[0, 0], [1, 0], [0, 1], [1, 1]],
      [[0, 0], [1, 0], [0, 1], [1, 1]],
      [[0, 0], [1, 0], [0, 1], [1, 1]]
    ],
    S: [
      [[1, 0], [2, 0], [0, 1], [1, 1]],
      [[0, 0], [0, 1], [1, 1], [1, 2]],
      [[1, 0], [2, 0], [0, 1], [1, 1]],
      [[0, 0], [0, 1], [1, 1], [1, 2]]
    ],
    T: [
      [[1, 0], [0, 1], [1, 1], [2, 1]],
      [[1, 0], [1, 1], [2, 1], [1, 2]],
      [[0, 0], [1, 0], [2, 0], [1, 1]],
      [[1, 0], [0, 1], [1, 1], [1, 2]]
    ],
    Z: [
      [[0, 0], [1, 0], [1, 1], [2, 1]],
      [[1, 0], [0, 1], [1, 1], [0, 2]],
      [[0, 0], [1, 0], [1, 1], [2, 1]],
      [[1, 0], [0, 1], [1, 1], [0, 2]]
    ]
  };

  let selectedBet = 5;
  let selectedDifficulty = 'level1';
  let activeRound = null;
  let localPiece = null;
  let busy = false;
  let timer = 0;
  let recent = [];
  let nextIntroTimer = 0;
  let lineClearTimer = 0;
  let boardGesture = null;

  function isActive() {
    return Boolean(activeRound && activeRound.status === 'active' && activeRound.current_piece);
  }

  function canCashout() {
    return isActive() && Boolean(activeRound.cashout_available);
  }

  function difficultyConfig(level) {
    return DIFFICULTIES[level] || DIFFICULTIES.level1;
  }

  function boardHeight() {
    if (activeRound && Number(activeRound.board_height) > 0) return Number(activeRound.board_height);
    if (activeRound && Array.isArray(activeRound.board) && activeRound.board.length) return activeRound.board.length;
    return difficultyConfig(selectedDifficulty).height || DEFAULT_HEIGHT;
  }

  function activeTickMs() {
    return Number(activeRound?.tick_ms || difficultyConfig(selectedDifficulty).tickMs || 520);
  }

  function startingMultiplier() {
    return Number(difficultyConfig(selectedDifficulty).start || 0.1);
  }

  function normalizeCells(cells) {
    if (!cells.length) return [];
    const minX = Math.min(...cells.map(([x]) => x));
    const minY = Math.min(...cells.map(([, y]) => y));
    return cells.map(([x, y]) => [x - minX, y - minY]);
  }

  function shape(pieceType, rotation) {
    return SHAPES[pieceType] ? normalizeCells(SHAPES[pieceType][Number(rotation || 0) % 4]) : [];
  }

  function normalizedBoard() {
    const board = activeRound && Array.isArray(activeRound.board) ? activeRound.board : [];
    return Array.from({ length: boardHeight() }, (_, y) => {
      const row = Array.isArray(board[y]) ? board[y] : [];
      return Array.from({ length: WIDTH }, (_, x) => String(row[x] || ''));
    });
  }

  function canPlace(board, pieceType, rotation, x, y) {
    return shape(pieceType, rotation).every(([dx, dy]) => {
      const px = x + dx;
      const py = y + dy;
      return px >= 0 && px < WIDTH && py >= 0 && py < board.length && !board[py][px];
    });
  }

  function pieceWidth(pieceType, rotation) {
    return Math.max(...shape(pieceType, rotation).map(([x]) => x)) + 1;
  }

  function clampPieceX(pieceType, rotation, x) {
    return Math.max(0, Math.min(WIDTH - pieceWidth(pieceType, rotation), x));
  }

  function resetLocalPiece() {
    if (!isActive()) {
      localPiece = null;
      return;
    }
    const piece = activeRound.current_piece;
    const rotation = 0;
    localPiece = {
      id: Number(piece.id),
      type: piece.type,
      rotation,
      x: clampPieceX(piece.type, rotation, Math.floor(WIDTH / 2) - 1),
      y: 0
    };
  }

  function currentBalance() {
    return Number(store.getDisplayUser().balance || 0);
  }

  function multiplierLabel(value) {
    return Number(value || 1).toFixed(2) + 'x';
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error), 'err');
    return true;
  }

  function controlsSeen() {
    try {
      return global.localStorage.getItem(CONTROLS_SEEN_KEY) === '1';
    } catch (err) {
      return false;
    }
  }

  function rememberControlsSeen() {
    try {
      global.localStorage.setItem(CONTROLS_SEEN_KEY, '1');
    } catch (err) {
      // The hint remains optional if browser storage is blocked.
    }
  }

  function hasBlockingOverlay() {
    return Boolean(document.querySelector(
      '.blocks-controls-overlay.open,.site-confirm-overlay.open,.overlay.open,.vip-clicker-overlay.open,.admin-confirm-overlay.open'
    ));
  }

  function openControlsModal() {
    const overlay = document.getElementById('blocksControlsOverlay');
    if (!overlay) return Promise.resolve(true);
    const skip = document.getElementById('blocksControlsSkip');
    if (skip) skip.checked = false;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    const start = overlay.querySelector('[data-blocks-controls="start"]');
    window.setTimeout(() => start?.focus(), 20);

    return new Promise(resolve => {
      let settled = false;
      const finish = value => {
        if (settled) return;
        settled = true;
        overlay.classList.remove('open');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
        overlay.removeEventListener('click', onClick);
        document.removeEventListener('keydown', onKeydown);
        if (value && skip?.checked) rememberControlsSeen();
        resolve(value);
      };
      const onClick = event => {
        if (event.target === overlay || event.target.closest('[data-blocks-controls="cancel"]')) {
          finish(false);
          return;
        }
        if (event.target.closest('[data-blocks-controls="start"]')) finish(true);
      };
      const onKeydown = event => {
        if (event.key === 'Escape') finish(false);
        if (event.key === 'Enter') finish(true);
      };
      overlay.addEventListener('click', onClick);
      document.addEventListener('keydown', onKeydown);
    });
  }

  function renderBalance() {
    const user = store.getDisplayUser();
    ui.setText('blocks-balance', ui.formatMoney(user.balance, user.currency));
  }

  function renderBets() {
    const mount = document.getElementById('blocksBets');
    if (!mount) return;
    mount.innerHTML = BETS.map(value => `
      <button class="chip-btn ${value === selectedBet ? 'selected' : ''}" type="button" data-blocks-bet="${value}" ${isActive() ? 'disabled' : ''}>
        ${ui.formatMoney(value)}
      </button>
    `).join('');
  }

  function renderDifficulty() {
    const mount = document.getElementById('blocksDifficulty');
    if (!mount) return;
    mount.innerHTML = Object.keys(DIFFICULTIES).map(level => `
      <button class="blocks-difficulty-btn ${level === selectedDifficulty ? 'selected' : ''}" type="button" data-blocks-difficulty="${level}" ${isActive() ? 'disabled' : ''}>
        ${ui.t('blocks_' + level)}
      </button>
    `).join('');
  }

  function boardWithLocalPiece() {
    const board = normalizedBoard();
    if (!localPiece || !isActive()) return board;
    shape(localPiece.type, localPiece.rotation).forEach(([dx, dy]) => {
      const px = localPiece.x + dx;
      const py = localPiece.y + dy;
      if (px >= 0 && px < WIDTH && py >= 0 && py < board.length) board[py][px] = localPiece.type + '-active';
    });
    return board;
  }

  function boardWithPlacedPiece(piece) {
    const board = normalizedBoard();
    if (!piece) return board;
    shape(piece.type, piece.rotation).forEach(([dx, dy]) => {
      const px = piece.x + dx;
      const py = piece.y + dy;
      if (px >= 0 && px < WIDTH && py >= 0 && py < board.length) board[py][px] = piece.type;
    });
    return board;
  }

  function createLineClearPreview() {
    if (!localPiece || !isActive()) return null;
    const board = normalizedBoard();
    if (!canPlace(board, localPiece.type, localPiece.rotation, localPiece.x, localPiece.y)) return null;
    const previewBoard = boardWithPlacedPiece(localPiece);
    const clearingRows = previewBoard
      .map((row, index) => row.every(Boolean) ? index : -1)
      .filter(index => index >= 0);
    return clearingRows.length ? { board: previewBoard, rows: clearingRows } : null;
  }

  function clearLineClearTimer() {
    if (lineClearTimer) global.clearTimeout(lineClearTimer);
    lineClearTimer = 0;
  }

  function renderBoard(options) {
    const mount = document.getElementById('blocksBoard');
    if (!mount) return;
    const opts = options || {};
    const board = opts.board || boardWithLocalPiece();
    const clearingRows = new Set(opts.clearingRows || []);
    const pressureLevel = Number(activeRound?.pressure_level || 0);
    const shell = document.querySelector('.blocks-board-shell');
    if (shell) {
      shell.classList.toggle('is-pressure-mid', pressureLevel >= 2);
      shell.classList.toggle('is-pressure-high', pressureLevel >= 4);
      shell.classList.toggle('is-line-clear', clearingRows.size > 0);
    }
    mount.classList.toggle('is-win', Boolean(activeRound && activeRound.status === 'completed'));
    mount.classList.toggle('is-loss', Boolean(activeRound && activeRound.status === 'lost'));
    mount.classList.toggle('is-pyramid-clear', Boolean(activeRound && Number(activeRound.last_clear || 0) >= 4));
    mount.classList.toggle('is-line-clear', clearingRows.size > 0);
    mount.style.gridTemplateRows = `repeat(${board.length}, 1fr)`;
    mount.style.aspectRatio = `${WIDTH}/${board.length}`;
    mount.innerHTML = board.flatMap((row, y) => row.map((cell, x) => {
      const clean = String(cell || '').replace('-active', '');
      const active = String(cell || '').endsWith('-active');
      const clearing = clearingRows.has(y) && clean;
      const delay = clearing ? Math.abs(x - ((WIDTH - 1) / 2)) * 24 : 0;
      const scatter = clearing ? (x < WIDTH / 2 ? -1 : 1) * (22 + Math.abs(x - ((WIDTH - 1) / 2)) * 7) : 0;
      const style = clearing ? ` style="--clear-delay:${delay}ms;--clear-x:${scatter}px;--clear-y:${-12 - (y % 3) * 5}px;--clear-rot:${x % 2 ? -14 : 14}deg"` : '';
      const shards = clearing
        ? '<i class="blocks-shard s1"></i><i class="blocks-shard s2"></i><i class="blocks-shard s3"></i><i class="blocks-shard s4"></i>'
        : '';
      return `<span class="blocks-cell ${clean ? 'piece-' + clean : ''} ${active ? 'is-active' : ''} ${clearing ? 'is-clearing' : ''}" data-x="${x}" data-y="${y}"${style}>${shards}</span>`;
    })).join('');
  }

  function playLineClearAnimation(preview) {
    if (!preview || !preview.rows || !preview.rows.length) return Promise.resolve();
    clearLineClearTimer();
    B.audio?.play?.(preview.rows.length >= 4 ? 'win' : 'cashout');
    renderBoard({ board: preview.board, clearingRows: preview.rows });
    return new Promise(resolve => {
      lineClearTimer = global.setTimeout(() => {
        lineClearTimer = 0;
        resolve();
      }, preview.rows.length >= 4 ? 980 : 840);
    });
  }

  function renderNextPiece(piece) {
    if (!piece) return '';
    const cells = shape(piece.type, 0);
    return `<div class="blocks-next-piece piece-${piece.type}" title="${ui.escapeHTML(piece.type)}">
      ${Array.from({ length: 16 }, (_, index) => {
        const x = index % 4;
        const y = Math.floor(index / 4);
        const filled = cells.some(([dx, dy]) => dx === x && dy === y);
        return `<span class="${filled ? 'filled' : ''}"></span>`;
      }).join('')}
    </div>`;
  }

  function renderNext() {
    const box = document.getElementById('blocksNextBox');
    const mount = document.getElementById('blocksNext');
    if (!mount) return;
    if (box) box.hidden = !activeRound;
    const pieces = activeRound && Array.isArray(activeRound.next_pieces) ? activeRound.next_pieces : [];
    mount.innerHTML = pieces.slice(0, 3).map(renderNextPiece).join('') || `<span class="recent-empty">${ui.t('blocks_next_empty')}</span>`;
  }

  function renderStats() {
    const multiplier = activeRound ? Number(activeRound.current_multiplier || startingMultiplier()) : startingMultiplier();
    const potential = activeRound ? Number(activeRound.potential_win || 0) : selectedBet * multiplier;
    ui.setText('blocksMultiplier', multiplierLabel(multiplier));
    ui.setText('blocksPotential', ui.formatMoney(potential));
    ui.setText('blocksScore', ui.formatNumber(Number(activeRound?.score || 0)));
    ui.setText('blocksLines', ui.formatNumber(Number(activeRound?.lines_cleared || 0)));
    ui.setText('blocksPieces', ui.formatNumber(Number(activeRound?.pieces_placed || 0)));
    ui.setText('blocksSpeed', activeTickMs() + 'ms');
    document.querySelector('.blocks-meter')?.classList.toggle('is-win', Boolean(activeRound && activeRound.status === 'completed'));
  }

  function renderStatus() {
    const status = document.getElementById('blocksStatus');
    if (!status) return;
    status.classList.toggle('win', Boolean(activeRound && activeRound.status === 'completed'));
    status.classList.toggle('loss', Boolean(activeRound && activeRound.status === 'lost'));
    if (!activeRound) {
      status.textContent = ui.t('blocks_waiting');
      return;
    }
    if (activeRound.status === 'lost') {
      status.textContent = activeRound.loss_reason === 'forfeit'
        ? ui.t('blocks_forfeit_status')
        : ui.t('blocks_lost');
      return;
    }
    if (activeRound.status === 'completed') {
      status.textContent = ui.t('blocks_win', {
        multiplier: multiplierLabel(activeRound.current_multiplier),
        amount: ui.formatMoney(Number(activeRound.total_win || 0))
      });
      return;
    }
    if (Number(activeRound.last_clear || 0) >= 4) {
      status.textContent = ui.t('blocks_pyramid_clear', { multiplier: multiplierLabel(activeRound.current_multiplier) });
      return;
    }
    status.textContent = canCashout()
      ? ui.t('blocks_active_cashout', { multiplier: multiplierLabel(activeRound.current_multiplier) })
      : ui.t('blocks_cashout_locked');
  }

  function renderActions() {
    const action = document.getElementById('blocksAction');
    const forfeit = document.getElementById('blocksForfeit');
    if (action) {
      action.disabled = busy || (isActive() && !canCashout());
      action.textContent = isActive() ? ui.t('blocks_cashout') : ui.t('blocks_start');
    }
    if (forfeit) {
      forfeit.hidden = !isActive();
      forfeit.disabled = busy;
    }
  }

  function renderRecent() {
    ui.renderGameHistory?.('blocksRecent', recent, ui.t('blocks_recent_empty'));
  }

  function renderAll() {
    document.body.classList.toggle('blocks-round-active', isActive());
    document.body.classList.toggle('game-round-active', isActive());
    renderBalance();
    renderBets();
    renderDifficulty();
    renderBoard();
    renderNext();
    renderStats();
    renderStatus();
    renderActions();
    renderRecent();
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

  function acceptRound(result, options) {
    const hadNoRound = !activeRound;
    clearLineClearTimer();
    activeRound = result || null;
    if (activeRound && activeRound.difficulty) selectedDifficulty = activeRound.difficulty;
    if (!activeRound || activeRound.status !== 'active') {
      localPiece = null;
      stopTimer();
      if (activeRound && activeRound.status !== 'active') recordSettledRound(activeRound);
    } else if (!options || options.resetPiece !== false) {
      resetLocalPiece();
      startTimer();
    }
    renderAll();
    if (hadNoRound && activeRound && activeRound.status === 'active') {
      const box = document.getElementById('blocksNextBox');
      if (box) {
        box.classList.remove('is-intro');
        void box.offsetWidth;
        box.classList.add('is-intro');
        if (nextIntroTimer) global.clearTimeout(nextIntroTimer);
        nextIntroTimer = global.setTimeout(() => box.classList.remove('is-intro'), 2200);
      }
    }
  }

  async function restoreActiveRound() {
    const user = store.getDisplayUser();
    if (!user || !user.apiId || !store.getActiveNeonPyramidsRound) return;
    const result = await store.getActiveNeonPyramidsRound();
    if (!result || result.error) {
      activeRound = null;
      localPiece = null;
      stopTimer();
      renderAll();
      return;
    }
    if (result.status === 'active') acceptRound(result);
    else renderAll();
  }

  async function startRound() {
    if (busy) return;
    if (selectedBet > currentBalance()) {
      ui.showToast(ui.t('err_blocks_balance'), 'err');
      renderAll();
      return;
    }
    busy = true;
    renderActions();
    B.audio?.play?.('drop');
    const result = await store.startNeonPyramids(selectedBet, selectedDifficulty);
    busy = false;
    if (result && result.error === 'err_blocks_active_round') {
      await restoreActiveRound();
      return;
    }
    if (showStoreError(result)) {
      renderAll();
      return;
    }
    acceptRound(result);
  }

  async function requestStartRound() {
    if (isActive()) return;
    if (!controlsSeen()) {
      const confirmed = await openControlsModal();
      if (!confirmed) return;
    }
    startRound();
  }

  async function placeCurrentPiece() {
    if (busy || !isActive() || !localPiece) return;
    const clearPreview = createLineClearPreview();
    busy = true;
    stopTimer();
    renderActions();
    const result = await store.placeNeonPyramidsPiece(activeRound.round_id, {
      pieceId: localPiece.id,
      rotation: localPiece.rotation,
      x: localPiece.x,
      y: localPiece.y
    });
    busy = false;
    if (showStoreError(result)) {
      startTimer();
      renderAll();
      return;
    }
    if (result.status !== 'active') {
      store.commitGameWallet(result, 'game:blocks:settled');
      B.audio?.play?.('loss');
    }
    if (result.status === 'active' && Number(result.last_clear || 0) > 0 && clearPreview) {
      await playLineClearAnimation(clearPreview);
    }
    acceptRound(result);
  }

  async function cashoutRound() {
    if (busy || !canCashout()) return;
    busy = true;
    stopTimer();
    renderActions();
    const result = await store.cashoutNeonPyramids(activeRound.round_id);
    busy = false;
    if (showStoreError(result)) {
      startTimer();
      renderAll();
      return;
    }
    store.commitGameWallet(result, 'game:blocks:settled');
    B.audio?.play?.(Number(result.net || 0) > 0 ? 'win' : 'push');
    acceptRound(result);
  }

  async function forfeitRound() {
    if (busy || !isActive()) return;
    const confirmed = await ui.confirmAction({
      title: ui.t('blocks_forfeit_confirm_title'),
      message: ui.t('blocks_forfeit_confirm_message'),
      okLabel: ui.t('blocks_forfeit'),
      cancelLabel: ui.t('confirm_cancel')
    });
    if (!confirmed) return;
    busy = true;
    stopTimer();
    renderActions();
    const result = await store.forfeitNeonPyramids(activeRound.round_id);
    busy = false;
    if (showStoreError(result)) {
      startTimer();
      renderAll();
      return;
    }
    store.commitGameWallet(result, 'game:blocks:settled');
    B.audio?.play?.('loss');
    acceptRound(result);
  }

  function movePiece(delta) {
    if (!isActive() || !localPiece || busy) return;
    const board = normalizedBoard();
    const nextX = clampPieceX(localPiece.type, localPiece.rotation, localPiece.x + delta);
    if (canPlace(board, localPiece.type, localPiece.rotation, nextX, localPiece.y)) {
      localPiece.x = nextX;
      B.audio?.play?.('click');
      renderBoard();
    }
  }

  function rotatePiece() {
    if (!isActive() || !localPiece || busy) return;
    const board = normalizedBoard();
    const nextRotation = (localPiece.rotation + 1) % 4;
    const nextX = clampPieceX(localPiece.type, nextRotation, localPiece.x);
    if (canPlace(board, localPiece.type, nextRotation, nextX, localPiece.y)) {
      localPiece.rotation = nextRotation;
      localPiece.x = nextX;
      B.audio?.play?.('chip');
      renderBoard();
    }
  }

  function tickPiece() {
    if (!isActive() || !localPiece || busy) return;
    const board = normalizedBoard();
    if (canPlace(board, localPiece.type, localPiece.rotation, localPiece.x, localPiece.y + 1)) {
      localPiece.y += 1;
      renderBoard();
      return;
    }
    placeCurrentPiece();
  }

  function softDrop() {
    tickPiece();
  }

  function hardDrop() {
    if (!isActive() || !localPiece || busy) return;
    const board = normalizedBoard();
    while (canPlace(board, localPiece.type, localPiece.rotation, localPiece.x, localPiece.y + 1)) {
      localPiece.y += 1;
    }
    renderBoard();
    B.audio?.play?.('drop');
    placeCurrentPiece();
  }

  function startTimer() {
    stopTimer();
    if (isActive() && !document.hidden) timer = global.setInterval(tickPiece, activeTickMs());
  }

  function stopTimer() {
    if (timer) global.clearInterval(timer);
    timer = 0;
  }

  function handleKey(event) {
    if (!isActive()) return;
    const target = event.target;
    if (target && /input|textarea|select/i.test(target.tagName || '')) return;
    if (hasBlockingOverlay()) return;
    if (event.key === 'ArrowLeft' || event.code === 'KeyA') {
      event.preventDefault();
      movePiece(-1);
    } else if (event.key === 'ArrowRight' || event.code === 'KeyD') {
      event.preventDefault();
      movePiece(1);
    } else if (event.key === 'ArrowUp' || event.code === 'KeyW') {
      event.preventDefault();
      rotatePiece();
    } else if (event.key === 'ArrowDown' || event.code === 'KeyS') {
      event.preventDefault();
      softDrop();
    } else if (event.code === 'Space') {
      event.preventDefault();
      hardDrop();
    } else if (event.code === 'KeyC') {
      event.preventDefault();
      if (canCashout()) cashoutRound();
    }
  }

  function gestureCellSize(shell) {
    const rect = shell.getBoundingClientRect();
    return {
      x: Math.max(18, rect.width / WIDTH),
      y: Math.max(18, rect.height / boardHeight())
    };
  }

  function startBoardGesture(event) {
    if (!isActive() || busy || event.button > 0) return;
    const shell = event.currentTarget;
    boardGesture = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      moved: false,
      size: gestureCellSize(shell)
    };
    shell.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function moveBoardGesture(event) {
    if (!boardGesture || boardGesture.pointerId !== event.pointerId || !isActive() || busy) return;
    let dx = event.clientX - boardGesture.lastX;
    let dy = event.clientY - boardGesture.lastY;
    const horizontalStep = boardGesture.size.x * .72;
    const verticalStep = boardGesture.size.y * .9;
    while (Math.abs(dx) >= horizontalStep) {
      movePiece(dx > 0 ? 1 : -1);
      boardGesture.lastX += dx > 0 ? horizontalStep : -horizontalStep;
      dx = event.clientX - boardGesture.lastX;
      boardGesture.moved = true;
    }
    while (dy >= verticalStep) {
      softDrop();
      boardGesture.lastY += verticalStep;
      dy = event.clientY - boardGesture.lastY;
      boardGesture.moved = true;
    }
    event.preventDefault();
  }

  function finishBoardGesture(event) {
    if (!boardGesture || boardGesture.pointerId !== event.pointerId) return;
    const gesture = boardGesture;
    boardGesture = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (!isActive() || busy) return;
    const totalX = event.clientX - gesture.startX;
    const totalY = event.clientY - gesture.startY;
    const distance = Math.hypot(totalX, totalY);
    if (totalY > gesture.size.y * 2.2 && Math.abs(totalY) > Math.abs(totalX)) {
      hardDrop();
    } else if (totalY < -gesture.size.y * 1.25 && Math.abs(totalY) > Math.abs(totalX)) {
      rotatePiece();
    } else if (!gesture.moved && distance < 14) {
      rotatePiece();
    }
    event.preventDefault();
  }

  function initBlocks() {
    const boardShell = document.querySelector('.blocks-board-shell');
    boardShell?.addEventListener('pointerdown', startBoardGesture);
    boardShell?.addEventListener('pointermove', moveBoardGesture);
    boardShell?.addEventListener('pointerup', finishBoardGesture);
    boardShell?.addEventListener('pointercancel', () => { boardGesture = null; });
    document.addEventListener('click', e => {
      const bet = e.target.closest('[data-blocks-bet]');
      if (bet && !isActive()) {
        selectedBet = Number(bet.dataset.blocksBet);
        renderAll();
        return;
      }
      const control = e.target.closest('[data-blocks-control]');
      if (control) {
        const action = control.dataset.blocksControl;
        if (action === 'left') movePiece(-1);
        if (action === 'right') movePiece(1);
        if (action === 'rotate') rotatePiece();
        if (action === 'drop') hardDrop();
      }
      const difficulty = e.target.closest('[data-blocks-difficulty]');
      if (difficulty && !isActive()) {
        selectedDifficulty = difficulty.dataset.blocksDifficulty || 'level1';
        renderAll();
      }
    });
    document.addEventListener('keydown', handleKey);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopTimer();
      else if (isActive()) startTimer();
    });
    document.getElementById('blocksAction')?.addEventListener('click', () => {
      if (isActive()) cashoutRound();
      else requestStartRound();
    });
    document.getElementById('blocksForfeit')?.addEventListener('click', forfeitRound);
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
        BETS.splice(0, BETS.length, ...store.getManagerBetOptions('neon-pyramids'));
        if (selectedBet === 100) selectedBet = BETS[BETS.length - 1];
        renderBets();
      }
    });
    restoreActiveRound();
  }

  B.blocks = { init: initBlocks };
})(window);
