(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  const CHIPS = [5, 10, 25, 100];
  const VIP_TABLE_LIMITS = Object.freeze({ bronze: 100, silver: 150, gold: 250, platinum: 500 });
  const EUROPEAN_WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
  const redNumbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36];
  const RED_NUMBERS = new Set(redNumbers);
  const TWO_PI = Math.PI * 2;
  const TOP_ANGLE = -Math.PI / 2;
  const SPIN_MS = 4600;
  const WHEEL_TURNS = 6;
  const BALL_TURNS = 8;
  const TABLE_ROWS = [
    [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36],
    [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35],
    [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34]
  ];

  const bets = new Map();
  let selectedChip = 5;
  let selectedAllIn = false;
  let spinning = false;
  let wheelAngle = 0;
  let ballAngle = TOP_ANGLE;
  let ballBounce = 0;
  let spinLandingAngle = TOP_ANGLE;
  let canvas = null;
  let ctx = null;
  let canvasSize = 0;
  let lastResult = null;
  let initialized = false;
  let recentResults = [];
  let settledBets = [];
  let settlementState = '';
  let wheelResizeObserver = null;
  let wheelResizeFrame = 0;
  let spinFrameProgress = 1;
  let canvasDpr = 1;
  let wheelLayerCanvas = null;
  let wheelLayerSize = 0;
  let wheelLayerDpr = 0;

  function betKey(type, selection) {
    return type + ':' + selection;
  }

  function positiveModulo(value, mod) {
    return ((value % mod) + mod) % mod;
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function numberColor(number) {
    if (number === 0) return 'green';
    return RED_NUMBERS.has(number) ? 'red' : 'black';
  }

  function colorLabel(color) {
    return String(color || '').toUpperCase();
  }

  function tFallback(key, ruText, enText, vars) {
    const translated = ui.t(key, vars);
    if (translated !== key) return translated;
    const state = store.peekState ? store.peekState() : store.getState();
    const raw = state.lang === 'en' ? enText : ruText;
    return String(raw).replace(/\{\{(\w+)\}\}/g, (match, name) => vars && vars[name] !== undefined ? vars[name] : match);
  }

  function colorPaint(color) {
    if (color === 'green') return '#016f34';
    if (color === 'red') return '#b21c1c';
    return '#000000';
  }

  function pocketPaint(color, cx, cy, radius) {
    const gradient = ctx.createRadialGradient(cx - radius * 0.18, cy - radius * 0.24, radius * 0.1, cx, cy, radius);
    if (color === 'green') {
      gradient.addColorStop(0, '#11a964');
      gradient.addColorStop(0.44, '#016f34');
      gradient.addColorStop(1, '#002815');
    } else if (color === 'red') {
      gradient.addColorStop(0, '#e23a3a');
      gradient.addColorStop(0.42, '#9f1717');
      gradient.addColorStop(1, '#2a0505');
    } else {
      gradient.addColorStop(0, '#242424');
      gradient.addColorStop(0.46, '#050505');
      gradient.addColorStop(1, '#000000');
    }
    return gradient;
  }

  function selectorValue(value) {
    return global.CSS && global.CSS.escape ? global.CSS.escape(String(value)) : String(value).replace(/"/g, '\\"');
  }

  function textPaint(color) {
    if (color === 'green') return '#35df8b';
    if (color === 'red') return '#ff6b6b';
    return '#f7f3df';
  }

  function createRadialGradient(cx, cy, r, stops) {
    const gradient = ctx.createRadialGradient(cx - r * 0.22, cy - r * 0.28, r * 0.06, cx, cy, r);
    stops.forEach(stop => gradient.addColorStop(stop[0], stop[1]));
    return gradient;
  }

  function drawAnnularSector(cx, cy, innerR, outerR, start, end) {
    ctx.beginPath();
    ctx.arc(cx, cy, outerR, start, end, false);
    ctx.arc(cx, cy, innerR, end, start, true);
    ctx.closePath();
  }

  function drawCircle(cx, cy, r, fill, stroke, lineWidth) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, TWO_PI);
    ctx.fillStyle = fill;
    ctx.fill();
    if (stroke && lineWidth) {
      ctx.lineWidth = lineWidth;
      ctx.strokeStyle = stroke;
      ctx.stroke();
    }
  }

  function drawPocketNumber(number, angle, radius, color) {
    const fontSize = Math.max(13, canvasSize * 0.039);
    ctx.save();
    ctx.translate(canvasSize / 2 + Math.cos(angle) * radius, canvasSize / 2 + Math.sin(angle) * radius);
    ctx.rotate(angle + Math.PI / 2);
    ctx.fillStyle = '#fffdf5';
    ctx.strokeStyle = 'rgba(0,0,0,.78)';
    ctx.lineWidth = Math.max(2.1, canvasSize * 0.0035);
    ctx.font = `800 ${fontSize}px "Arial Narrow", "Roboto Condensed", "Trebuchet MS", Arial, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(0,0,0,.58)';
    ctx.shadowBlur = Math.max(2, canvasSize * 0.006);
    ctx.shadowOffsetY = Math.max(1, canvasSize * 0.002);
    ctx.strokeText(String(number), 0, 0);
    ctx.fillText(String(number), 0, 0);
    if (color === 'green') {
      ctx.strokeStyle = 'rgba(0,0,0,.7)';
      ctx.fillStyle = '#ffffff';
      ctx.strokeText(String(number), 0, 0);
      ctx.fillText(String(number), 0, 0);
    }
    ctx.restore();
  }

  function drawWheelFloorShadow(cx, cy, size) {
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(cx, cy + size * 0.05, size * 0.43, size * 0.12, 0, 0, TWO_PI);
    ctx.fillStyle = 'rgba(0,0,0,.32)';
    ctx.filter = `blur(${Math.max(6, size * 0.018)}px)`;
    ctx.fill();
    ctx.restore();
  }

  function drawCenterDisplay(cx, cy, size, turretRadius, fastFrame) {
    const displayW = turretRadius * 1.18;
    const displayH = turretRadius * 0.82;
    const displayX = cx - displayW / 2;
    const displayY = cy - displayH / 2;
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,.82)';
    ctx.strokeStyle = 'rgba(212,175,55,.86)';
    ctx.lineWidth = Math.max(1, size * 0.003);
    roundRect(displayX, displayY, displayW, displayH, size * 0.018);
    ctx.fill();
    ctx.stroke();

    const displayNumber = lastResult ? String(lastResult.number) : '--';
    const displayColor = lastResult ? colorLabel(lastResult.color) : 'READY';
    ctx.fillStyle = lastResult ? textPaint(lastResult.color) : '#d4af37';
    ctx.font = `900 ${lastResult ? size * 0.078 : size * 0.058}px Arial, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = lastResult ? textPaint(lastResult.color) : '#d4af37';
    ctx.shadowBlur = fastFrame ? 0 : size * 0.018;
    ctx.fillText(displayNumber, cx, cy - displayH * 0.08);
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#e8d8a2';
    ctx.font = `800 ${size * 0.022}px Arial, sans-serif`;
    ctx.fillText(displayColor, cx, cy + displayH * 0.30);
    ctx.restore();
  }

  function getWheelLayer() {
    if (wheelLayerCanvas && wheelLayerSize === canvasSize && wheelLayerDpr === canvasDpr) return wheelLayerCanvas;
    if (!global.document || !canvasSize) return null;

    const layer = global.document.createElement('canvas');
    layer.width = Math.round(canvasSize * canvasDpr);
    layer.height = Math.round(canvasSize * canvasDpr);
    const layerCtx = layer.getContext('2d');
    if (!layerCtx) return null;

    const previousCtx = ctx;
    const previousSize = canvasSize;
    ctx = layerCtx;
    canvasSize = previousSize;
    ctx.setTransform(canvasDpr, 0, 0, canvasDpr, 0, 0);
    drawWheel({
      renderLayer: true,
      wheelAngle: 0,
      skipBall: true,
      skipDisplay: true,
      skipFloorShadow: true
    });
    ctx = previousCtx;
    canvasSize = previousSize;

    wheelLayerCanvas = layer;
    wheelLayerSize = canvasSize;
    wheelLayerDpr = canvasDpr;
    return wheelLayerCanvas;
  }

  function drawSpinFrame() {
    const layer = getWheelLayer();
    if (!layer) return drawWheel({ renderLayer: true });

    const size = canvasSize;
    const cx = size / 2;
    const cy = size / 2;
    const pocketOuter = size * 0.38;
    const turretRadius = size * 0.154;

    ctx.clearRect(0, 0, size, size);
    drawWheelFloorShadow(cx, cy, size);
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(wheelAngle);
    ctx.drawImage(layer, -size / 2, -size / 2, size, size);
    ctx.restore();
    drawCenterDisplay(cx, cy, size, turretRadius, false);
    drawBall(cx, cy, pocketOuter - size * 0.034);
  }

  function drawWheel(options) {
    if (!ctx || !canvasSize) return;
    const opts = options || {};
    if (spinning && !opts.renderLayer) {
      drawSpinFrame();
      return;
    }
    const size = canvasSize;
    const fastFrame = false;
    const activeWheelAngle = opts.wheelAngle !== undefined ? opts.wheelAngle : wheelAngle;
    const cx = size / 2;
    const cy = size / 2;
    const outerWood = size * 0.46;
    const brassOuter = size * 0.418;
    const pocketOuter = size * 0.38;
    const pocketInner = size * 0.267;
    const bowlRadius = size * 0.236;
    const turretRadius = size * 0.154;
    const segment = TWO_PI / EUROPEAN_WHEEL.length;

    ctx.clearRect(0, 0, size, size);

    if (!opts.skipFloorShadow) drawWheelFloorShadow(cx, cy, size);

    // Polished mahogany/walnut outer board with subtle depth.
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.65)';
    ctx.shadowBlur = fastFrame ? 0 : size * 0.025;
    ctx.shadowOffsetY = fastFrame ? 0 : size * 0.014;
    drawCircle(cx, cy, outerWood, createRadialGradient(cx, cy, outerWood, [
      [0, '#8a5430'],
      [0.32, '#5c351f'],
      [0.66, '#28150d'],
      [1, '#090403']
    ]), '#d4af37', size * 0.012);
    ctx.restore();

    drawCircle(cx, cy, outerWood * 0.95, 'transparent', 'rgba(255,224,145,.18)', size * 0.004);
    drawCircle(cx, cy, outerWood * 0.88, 'transparent', 'rgba(0,0,0,.26)', size * 0.008);
    drawCircle(cx, cy, brassOuter, 'transparent', 'rgba(212,175,55,.96)', size * 0.02);
    drawCircle(cx, cy, brassOuter - size * 0.02, 'transparent', 'rgba(255,238,181,.18)', size * 0.006);
    drawCircle(cx, cy, pocketOuter + size * 0.012, 'transparent', 'rgba(255,234,173,.32)', size * 0.007);
    drawCircle(cx, cy, pocketInner - size * 0.016, createRadialGradient(cx, cy, pocketInner, [
      [0, 'rgba(255,255,255,.08)'],
      [0.52, 'rgba(0,0,0,.06)'],
      [1, 'rgba(0,0,0,.26)']
    ]), null, 0);

    // Number pockets in strict European order.
    EUROPEAN_WHEEL.forEach((number, index) => {
      const centerAngle = TOP_ANGLE + activeWheelAngle + index * segment;
      const start = centerAngle - segment / 2;
      const end = centerAngle + segment / 2;
      const color = numberColor(number);

      drawAnnularSector(cx, cy, pocketInner, pocketOuter, start, end);
      ctx.fillStyle = fastFrame ? colorPaint(color) : pocketPaint(color, cx, cy, pocketOuter);
      ctx.fill();
      ctx.lineWidth = Math.max(1.2, size * 0.0022);
      ctx.strokeStyle = 'rgba(255,224,145,.66)';
      ctx.stroke();

      if (!fastFrame) {
        // Small inner shine on every pocket.
        drawAnnularSector(cx, cy, pocketInner, pocketOuter, start + segment * 0.04, end - segment * 0.04);
        ctx.fillStyle = 'rgba(255,255,255,.055)';
        ctx.fill();
      }

      if (!fastFrame || index % 2 === 0) {
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(start) * pocketInner, cy + Math.sin(start) * pocketInner);
        ctx.lineTo(cx + Math.cos(start) * pocketOuter, cy + Math.sin(start) * pocketOuter);
        ctx.lineWidth = Math.max(1, size * 0.002);
        ctx.strokeStyle = 'rgba(255,234,173,.36)';
        ctx.stroke();
        ctx.restore();
      }

      drawPocketNumber(number, centerAngle, pocketInner + (pocketOuter - pocketInner) * 0.43, color);
    });

    drawCircle(cx, cy, pocketInner - size * 0.008, 'transparent', 'rgba(212,175,55,.98)', size * 0.008);
    drawCircle(cx, cy, pocketInner - size * 0.026, 'transparent', 'rgba(0,0,0,.28)', size * 0.01);
    drawCircle(cx, cy, bowlRadius, createRadialGradient(cx, cy, bowlRadius, [
      [0, '#f1eee4'],
      [0.48, '#d8d1bf'],
      [0.74, '#8d7b57'],
      [1, '#3b2815']
    ]), 'rgba(212,175,55,.65)', size * 0.004);
    drawCircle(cx, cy, bowlRadius * 0.82, 'transparent', 'rgba(255,255,255,.16)', size * 0.004);
    drawCircle(cx, cy, bowlRadius * 0.62, 'transparent', 'rgba(0,0,0,.18)', size * 0.006);

    // Glossy central turret and digital result display.
    for (let i = 0; i < 8; i += 1) {
      const spoke = activeWheelAngle * 0.22 + i * TWO_PI / 8;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(spoke);
      ctx.beginPath();
      ctx.roundRect?.(-size * 0.012, -bowlRadius * 0.88, size * 0.024, bowlRadius * 0.36, size * 0.008);
      if (!ctx.roundRect) roundRect(-size * 0.012, -bowlRadius * 0.88, size * 0.024, bowlRadius * 0.36, size * 0.008);
      ctx.fillStyle = 'rgba(75,48,25,.38)';
      ctx.fill();
      ctx.restore();
    }
    drawCircle(cx, cy, turretRadius, createRadialGradient(cx, cy, turretRadius, [
      [0, '#70634b'],
      [0.24, '#302821'],
      [0.68, '#080808'],
      [1, '#1b130c']
    ]), '#d4af37', size * 0.008);
    drawCircle(cx, cy, turretRadius * 0.88, 'transparent', 'rgba(255,234,173,.22)', size * 0.003);
    drawCircle(cx, cy, turretRadius * 0.72, 'rgba(255,255,255,.04)', 'rgba(255,255,255,.08)', 1);
    drawCircle(cx, cy, turretRadius * 0.26, createRadialGradient(cx, cy, turretRadius * 0.26, [
      [0, '#fff5c6'],
      [0.35, '#d4af37'],
      [1, '#5b371c']
    ]), 'rgba(255,244,190,.75)', size * 0.002);

    if (!opts.skipDisplay) drawCenterDisplay(cx, cy, size, turretRadius, fastFrame);
    if (!opts.skipBall) drawBall(cx, cy, pocketOuter - size * 0.034);
  }

  function roundRect(x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }

  function drawBall(cx, cy, baseRadius) {
    const radius = baseRadius + ballBounce;
    const x = cx + Math.cos(ballAngle) * radius;
    const y = cy + Math.sin(ballAngle) * radius;
    const ballR = Math.max(7, canvasSize * 0.017);

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(x + ballR * 0.34, y + ballR * 0.42, ballR * 0.9, ballR * 0.36, 0, 0, TWO_PI);
    ctx.fillStyle = 'rgba(0,0,0,.38)';
    ctx.fill();

    const gradient = ctx.createRadialGradient(x - ballR * 0.35, y - ballR * 0.35, ballR * 0.1, x, y, ballR);
    gradient.addColorStop(0, '#ffffff');
    gradient.addColorStop(0.42, '#f2f2f2');
    gradient.addColorStop(0.78, '#c9c9c9');
    gradient.addColorStop(1, '#7c7c7c');
    drawCircle(x, y, ballR, gradient, 'rgba(255,255,255,.8)', 1);
    ctx.restore();
  }

  function resizeCanvas() {
    if (!canvas) return;
    const box = canvas.getBoundingClientRect();
    const size = Math.max(280, Math.round(Math.min(box.width || 500, box.height || box.width || 500)));
    const dpr = Math.max(1, Math.min(1.6, global.devicePixelRatio || 1));
    canvasDpr = dpr;
    wheelLayerCanvas = null;
    wheelLayerSize = 0;
    wheelLayerDpr = 0;
    canvasSize = size;
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawWheel();
  }

  function scheduleCanvasResize() {
    if (wheelResizeFrame) return;
    wheelResizeFrame = requestAnimationFrame(() => {
      wheelResizeFrame = 0;
      resizeCanvas();
    });
  }

  function labelFor(type, selection) {
    const labels = {
      straight: ui.t('roulette_bet_straight', { value: selection }),
      split: ui.t('roulette_bet_split', { value: selection.replace(/-/g, '/') }),
      street: ui.t('roulette_bet_street', { value: selection }),
      corner: ui.t('roulette_bet_corner', { value: selection.replace(/-/g, '/') }),
      six_line: ui.t('roulette_bet_sixline', { value: selection }),
      dozen: ui.t('roulette_bet_dozen', { value: selection }),
      column: ui.t('roulette_bet_column', { value: selection }),
      color: ui.t('roulette_bet_' + selection),
      parity: ui.t('roulette_bet_' + selection),
      range: ui.t('roulette_bet_' + selection)
    };
    return labels[type] || `${type} ${selection}`;
  }

  function totalBet() {
    return Array.from(bets.values()).reduce((sum, bet) => sum + bet.amount, 0);
  }

  function currentBalance() {
    return Number(store.getDisplayUser().balance || 0);
  }

  function tableLimit() {
    const tier = String(store.getDisplayUser().vipTier || 'bronze').toLowerCase();
    const tierLimit = VIP_TABLE_LIMITS[tier] || VIP_TABLE_LIMITS.bronze;
    return Math.max(tierLimit, ...CHIPS.map(Number).filter(Number.isFinite));
  }

  function availableBetAmount() {
    const availableBalance = currentBalance() - totalBet();
    const availableAtTable = tableLimit() - totalBet();
    return Math.max(0, Math.floor(Math.min(availableBalance, availableAtTable) * 100) / 100);
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    const amount = result.min || result.max || 0;
    ui.showToast(ui.t(result.error, { amount: ui.formatMoney(amount) }), 'err');
    return true;
  }

  function resultState(result) {
    const net = Number(result?.net || 0);
    if (net > 0) return 'win';
    if (net < 0) return 'loss';
    return 'push';
  }

  function clearSettlement(clearResult) {
    settledBets = [];
    settlementState = '';
    document.querySelectorAll('.roulette-bet.is-settled-win,.roulette-bet.is-settled-loss,.roulette-bet.is-settled-push').forEach(el => {
      el.classList.remove('is-settled-win', 'is-settled-loss', 'is-settled-push');
      el.style.removeProperty('--settle-order');
    });
    const table = document.querySelector('.roulette-table-wrap');
    if (table) table.classList.remove('is-settled-win', 'is-settled-loss', 'is-settled-push');
    if (clearResult !== false) {
      const resultBox = document.getElementById('rouletteResult');
      if (resultBox) {
        resultBox.classList.remove('win', 'loss', 'push');
        resultBox.textContent = ui.t('roulette_result_empty');
      }
    }
  }

  function applySettlement(result) {
    settlementState = resultState(result);
    settledBets = Array.isArray(result?.bets) ? result.bets.map((bet, index) => ({
      type: String(bet.type || ''),
      selection: String(bet.selection || ''),
      won: Boolean(bet.won),
      order: index
    })) : [];

    const table = document.querySelector('.roulette-table-wrap');
    if (table) {
      table.classList.toggle('is-settled-win', settlementState === 'win');
      table.classList.toggle('is-settled-loss', settlementState === 'loss');
      table.classList.toggle('is-settled-push', settlementState === 'push');
    }
    syncBetHighlights();
  }

  function addBet(type, selection) {
    if (spinning) return;
    clearSettlement();
    const key = betKey(type, selection);
    const existing = bets.get(key);
    const available = availableBetAmount();
    const amount = selectedAllIn ? available : selectedChip;
    if (amount < 1) {
      const balanceBlocked = currentBalance() - totalBet() < 1;
      ui.showToast(ui.t(balanceBlocked ? 'err_roulette_balance' : 'err_roulette_total_max', {
        amount: ui.formatMoney(tableLimit())
      }), 'err');
      return;
    }
    if (!selectedAllIn && amount > available) {
      const balanceBlocked = currentBalance() - totalBet() < amount;
      ui.showToast(ui.t(balanceBlocked ? 'err_roulette_balance' : 'err_roulette_total_max', {
        amount: ui.formatMoney(tableLimit())
      }), 'err');
      return;
    }
    bets.set(key, {
      type,
      selection: String(selection),
      amount: (existing ? existing.amount : 0) + amount
    });
    renderBets();
  }

  function removeBet(key) {
    if (spinning) return;
    clearSettlement();
    bets.delete(key);
    renderBets();
  }

  function clearBets() {
    if (spinning) return;
    clearSettlement();
    bets.clear();
    renderBets();
  }

  function renderBalance() {
    const user = store.getDisplayUser();
    ui.setText('game-balance', ui.formatMoney(user.balance, user.currency));
  }

  function renderChips() {
    const mount = document.getElementById('rouletteChips');
    if (!mount) return;
    const allInAmount = availableBetAmount();
    if (allInAmount < 1) selectedAllIn = false;
    mount.innerHTML = CHIPS.map(value => `
      <button class="chip-btn ${!selectedAllIn && value === selectedChip ? 'selected' : ''}" type="button" data-chip="${value}">
        ${ui.formatMoney(value)}
      </button>
    `).join('') + `
      <button class="chip-btn roulette-all-in-chip ${selectedAllIn ? 'selected' : ''}" type="button" data-all-in-chip ${allInAmount < 1 ? 'disabled' : ''}>
        <span>${ui.t('roulette_all_in')}</span>
      </button>
    `;
  }

  function renderBets() {
    const slip = document.getElementById('rouletteBetSlip');
    if (slip) {
      const items = Array.from(bets.entries());
      slip.innerHTML = items.length ? items.map(([key, bet]) => `
        <div class="bet-slip-item">
          <span>${ui.escapeHTML(labelFor(bet.type, bet.selection))}</span>
          <strong>${ui.formatMoney(bet.amount)}</strong>
          <button type="button" aria-label="Remove bet" data-remove-bet="${ui.escapeHTML(key)}">x</button>
        </div>
      `).join('') : `<div class="empty-cell">${ui.t('roulette_no_bets')}</div>`;
    }
    ui.setText('rouletteTotal', ui.formatMoney(totalBet()));
    const spin = document.getElementById('rouletteSpin');
    if (spin) spin.disabled = spinning || !bets.size;
    renderChips();
    document.querySelector('.roulette-table-wrap')?.classList.toggle('is-disabled', spinning);
    syncBetHighlights();
  }

  function syncBetHighlights() {
    document.querySelectorAll('.roulette-bet.is-selected').forEach(el => {
      el.classList.remove('is-selected');
      el.removeAttribute('data-bet-amount');
    });
    document.querySelectorAll('.roulette-bet.is-settled-win,.roulette-bet.is-settled-loss,.roulette-bet.is-settled-push').forEach(el => {
      el.classList.remove('is-settled-win', 'is-settled-loss', 'is-settled-push');
      el.style.removeProperty('--settle-order');
    });
    bets.forEach(bet => {
      const selector = `.roulette-bet[data-bet-type="${selectorValue(bet.type)}"][data-selection="${selectorValue(bet.selection)}"]`;
      const button = document.querySelector(selector);
      if (!button) return;
      button.classList.add('is-selected');
      button.dataset.betAmount = ui.formatMoney(bet.amount);
    });
    settledBets.forEach((bet, index) => {
      const selector = `.roulette-bet[data-bet-type="${selectorValue(bet.type)}"][data-selection="${selectorValue(bet.selection)}"]`;
      const button = document.querySelector(selector);
      if (!button) return;
      const className = bet.won ? 'is-settled-win' : settlementState === 'push' ? 'is-settled-push' : 'is-settled-loss';
      button.classList.add(className);
      button.style.setProperty('--settle-order', String(index));
    });
  }

  function button(type, selection, label, extraClass) {
    return `<button class="roulette-bet ${extraClass || ''}" type="button" data-bet-type="${type}" data-selection="${selection}">${label}</button>`;
  }

  function renderNumbers() {
    const mount = document.getElementById('rouletteNumbers');
    if (!mount) return;
    const buttons = [`
      <button class="roulette-bet number-bet green zero" type="button" data-bet-type="straight" data-selection="0" data-number-color="green">0</button>
    `];
    TABLE_ROWS.forEach(row => {
      row.forEach(number => {
      const color = numberColor(number);
        buttons.push(`<button class="roulette-bet number-bet ${color}" type="button" data-bet-type="straight" data-selection="${number}" data-number-color="${color}">${number}</button>`);
      });
    });
    mount.innerHTML = buttons.join('');
  }

  function renderOutside() {
    const mount = document.getElementById('rouletteOutside');
    if (!mount) return;
    const items = [
      ['range', 'low', '1-18'],
      ['parity', 'even', ui.t('roulette_even')],
      ['color', 'red', ui.t('roulette_red')],
      ['color', 'black', ui.t('roulette_black')],
      ['parity', 'odd', ui.t('roulette_odd')],
      ['range', 'high', '19-36']
    ];
    mount.innerHTML = items.map(item => button(item[0], item[1], item[2], item[1])).join('');
  }

  function renderRows() {
    const mount = document.getElementById('rouletteRows');
    if (!mount) return;
    const streets = Array.from({ length: 12 }, (_, index) => index + 1)
      .map(row => button('street', row, `${ui.t('roulette_street_short')} ${row}`, 'mini-bet'));
    const sixLines = Array.from({ length: 11 }, (_, index) => index + 1)
      .map(row => button('six_line', row, `${ui.t('roulette_sixline_short')} ${row}`, 'mini-bet'));
    mount.innerHTML = streets.concat(sixLines).join('');
  }

  function renderSplits() {
    const mount = document.getElementById('rouletteSplits');
    if (!mount) return;
    const pairs = [[0, 1], [0, 2], [0, 3]];
    for (let row = 0; row < 12; row += 1) {
      const base = row * 3 + 1;
      pairs.push([base, base + 1], [base + 1, base + 2]);
      if (row < 11) pairs.push([base, base + 3], [base + 1, base + 4], [base + 2, base + 5]);
    }
    mount.innerHTML = pairs.map(pair => button('split', pair.join('-'), pair.join('/'), 'mini-bet')).join('');
  }

  function renderCorners() {
    const mount = document.getElementById('rouletteCorners');
    if (!mount) return;
    const corners = [];
    for (let row = 0; row < 11; row += 1) {
      const base = row * 3 + 1;
      corners.push([base, base + 1, base + 3, base + 4]);
      corners.push([base + 1, base + 2, base + 4, base + 5]);
    }
    mount.innerHTML = corners.map(corner => button('corner', corner.join('-'), corner.join('/'), 'mini-bet')).join('');
  }

  function renderTable() {
    renderNumbers();
    renderOutside();
    renderRows();
    renderSplits();
    renderCorners();
  }

  function targetWheelAngleFor(number, landingAngle) {
    const index = Math.max(0, EUROPEAN_WHEEL.indexOf(Number(number)));
    const segment = TWO_PI / EUROPEAN_WHEEL.length;
    const desiredModulo = positiveModulo(landingAngle - TOP_ANGLE - index * segment, TWO_PI);
    const currentModulo = positiveModulo(wheelAngle, TWO_PI);
    let delta = desiredModulo - currentModulo;
    if (delta < 0) delta += TWO_PI;
    return wheelAngle + WHEEL_TURNS * TWO_PI + delta;
  }

  function targetBallAngle(landingAngle) {
    const desiredModulo = positiveModulo(landingAngle, TWO_PI);
    const currentModulo = positiveModulo(ballAngle, TWO_PI);
    let delta = desiredModulo - currentModulo;
    if (delta > 0) delta -= TWO_PI;
    return ballAngle - BALL_TURNS * TWO_PI + delta;
  }

  function randomLandingAngle(number) {
    const segment = TWO_PI / EUROPEAN_WHEEL.length;
    const index = Math.max(0, EUROPEAN_WHEEL.indexOf(Number(number)));
    const pocketCenter = TOP_ANGLE + wheelAngle + index * segment;
    const pocketJitter = (Math.random() - 0.5) * segment * 0.56;
    return positiveModulo(pocketCenter + Math.PI * 0.75 + Math.random() * Math.PI * 1.5 + pocketJitter, TWO_PI);
  }

  function animateSpin(result) {
    spinLandingAngle = randomLandingAngle(result.number);
    const startWheel = wheelAngle;
    const endWheel = targetWheelAngleFor(result.number, spinLandingAngle);
    const startBall = ballAngle;
    const endBall = targetBallAngle(spinLandingAngle);
    const startedAt = performance.now();

    return new Promise(resolve => {
      function frame(now) {
        const raw = Math.min(1, (now - startedAt) / SPIN_MS);
        spinFrameProgress = raw;
        const eased = easeOutCubic(raw);
        wheelAngle = startWheel + (endWheel - startWheel) * eased;
        ballAngle = startBall + (endBall - startBall) * eased;

        // On the last third of the spin the ball hops from pocket to pocket and settles.
        if (raw > 0.62 && raw < 0.985) {
          const settle = 1 - ((raw - 0.62) / 0.365);
          ballBounce = Math.sin(raw * 44 * Math.PI) * canvasSize * 0.011 * Math.max(0, settle);
        } else {
          ballBounce = 0;
        }

        drawWheel();
        if (raw < 1) {
          requestAnimationFrame(frame);
        } else {
          wheelAngle = positiveModulo(endWheel, TWO_PI);
          ballAngle = positiveModulo(endBall, TWO_PI);
          ballBounce = 0;
          spinFrameProgress = 1;
          drawWheel();
          resolve();
        }
      }
      requestAnimationFrame(frame);
    });
  }

  function renderResult(result) {
    const resultBox = document.getElementById('rouletteResult');
    const colorKey = 'roulette_color_' + result.result.color;
    if (resultBox) {
      const net = Number(result.net || 0);
      const totalWin = Math.max(0, Number(result.total_win || 0));
      const netLabel = (net > 0 ? '+' : '') + ui.formatMoney(net);
      resultBox.classList.toggle('win', net > 0);
      resultBox.classList.toggle('loss', net < 0);
      resultBox.classList.toggle('push', net === 0);
      const vars = {
        number: result.result.number,
        color: ui.t(colorKey),
        amount: ui.formatMoney(Math.abs(net)),
        payout: ui.formatMoney(totalWin),
        net: netLabel
      };
      if (totalWin > 0) {
        resultBox.textContent = ui.t('roulette_result_win', vars);
      } else {
        resultBox.textContent = net === 0
          ? tFallback('roulette_result_push', '{{number}} {{color}} - без изменений', '{{number}} {{color}} - push', vars)
          : ui.t('roulette_result_loss', vars);
      }
    }
  }

  function renderRecentResults() {
    const mount = document.getElementById('rouletteRecent');
    if (!mount) return;
    mount.innerHTML = recentResults.length ? recentResults.map(item => `
      <span class="recent-number ${ui.escapeHTML(item.color)}">${ui.escapeHTML(item.number)}</span>
    `).join('') : `<span class="recent-empty">${tFallback('roulette_recent_empty', 'Последние числа появятся после spin', 'Recent numbers appear after a spin')}</span>`;
  }

  function toggleAdvancedBets() {
    const panel = document.getElementById('rouletteAdvancedPanel');
    const toggle = document.getElementById('rouletteAdvancedToggle');
    if (!panel || !toggle) return;
    const isOpen = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
    if (isOpen) {
      panel.classList.remove('is-open');
      window.setTimeout(() => {
        if (toggle.getAttribute('aria-expanded') !== 'true') panel.hidden = true;
      }, 280);
      return;
    }
    panel.hidden = false;
    requestAnimationFrame(() => panel.classList.add('is-open'));
  }

  async function spin() {
    if (spinning) return;
    if (!bets.size) {
      ui.showToast(ui.t('err_roulette_no_bets'), 'err');
      return;
    }
    if (totalBet() > currentBalance()) {
      ui.showToast(ui.t('err_roulette_balance'), 'err');
      return;
    }

    spinning = true;
    clearSettlement();
    lastResult = null;
    renderBets();
    drawWheel();
    B.audio?.play?.('spin');

    const payload = Array.from(bets.values()).map(bet => ({
      type: bet.type,
      selection: bet.selection,
      amount: bet.amount
    }));
    const result = await store.playRoulette(payload);

    if (showStoreError(result)) {
      spinning = false;
      renderBets();
      drawWheel();
      return;
    }

    await animateSpin(result.result);
    lastResult = result.result;
    recentResults.unshift(result.result);
    recentResults = recentResults.slice(0, 12);
    drawWheel();
    renderResult(result);
    renderRecentResults();
    applySettlement(result);
    store.commitGameWallet(result, 'game:roulette:settled');
    B.audio?.play?.(Number(result.net || 0) > 0 ? 'win' : (Number(result.net || 0) < 0 ? 'loss' : 'push'));
    bets.clear();
    spinning = false;
    renderBalance();
    renderBets();
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      const chip = event.target.closest('[data-chip]');
      if (chip) {
        selectedChip = Number(chip.dataset.chip || selectedChip);
        selectedAllIn = false;
        renderChips();
        return;
      }

      const allIn = event.target.closest('[data-all-in-chip]');
      if (allIn) {
        selectedAllIn = true;
        renderChips();
        return;
      }

      const bet = event.target.closest('[data-bet-type][data-selection]');
      if (bet) {
        addBet(bet.dataset.betType, bet.dataset.selection);
        return;
      }

      const remove = event.target.closest('[data-remove-bet]');
      if (remove) {
        removeBet(remove.dataset.removeBet);
      }
    });
    document.getElementById('rouletteClear')?.addEventListener('click', clearBets);
    document.getElementById('rouletteSpin')?.addEventListener('click', spin);
    document.getElementById('rouletteAdvancedToggle')?.addEventListener('click', toggleAdvancedBets);
    global.addEventListener('resize', scheduleCanvasResize);
    if (global.ResizeObserver && canvas && !wheelResizeObserver) {
      wheelResizeObserver = new ResizeObserver(scheduleCanvasResize);
      wheelResizeObserver.observe(canvas);
    }
  }

  function initCanvas() {
    canvas = document.getElementById('rouletteCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    resizeCanvas();
  }

  function init() {
    if (document.body.dataset.page !== 'game' || initialized) return;
    initialized = true;
    initCanvas();
    renderBalance();
    renderChips();
    renderTable();
    renderBets();
    renderRecentResults();
    bindEvents();
    store.subscribe(() => {
      if (!spinning) renderBalance();
    });
    store.getManagerState?.().then(result => {
      if (!result?.error) {
        CHIPS.splice(0, CHIPS.length, ...store.getManagerBetOptions('roulette'));
        if (selectedChip === 100) selectedChip = CHIPS[CHIPS.length - 1];
        renderChips();
      }
    });
  }

  B.game = { init };
})(window);
