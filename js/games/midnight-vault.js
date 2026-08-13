(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;

  const BETS = [5, 10, 25, 100];
  const MODES = ['classic', 'multi'];
  const RISKS = ['low', 'medium', 'high'];
  const ROWS = [8, 12, 16];
  const BALLS = [3, 5, 10];

  let selectedBet = 5;
  let selectedMode = 'classic';
  let selectedRisk = 'medium';
  let selectedRows = 12;
  let selectedBalls = 3;
  let initialized = false;
  let busy = false;
  let recent = [];
  let engine = null;
  let lastPockets = clientPockets(selectedRows, selectedRisk);

  class PlinkoCanvasEngine {
    constructor(root) {
      this.root = root;
      this.canvas = document.createElement('canvas');
      this.canvas.className = 'plinko-canvas';
      this.ctx = this.canvas.getContext('2d');
      this.dpr = 1;
      this.rows = 12;
      this.risk = 'medium';
      this.pockets = clientPockets(12, 'medium');
      this.balls = [];
      this.sparks = [];
      this.pocketHits = [];
      this.state = '';
      this.highLoad = false;
      this.reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      this.raf = 0;
      this.resolve = null;
      this.root.innerHTML = '';
      this.root.appendChild(this.canvas);
      this.resize = this.resize.bind(this);
      this.frame = this.frame.bind(this);
      this.handleVisibility = this.handleVisibility.bind(this);
      if (window.ResizeObserver) {
        this.resizeObserver = new ResizeObserver(this.resize);
        this.resizeObserver.observe(this.root);
      }
      window.addEventListener('resize', this.resize);
      document.addEventListener('visibilitychange', this.handleVisibility);
      this.resize();
    }

    handleVisibility() {
      if (document.hidden || this.raf || !this.resolve) return;
      this.raf = requestAnimationFrame(this.frame);
    }

    configure(rows, risk, pockets) {
      this.rows = rows;
      this.risk = risk;
      this.pockets = pockets || clientPockets(rows, risk);
      this.balls = [];
      this.sparks = [];
      this.pocketHits = [];
      this.state = '';
      this.highLoad = false;
      this.draw(performance.now());
    }

    resize() {
      const rect = this.root.getBoundingClientRect();
      const width = Math.max(320, Math.floor(rect.width || 900));
      const height = Math.max(420, Math.floor(rect.height || 600));
      const dpr = Math.max(1, Math.min(1.75, window.devicePixelRatio || 1));
      const geometryChanged = width !== this.width || height !== this.height;
      if (!geometryChanged && dpr === this.dpr) return;

      this.width = width;
      this.height = height;
      this.dpr = dpr;
      this.canvas.width = Math.floor(this.width * this.dpr);
      this.canvas.height = Math.floor(this.height * this.dpr);
      this.canvas.style.width = this.width + 'px';
      this.canvas.style.height = this.height + 'px';
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      const now = performance.now();
      if (geometryChanged && this.balls.length) this.reflowAnimation(now);
      this.draw(now);
    }

    reflowAnimation(now) {
      this.sparks = [];
      this.balls.forEach(ball => {
        const basket = this.basketBallPosition(Number(ball.source.slot || 0), ball.stackIndex);
        const points = this.buildPath(ball.source, basket);
        ball.points = points;
        ball.basket = basket;
        ball.trail = [];
        ball.segments.forEach((segment, index) => {
          segment.from = points[index];
          segment.to = points[index + 1];
        });
        if (ball.done) {
          const last = points[points.length - 1];
          ball.x = last.x;
          ball.y = last.y;
          return;
        }
        if (now < ball.startAt) {
          ball.x = points[0].x;
          ball.y = points[0].y;
          return;
        }
        this.updateBall(ball, now);
      });
    }

    geometry() {
      const w = this.width;
      const h = this.height;
      return {
        w,
        h,
        pinTop: 86,
        pinBottom: h - 142,
        pocketY: h - 56,
        pocketLeft: w * 0.075,
        pocketWidth: w * 0.85,
        centerX: w / 2
      };
    }

    pinPosition(row, index, rows) {
      const geo = this.geometry();
      const t = rows <= 1 ? 0 : row / (rows - 1);
      const y = geo.pinTop + t * (geo.pinBottom - geo.pinTop);
      if (row === 0) return { x: geo.centerX, y };
      const rowWidth = geo.w * (0.1 + t * 0.7);
      const x = geo.centerX - rowWidth / 2 + (index / row) * rowWidth;
      return { x, y };
    }

    pocketX(slot, rows) {
      const geo = this.geometry();
      return geo.pocketLeft + (slot / rows) * geo.pocketWidth;
    }

    buildPath(ball, basketPoint) {
      const path = ball.path || [];
      const rows = path.length || this.rows;
      const points = [{ x: this.width / 2, y: 46, type: 'drop' }];
      let rights = 0;
      path.forEach((step, row) => {
        const pin = this.pinPosition(row, rights, rows);
        points.push({ ...pin, type: 'pin', row, index: rights, step });
        if (step === 'R') rights += 1;
      });
      const slot = Number(ball.slot || 0);
      const pocketX = this.pocketX(slot, rows);
      const pocketY = this.geometry().pocketY;
      points.push({ x: pocketX, y: pocketY - 50, type: 'pocket-lip', slot });
      points.push({ x: basketPoint.x, y: basketPoint.y, type: 'pocket', slot });
      return points;
    }

    play(result, state) {
      cancelAnimationFrame(this.raf);
      this.configure(result.rows || this.rows, result.risk || this.risk, result.pockets || this.pockets);
      this.state = state || '';
      const now = performance.now();
      const resultBalls = result.balls || [];
      this.highLoad = resultBalls.length >= 5 || (resultBalls.length >= 3 && Number(result.rows || this.rows) >= 16);
      const slotCounts = new Map();
      this.balls = resultBalls.map((ball, index) => {
        const slot = Number(ball.slot || 0);
        const stackIndex = slotCounts.get(slot) || 0;
        slotCounts.set(slot, stackIndex + 1);
        return this.createBall(ball, index, now, stackIndex);
      });
      return new Promise(resolve => {
        this.resolve = resolve;
        this.frame(now);
      });
    }

    createBall(ball, index, now, stackIndex) {
      const basket = this.basketBallPosition(Number(ball.slot || 0), stackIndex);
      const points = this.buildPath(ball, basket);
      const speed = this.reduceMotion ? 0.72 : 0.86 + Math.random() * 0.24;
      const segments = [];
      let cursor = now + index * (this.reduceMotion ? 90 : 185);
      for (let i = 0; i < points.length - 1; i++) {
        const from = points[i];
        const to = points[i + 1];
        const distance = Math.hypot(to.x - from.x, to.y - from.y);
        const isPocketLip = to.type === 'pocket-lip';
        const isPocketDrop = to.type === 'pocket';
        const base = this.reduceMotion ? 95 : 118 + i * 5;
        const landingWeight = isPocketLip ? 1.38 : isPocketDrop ? 1.12 : 1;
        const duration = (Math.max(86, Math.min(isPocketLip ? 260 : 210, base + distance * 1.3)) * landingWeight) / speed;
        segments.push({ from, to, start: cursor, end: cursor + duration, hit: false, index: i, isPocketLip, isPocketDrop });
        cursor += duration;
      }
      return {
        source: ball,
        points,
        segments,
        startAt: now + index * (this.reduceMotion ? 90 : 185),
        endAt: cursor,
        x: points[0].x,
        y: points[0].y,
        r: 9,
        basket,
        stackIndex,
        rotation: 0,
        squash: 1,
        trail: [],
        done: false,
        seed: Math.random() * Math.PI * 2
      };
    }

    pocketMetrics(slot) {
      const geo = this.geometry();
      const count = this.rows + 1;
      const gap = 4;
      const width = Math.min(58, (geo.pocketWidth - gap * (count - 1)) / count);
      return {
        x: this.pocketX(slot, this.rows) - width / 2,
        y: geo.pocketY - 28,
        w: width,
        h: 58,
        centerX: this.pocketX(slot, this.rows),
        bottomY: geo.pocketY + 28
      };
    }

    basketBallPosition(slot, stackIndex) {
      const pocket = this.pocketMetrics(slot);
      const offsets = [0, -7.2, 7.2, -3.6, 3.6, -10.2, 10.2, -1.8, 1.8, 0];
      const row = Math.floor(stackIndex / 3);
      const maxOffset = Math.max(0, pocket.w / 2 - 11);
      const offset = Math.max(-maxOffset, Math.min(maxOffset, offsets[stackIndex % offsets.length] || 0));
      return {
        x: pocket.centerX + offset,
        y: pocket.bottomY - 9 - row * 7.2,
        slot
      };
    }

    frame(now) {
      if (document.hidden) {
        this.raf = 0;
        return;
      }
      this.update(now);
      this.draw(now);
      const active = this.balls.some(ball => !ball.done || (ball.done && now - ball.endAt < 260)) || this.sparks.length > 0;
      if (active) {
        this.raf = requestAnimationFrame(this.frame);
        return;
      }
      this.raf = 0;
      const resolver = this.resolve;
      this.resolve = null;
      if (resolver) setTimeout(resolver, 160);
    }

    update(now) {
      this.sparks = this.sparks.filter(spark => now - spark.at < spark.life);
      this.balls.forEach(ball => this.updateBall(ball, now));
    }

    updateBall(ball, now) {
      if (ball.done || now < ball.startAt) return;
      const segment = ball.segments.find(item => now >= item.start && now <= item.end);
      if (!segment) {
        const last = ball.points[ball.points.length - 1];
        ball.x = last.x;
        ball.y = last.y;
        ball.done = now >= ball.endAt;
        if (ball.done && !ball.landed) {
          ball.landed = true;
          this.hitPocket(ball.source.slot);
        }
        return;
      }

      const t = Math.max(0, Math.min(1, (now - segment.start) / (segment.end - segment.start)));
      const point = this.segmentPoint(segment.from, segment.to, t, ball.seed, segment.index);
      ball.x = point.x;
      ball.y = point.y;
      ball.rotation += (segment.to.x >= segment.from.x ? 1 : -1) * (3.2 + t * 1.4);
      ball.squash = this.ballSquash(segment, t);
      if (!this.reduceMotion) {
        const trailLife = this.highLoad ? 90 : 180;
        const trailLimit = this.highLoad ? 4 : 10;
        if (!this.highLoad || !ball.lastTrailAt || now - ball.lastTrailAt > 42) {
          ball.trail.push({ x: ball.x, y: ball.y, at: now });
          ball.lastTrailAt = now;
        }
        ball.trail = ball.trail.filter(item => now - item.at < trailLife).slice(-trailLimit);
      }
      if (t > 0.92 && !segment.hit) {
        segment.hit = true;
        if (segment.to.type === 'pin') this.hitPin(segment.to);
        if (segment.to.type === 'pocket-lip') this.hitPocketLip(segment.to.slot);
      }
    }

    segmentPoint(from, to, t, seed, index) {
      if (to.type === 'pocket-lip') return this.pocketApproachPoint(from, to, t, seed, index);
      if (to.type === 'pocket') return this.pocketDropPoint(from, to, t);
      const gravity = 1 - Math.pow(1 - t, 2.25);
      const lateral = t * t * (3 - 2 * t);
      const dx = to.x - from.x;
      const direction = dx === 0 ? (to.step === 'R' ? 1 : -1) : Math.sign(dx);
      const arc = this.reduceMotion ? 0 : Math.sin(Math.PI * t) * direction * Math.min(34, Math.max(8, Math.abs(dx) * 0.28));
      const jitter = this.reduceMotion ? 0 : Math.sin(seed + index * 1.9 + t * Math.PI * 2) * Math.sin(Math.PI * t) * 1.6;
      const lift = this.reduceMotion ? 0 : Math.sin(Math.PI * Math.min(1, t * 1.18)) * 5.5;
      return {
        x: from.x + dx * lateral + arc + jitter,
        y: from.y + (to.y - from.y) * gravity - lift
      };
    }

    pocketApproachPoint(from, to, t, seed, index) {
      const ease = 1 - Math.pow(1 - t, 2.55);
      const dx = to.x - from.x;
      const direction = dx === 0 ? 1 : Math.sign(dx);
      const settle = t * t * (3 - 2 * t);
      const hook = this.reduceMotion ? 0 : Math.sin(Math.PI * t) * direction * Math.min(46, Math.max(18, Math.abs(dx) * 0.35 + 12));
      const dropArc = this.reduceMotion ? 0 : Math.sin(Math.PI * t) * 20;
      const tinyJitter = this.reduceMotion ? 0 : Math.sin(seed + index + t * Math.PI * 3) * Math.sin(Math.PI * t) * 1.1;
      return {
        x: from.x + dx * settle + hook + tinyJitter,
        y: from.y + (to.y - from.y) * ease - dropArc
      };
    }

    pocketDropPoint(from, to, t) {
      const ease = t * t * (3 - 2 * t);
      const sink = Math.pow(t, 1.85);
      const bounce = this.reduceMotion ? 0 : Math.sin(Math.PI * t) * 4;
      return {
        x: from.x + (to.x - from.x) * ease,
        y: from.y + (to.y - from.y) * sink + bounce
      };
    }

    ballSquash(segment, t) {
      if (segment.isPocketDrop) {
        return 1.18 - t * 0.26 + Math.sin(Math.PI * t) * 0.1;
      }
      if (segment.isPocketLip) {
        return 1 + Math.sin(Math.PI * t) * 0.16;
      }
      return t > 0.78 ? 1 + Math.sin((t - 0.78) / 0.22 * Math.PI) * 0.12 : 1;
    }

    hitPin(pin) {
      if (this.reduceMotion) return;
      if (this.highLoad && Math.random() < 0.45) return;
      this.sparks.push({ x: pin.x, y: pin.y, row: pin.row, index: pin.index, at: performance.now(), life: this.highLoad ? 180 : 260, type: 'pin' });
      if (this.sparks.length > (this.highLoad ? 28 : 72)) this.sparks.splice(0, this.sparks.length - (this.highLoad ? 28 : 72));
    }

    hitPocketLip(slot) {
      if (this.reduceMotion) return;
      const x = this.pocketX(Number(slot || 0), this.rows);
      this.sparks.push({ x, y: this.geometry().pocketY - 34, at: performance.now(), life: this.highLoad ? 220 : 300, type: 'lip' });
    }

    hitPocket(slot) {
      this.pocketHits.push({ slot: Number(slot || 0), at: performance.now(), life: 680, state: this.state });
      if (!this.reduceMotion) {
        const x = this.pocketX(Number(slot || 0), this.rows);
        this.sparks.push({ x, y: this.geometry().pocketY - 8, at: performance.now(), life: this.highLoad ? 360 : 520, type: 'pocket' });
      }
    }

    draw(now) {
      const ctx = this.ctx;
      const geo = this.geometry();
      ctx.clearRect(0, 0, geo.w, geo.h);
      this.drawBackdrop(ctx, geo);
      this.drawRails(ctx, geo);
      this.drawPockets(ctx, geo, now);
      this.drawPins(ctx, geo, now);
      this.drawSparks(ctx, now);
      this.drawBalls(ctx, now);
      this.drawPocketFronts(ctx, geo, now);
      this.drawLabels(ctx, geo);
    }

    drawBackdrop(ctx, geo) {
      const bg = ctx.createLinearGradient(0, 0, 0, geo.h);
      bg.addColorStop(0, '#07111d');
      bg.addColorStop(0.52, '#040812');
      bg.addColorStop(1, '#020407');
      ctx.fillStyle = bg;
      this.roundRect(ctx, 0, 0, geo.w, geo.h, 14);
      ctx.fill();

      const glow = ctx.createRadialGradient(geo.centerX, 120, 10, geo.centerX, 170, geo.w * 0.44);
      glow.addColorStop(0, 'rgba(88, 151, 193, .20)');
      glow.addColorStop(0.45, 'rgba(33, 75, 116, .10)');
      glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, geo.w, geo.h);

      ctx.save();
      ctx.globalAlpha = 0.09;
      ctx.strokeStyle = '#9cc9e8';
      ctx.lineWidth = 1;
      for (let x = 0; x < geo.w; x += 24) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, geo.h);
        ctx.stroke();
      }
      ctx.restore();
    }

    drawRails(ctx, geo) {
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(geo.centerX, 62);
      ctx.lineTo(geo.pocketLeft - 8, geo.pocketY - 52);
      ctx.lineTo(geo.pocketLeft + geo.pocketWidth + 8, geo.pocketY - 52);
      ctx.closePath();
      ctx.fillStyle = 'rgba(4, 7, 12, .42)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(156, 201, 232, .12)';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(geo.centerX, 210, 165, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(174, 137, 68, .12)';
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(geo.centerX, 210, 108, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(156, 201, 232, .08)';
      ctx.stroke();
      ctx.restore();
    }

    drawPins(ctx, geo, now) {
      const pulseByPin = new Map();
      this.sparks.forEach(spark => {
        if (spark.type === 'pin' && spark.row !== undefined && spark.index !== undefined) {
          pulseByPin.set(`${spark.row}:${spark.index}`, spark);
        }
      });
      for (let row = 0; row < this.rows; row++) {
        for (let index = 0; index <= row; index++) {
          const pin = this.pinPosition(row, index, this.rows);
          const touch = pulseByPin.get(`${row}:${index}`);
          const pulse = touch ? Math.max(0, 1 - (now - touch.at) / touch.life) : 0;
          ctx.save();
          ctx.shadowColor = pulse ? 'rgba(206,226,240,.95)' : 'rgba(141,204,232,.62)';
          ctx.shadowBlur = pulse ? (this.highLoad ? 10 : 18) : (this.highLoad ? 0 : 10);
          const r = 4.1 + pulse * 2.5;
          if (this.highLoad && !pulse) {
            ctx.fillStyle = '#8dcce8';
          } else {
            const grad = ctx.createRadialGradient(pin.x - 1.5, pin.y - 1.5, 1, pin.x, pin.y, r + 3);
            grad.addColorStop(0, '#f8fcff');
            grad.addColorStop(pulse ? 0.38 : 0.45, pulse ? '#dce8f2' : '#8dcce8');
            grad.addColorStop(1, pulse ? '#6d8294' : '#356f98');
            ctx.fillStyle = grad;
          }
          ctx.beginPath();
          ctx.arc(pin.x, pin.y, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      }
    }

    drawPockets(ctx, geo, now) {
      const count = this.rows + 1;
      for (let slot = 0; slot < count; slot++) {
        const pocket = this.pocketMetrics(slot);
        const hit = this.pocketHits.find(item => item.slot === slot && now - item.at < item.life);
        const p = hit ? Math.max(0, 1 - (now - hit.at) / hit.life) : 0;
        const grad = ctx.createLinearGradient(0, pocket.y, 0, pocket.y + pocket.h);
        grad.addColorStop(0, p ? '#374655' : '#2a323d');
        grad.addColorStop(0.42, '#121820');
        grad.addColorStop(1, '#010204');
        ctx.save();
        ctx.shadowColor = hit && hit.state === 'win' ? 'rgba(184,205,222,.32)' : hit && hit.state === 'loss' ? 'rgba(150,73,65,.28)' : 'rgba(0,0,0,0)';
        ctx.shadowBlur = p * (this.highLoad ? 12 : 28);
        ctx.fillStyle = grad;
        ctx.strokeStyle = p ? (hit.state === 'loss' ? 'rgba(150,73,65,.82)' : 'rgba(184,205,222,.86)') : 'rgba(139,163,184,.38)';
        ctx.lineWidth = 1 + p;
        this.roundRect(ctx, pocket.x, pocket.y - p * 5, pocket.w, pocket.h, 9);
        ctx.fill();
        ctx.stroke();

        const inner = ctx.createLinearGradient(0, pocket.y + 8, 0, pocket.y + pocket.h);
        inner.addColorStop(0, 'rgba(2,4,8,.12)');
        inner.addColorStop(1, 'rgba(0,0,0,.72)');
        ctx.fillStyle = inner;
        this.roundRect(ctx, pocket.x + 4, pocket.y + 8 - p * 4, pocket.w - 8, pocket.h - 14, 7);
        ctx.fill();

        ctx.globalAlpha = 0.34 + p * 0.3;
        ctx.strokeStyle = p ? 'rgba(220,234,244,.68)' : 'rgba(156,201,232,.16)';
        ctx.beginPath();
        ctx.moveTo(pocket.x + 8, pocket.y + 10 - p * 5);
        ctx.lineTo(pocket.x + pocket.w - 8, pocket.y + 10 - p * 5);
        ctx.stroke();
        ctx.globalAlpha = 0.16 + p * 0.12;
        ctx.fillStyle = '#9cc9e8';
        ctx.fillRect(pocket.x + 6, pocket.y + 14, Math.max(2, pocket.w - 12), 1);
        ctx.restore();
      }
    }

    drawPocketFronts(ctx, geo, now) {
      const count = this.rows + 1;
      for (let slot = 0; slot < count; slot++) {
        const pocket = this.pocketMetrics(slot);
        const hit = this.pocketHits.find(item => item.slot === slot && now - item.at < item.life);
        const p = hit ? Math.max(0, 1 - (now - hit.at) / hit.life) : 0;
        const frontY = pocket.y + pocket.h - 22 - p * 5;
        const grad = ctx.createLinearGradient(0, frontY, 0, frontY + 24);
        grad.addColorStop(0, p ? '#344453' : '#1d242d');
        grad.addColorStop(0.46, '#12161d');
        grad.addColorStop(1, '#07080b');
        ctx.save();
        ctx.shadowColor = hit && hit.state === 'win' ? 'rgba(184,205,222,.2)' : hit && hit.state === 'loss' ? 'rgba(150,73,65,.18)' : 'rgba(0,0,0,0)';
        ctx.shadowBlur = p * (this.highLoad ? 8 : 18);
        ctx.fillStyle = grad;
        ctx.strokeStyle = p ? (hit.state === 'loss' ? 'rgba(150,73,65,.78)' : 'rgba(184,205,222,.82)') : 'rgba(139,163,184,.46)';
        ctx.lineWidth = 1 + p * 0.7;
        this.roundRect(ctx, pocket.x - 1, frontY, pocket.w + 2, 25, 8);
        ctx.fill();
        ctx.stroke();
        ctx.globalAlpha = 0.55 + p * 0.34;
        ctx.strokeStyle = p ? 'rgba(220,234,244,.66)' : 'rgba(156,201,232,.12)';
        ctx.beginPath();
        ctx.moveTo(pocket.x + 7, frontY + 5);
        ctx.lineTo(pocket.x + pocket.w - 7, frontY + 5);
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.fillStyle = p && hit.state === 'loss' ? '#d98f86' : '#dce8f2';
        ctx.font = '900 10px Inter, Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(formatMultiplier(this.pockets[slot]), pocket.centerX, frontY + 15);
        ctx.restore();
      }
    }

    drawBalls(ctx, now) {
      this.balls.forEach(ball => {
        const doneAge = ball.done ? now - ball.endAt : 0;
        if (now < ball.startAt || doneAge > 260) return;
        const vanish = ball.done ? Math.max(0, 1 - doneAge / 260) : 1;
        if (!this.reduceMotion) {
          ball.trail.forEach((item, index) => {
            const age = Math.max(0, 1 - (now - item.at) / 180);
            ctx.save();
            ctx.globalAlpha = age * (this.highLoad ? 0.16 : 0.28) * (index / Math.max(1, ball.trail.length));
            ctx.fillStyle = '#b8cdde';
            ctx.beginPath();
            ctx.arc(item.x, item.y, ball.r * age, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          });
        }

        ctx.save();
        ctx.translate(ball.x, ball.y + doneAge * 0.035);
        ctx.rotate(ball.rotation * Math.PI / 180);
        ctx.scale(ball.squash, 1 / Math.max(0.86, ball.squash));
        const sinking = ball.y > this.geometry().pocketY - 35;
        const sinkAmount = sinking ? Math.min(1, Math.max(0, (ball.y - (this.geometry().pocketY - 35)) / 42)) : 0;
        ctx.globalAlpha = (1 - sinkAmount * 0.42) * vanish;
        ctx.shadowColor = 'rgba(184,205,222,.44)';
        ctx.shadowBlur = this.highLoad ? 8 : 18;
        const grad = ctx.createRadialGradient(-3, -4, 1, 0, 0, ball.r + 3);
        grad.addColorStop(0, '#f4fbff');
        grad.addColorStop(0.38, '#b8cdde');
        grad.addColorStop(1, '#4d6579');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(0, 0, Math.max(4.2, ball.r - sinkAmount * 3.4 - (1 - vanish) * 2), 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.fillStyle = 'rgba(255,255,255,.48)';
        ctx.beginPath();
        ctx.arc(-3, -4, Math.max(1.2, 2.4 - sinkAmount * 0.8), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      });
    }

    drawSparks(ctx, now) {
      this.sparks.forEach(spark => {
        const age = Math.max(0, 1 - (now - spark.at) / spark.life);
        ctx.save();
        ctx.globalAlpha = age;
        ctx.strokeStyle = spark.type === 'pocket' ? 'rgba(184,205,222,.68)' : 'rgba(206,226,240,.68)';
        ctx.lineWidth = 1.4;
        ctx.shadowColor = ctx.strokeStyle;
        ctx.shadowBlur = this.highLoad ? 0 : 12;
        ctx.beginPath();
        ctx.arc(spark.x, spark.y, (1 - age) * (spark.type === 'pocket' ? (this.highLoad ? 18 : 28) : (this.highLoad ? 9 : 16)) + 4, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      });
    }

    drawLabels(ctx, geo) {
      ctx.save();
      ctx.font = '950 11px Inter, Arial, sans-serif';
      ctx.letterSpacing = '1px';
      ctx.fillStyle = '#9cc9e8';
      ctx.textAlign = 'left';
      ctx.fillText('VAULT DROP', 20, 28);
      ctx.fillStyle = '#b8cdde';
      ctx.textAlign = 'right';
      ctx.fillText(`${this.rows} ROWS`, geo.w - 20, 28);
      ctx.restore();
    }

    roundRect(ctx, x, y, w, h, r) {
      const radius = Math.min(r, w / 2, h / 2);
      ctx.beginPath();
      ctx.moveTo(x + radius, y);
      ctx.arcTo(x + w, y, x + w, y + h, radius);
      ctx.arcTo(x + w, y + h, x, y + h, radius);
      ctx.arcTo(x, y + h, x, y, radius);
      ctx.arcTo(x, y, x + w, y, radius);
      ctx.closePath();
    }
  }

  function currentBalance() {
    return Number(store.getDisplayUser().balance || 0);
  }

  function formatMultiplier(multiplierCents) {
    return (Number(multiplierCents || 0) / 100).toFixed(2) + 'x';
  }

  function renderBalance() {
    const user = store.getDisplayUser();
    ui.setText('plinko-balance', ui.formatMoney(user.balance, user.currency));
  }

  function baseMultiplier(slot, rows, risk) {
    const center = rows / 2;
    const distance = center ? Math.abs(slot - center) / center : 0;
    const profiles = {
      low: [42, 430, 2.0],
      medium: [18, 1850, 2.55],
      high: [4, 9200, 3.05]
    };
    const profile = profiles[risk] || profiles.medium;
    return profile[0] + Math.floor(profile[1] * Math.pow(distance, profile[2]));
  }

  function combination(n, k) {
    let result = 1;
    for (let i = 1; i <= k; i++) result = result * (n - k + i) / i;
    return result;
  }

  function clientPockets(rows, risk) {
    const base = Array.from({ length: rows + 1 }, (_, slot) => baseMultiplier(slot, rows, risk));
    const expected = base.reduce((sum, value, slot) => sum + value * (combination(rows, slot) / Math.pow(2, rows)), 0);
    const scale = expected ? 96 / expected : 1;
    return base.map(value => Math.max(1, Math.floor(value * scale)));
  }

  function optionLabel(group, value) {
    if (group === 'mode') return ui.t(value === 'classic' ? 'plinko_mode_classic' : 'plinko_mode_multi');
    if (group === 'risk') return ui.t('plinko_risk_' + value);
    return String(value);
  }

  function optionButton(group, value, selected) {
    return `
      <button class="plinko-option ${selected ? 'selected' : ''}" type="button" data-plinko-${group}="${ui.escapeHTML(value)}">
        ${ui.escapeHTML(optionLabel(group, value))}
      </button>
    `;
  }

  function renderControls() {
    const bets = document.getElementById('plinkoBets');
    if (bets) {
      bets.innerHTML = BETS.map(value => `
        <button class="chip-btn ${value === selectedBet ? 'selected' : ''}" type="button" data-plinko-bet="${value}">
          ${ui.formatMoney(value)}
        </button>
      `).join('');
    }
    const modes = document.getElementById('plinkoModes');
    if (modes) modes.innerHTML = MODES.map(value => optionButton('mode', value, value === selectedMode)).join('');
    const risks = document.getElementById('plinkoRisks');
    if (risks) risks.innerHTML = RISKS.map(value => optionButton('risk', value, value === selectedRisk)).join('');
    const rows = document.getElementById('plinkoRows');
    if (rows) rows.innerHTML = ROWS.map(value => optionButton('rows', value, value === selectedRows)).join('');
    const balls = document.getElementById('plinkoBalls');
    if (balls) balls.innerHTML = BALLS.map(value => optionButton('balls', value, value === selectedBalls)).join('');
    const ballsBox = document.getElementById('plinkoBallsBox');
    if (ballsBox) ballsBox.hidden = selectedMode !== 'multi';
  }

  function ensureEngine() {
    const board = document.getElementById('plinkoBoard');
    if (!board) return null;
    if (!engine || engine.root !== board) engine = new PlinkoCanvasEngine(board);
    return engine;
  }

  function renderBoard(pockets) {
    lastPockets = pockets || clientPockets(selectedRows, selectedRisk);
    const canvasEngine = ensureEngine();
    if (canvasEngine) canvasEngine.configure(selectedRows, selectedRisk, lastPockets);
  }

  function clearResultClasses() {
    const stage = document.getElementById('plinkoStage');
    const box = document.getElementById('plinkoResult');
    if (stage) stage.classList.remove('is-dropping', 'is-win', 'is-loss', 'is-push');
    if (box) box.classList.remove('win', 'loss', 'push');
  }

  function resultState(result) {
    const net = Number(result && result.net || 0);
    if (net > 0) return 'win';
    if (net < 0) return 'loss';
    return 'push';
  }

  function setResult(result, state) {
    const box = document.getElementById('plinkoResult');
    const stage = document.getElementById('plinkoStage');
    if (stage) {
      stage.classList.remove('is-dropping', 'is-win', 'is-loss', 'is-push');
      stage.classList.add('is-' + state);
    }
    if (!box) return;
    const net = Number(result.net || 0);
    box.classList.remove('win', 'loss', 'push');
    box.classList.add(state);
    if (net > 0) {
      box.textContent = ui.t('plinko_result_win', { amount: ui.formatMoney(result.total_win), net: '+' + ui.formatMoney(net) });
    } else if (net === 0) {
      box.textContent = ui.t('plinko_result_push');
    } else {
      box.textContent = ui.t('plinko_result_loss', { amount: ui.formatMoney(Math.abs(net)) });
    }
  }

  function renderRecent() {
    ui.renderGameHistory?.('plinkoRecent', recent, ui.t('plinko_recent_empty'));
  }

  function bestBallMultiplier(result) {
    const balls = Array.isArray(result && result.balls) ? result.balls : [];
    const best = balls.reduce((max, ball) => Math.max(max, Number(ball.multiplier || 0)), 0);
    return best || 0;
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error), 'err');
    return true;
  }

  async function drop() {
    if (busy) return;
    if (selectedBet > currentBalance()) {
      ui.showToast(ui.t('err_plinko_balance'), 'err');
      return;
    }

    busy = true;
    const button = document.getElementById('plinkoDrop');
    const stage = document.getElementById('plinkoStage');
    if (button) button.disabled = true;
    clearResultClasses();
    if (stage) stage.classList.add('is-dropping');
    renderBoard(clientPockets(selectedRows, selectedRisk));
    ui.setText('plinkoResult', ui.t('plinko_dropping'));
    B.audio?.play?.('drop');

    const result = await store.dropMidnightVault(selectedBet, selectedMode, selectedRisk, selectedRows, selectedBalls);
    if (showStoreError(result)) {
      busy = false;
      if (button) button.disabled = false;
      if (stage) stage.classList.remove('is-dropping');
      ui.setText('plinkoResult', ui.t('plinko_waiting'));
      return;
    }

    selectedRows = Number(result.rows || selectedRows);
    selectedRisk = String(result.risk || selectedRisk);
    lastPockets = result.pockets || lastPockets;
    const state = resultState(result);
    const canvasEngine = ensureEngine();
    if (canvasEngine) {
      await canvasEngine.play(result, state);
    }
    setResult(result, state);
    store.commitGameWallet(result, 'game:plinko:settled');
    B.audio?.play?.(state === 'win' ? 'win' : (state === 'loss' ? 'loss' : 'push'));
    recent.unshift({
      state,
      label: (Number(result.net || 0) > 0 ? '+' : '') + ui.formatMoney(result.net),
      meta: `${bestBallMultiplier(result).toFixed(2)}x`
    });
    recent = recent.slice(0, 8);
    renderRecent();
    renderBalance();
    busy = false;
    if (button) button.disabled = false;
  }

  function bindEvents() {
    document.addEventListener('click', event => {
      if (busy) return;
      const bet = event.target.closest('[data-plinko-bet]');
      const mode = event.target.closest('[data-plinko-mode]');
      const risk = event.target.closest('[data-plinko-risk]');
      const rows = event.target.closest('[data-plinko-rows]');
      const balls = event.target.closest('[data-plinko-balls]');
      if (bet) selectedBet = Number(bet.dataset.plinkoBet || selectedBet);
      if (mode) selectedMode = mode.dataset.plinkoMode || selectedMode;
      if (risk) selectedRisk = risk.dataset.plinkoRisk || selectedRisk;
      if (rows) selectedRows = Number(rows.dataset.plinkoRows || selectedRows);
      if (balls) selectedBalls = Number(balls.dataset.plinkoBalls || selectedBalls);
      if (bet || mode || risk || rows || balls) {
        clearResultClasses();
        renderControls();
        renderBoard(clientPockets(selectedRows, selectedRisk));
      }
    });
    document.getElementById('plinkoDrop')?.addEventListener('click', drop);
  }

  function init() {
    if (document.body.dataset.page !== 'plinko' || initialized) return;
    initialized = true;
    renderBalance();
    renderControls();
    renderBoard(lastPockets);
    renderRecent();
    bindEvents();
    store.subscribe(() => {
      if (!busy) renderBalance();
    });
    store.getManagerState?.().then(result => {
      if (!result?.error) {
        BETS.splice(0, BETS.length, ...store.getManagerBetOptions('midnight-vault'));
        if (selectedBet === 100) selectedBet = BETS[BETS.length - 1];
        renderControls();
      }
    });
  }

  B.plinko = { init };
})(window);
