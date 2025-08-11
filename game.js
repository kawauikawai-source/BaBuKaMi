// game.js — усиленная версия: больше бомб, выше скорость падения и частота спавна.
// Замените текущий game.js этим файлом.

(function(){
  const canvas = document.getElementById('gameCanvas');
  const ctx = canvas.getContext('2d');

  // DOM refs
  const startOverlay = document.getElementById('startOverlay');
  const startBtn = document.getElementById('startBtn');
  const restartBtn = document.getElementById('restartBtn');
  const progressFill = document.getElementById('progressFill');
  const countText = document.getElementById('countText');
  const btnGetPrize = document.getElementById('btnGetPrize');
  const endOverlay = document.getElementById('endOverlay');
  const claimBtn = document.getElementById('claimBtn');
  const closeOverlay = document.getElementById('closeOverlay');
  const bottleFill = document.getElementById('bottleFill');

  // HUD
  const scoreBox = document.getElementById('scoreBox');
  const bestBox = document.getElementById('bestBox');
  const levelBox = document.getElementById('levelBox');
  const multBox = document.getElementById('multBox');
  const timerBox = document.getElementById('timerBox');
  const pauseBtn = document.getElementById('pauseBtn');
  const sensitivityInput = document.getElementById('sensitivity');

  // tuning constants — усиленные значения (скорость и бомбы)
  const GLOBAL_SPEED_MULT = 2.6;    // сильно увеличен общий множитель скорости
  const FALL_ACCEL = 0.12;          // ускорение падения (увеличено)
  let spawnInterval = 300;          // стартовый интервал спавна (мс) — уменьшён
  const spawnMin = 60;              // минимальный интервал (мс) — уменьшён

  // bad-object tuning (два типа) — увеличена вероятность и доля бомб
  const baseBadProb = 0.20;         // базовая вероятность плохого объекта (увеличена)
  const badIncreasePerLevel = 0.06; // усиленный рост вероятности bad с уровнем
  const maxBadProb = 0.80;          // высокий максимум вероятности bad

  // среди плохих — доля, которая будет бомбой (рост с уровнем)
  const baseBombShare = 0.50;       // базовая доля плохих, которые бомбы (увеличена)
  const bombSharePerLevel = 0.06;   // рост доли бомб с уровнем (увеличен)
  const maxBombShare = 0.95;

  // penalties (оставил прежние, можно менять)
  const badSmallPenalty = 120;      // лёгкий штраф очков (слегка увеличен)
  const badSmallStunMs = 700;       // лёгкий стан (ms)

  const badBombPenalty = 450;       // сильный штраф очков (увеличен)
  const badBombStunMs = 2000;       // длительный стан (ms)

  // state
  let drops = [];
  let lastSpawn = 0;
  let lastTime = 0;
  let rafId = null;

  let catcher = { x: 0, y: 0, w: 120, h: 34, vx:0, ax:0, maxSpeed: 20, accel: 1.0, friction: 0.88 };
  let count = 0;
  const targetDefault = 10;

  // scoring & combo
  let score = 0;
  const basePoints = 100;
  let comboCount = 0;
  let multiplier = 1;
  const comboTimeoutMs = 2500;
  let lastComboAt = 0;

  // waves & modes
  let mode = 'quick'; // quick | infinite | hardcore
  let level = 1;
  let waveIndex = 0;
  let waves = []; // array of {target, time}
  let waveTimer = 0; // ms left
  let waveActive = false;

  // infinite mode variables
  let timeSinceStart = 0;

  // UI/game flags
  let running = false;
  let finished = false;
  let paused = false;

  let pointerX = null;
  const keys = { left:false, right:false };

  // stun (block movement until timestamp)
  let disabledMovementUntil = 0;

  // floating texts & camera shake
  const floatingTexts = [];
  let shakeUntil = 0;
  let shakeIntensity = 0;
  const canvasOuter = document.getElementById('canvasOuter');

  // best score per mode key
  function bestKeyForMode(m){ return 'bibu_best_score_' + m; }

  // helper to get current logical size (CSS pixels)
  function getSize(){
    return { w: canvas.clientWidth, h: canvas.clientHeight };
  }

  // DPR-aware resize
  function resizeCanvas(){
    const { w: cssW, h: cssH } = getSize();
    const DPR = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(cssW * DPR));
    canvas.height = Math.max(1, Math.floor(cssH * DPR));
    ctx.setTransform(DPR,0,0,DPR,0,0);
    const cw = cssW, ch = cssH;
    catcher.y = ch - 48;
    catcher.w = Math.max(72, Math.min(220, Math.round(cw * 0.14)));
    catcher.h = 28;
    catcher.x = Math.max(0, Math.min(cw - catcher.w, catcher.x || (cw/2 - catcher.w/2)));
  }

  // mode/waves presets
  const MODE_PRESETS = {
    quick: { waves: [ {target:5, time:30000}, {target:6, time:26000}, {target:8, time:24000} ], info: 'Короткие волны с таймером' },
    infinite: { waves: [], info: 'Бесконечная игра на очки' },
    hardcore: { waves: [ {target:6, time:18000}, {target:7, time:16000}, {target:9, time:14000}, {target:12, time:12000} ], info: 'Жёсткие таймеры и цели' }
  };

  function prepareMode(selectedMode){
    mode = selectedMode;
    comboCount = 0;
    multiplier = 1;
    level = 1;
    waveIndex = 0;
    count = 0;
    score = 0;
    timeSinceStart = 0;
    disabledMovementUntil = 0;
    // faster baseline
    spawnInterval = 300;
    if (mode === 'infinite'){
      waves = [];
      waveTimer = 0;
      waveActive = false;
      spawnInterval = 300;
    } else {
      waves = JSON.parse(JSON.stringify(MODE_PRESETS[mode].waves));
      waveIndex = 0;
      if (waves.length) {
        waveTimer = waves[0].time;
        waveActive = true;
        spawnInterval = Math.max(spawnMin, 300 - waveIndex * 50);
      }
    }
    updateHUD();
    updateBestDisplay();
  }

  function updateBestDisplay(){
    const best = Number(localStorage.getItem(bestKeyForMode(mode)) || 0);
    bestBox.textContent = 'Рекорд: ' + best;
  }

  // spawn drop with chance to be good / bad_small / bad_bomb
  function spawnDrop(){
    if (finished || !running || paused) return;
    const { w: cw } = getSize();
    const r = Math.max(5, Math.round(Math.random() * 8 + 6));
    const x = Math.random() * (cw - r*2) + r;

    // compute bad probability based on level
    const badProb = Math.min(maxBadProb, baseBadProb + (level - 1) * badIncreasePerLevel);
    const isBad = Math.random() < badProb;

    // among bad, decide bomb or small (bombShare grows with level)
    const bombShare = Math.min(maxBombShare, baseBombShare + (level - 1) * bombSharePerLevel);
    const isBomb = isBad && (Math.random() < bombShare);

    // base speed higher, multiplied by global constant
    const baseSpeed = (Math.random() * 1.1 + 1.9); // 1.9..3.0 — больше вариативности и скорость
    const speed = baseSpeed * GLOBAL_SPEED_MULT * (1 + (level - 1) * 0.12) * (mode === 'hardcore' ? 1.12 : 1);

    const type = isBad ? (isBomb ? 'bad_bomb' : 'bad_small') : 'good';
    drops.push({ x, y: -r*2, r, vy: speed, type });
  }

  // update difficulty on level
  function updateDifficulty(){
    spawnInterval = Math.max(spawnMin, 300 - (level - 1) * 56);
  }

  // update loop
  function update(dt, now){
    if (!running || paused) return;
    lastSpawn += dt;

    // adaptive spawn for infinite (быстрее со временем)
    if (mode === 'infinite') {
      timeSinceStart += dt;
      const dynamicInterval = Math.max(spawnMin, 300 - Math.floor(timeSinceStart / 900)); // сильнее ускоряем со временем
      if (lastSpawn > dynamicInterval) {
        spawnDrop();
        lastSpawn = 0;
      }
    } else {
      if (lastSpawn > spawnInterval){
        spawnDrop();
        lastSpawn = 0;
      }
    }

    const { w: cw, h: ch } = getSize();

    for (let i = drops.length - 1; i >= 0; i--){
      const d = drops[i];
      // faster fall using FALL_ACCEL
      d.y += d.vy * dt * FALL_ACCEL;

      // collision with catcher
      if (d.y + d.r >= catcher.y && d.x >= catcher.x && d.x <= catcher.x + catcher.w){
        drops.splice(i,1);
        if (d.type === 'good') onCatch(d, now);
        else if (d.type === 'bad_small') onBadSmallCatch(d, now);
        else if (d.type === 'bad_bomb') onBadBombCatch(d, now);
        continue;
      }
      // missed
      if (d.y - d.r > ch + 30){
        drops.splice(i,1);
        if (d.type === 'good') onMiss();
      }
    }

    // movement handling — blocked if stunned
    const sens = parseFloat(sensitivityInput.value || '1');
    if (now < disabledMovementUntil) {
      // stunned — strong braking
      catcher.vx *= 0.75;
    } else {
      if (keys.left) catcher.vx -= catcher.accel * sens;
      if (keys.right) catcher.vx += catcher.accel * sens;

      // pointer influence only when not stunned
      if (pointerX !== null){
        const targetX = pointerX - catcher.w/2;
        catcher.vx += (targetX - catcher.x) * 0.025 * sens;
      }
    }

    // friction and velocity clamp
    catcher.vx *= catcher.friction;
    catcher.vx = Math.max(-catcher.maxSpeed, Math.min(catcher.maxSpeed, catcher.vx));
    catcher.x += catcher.vx * dt * 0.06;
    catcher.x = Math.max(0, Math.min(cw - catcher.w, catcher.x));

    // combo timeout
    if (comboCount > 0 && now - lastComboAt > comboTimeoutMs){
      comboCount = 0;
      multiplier = 1;
      updateHUD();
    }

    // timer handling for waves
    if (waveActive && mode !== 'infinite'){
      waveTimer -= dt;
      if (waveTimer <= 0){
        onWaveFail();
      }
    }

    // update level for infinite
    if (mode === 'infinite'){
      const newLevel = 1 + Math.floor(timeSinceStart / 6500); // уровень растёт чуть быстрее
      if (newLevel > level){
        level = newLevel;
        levelBox.textContent = 'Уровень: ' + level;
        updateDifficulty();
      }
    }
  }

  // on good catch
  function onCatch(d, now){
    comboCount++;
    lastComboAt = now || performance.now();
    multiplier = 1 + Math.floor(comboCount / 3);

    const gained = Math.round(basePoints * multiplier);
    score += gained;

    count = count + 1;
    updateHUD();

    if (mode !== 'infinite' && waveActive){
      const currentWave = waves[waveIndex];
      if (count >= currentWave.target){
        onWaveComplete();
      }
    }

    if (mode === 'infinite'){
      const newLevel = 1 + Math.floor(count / 8);
      if (newLevel > level){
        level = newLevel;
        levelBox.textContent = 'Уровень: ' + level;
        updateDifficulty();
      }
    }
  }

  // bad small catch
  function onBadSmallCatch(d, now){
    score = Math.max(0, score - badSmallPenalty);
    comboCount = 0;
    multiplier = 1;
    disabledMovementUntil = (now || performance.now()) + badSmallStunMs;
    flashHUD('#fff7f7', '#b00020', 360);
    popPenalty('-' + badSmallPenalty, d.x, d.y);
    updateHUD();
  }

  // bad bomb catch
  function onBadBombCatch(d, now){
    score = Math.max(0, score - badBombPenalty);
    comboCount = 0;
    multiplier = 1;
    disabledMovementUntil = (now || performance.now()) + badBombStunMs;
    flashHUD('#fff0f0', '#8b0000', 620);
    popPenalty('-' + badBombPenalty, d.x, d.y);
    cameraShake(14, 520);
    updateHUD();
  }

  // missed good
  function onMiss(){
    comboCount = 0;
    multiplier = 1;
    updateHUD();
  }

  function onWaveComplete(){
    waveIndex++;
    count = 0;
    comboCount = 0;
    multiplier = 1;
    score += 200 * level; // bonus
    if (waveIndex >= waves.length){
      onWin();
    } else {
      level++;
      updateDifficulty();
      waveTimer = waves[waveIndex].time;
      levelBox.textContent = 'Уровень: ' + level;
      levelBox.style.transform = 'scale(1.06)';
      setTimeout(()=> levelBox.style.transform = '', 260);
    }
    updateHUD();
  }

  function onWaveFail(){
    finished = true;
    running = false;
    waveActive = false;
    if (rafId) cancelAnimationFrame(rafId);
    saveBestIfNeeded();
    showEndOverlay('Время вышло — вы не успели пройти волну.');
  }

  function saveBestIfNeeded(){
    const key = bestKeyForMode(mode);
    const best = Number(localStorage.getItem(key) || 0);
    if (score > best){
      localStorage.setItem(key, score);
    }
  }

  function onWin(){
    finished = true;
    running = false;
    if (rafId) cancelAnimationFrame(rafId);
    bottleFill.style.height = '100%';
    claimBtn.disabled = false;
    btnGetPrize.disabled = false;
    saveBestIfNeeded();
    showEndOverlay('Поздравляем! Вы прошли все волны.');
  }

  function showEndOverlay(message){
    const endTitle = document.getElementById('endTitle');
    const endMessage = document.getElementById('endMessage');
    if (endTitle) endTitle.textContent = finished ? 'Игра окончена' : 'Итог';
    if (endMessage) endMessage.textContent = message;
    endOverlay.classList.add('show');
    endOverlay.setAttribute('aria-hidden','false');
    updateBestDisplay();
  }

  // start / pause / restart
  function startGame(){
    const sel = document.querySelector('input[name="mode"]:checked');
    const selectedMode = sel ? sel.value : 'quick';
    prepareMode(selectedMode);
    running = true;
    finished = false;
    paused = false;
    lastTime = 0;
    lastSpawn = 0;
    startOverlay.setAttribute('aria-hidden','true');
    startOverlay.style.display = 'none';
    restartBtn.disabled = false;
    pauseBtn.disabled = false;
    rafId = requestAnimationFrame(loop);
  }

  function togglePause(){
    if (finished || !running) return;
    paused = !paused;
    if (paused){
      pauseBtn.textContent = 'Продолжить';
      pauseBtn.setAttribute('aria-pressed','true');
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;
    } else {
      pauseBtn.textContent = 'Пауза';
      pauseBtn.setAttribute('aria-pressed','false');
      lastTime = 0;
      rafId = requestAnimationFrame(loop);
    }
  }

  function restartGame(){
    running = false;
    finished = false;
    paused = false;
    drops.length = 0;
    lastSpawn = 0;
    spawnInterval = 300;
    count = 0;
    score = 0;
    comboCount = 0;
    multiplier = 1;
    level = 1;
    waveIndex = 0;
    waveTimer = 0;
    waveActive = false;
    timeSinceStart = 0;
    disabledMovementUntil = 0;
    catcher.vx = 0;
    catcher.x = (canvas.clientWidth/2) - (catcher.w/2);
    updateHUD();
    bottleFill.style.height = '0%';
    endOverlay.classList.remove('show');
    endOverlay.setAttribute('aria-hidden','true');
    claimBtn.disabled = true;
    btnGetPrize.disabled = true;
    startOverlay.setAttribute('aria-hidden','false');
    startOverlay.style.display = 'flex';
    startBtn.disabled = false;
    restartBtn.disabled = true;
    pauseBtn.disabled = true;
    if (rafId) cancelAnimationFrame(rafId);
    lastTime = 0;
  }

  // HUD update
  function updateHUD(){
    const target = (mode !== 'infinite' && waves[waveIndex] ? waves[waveIndex].target : targetDefault);
    const pct = Math.round((count / target) * 100);
    progressFill.style.width = Math.max(0, Math.min(100, pct)) + '%';
    countText.textContent = (mode !== 'infinite' && waves[waveIndex] ? count + ' / ' + waves[waveIndex].target : count + ' / —');
    scoreBox.textContent = 'Очки: ' + score;
    multBox.textContent = 'x' + multiplier;
    levelBox.textContent = 'Уровень: ' + level;
    if (mode !== 'infinite' && waveActive){
      const secs = Math.max(0, Math.ceil(waveTimer / 1000));
      const mm = String(Math.floor(secs/60)).padStart(2,'0');
      const ss = String(secs%60).padStart(2,'0');
      timerBox.textContent = mm + ':' + ss;
    } else {
      timerBox.textContent = '--:--';
    }
    updateBestDisplay();
    btnGetPrize.disabled = !(finished && score>0);
  }

  function updateBestDisplay(){
    const best = Number(localStorage.getItem(bestKeyForMode(mode)) || 0);
    bestBox.textContent = 'Рекорд: ' + best;
  }

  // draw (visuals for good / bad_small / bad_bomb)
  function draw(){
    const { w: cw, h: ch } = getSize();
    ctx.clearRect(0,0,cw,ch);

    // background
    const g = ctx.createLinearGradient(0,0,0,ch);
    g.addColorStop(0, '#eaf7fb');
    g.addColorStop(1, '#fff');
    ctx.fillStyle = g;
    ctx.fillRect(0,0,cw,ch);

    // drops
    for (const d of drops){
      if (d.type === 'good') {
        ctx.beginPath();
        const grd = ctx.createRadialGradient(d.x - d.r*0.2, d.y - d.r*0.6, d.r*0.2, d.x, d.y, d.r);
        grd.addColorStop(0, '#dff7fb');
        grd.addColorStop(1, '#06b6d4');
        ctx.fillStyle = grd;
        ctx.arc(d.x, d.y, d.r, 0, Math.PI*2);
        ctx.fill();

        ctx.beginPath();
        ctx.fillStyle = 'rgba(255,255,255,0.45)';
        ctx.arc(d.x - d.r*0.3, d.y - d.r*0.6, d.r*0.35, 0, Math.PI*2);
        ctx.fill();
      } else if (d.type === 'bad_small') {
        ctx.beginPath();
        const grd2 = ctx.createRadialGradient(d.x - d.r*0.2, d.y - d.r*0.2, d.r*0.2, d.x, d.y, d.r);
        grd2.addColorStop(0, '#7a4f2a');
        grd2.addColorStop(1, '#4b2f12');
        ctx.fillStyle = grd2;
        ctx.arc(d.x, d.y, d.r, 0, Math.PI*2);
        ctx.fill();

        ctx.beginPath();
        ctx.fillStyle = 'rgba(255,255,255,0.06)';
        ctx.arc(d.x - d.r*0.25, d.y - d.r*0.25, d.r*0.28, 0, Math.PI*2);
        ctx.fill();
      } else if (d.type === 'bad_bomb') {
        ctx.beginPath();
        const grd3 = ctx.createRadialGradient(d.x - d.r*0.25, d.y - d.r*0.15, d.r*0.25, d.x, d.y, d.r);
        grd3.addColorStop(0, '#3b1f08');
        grd3.addColorStop(1, '#1f0b03');
        ctx.fillStyle = grd3;
        ctx.arc(d.x, d.y, d.r*1.05, 0, Math.PI*2);
        ctx.fill();

        ctx.beginPath();
        ctx.lineWidth = Math.max(1, d.r*0.12);
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
        ctx.arc(d.x, d.y, d.r*1.05, 0, Math.PI*2);
        ctx.stroke();

        ctx.beginPath();
        ctx.strokeStyle = 'rgba(255,255,255,0.12)';
        ctx.lineWidth = Math.max(1.2, d.r*0.12);
        ctx.moveTo(d.x - d.r*0.7, d.y - d.r*0.7);
        ctx.lineTo(d.x + d.r*0.7, d.y + d.r*0.7);
        ctx.moveTo(d.x + d.r*0.7, d.y - d.r*0.7);
        ctx.lineTo(d.x - d.r*0.7, d.y + d.r*0.7);
        ctx.stroke();
      }
    }

    // catcher
    ctx.save();
    const gradient = ctx.createLinearGradient(catcher.x, catcher.y, catcher.x, catcher.y + catcher.h);
    gradient.addColorStop(0, '#111');
    gradient.addColorStop(1, '#333');
    ctx.fillStyle = gradient;
    ctx.fillRect(catcher.x, catcher.y, catcher.w, catcher.h);
    ctx.fillStyle = '#fff';
    ctx.fillRect(catcher.x + catcher.w/2 - 10, catcher.y - 12, 20, 12);
    ctx.restore();
  }

  // overlays (floating texts & shake)
  function popPenalty(text, x, y){
    floatingTexts.push({ text, x, y, alpha:1, life:900, size:16, vy:-0.05, _last: performance.now() });
  }

  function flashHUD(bg, color, ms){
    levelBox.style.background = bg;
    levelBox.style.color = color;
    setTimeout(()=> { levelBox.style.background = ''; levelBox.style.color = ''; }, ms);
  }

  function cameraShake(intensity = 8, duration = 350){
    shakeIntensity = intensity;
    shakeUntil = performance.now() + duration;
  }

  function renderOverlays(now){
    // camera shake
    if (canvasOuter){
      if (now < shakeUntil){
        const s = shakeIntensity * ( (shakeUntil - now) / (shakeUntil - (now - 1)) );
        const dx = (Math.random() - 0.5) * shakeIntensity;
        const dy = (Math.random() - 0.5) * (shakeIntensity * 0.6);
        canvasOuter.style.transform = `translate(${dx}px, ${dy}px)`;
      } else {
        canvasOuter.style.transform = '';
      }
    }

    // floating texts
    if (floatingTexts.length){
      const { w: cw } = getSize();
      ctx.save();
      for (let i = floatingTexts.length -1; i >= 0; i--){
        const t = floatingTexts[i];
        const nowTs = now || performance.now();
        const dt = nowTs - (t._last || nowTs);
        t._last = nowTs;
        t.life -= dt;
        if (t.life <= 0) { floatingTexts.splice(i,1); continue; }
        t.y += t.vy * dt;
        const progress = t.life / 900;
        ctx.globalAlpha = Math.max(0, Math.min(1, progress));
        ctx.font = `${t.size}px Inter, Arial`;
        ctx.fillStyle = '#b00020';
        ctx.fillText(t.text, t.x, t.y);
      }
      ctx.globalAlpha = 1;
      ctx.restore();
    }
  }

  // main loop
  function loop(now){
    if (!lastTime) lastTime = now;
    const dt = Math.min(60, now - lastTime);
    lastTime = now;

    update(dt, now);
    draw();
    renderOverlays(now);
    updateHUD();

    if (running && !paused) rafId = requestAnimationFrame(loop);
    else rafId = null;
  }

  // events
  function pointerMoveFromEvent(e){
    const rect = canvas.getBoundingClientRect();
    let clientX;
    if (e.touches) clientX = e.touches[0].clientX;
    else clientX = e.clientX;
    pointerX = clientX - rect.left;
  }

  canvas.addEventListener('mousemove', pointerMoveFromEvent);
  canvas.addEventListener('mouseleave', ()=>{ pointerX = null; });
  canvas.addEventListener('touchmove', (e)=>{ pointerMoveFromEvent(e); e.preventDefault(); }, {passive:false});
  canvas.addEventListener('touchend', ()=>{ pointerX = null; });

  window.addEventListener('keydown', (e)=>{
    if (e.key === 'ArrowLeft') keys.left = true;
    if (e.key === 'ArrowRight') keys.right = true;
    if (e.key === ' ' && running && !finished) { togglePause(); e.preventDefault(); }
  });
  window.addEventListener('keyup', (e)=>{
    if (e.key === 'ArrowLeft') keys.left = false;
    if (e.key === 'ArrowRight') keys.right = false;
  });

  startBtn.addEventListener('click', startGame);
  restartBtn.addEventListener('click', restartGame);
  pauseBtn.addEventListener('click', togglePause);

  claimBtn.addEventListener('click', ()=> {
    const code = 'BIBU-PRIZE-2025';
    alert('Поздравляем! Ваш промо-код: ' + code + '\nПодробности: промокод применим к первой покупке.');
  });

  closeOverlay.addEventListener('click', ()=> {
    endOverlay.classList.remove('show');
    endOverlay.setAttribute('aria-hidden','true');
  });

  btnGetPrize.addEventListener('click', ()=> {
    endOverlay.classList.add('show');
    endOverlay.setAttribute('aria-hidden','false');
    document.getElementById('endTitle').textContent = 'Поздравляем!';
    document.getElementById('endMessage').textContent = 'Вы можете получить приз — промокод отправится на вашу почту (демо).';
  });

  // resize handling
  const resizeObserver = new ResizeObserver(()=> {
    resizeCanvas();
    draw();
  });
  resizeObserver.observe(canvas);
  window.addEventListener('resize', ()=> { resizeCanvas(); draw(); });

  // init
  (function init(){
    const outer = document.getElementById('canvasOuter');
    if (outer) {
      const minH = Math.max(420, Math.floor(window.innerHeight * 0.56));
      outer.style.minHeight = minH + 'px';
    }
    resizeCanvas();
    catcher.x = (canvas.clientWidth/2) - (catcher.w/2);
    catcher.y = canvas.clientHeight - 48;
    prepareMode('quick');
    updateHUD();
    restartBtn.disabled = true;
    claimBtn.disabled = true;
    btnGetPrize.disabled = true;
    pauseBtn.disabled = true;
  })();

})();