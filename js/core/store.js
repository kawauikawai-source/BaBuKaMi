(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;

  const clone = value => JSON.parse(JSON.stringify(value));
  const toNumber = value => {
    const next = Number(value);
    return Number.isFinite(next) ? next : 0;
  };
  const apiBaseUrl = (C.api && C.api.baseUrl) || 'http://127.0.0.1:8000/api';
  let accessToken = '';
  let refreshAccessPromise = null;
  const moneyRequestLocks = new Map();
  let apiStatusTimer = null;
  let apiStatusVisibilityBound = false;

  /**
   * @typedef {Object} StoreResult
   * @property {string=} error
   * @property {Object=} user
   * @property {number=} min
   * @property {number=} max
   */

  /** @param {string} key @returns {StoreResult} */
  function fail(key, extra) {
    return Object.assign({ error: key }, extra || {});
  }

  /** @param {Object} user @returns {StoreResult} */
  function okUser(user) {
    return { user: publicUser(user) };
  }

  function safeParse(raw, fallback) {
    try {
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) {
      return fallback;
    }
  }

  function save(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (err) {
      // LocalStorage can be unavailable in very restrictive browser modes.
    }
  }

  function read(key, fallback) {
    try {
      return safeParse(localStorage.getItem(key), fallback);
    } catch (err) {
      return fallback;
    }
  }

  function remove(key) {
    try {
      localStorage.removeItem(key);
    } catch (err) {
      // Keep logout non-fatal if storage is blocked.
    }
  }

  function kycStorageKey() {
    return C.storage.kyc || 'bk_kyc';
  }

  function kycUserKey(user) {
    const source = user || {};
    return String(source.apiId || source.id || source.email || 'local-user').toLowerCase();
  }

  function readKycStatus(user) {
    const stored = read(kycStorageKey(), {});
    if (!stored || typeof stored !== 'object') return '';
    return stored[kycUserKey(user)] || (user && user.email ? stored[String(user.email).toLowerCase()] : '') || '';
  }

  function writeKycStatus(user, status) {
    const stored = read(kycStorageKey(), {});
    const next = stored && typeof stored === 'object' ? stored : {};
    next[kycUserKey(user)] = status;
    if (user && user.email) next[String(user.email).toLowerCase()] = status;
    save(kycStorageKey(), next);
  }

  function apiToken() {
    return accessToken;
  }

  function saveApiToken(token) {
    accessToken = token || '';
    try {
      localStorage.removeItem(C.storage.apiToken || 'bk_api_token');
    } catch (err) {
      // API auth still works for the current page even if storage is blocked.
    }
  }

  saveApiToken('');

  function consumeAuthRedirectToken() {
    try {
      const url = new URL(location.href);
      const token = url.searchParams.get('access_token');
      if (!token) return '';
      saveApiToken(token);
      url.searchParams.delete('access_token');
      url.searchParams.delete('token_type');
      history.replaceState(null, '', url.toString());
      return token;
    } catch (err) {
      return '';
    }
  }

  function refreshAccessToken() {
    if (refreshAccessPromise) return refreshAccessPromise;

    refreshAccessPromise = (async () => {
      const response = await fetch(apiBaseUrl + '/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' }
      });
      let data = null;
      try {
        data = await response.json();
      } catch (err) {
        data = null;
      }
      if (!response.ok || !data || !data.access_token) {
        saveApiToken('');
        if (data && data.detail && /^err_refresh_/.test(String(data.detail.code || ''))) {
          clearApiSession('auth:refresh-failed');
        }
        return null;
      }
      saveApiToken(data.access_token);
      return data;
    })().finally(() => {
      refreshAccessPromise = null;
    });

    return refreshAccessPromise;
  }

  function setApiStatus(status) {
    const nextStatus = ['checking', 'online', 'offline'].includes(status) ? status : 'offline';
    if (!state || state.apiStatus === nextStatus) return nextStatus;
    setState(next => {
      next.apiStatus = nextStatus;
      next.apiCheckedAt = new Date().toISOString();
      return next;
    }, 'api:status');
    return nextStatus;
  }

  function requestMethod(options) {
    return String((options && options.method) || 'GET').toUpperCase();
  }

  function requestBodyKey(options) {
    const body = options && options.body;
    if (typeof body === 'string') return body;
    if (!body) return '';
    try {
      return JSON.stringify(body);
    } catch (err) {
      return String(body);
    }
  }

  function newIdempotencyKey() {
    if (global.crypto && typeof global.crypto.randomUUID === 'function') {
      return global.crypto.randomUUID();
    }
    return 'bk_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2);
  }

  function isMoneyPost(path, options) {
    if (requestMethod(options) !== 'POST') return false;
    return [
      /^\/cashier\/(deposit|withdraw)$/,
      /^\/admin\/users\/[^/]+\/balance$/,
      /^\/admin\/withdrawals\/[^/]+\/(approve|reject)$/,
      /^\/vip\/tiers\/purchase$/,
      /^\/games\/roulette\/spin$/,
      /^\/games\/slots\/lucky-bamboo\/spin$/,
      /^\/games\/plinko\/midnight-vault\/drop$/,
      /^\/games\/survival\/arctic-protocol\/start$/,
      /^\/games\/survival\/arctic-protocol\/rounds\/[^/]+\/(ready|choice|continue|timeout)$/,
      /^\/games\/mines\/solar-wilds\/start$/,
      /^\/games\/mines\/solar-wilds\/rounds\/[^/]+\/cashout$/,
      /^\/games\/blocks\/neon-pyramids\/start$/,
      /^\/games\/blocks\/neon-pyramids\/rounds\/[^/]+\/(cashout|forfeit)$/,
      /^\/games\/holdem\/texas-holdem\/start$/,
      /^\/games\/holdem\/texas-holdem\/rounds\/[^/]+\/decision$/,
      /^\/games\/crash\/dragons-fortune\/start$/,
      /^\/games\/crash\/dragons-fortune\/rounds\/[^/]+\/cashout$/
    ].some(pattern => pattern.test(path));
  }

  function prepareRequestOptions(path, options) {
    const prepared = Object.assign({}, options || {});
    prepared.headers = Object.assign({}, prepared.headers || {});
    if (isMoneyPost(path, prepared) && !prepared.headers['Idempotency-Key']) {
      prepared.headers['Idempotency-Key'] = newIdempotencyKey();
    }
    return prepared;
  }

  async function performRequest(path, options, retrying) {
    const token = apiToken();
    const preparedOptions = Object.assign({}, options || {});
    preparedOptions.credentials = 'include';
    preparedOptions.headers = Object.assign({
        'Content-Type': 'application/json'
      }, token ? { Authorization: 'Bearer ' + token } : {}, preparedOptions.headers || {});
    if (state && state.apiStatus === 'offline' && path !== '/health') {
      throw new Error('err_api_unavailable');
    }
    let response;
    try {
      response = await fetch(apiBaseUrl + path, preparedOptions);
      if (path !== '/health') setApiStatus('online');
    } catch (err) {
      setApiStatus('offline');
      throw new Error('err_api_unavailable');
    }
    let data = null;
    try {
      data = await response.json();
    } catch (err) {
      data = null;
    }
    if (!response.ok) {
      if (response.status === 401 && !retrying && path !== '/auth/refresh') {
        const refreshed = await refreshAccessToken();
        if (refreshed) return performRequest(path, options, true);
      }
      const detail = data && data.detail ? data.detail : 'api_error';
      const apiError = new Error(Array.isArray(detail) ? 'api_validation_error' : (detail.code || detail));
      apiError.detail = detail;
      throw apiError;
    }
    return data;
  }

  async function requestApi(path, options) {
    const prepared = prepareRequestOptions(path, options);
    if (!isMoneyPost(path, prepared)) return performRequest(path, prepared, false);

    const lockKey = requestMethod(prepared) + ' ' + path + ' ' + requestBodyKey(prepared);
    if (moneyRequestLocks.has(lockKey)) return moneyRequestLocks.get(lockKey);

    const promise = performRequest(path, prepared, false).finally(() => {
      moneyRequestLocks.delete(lockKey);
    });
    moneyRequestLocks.set(lockKey, promise);
    return promise;
  }

  function activeUser(sourceState) {
    return sourceState.currentUser || null;
  }

  function guestUser() {
    return normalizeUser({
      id: 'guest-user',
      name: '',
      email: '',
      currency: C.defaults.currency,
      balance: 0,
      vipPoints: 0,
      gamesPlayed: 0,
      totalWon: 0,
      history: []
    }, 'registered');
  }

  function displayUser(sourceState) {
    return sourceState.currentUser || guestUser();
  }

  function hashPassword(password) {
    const value = String(password || '');
    let hash = 2166136261;
    for (let i = 0; i < value.length; i++) {
      hash ^= value.charCodeAt(i);
      hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
    }
    return 'h_' + (hash >>> 0).toString(16);
  }

  function verifyPassword(user, password) {
    const candidate = hashPassword(password);
    if (user.passwordHash) return user.passwordHash === candidate;
    return user.password === password;
  }

  function getTier(points) {
    if (typeof points === 'string') {
      const byName = C.vipTiers.find(tier => tier.name.toLowerCase() === points.toLowerCase());
      if (byName) return byName;
    }
    const value = toNumber(points);
    return C.vipTiers.find(tier => value >= tier.min && value <= tier.max) || C.vipTiers[C.vipTiers.length - 1];
  }

  function emailError(email) {
    const value = String(email || '').trim();
    if (!value) return 'err_email_empty';
    if (value.length < 5) return 'err_email_short';
    if (!/^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(value)) return 'err_email_invalid';
    if (value.includes('..') || value.startsWith('.') || value.startsWith('@')) return 'err_email_invalid';
    return null;
  }

  function isAdminEmail(email) {
    const value = String(email || '').trim().toLowerCase();
    if (!value) return false;
    return (C.adminEmails || []).some(item => String(item || '').trim().toLowerCase() === value);
  }

  function passwordError(password) {
    if (!password) return 'err_pass_empty';
    if (String(password).length < 8) return 'err_pass_short';
    return null;
  }

  function nameError(name) {
    return String(name || '').trim() ? null : 'err_name_empty';
  }

  function normalizeTransaction(entry) {
    const source = entry || {};
    const createdAt = source.createdAt || source.created_at || source.date || new Date().toISOString();
    const amount = toNumber(source.amount);
    return {
      id: source.id || 'tx-' + Date.now() + '-' + Math.random().toString(16).slice(2),
      createdAt,
      date: createdAt,
      type: ['deposit', 'withdraw', 'win', 'game', 'vip'].includes(source.type) ? source.type : 'deposit',
      status: source.status || 'completed',
      title: source.title || '',
      titleKey: source.titleKey || source.title_key || '',
      methodId: source.methodId || source.method_id || '',
      amount,
      fee: toNumber(source.fee !== undefined ? source.fee : toNumber(source.fee_cents) / 100),
      payout: toNumber(source.payout !== undefined ? source.payout : toNumber(source.payout_cents) / 100)
    };
  }

  function normalizeUser(user, kind) {
    const source = user || {};
    const isDemo = kind === 'demo' || source.id === C.demoUser.id;
    const base = clone(isDemo ? C.demoUser : C.registeredUser);
    const merged = Object.assign(base, source);

    merged.id = merged.id || 'user-' + Date.now() + '-' + Math.random().toString(16).slice(2);
    merged.name = String(merged.name || '').trim();
    merged.firstName = String(merged.firstName || '').trim();
    merged.lastName = String(merged.lastName || '').trim();
    if (!merged.firstName && merged.name) {
      const nameParts = merged.name.split(/\s+/);
      merged.firstName = nameParts.shift() || '';
      merged.lastName = merged.lastName || nameParts.join(' ');
    }
    merged.email = String(merged.email || '').trim();
    merged.phone = String(merged.phone || '').trim();
    merged.dob = String(merged.dob || '');
    merged.country = String(merged.country || '').trim();
    merged.currency = merged.currency || C.defaults.currency;
    merged.security = Object.assign({}, base.security, source.security || {});
    merged.history = Array.isArray(merged.history) ? merged.history.map(normalizeTransaction) : [];
    merged.passwordHash = merged.passwordHash || (source.password ? hashPassword(source.password) : '');
    delete merged.password;
    merged.balance = toNumber(merged.balance);
    merged.vipPoints = Math.max(0, Math.floor(toNumber(merged.vipPoints)));
    merged.vipTier = getTier(merged.vipTier || 'bronze').name.toLowerCase();
    merged.gamesPlayed = Math.max(0, Math.floor(toNumber(merged.gamesPlayed)));
    merged.totalWon = toNumber(merged.totalWon);
    merged.isAdmin = Boolean(merged.isAdmin || isAdminEmail(merged.email));
    merged.vipLevel = getTier(merged.vipTier).name;
    return merged;
  }

  function publicUser(user) {
    if (!user) return null;
    const safe = clone(user);
    delete safe.password;
    delete safe.passwordHash;
    return safe;
  }

  function userFromApi(apiUser) {
    const source = apiUser || {};
    const storedKycStatus = readKycStatus({ id: source.id ? 'api-' + source.id : '', apiId: source.id, email: source.email });
    return normalizeUser(Object.assign({}, C.registeredUser, {
      id: 'api-' + source.id,
      apiId: source.id,
      name: source.name || source.email,
      firstName: source.first_name || source.firstName || '',
      lastName: source.last_name || source.lastName || '',
      email: source.email,
      phone: source.phone || '',
      dob: source.dob || '',
      country: source.country || '',
      currency: source.currency || C.defaults.currency,
      balance: source.balance !== undefined ? source.balance : toNumber(source.balance_cents) / 100,
      vipPoints: source.vip_points !== undefined ? source.vip_points : source.vipPoints,
      vipTier: source.vip_tier || source.vipTier || 'bronze',
      gamesPlayed: source.games_played !== undefined ? source.games_played : source.gamesPlayed,
      totalWon: source.total_won !== undefined ? source.total_won : toNumber(source.total_won_cents) / 100,
      isAdmin: Boolean(source.is_admin || source.isAdmin),
      history: Array.isArray(source.history) ? source.history : [],
      provider: source.provider || 'local',
      security: {
        twoFactor: false,
        emailVerified: Boolean(source.email_verified),
        kycStatus: source.kyc_status && source.kyc_status !== 'not_started'
          ? source.kyc_status
          : storedKycStatus || source.kyc_status || 'not_started'
      },
      profileCompletion: source.profile_completion !== undefined ? source.profile_completion : 0,
      profileMissingFields: source.profile_missing_fields || [],
      onboardingRequired: Boolean(source.onboarding_required),
      createdAt: source.created_at,
      lastLoginAt: source.last_login_at
    }), 'registered');
  }

  function authErrorKey(error) {
    const code = apiErrorCode(error);
    if (code) return code;
    const message = String(error && error.message ? error.message : error || '');
    if (/already registered/i.test(message)) return 'err_user_exists';
    if (/invalid email or password/i.test(message)) return 'err_wrong_password';
    if (/not authenticated/i.test(message)) return 'err_auth_required';
    if (/admin access/i.test(message)) return 'err_admin_required';
    if (/fetch|failed|network/i.test(message)) return 'err_api_unavailable';
    return 'err_api_unavailable';
  }

  function apiErrorCode(error) {
    const detail = error && error.detail && typeof error.detail === 'object' && !Array.isArray(error.detail) ? error.detail : null;
    if (detail && typeof detail.code === 'string' && detail.code) return detail.code;
    const message = String(error && error.message ? error.message : error || '');
    const match = message.match(/\berr_[a-z0-9_]+\b/i);
    return match ? match[0] : '';
  }

  function cashierError(error) {
    const detail = error && error.detail && typeof error.detail === 'object' ? error.detail : {};
    const backendAmount = Number(detail.amount);
    const message = String(error && error.message ? error.message : error || '');
    if (/err_deposit_min/i.test(message)) return fail('err_deposit_min', { min: Number.isFinite(backendAmount) ? backendAmount : C.cashier.depositMin });
    if (/err_deposit_max/i.test(message)) return fail('err_deposit_max', { max: Number.isFinite(backendAmount) ? backendAmount : C.cashier.depositMax });
    if (/err_withdraw_min/i.test(message)) return fail('err_withdraw_min', { min: Number.isFinite(backendAmount) ? backendAmount : C.cashier.withdrawMin });
    if (/err_withdraw_max/i.test(message)) return fail('err_withdraw_max', { max: Number.isFinite(backendAmount) ? backendAmount : C.cashier.withdrawMax });
    if (/err_withdraw_balance/i.test(message)) return fail('err_withdraw_balance');
    if (/err_payment_method_invalid/i.test(message)) return fail('err_method_invalid');
    if (/err_insufficient_balance/i.test(message)) return fail('err_withdraw_balance');
    if (/err_promo_required/i.test(message)) return fail('err_promo_required');
    if (/err_promo_invalid/i.test(message)) return fail('err_promo_invalid');
    if (/err_promo_inactive/i.test(message)) return fail('err_promo_inactive');
    if (/err_promo_not_started/i.test(message)) return fail('err_promo_not_started');
    if (/err_promo_expired/i.test(message)) return fail('err_promo_expired');
    if (/err_promo_usage_limit/i.test(message)) return fail('err_promo_usage_limit');
    if (/err_promo_already_used/i.test(message)) return fail('err_promo_already_used');
    if (/err_promo_reward_type/i.test(message)) return fail('err_promo_reward_type');
    if (/err_promo_fixed_amount/i.test(message)) return fail('err_promo_fixed_amount');
    if (/err_promo_percent_value/i.test(message)) return fail('err_promo_percent_value');
    if (/err_promo_max_bonus/i.test(message)) return fail('err_promo_max_bonus');
    if (/err_promo_date_range/i.test(message)) return fail('err_promo_date_range');
    if (/err_abuse_promo_blocked/i.test(message)) return fail('err_abuse_promo_blocked');
    if (/err_promo_min_deposit/i.test(message)) return fail('err_promo_min_deposit', {
      min: toNumber(error && error.detail && error.detail.amount !== undefined ? error.detail.amount : 0)
    });
    if (/promo code already exists/i.test(message)) return fail('err_promo_duplicate');
    if (/promo requires|promo reward|promo expires/i.test(message)) return fail('err_promo_config');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function vipError(error) {
    const message = String(error && error.message ? error.message : error || '');
    if (/err_vip_balance/i.test(message)) return fail('err_vip_balance');
    if (/err_vip_not_enough_points/i.test(message)) return fail('err_vip_not_enough_points');
    if (/err_vip_not_next/i.test(message)) return fail('err_vip_not_next');
    if (/err_vip_already_unlocked/i.test(message)) return fail('err_vip_already_unlocked');
    if (/err_vip_invalid/i.test(message)) return fail('err_vip_invalid');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function rouletteError(error) {
    const message = String(error && error.message ? error.message : error || '');
    const detail = error && error.detail && typeof error.detail === 'object' ? error.detail : null;
    const amount = detail && detail.amount !== undefined ? toNumber(detail.amount) : null;
    if (/err_roulette_bet_min/i.test(message)) return fail('err_roulette_bet_min', { min: amount != null ? amount : 1 });
    if (/err_roulette_bet_max/i.test(message)) return fail('err_roulette_bet_max', { max: amount != null ? amount : 999999.99 });
    if (/err_roulette_total_max/i.test(message)) return fail('err_roulette_total_max', { max: amount != null ? amount : 999999.99 });
    if (/err_roulette_balance/i.test(message)) return fail('err_roulette_balance');
    if (/err_roulette_bet_invalid/i.test(message)) return fail('err_roulette_bet_invalid');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function slotError(error) {
    const message = String(error && error.message ? error.message : error || '');
    if (/err_slot_bet_invalid/i.test(message)) return fail('err_slot_bet_invalid');
    if (/err_slot_balance/i.test(message)) return fail('err_slot_balance');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function plinkoError(error) {
    const message = String(error && error.message ? error.message : error || '');
    if (/err_plinko_bet_invalid/i.test(message)) return fail('err_plinko_bet_invalid');
    if (/err_plinko_mode_invalid/i.test(message)) return fail('err_plinko_mode_invalid');
    if (/err_plinko_risk_invalid/i.test(message)) return fail('err_plinko_risk_invalid');
    if (/err_plinko_rows_invalid/i.test(message)) return fail('err_plinko_rows_invalid');
    if (/err_plinko_balls_invalid/i.test(message)) return fail('err_plinko_balls_invalid');
    if (/err_plinko_balance/i.test(message)) return fail('err_plinko_balance');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function survivalError(error) {
    const message = String(error && error.message ? error.message : error || '');
    const known = message.match(/err_survival_[a-z_]+/i);
    if (known) return fail(known[0].toLowerCase());
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function minesError(error) {
    const message = String(error && error.message ? error.message : error || '');
    if (/err_mines_bet_invalid/i.test(message)) return fail('err_mines_bet_invalid');
    if (/err_mines_count_invalid/i.test(message)) return fail('err_mines_count_invalid');
    if (/err_mines_balance/i.test(message)) return fail('err_mines_balance');
    if (/err_mines_active_round/i.test(message)) return fail('err_mines_active_round');
    if (/err_mines_cell_invalid/i.test(message)) return fail('err_mines_cell_invalid');
    if (/err_mines_cell_revealed/i.test(message)) return fail('err_mines_cell_revealed');
    if (/err_mines_no_reveals/i.test(message)) return fail('err_mines_no_reveals');
    if (/err_mines_round_settled/i.test(message)) return fail('err_mines_round_settled');
    if (/err_mines_round_not_found/i.test(message)) return fail('err_mines_round_not_found');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function blocksError(error) {
    const message = String(error && error.message ? error.message : error || '');
    if (/err_blocks_bet_invalid/i.test(message)) return fail('err_blocks_bet_invalid');
    if (/err_blocks_difficulty_invalid/i.test(message)) return fail('err_blocks_difficulty_invalid');
    if (/err_blocks_balance/i.test(message)) return fail('err_blocks_balance');
    if (/err_blocks_active_round/i.test(message)) return fail('err_blocks_active_round');
    if (/err_blocks_piece_invalid/i.test(message)) return fail('err_blocks_piece_invalid');
    if (/err_blocks_placement_invalid/i.test(message)) return fail('err_blocks_placement_invalid');
    if (/err_blocks_no_lines/i.test(message)) return fail('err_blocks_no_lines');
    if (/err_blocks_round_settled/i.test(message)) return fail('err_blocks_round_settled');
    if (/err_blocks_round_not_found/i.test(message)) return fail('err_blocks_round_not_found');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function holdemError(error) {
    const message = String(error && error.message ? error.message : error || '');
    if (/err_holdem_ante_invalid/i.test(message)) return fail('err_holdem_ante_invalid');
    if (/err_holdem_balance/i.test(message)) return fail('err_holdem_balance');
    if (/err_holdem_active_round/i.test(message)) return fail('err_holdem_active_round');
    if (/err_holdem_action_invalid/i.test(message)) return fail('err_holdem_action_invalid');
    if (/err_holdem_round_settled/i.test(message)) return fail('err_holdem_round_settled');
    if (/err_holdem_round_not_found/i.test(message)) return fail('err_holdem_round_not_found');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function crashError(error) {
    const message = String(error && error.message ? error.message : error || '');
    if (/err_crash_bet_invalid/i.test(message)) return fail('err_crash_bet_invalid');
    if (/err_crash_balance/i.test(message)) return fail('err_crash_balance');
    if (/err_crash_cashout_locked/i.test(message)) return fail('err_crash_cashout_locked');
    if (/err_crash_active_round/i.test(message)) return fail('err_crash_active_round');
    if (/err_crash_round_settled/i.test(message)) return fail('err_crash_round_settled');
    if (/err_crash_round_not_found/i.test(message)) return fail('err_crash_round_not_found');
    if (/not authenticated/i.test(message)) return fail('err_auth_required');
    return fail(authErrorKey(error));
  }

  function setApiUser(apiUser, action) {
    const user = userFromApi(apiUser);
    const previous = state.users.find(item => item.id === user.id) || state.currentUser;
    if ((!user.history || !user.history.length) && previous && Array.isArray(previous.history)) {
      user.history = previous.history.map(normalizeTransaction);
    }
    save(C.storage.session, publicUser(user));
    setState(next => {
      const idx = next.users.findIndex(item => item.id === user.id);
      if (idx >= 0) next.users[idx] = user;
      else next.users.push(user);
      next.currentUser = publicUser(user);
      next.session = publicUser(user);
      return next;
    }, action || 'auth:api');
    return user;
  }

  function updateApiWallet(wallet, transaction, action) {
    const active = activeUser(state);
    if (!active || !active.apiId) return active;
    const history = Array.isArray(active.history) ? active.history.slice() : [];
    if (transaction) {
      const normalizedTransaction = normalizeTransaction(transaction);
      const idx = history.findIndex(item => String(item.id) === String(normalizedTransaction.id));
      if (idx >= 0) history[idx] = normalizedTransaction;
      else history.unshift(normalizedTransaction);
    }
    return persistCurrentUser(Object.assign({}, active, {
      currency: wallet.currency || active.currency,
      balance: wallet.balance !== undefined ? wallet.balance : toNumber(wallet.balance_cents) / 100,
      vipPoints: wallet.vip_points !== undefined ? wallet.vip_points : active.vipPoints,
      vipTier: wallet.vip_tier || wallet.vipTier || active.vipTier || 'bronze',
      gamesPlayed: wallet.games_played !== undefined ? wallet.games_played : active.gamesPlayed,
      totalWon: wallet.total_won !== undefined ? wallet.total_won : toNumber(wallet.total_won_cents) / 100,
      history
    }), action || 'wallet:update');
  }

  async function refreshApiTransactions(action, options) {
    const active = activeUser(state);
    if (!active || !active.apiId) return active;
    const config = options || {};
    const params = new URLSearchParams({
      limit: String(Math.min(100, Math.max(1, Number(config.limit) || 100))),
      offset: String(Math.max(0, Number(config.offset) || 0))
    });
    const history = await requestApi('/transactions?' + params.toString());
    return persistCurrentUser(Object.assign({}, active, {
      history: Array.isArray(history) ? history.map(normalizeTransaction) : []
    }), action || 'transactions:refresh');
  }

  function findStoredUser(users, user) {
    if (!user) return null;
    const email = String(user.email || '').toLowerCase();
    return users.find(item => item.id === user.id) || users.find(item => item.email.toLowerCase() === email) || null;
  }

  function createInitialState() {
    const users = read(C.storage.users, []).map(user => normalizeUser(user, 'registered'));
    const session = read(C.storage.session, null);
    const storedSessionUser = findStoredUser(users, session);
    const currentUser = session && session.apiId ? normalizeUser(Object.assign({}, storedSessionUser || {}, session), 'registered') : null;
    const demoUser = normalizeUser(read(C.storage.demoUser, C.demoUser), 'demo');
    const initialDisplayUser = currentUser || guestUser();
    const storedLang = (() => {
      try {
        const raw = localStorage.getItem(C.storage.lang);
        return safeParse(raw, raw);
      } catch (err) {
        return null;
      }
    })();

    return {
      lang: C.fallbackI18n[storedLang] ? storedLang : C.defaults.lang,
      users,
      session: currentUser ? publicUser(currentUser) : null,
      currentUser: currentUser ? publicUser(currentUser) : null,
      demoUser,
      balance: initialDisplayUser.balance,
      vipPoints: initialDisplayUser.vipPoints,
      vipLevel: initialDisplayUser.vipLevel,
      history: initialDisplayUser.history,
      apiStatus: 'checking',
      apiCheckedAt: '',
      cashier: {
        mode: 'deposit',
        selectedMethod: C.cashier.depositMethods[0].id,
        selectedWithdrawMethod: C.cashier.withdrawMethods[0].id
      },
      data: {
        games: clone(C.fallbackGames),
        i18n: clone(C.fallbackI18n)
      },
      ui: {}
    };
  }

  function mergeI18n(loaded) {
    const merged = clone(C.fallbackI18n);
    if (!loaded) return merged;
    Object.keys(loaded).forEach(lang => {
      merged[lang] = Object.assign({}, merged[lang] || {}, loaded[lang] || {});
    });
    return merged;
  }

  let state = createInitialState();
  const listeners = new Set();

  function refreshDerived(next) {
    const active = displayUser(next);
    next.balance = active.balance;
    next.vipPoints = active.vipPoints;
    next.vipLevel = getTier(active.vipTier || active.vipPoints).name;
    next.history = active.history || [];
    return next;
  }

  function emit(prev, action, lightweight) {
    const detail = lightweight
      ? { state, previous: prev, action }
      : { state: getState(), previous: clone(prev), action };
    listeners.forEach(fn => fn(detail.state, detail.previous, action));
    global.dispatchEvent(new CustomEvent('bambiku:state', { detail }));
  }

  function setState(updater, action) {
    const prev = state;
    const next = typeof updater === 'function' ? updater(clone(state)) : Object.assign(clone(state), updater);
    state = refreshDerived(next);
    emit(prev, action || 'setState');
    return getState();
  }

  function getState() {
    return clone(state);
  }

  function clearApiSession(action) {
    saveApiToken('');
    remove(C.storage.session);
    if (!state) return;
    setState(next => {
      next.currentUser = null;
      next.session = null;
      return next;
    }, action || 'auth:clear');
  }

  function getDisplayUser() {
    return clone(displayUser(state));
  }

  function emailInUse(email, exceptId) {
    const normalized = String(email || '').trim().toLowerCase();
    return state.users.some(user => user.email.toLowerCase() === normalized && user.id !== exceptId);
  }

  function persistCurrentUser(nextUser, action) {
    if (state.currentUser) {
      const users = state.users.slice();
      const currentId = state.currentUser.id;
      const user = normalizeUser(Object.assign({}, state.currentUser, nextUser, { id: currentId }), 'registered');
      const idx = users.findIndex(item => item.id === currentId);
      const storedUser = normalizeUser(Object.assign({}, idx >= 0 ? users[idx] : {}, user), 'registered');

      if (idx >= 0) users[idx] = storedUser;
      else users.push(storedUser);

      save(C.storage.users, users);
      save(C.storage.session, publicUser(storedUser));
      setState(next => {
        next.users = users.map(item => normalizeUser(item, 'registered'));
        next.currentUser = publicUser(storedUser);
        next.session = publicUser(storedUser);
        return next;
      }, action || 'user:update');
      return storedUser;
    }

    const user = normalizeUser(Object.assign({}, state.demoUser, nextUser), 'demo');
    save(C.storage.demoUser, user);
    setState(next => {
      next.demoUser = user;
      return next;
    }, action || 'demo:update');
    return user;
  }

  function persistAndReturn(nextUser) {
    return okUser(persistCurrentUser(nextUser));
  }

  function addHistoryEntry(user, entry) {
    const history = Array.isArray(user.history) ? user.history.slice() : [];
    history.unshift(normalizeTransaction(Object.assign({
      id: 'tx-' + Date.now(),
      createdAt: new Date().toISOString()
    }, entry)));
    return Object.assign({}, user, { history });
  }

  function cashierMethod(kind, methodId) {
    const list = kind === 'withdraw' ? C.cashier.withdrawMethods : C.cashier.depositMethods;
    return list.find(method => method.id === methodId) || null;
  }

  const api = {
    getState,
    peekState() {
      return state;
    },
    getDisplayUser,
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    validateEmail: emailError,
    validatePassword: passwordError,
    validateName: nameError,
    cashierMethod,
    getApiStatus() {
      return state.apiStatus || 'checking';
    },
    setApiStatus,
    refreshTransactions: refreshApiTransactions,
    async checkApiHealth() {
      try {
        const response = await fetch(apiBaseUrl + '/health', {
          cache: 'no-store',
          credentials: 'include'
        });
        setApiStatus(response.ok ? 'online' : 'offline');
        return state.apiStatus;
      } catch (err) {
        setApiStatus('offline');
        return 'offline';
      }
    },
    startApiStatusPolling(intervalMs) {
      if (apiStatusTimer) return;
      api.checkApiHealth();
      apiStatusTimer = global.setInterval(() => {
        if (!document.hidden) api.checkApiHealth();
      }, intervalMs || 30000);
      if (!apiStatusVisibilityBound) {
        apiStatusVisibilityBound = true;
        document.addEventListener('visibilitychange', () => {
          if (!document.hidden) api.checkApiHealth();
        });
      }
    },
    async restoreSession() {
      try {
        const token = consumeAuthRedirectToken();
        if (!token && !apiToken()) {
          const refreshed = await refreshAccessToken();
          if (!refreshed) {
            remove(C.storage.session);
            return getState();
          }
        }
        const user = await requestApi('/users/me');
        setApiUser(user, 'auth:restore');
      } catch (err) {
        saveApiToken('');
        remove(C.storage.session);
      }
      return getState();
    },
    setData(games, i18n) {
      return setState(next => {
        next.data.games = games || clone(C.fallbackGames);
        next.data.i18n = mergeI18n(i18n);
        return next;
      }, 'data:set');
    },
    setLang(lang) {
      const nextLang = (state.data.i18n && state.data.i18n[lang]) || C.fallbackI18n[lang] ? lang : C.defaults.lang;
      if (nextLang === state.lang) return state;
      try {
        localStorage.setItem(C.storage.lang, nextLang);
      } catch (err) {
        // Language can still update in memory if persistence is unavailable.
      }
      const prev = state;
      state = refreshDerived(Object.assign({}, state, { lang: nextLang }));
      emit(prev, 'lang:set', true);
      return state;
    },
    async register(payload) {
      const firstName = String(payload?.firstName || '').trim();
      const lastName = String(payload?.lastName || '').trim();
      const name = String(payload?.name || (firstName + ' ' + lastName)).trim();
      const email = String(payload?.email || '').trim();
      const password = String(payload?.password || '');
      const nameErr = nameError(name);
      const emailErr = emailError(email);
      const passErr = passwordError(password);
      if (nameErr) return fail(nameErr);
      if (emailErr) return fail(emailErr);
      if (passErr) return fail(passErr);
      if (emailInUse(email)) return fail('err_user_exists');

      try {
        const result = await requestApi('/auth/register', {
          method: 'POST',
          body: JSON.stringify({
            name,
            first_name: firstName,
            last_name: lastName,
            email,
            password,
            dob: String(payload?.dob || ''),
            country: String(payload?.country || '').trim(),
            phone: String(payload?.phone || '').trim(),
            kyc_opt_in: Boolean(payload?.kycOptIn)
          })
        });
        saveApiToken(result.access_token);
        const user = setApiUser(result.user, 'auth:register');
        return okUser(user);
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    registerLocal(payload) {
      const name = String(payload?.name || '').trim();
      const email = String(payload?.email || '').trim();
      const password = String(payload?.password || '');
      const nameErr = nameError(name);
      const emailErr = emailError(email);
      const passErr = passwordError(password);
      if (nameErr) return fail(nameErr);
      if (emailErr) return fail(emailErr);
      if (passErr) return fail(passErr);
      if (emailInUse(email)) return fail('err_user_exists');

      const user = normalizeUser(Object.assign({}, C.registeredUser, {
        id: 'user-' + Date.now(),
        name,
        email,
        passwordHash: hashPassword(password),
        passwordChangedAt: new Date().toISOString().slice(0, 10),
        createdAt: new Date().toISOString()
      }), 'registered');
      const users = state.users.concat(user);

      save(C.storage.users, users);
      save(C.storage.session, publicUser(user));
      setState(next => {
        next.users = users;
        next.currentUser = publicUser(user);
        next.session = publicUser(user);
        return next;
      }, 'auth:register');
      return okUser(user);
    },
    async login(email, password) {
      const normalized = String(email || '').trim().toLowerCase();
      try {
        const result = await requestApi('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email: normalized, password: String(password || '') })
        });
        saveApiToken(result.access_token);
        const user = setApiUser(result.user, 'auth:login');
        return okUser(user);
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    loginLocal(email, password) {
      const normalized = String(email || '').trim().toLowerCase();
      const user = state.users.find(item => item.email.toLowerCase() === normalized);
      if (!user) return fail('err_user_not_found');
      if (!verifyPassword(user, password)) return fail('err_wrong_password');

      save(C.storage.session, publicUser(user));
      setState(next => {
        next.currentUser = publicUser(user);
        next.session = publicUser(user);
        return next;
      }, 'auth:login');
      return okUser(user);
    },
    logout() {
      requestApi('/auth/logout', { method: 'POST' }).catch(() => {});
      clearApiSession('auth:logout');
      return getState();
    },
    async logoutAll() {
      try {
        await requestApi('/auth/logout-all', { method: 'POST' });
      } catch (err) {
        const code = authErrorKey(err);
        if (!/^err_refresh_|err_auth_required$/.test(code)) return fail(code);
      }
      clearApiSession('auth:logout-all');
      return getState();
    },
    async updateProfile(fields) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      const name = String(fields?.name || '').trim();
      const email = String(fields?.email || '').trim();
      const nameErr = nameError(name);
      const emailErr = emailError(email);
      if (nameErr) return fail(nameErr);
      if (emailErr) return fail(emailErr);
      if (state.currentUser && emailInUse(email, state.currentUser.id)) return fail('err_profile_email_exists');

      try {
        const user = await requestApi('/users/me', {
          method: 'PATCH',
          body: JSON.stringify({
            name,
            first_name: String(fields?.firstName || '').trim(),
            last_name: String(fields?.lastName || '').trim(),
            email,
            phone: String(fields?.phone || '').trim(),
            dob: String(fields?.dob || ''),
            country: String(fields?.country || '').trim(),
            currency: String(fields?.currency || active.currency || C.defaults.currency).trim().toUpperCase()
          })
        });
        return okUser(setApiUser(user, 'user:update'));
      } catch (err) {
        if (/already registered/i.test(String(err && err.message ? err.message : err))) {
          return fail('err_profile_email_exists');
        }
        return fail(authErrorKey(err));
      }
    },
    updateKycStatus(status) {
      const active = activeUser(state);
      if (!active) return fail('err_auth_required');
      const allowed = ['not_started', 'pending', 'verified'];
      const nextStatus = allowed.includes(status) ? status : 'pending';
      const security = Object.assign({}, active.security || {}, { kycStatus: nextStatus });
      writeKycStatus(active, nextStatus);
      return okUser(persistCurrentUser(Object.assign({}, active, { security }), 'kyc:update'));
    },
    async deposit(amount, methodId, promoCode) {
      const method = cashierMethod('deposit', methodId);
      const value = Number(amount);
      const active = activeUser(state);
      if (!method) return fail('err_method_invalid');
      if (!active || !active.apiId) return fail('err_auth_required');
      if (method.requiresPromo) {
        if (!String(promoCode || '').trim()) return fail('err_promo_required');
      } else if (!Number.isFinite(value) || value <= 0) {
        return fail('err_amount_invalid');
      }

      if (!method.requiresPromo) {
        const rules = C.cashier.tierRules[String(active.vipTier || 'bronze').toLowerCase()] || C.cashier.tierRules.bronze;
        const min = method.requiresCard ? rules.depositMin : Math.max(rules.depositMin, C.cashier.cryptoDepositMin);
        if (value < min) return fail('err_deposit_min', { min });
        if (value > rules.depositMax) return fail('err_deposit_max', { max: rules.depositMax });
      }

      try {
        const result = await requestApi('/cashier/deposit', {
          method: 'POST',
          body: JSON.stringify({
            amount: method.requiresPromo && Number.isFinite(value) && value > 0 ? value : (method.requiresPromo ? null : value),
            method_id: method.id,
            promo_code: String(promoCode || '').trim().toUpperCase()
          })
        });
        return okUser(updateApiWallet(result.wallet, result.transaction, 'cashier:deposit'));
      } catch (err) {
        return cashierError(err);
      }
    },
    async previewPromo(code, amount) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      const promoCode = String(code || '').trim().toUpperCase();
      if (promoCode.length < 3) return fail('err_promo_required');
      try {
        const params = new URLSearchParams({ code: promoCode });
        const value = Number(amount);
        if (Number.isFinite(value) && value > 0) params.set('amount', String(value));
        return await requestApi('/cashier/promos/preview?' + params.toString());
      } catch (err) {
        return cashierError(err);
      }
    },
    async withdraw(amount, methodId) {
      const method = cashierMethod('withdraw', methodId);
      const value = Number(amount);
      const active = activeUser(state);
      if (!method) return fail('err_method_invalid');
      if (!active || !active.apiId) return fail('err_auth_required');
      if (!Number.isFinite(value) || value <= 0) return fail('err_amount_invalid');
      const rules = C.cashier.tierRules[String(active.vipTier || 'bronze').toLowerCase()] || C.cashier.tierRules.bronze;
      if (value < rules.withdrawMin) return fail('err_withdraw_min', { min: rules.withdrawMin });
      if (rules.withdrawMax && value > rules.withdrawMax) return fail('err_withdraw_max', { max: rules.withdrawMax });
      if (value > toNumber(active.balance)) return fail('err_withdraw_balance');

      try {
        const result = await requestApi('/cashier/withdraw', {
          method: 'POST',
          body: JSON.stringify({ amount: value, method_id: method.id })
        });
        const updated = updateApiWallet(result.wallet, result.transaction, 'cashier:withdraw');
        return { user: publicUser(updated), transaction: result.transaction };
      } catch (err) {
        return cashierError(err);
      }
    },
    async playRoulette(bets) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      if (!Array.isArray(bets) || !bets.length) return fail('err_roulette_no_bets');

      try {
        return await requestApi('/games/roulette/spin', {
          method: 'POST',
          body: JSON.stringify({ bets })
        });
      } catch (err) {
        return rouletteError(err);
      }
    },
    async playLuckyBamboo(bet) {
      const active = activeUser(state);
      const value = Number(bet);
      if (!active || !active.apiId) return fail('err_auth_required');
      if (![5, 10, 25, 100].includes(value)) return fail('err_slot_bet_invalid');
      if (value > toNumber(active.balance)) return fail('err_slot_balance');

      try {
        return await requestApi('/games/slots/lucky-bamboo/spin', {
          method: 'POST',
          body: JSON.stringify({ bet: value })
        });
      } catch (err) {
        return slotError(err);
      }
    },
    async dropMidnightVault(bet, mode, risk, rows, balls) {
      const active = activeUser(state);
      const value = Number(bet);
      const selectedMode = String(mode || 'classic').toLowerCase();
      const selectedRisk = String(risk || 'medium').toLowerCase();
      const selectedRows = Number(rows || 12);
      const selectedBalls = Number(balls || 1);
      if (!active || !active.apiId) return fail('err_auth_required');
      if (![5, 10, 25, 100].includes(value)) return fail('err_plinko_bet_invalid');
      if (!['classic', 'multi'].includes(selectedMode)) return fail('err_plinko_mode_invalid');
      if (!['low', 'medium', 'high'].includes(selectedRisk)) return fail('err_plinko_risk_invalid');
      if (![8, 12, 16].includes(selectedRows)) return fail('err_plinko_rows_invalid');
      if (selectedMode === 'multi' && ![3, 5, 10].includes(selectedBalls)) return fail('err_plinko_balls_invalid');
      if (value > toNumber(active.balance)) return fail('err_plinko_balance');

      try {
        return await requestApi('/games/plinko/midnight-vault/drop', {
          method: 'POST',
          body: JSON.stringify({
            bet: value,
            mode: selectedMode,
            risk: selectedRisk,
            rows: selectedRows,
            balls: selectedMode === 'classic' ? 1 : selectedBalls
          })
        });
      } catch (err) {
        return plinkoError(err);
      }
    },
    async startArcticProtocol(bet, lang) {
      const active = activeUser(state);
      const value = Number(bet);
      if (!active || !active.apiId) return fail('err_auth_required');
      if (![5, 10, 25, 100].includes(value)) return fail('err_survival_bet_invalid');
      if (value > toNumber(active.balance)) return fail('err_survival_balance');
      try {
        const result = await requestApi('/games/survival/arctic-protocol/start', {
          method: 'POST',
          body: JSON.stringify({ bet: value, lang: lang === 'en' ? 'en' : 'ru' })
        });
        updateApiWallet(result.wallet, result.transaction, 'game:survival:start');
        return result;
      } catch (err) {
        return survivalError(err);
      }
    },
    async getActiveArcticProtocol(lang) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        const params = new URLSearchParams({ lang: lang === 'en' ? 'en' : 'ru' });
        return await requestApi('/games/survival/arctic-protocol/active?' + params.toString());
      } catch (err) {
        return survivalError(err);
      }
    },
    async getArcticProtocolRound(roundId, lang) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        const params = new URLSearchParams({ lang: lang === 'en' ? 'en' : 'ru' });
        return await requestApi('/games/survival/arctic-protocol/rounds/' + encodeURIComponent(roundId) + '?' + params.toString());
      } catch (err) {
        return survivalError(err);
      }
    },
    async chooseArcticProtocol(roundId, choiceId, lang) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        const result = await requestApi('/games/survival/arctic-protocol/rounds/' + encodeURIComponent(roundId) + '/choice', {
          method: 'POST',
          body: JSON.stringify({
            choice_id: String(choiceId || ''),
            lang: lang === 'en' ? 'en' : 'ru'
          })
        });
        if (result && result.status !== 'active') {
          updateApiWallet(result.wallet, result.transaction, 'game:survival:settled');
        }
        return result;
      } catch (err) {
        return survivalError(err);
      }
    },
    async readyArcticProtocol(roundId, lang) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/survival/arctic-protocol/rounds/' + encodeURIComponent(roundId) + '/ready', {
          method: 'POST',
          body: JSON.stringify({ lang: lang === 'en' ? 'en' : 'ru' })
        });
      } catch (err) {
        return survivalError(err);
      }
    },
    async continueArcticProtocol(roundId, lang) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/survival/arctic-protocol/rounds/' + encodeURIComponent(roundId) + '/continue', {
          method: 'POST',
          body: JSON.stringify({ lang: lang === 'en' ? 'en' : 'ru' })
        });
      } catch (err) {
        return survivalError(err);
      }
    },
    async timeoutArcticProtocol(roundId, lang) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        const result = await requestApi('/games/survival/arctic-protocol/rounds/' + encodeURIComponent(roundId) + '/timeout', {
          method: 'POST',
          body: JSON.stringify({ lang: lang === 'en' ? 'en' : 'ru' })
        });
        if (result && result.status !== 'active') {
          updateApiWallet(result.wallet, result.transaction, 'game:survival:timeout');
        }
        return result;
      } catch (err) {
        return survivalError(err);
      }
    },
    async startSolarMines(bet, mineCount) {
      const active = activeUser(state);
      const value = Number(bet);
      const mines = Number(mineCount);
      if (!active || !active.apiId) return fail('err_auth_required');
      if (![5, 10, 25, 100].includes(value)) return fail('err_mines_bet_invalid');
      if (![5, 7, 10, 12].includes(mines)) return fail('err_mines_count_invalid');
      if (value > toNumber(active.balance)) return fail('err_mines_balance');

      try {
        const result = await requestApi('/games/mines/solar-wilds/start', {
          method: 'POST',
          body: JSON.stringify({ bet: value, mine_count: mines })
        });
        updateApiWallet(result.wallet, result.transaction, 'game:mines:start');
        return result;
      } catch (err) {
        return minesError(err);
      }
    },
    async getSolarMinesRound(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/mines/solar-wilds/rounds/' + encodeURIComponent(roundId));
      } catch (err) {
        return minesError(err);
      }
    },
    async getActiveSolarMinesRound() {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/mines/solar-wilds/active');
      } catch (err) {
        return minesError(err);
      }
    },
    async revealSolarMinesCell(roundId, cell) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/mines/solar-wilds/rounds/' + encodeURIComponent(roundId) + '/reveal', {
          method: 'POST',
          body: JSON.stringify({ cell: Number(cell) })
        });
      } catch (err) {
        return minesError(err);
      }
    },
    async cashoutSolarMines(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/mines/solar-wilds/rounds/' + encodeURIComponent(roundId) + '/cashout', {
          method: 'POST'
        });
      } catch (err) {
        return minesError(err);
      }
    },
    async startNeonPyramids(bet, difficulty) {
      const active = activeUser(state);
      const value = Number(bet);
      const level = String(difficulty || 'level1');
      if (!active || !active.apiId) return fail('err_auth_required');
      if (![5, 10, 25, 100].includes(value)) return fail('err_blocks_bet_invalid');
      if (!['level1', 'level2', 'level3'].includes(level)) return fail('err_blocks_difficulty_invalid');
      if (value > toNumber(active.balance)) return fail('err_blocks_balance');

      try {
        const result = await requestApi('/games/blocks/neon-pyramids/start', {
          method: 'POST',
          body: JSON.stringify({ bet: value, difficulty: level })
        });
        updateApiWallet(result.wallet, result.transaction, 'game:blocks:start');
        return result;
      } catch (err) {
        return blocksError(err);
      }
    },
    async getActiveNeonPyramidsRound() {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/blocks/neon-pyramids/active');
      } catch (err) {
        return blocksError(err);
      }
    },
    async getNeonPyramidsRound(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/blocks/neon-pyramids/rounds/' + encodeURIComponent(roundId));
      } catch (err) {
        return blocksError(err);
      }
    },
    async placeNeonPyramidsPiece(roundId, placement) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/blocks/neon-pyramids/rounds/' + encodeURIComponent(roundId) + '/place', {
          method: 'POST',
          body: JSON.stringify({
              piece_id: Number(placement && placement.pieceId),
              rotation: Number(placement && placement.rotation),
              x: Number(placement && placement.x),
              y: Number(placement && placement.y)
            })
          });
      } catch (err) {
        return blocksError(err);
      }
    },
    async cashoutNeonPyramids(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/blocks/neon-pyramids/rounds/' + encodeURIComponent(roundId) + '/cashout', {
          method: 'POST'
        });
      } catch (err) {
        return blocksError(err);
      }
    },
    async forfeitNeonPyramids(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/blocks/neon-pyramids/rounds/' + encodeURIComponent(roundId) + '/forfeit', {
          method: 'POST'
        });
      } catch (err) {
        return blocksError(err);
      }
    },
    async startTexasHoldem(ante) {
      const active = activeUser(state);
      const value = Number(ante);
      if (!active || !active.apiId) return fail('err_auth_required');
      if (![5, 10, 25, 100].includes(value)) return fail('err_holdem_ante_invalid');
      if (value > toNumber(active.balance)) return fail('err_holdem_balance');

      try {
        const result = await requestApi('/games/holdem/texas-holdem/start', {
          method: 'POST',
          body: JSON.stringify({ ante: value })
        });
        updateApiWallet(result.wallet, result.transaction, 'game:holdem:start');
        return result;
      } catch (err) {
        return holdemError(err);
      }
    },
    async getActiveTexasHoldemRound() {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/holdem/texas-holdem/active');
      } catch (err) {
        return holdemError(err);
      }
    },
    async getTexasHoldemRound(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/holdem/texas-holdem/rounds/' + encodeURIComponent(roundId));
      } catch (err) {
        return holdemError(err);
      }
    },
    async decideTexasHoldem(roundId, action) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        const result = await requestApi('/games/holdem/texas-holdem/rounds/' + encodeURIComponent(roundId) + '/decision', {
          method: 'POST',
          body: JSON.stringify({ action: String(action || '') })
        });
        updateApiWallet(result.wallet, result.transaction, 'game:holdem:settled');
        return result;
      } catch (err) {
        return holdemError(err);
      }
    },
    async startDragonCrash(bet) {
      const active = activeUser(state);
      const value = Number(bet);
      if (!active || !active.apiId) return fail('err_auth_required');
      if (![5, 10, 25, 100].includes(value)) return fail('err_crash_bet_invalid');
      if (value > toNumber(active.balance)) return fail('err_crash_balance');

      try {
        const result = await requestApi('/games/crash/dragons-fortune/start', {
          method: 'POST',
          body: JSON.stringify({ bet: value })
        });
        updateApiWallet(result.wallet, result.transaction, 'game:crash');
        return result;
      } catch (err) {
        return crashError(err);
      }
    },
    async getDragonCrashRound(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/crash/dragons-fortune/rounds/' + encodeURIComponent(roundId));
      } catch (err) {
        return crashError(err);
      }
    },
    async cashoutDragonCrash(roundId) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        return await requestApi('/games/crash/dragons-fortune/rounds/' + encodeURIComponent(roundId) + '/cashout', {
          method: 'POST'
        });
      } catch (err) {
        return crashError(err);
      }
    },
    commitGameWallet(result, action) {
      if (!result || result.error || !result.wallet) return activeUser(state);
      return updateApiWallet(result.wallet, result.transaction, action || 'game:settled');
    },
    async adminListWithdrawals(status, paging) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const value = status || 'pending';
        const params = new URLSearchParams(Object.assign({ status: value }, paging || {}));
        return await requestApi('/admin/withdrawals?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminListUsers(query, paging) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const params = new URLSearchParams(Object.assign({ q: String(query || '').trim() }, paging || {}));
        return await requestApi('/admin/users?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminGetUser(userId) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/users/' + encodeURIComponent(userId));
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminGetUserTransactions(userId, filters) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const params = new URLSearchParams(filters || {});
        return await requestApi('/admin/users/' + encodeURIComponent(userId) + '/transactions?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminGetUserGameRounds(userId, filters) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const params = new URLSearchParams(filters || {});
        return await requestApi('/admin/users/' + encodeURIComponent(userId) + '/game-rounds?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminGetUserPromoRedemptions(userId, paging) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const params = new URLSearchParams(paging || {});
        return await requestApi('/admin/users/' + encodeURIComponent(userId) + '/promo-redemptions?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminListAudit(filters) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const params = new URLSearchParams(filters || {});
        return await requestApi('/admin/audit?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminListPromos(status, paging) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const params = new URLSearchParams(Object.assign({ status: status || 'active' }, paging || {}));
        return await requestApi('/admin/promos?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminPromoStats() {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/promos/stats');
      } catch (err) {
        try {
          const promos = await requestApi('/admin/promos?status=all&limit=100&offset=0');
          const list = Array.isArray(promos) ? promos : [];
          return {
            total: list.length,
            active: list.filter(item => item.status === 'active').length,
            scheduled: list.filter(item => item.status === 'scheduled').length,
            inactive: list.filter(item => item.status === 'inactive').length,
            expired: list.filter(item => item.status === 'expired').length,
            total_redemptions: list.reduce((sum, item) => sum + Number(item.used_count || 0), 0)
          };
        } catch (fallbackErr) {
          return fail(authErrorKey(fallbackErr));
        }
      }
    },
    async adminGetPromo(id) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/promos/' + encodeURIComponent(id));
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminGetPromoRedemptions(id, paging) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        const params = new URLSearchParams(paging || {});
        return await requestApi('/admin/promos/' + encodeURIComponent(id) + '/redemptions?' + params.toString());
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminCreatePromo(payload) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/promos', {
          method: 'POST',
          body: JSON.stringify(payload || {})
        });
      } catch (err) {
        return cashierError(err);
      }
    },
    async adminUpdatePromo(id, payload) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/promos/' + encodeURIComponent(id), {
          method: 'PATCH',
          body: JSON.stringify(payload || {})
        });
      } catch (err) {
        return cashierError(err);
      }
    },
    async adminDisablePromo(id) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/promos/' + encodeURIComponent(id) + '/disable', { method: 'POST' });
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminAdjustBalance(userId, amount, note) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      const value = toNumber(amount);
      if (!value) return fail('err_amount_invalid');
      try {
        const result = await requestApi('/admin/users/' + encodeURIComponent(userId) + '/balance', {
          method: 'POST',
          body: JSON.stringify({ amount: value, note: String(note || '').trim() || 'Admin balance adjustment' })
        });
        if (result && result.user && active.apiId === result.user.id) {
          setState(next => {
            if (next.currentUser) next.currentUser.balance = toNumber(result.user.balance);
            return next;
          }, 'admin:balance');
        }
        return result;
      } catch (err) {
        return cashierError(err);
      }
    },
    async adminApproveWithdrawal(id) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/withdrawals/' + encodeURIComponent(id) + '/approve', { method: 'POST' });
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async adminRejectWithdrawal(id) {
      const active = activeUser(state);
      if (!active || !active.apiId || !active.isAdmin) return fail('err_admin_required');
      try {
        return await requestApi('/admin/withdrawals/' + encodeURIComponent(id) + '/reject', { method: 'POST' });
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    setCashierMode(mode) {
      return setState(next => {
        next.cashier.mode = mode === 'withdraw' ? 'withdraw' : 'deposit';
        return next;
      }, 'cashier:mode');
    },
    setCashierMethod(kind, methodId) {
      const method = cashierMethod(kind, methodId);
      if (!method) return getState();
      return setState(next => {
        if (kind === 'withdraw') next.cashier.selectedWithdrawMethod = method.id;
        else next.cashier.selectedMethod = method.id;
        return next;
      }, 'cashier:method');
    },
    async getVipClickerProgress() {
      const active = activeUser(state);
      if (!active || !active.apiId) return null;
      try {
        return await requestApi('/vip/clicker');
      } catch (err) {
        return null;
      }
    },
    async clickVipTier(tier, clientActionAt, count) {
      const active = activeUser(state);
      if (!active || !active.apiId) return null;
      try {
        return await requestApi('/vip/clicker/' + encodeURIComponent(tier) + '/click', {
          method: 'POST',
          body: JSON.stringify({
            client_action_at: clientActionAt || new Date().toISOString(),
            count: Math.max(1, Math.min(25, Number(count) || 1))
          })
        });
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async resetVipTier(tier) {
      const active = activeUser(state);
      if (!active || !active.apiId) return null;
      try {
        return await requestApi('/vip/clicker/' + encodeURIComponent(tier) + '/reset', { method: 'POST' });
      } catch (err) {
        return fail(authErrorKey(err));
      }
    },
    async purchaseVipTier(tier) {
      const active = activeUser(state);
      if (!active || !active.apiId) return fail('err_auth_required');
      try {
        const result = await requestApi('/vip/tiers/purchase', {
          method: 'POST',
          body: JSON.stringify({ tier: String(tier || '').toLowerCase() })
        });
        return okUser(updateApiWallet(result.wallet, result.transaction, 'vip:tier:purchase'));
      } catch (err) {
        return vipError(err);
      }
    },
    addHistory(entry) {
      return persistAndReturn(addHistoryEntry(activeUser(state), entry));
    }
  };

  B.store = api;
  B.getVipTier = getTier;
})(window);
