(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const C = B.constants;
  const store = B.store;
  const ui = B.ui;
  let promoPreview = null;
  let promoPreviewLoading = false;
  let selectedPaymentRail = 'sbp';
  let cardCheckoutOpen = false;
  let cryptoCheckoutOpen = false;
  let selectedCryptoAsset = 'usdt';
  let selectedCryptoNetwork = 'trc20';
  let withdrawCheckoutOpen = '';
  let selectedWithdrawCryptoAsset = 'usdt';
  let selectedWithdrawCryptoNetwork = 'trc20';
  let oopsContext = 'deposit';

  const cryptoAssets = {
    usdt: {
      networks: [
        { id: 'trc20', label: 'TRC20', placeholder: 'T...' },
        { id: 'erc20', label: 'ERC20', placeholder: '0x...' },
        { id: 'bep20', label: 'BEP20', placeholder: '0x...' }
      ]
    },
    eth: { networks: [{ id: 'ethereum', label: 'Ethereum', placeholder: '0x...' }] },
    sol: { networks: [{ id: 'solana', label: 'Solana', placeholder: '7Y...' }] },
    btc: { networks: [{ id: 'bitcoin', label: 'Bitcoin', placeholder: 'bc1...' }] }
  };

  function cashierRules(user) {
    const tier = String(user?.vipTier || 'bronze').toLowerCase();
    return {
      tier,
      ...(C.cashier.tierRules[tier] || C.cashier.tierRules.bronze)
    };
  }

  function selectedDepositMethod() {
    return store.cashierMethod('deposit', store.getState().cashier.selectedMethod) || C.cashier.depositMethods[0];
  }

  function selectedWithdrawMethod() {
    return store.cashierMethod('withdraw', store.getState().cashier.selectedWithdrawMethod) || C.cashier.withdrawMethods[0];
  }

  function errorAmount(result) {
    const limit = result.min || result.max || 0;
    return ui.formatMoney(limit);
  }

  function showStoreError(result) {
    if (!result || !result.error) return false;
    ui.showToast(ui.t(result.error, { amount: errorAmount(result) }), 'err');
    return true;
  }

  function parseAmount(inputId) {
    return Number(document.getElementById(inputId)?.value || 0);
  }

  function cardNumberPassesLuhn(number) {
    let sum = 0;
    let doubleDigit = false;
    for (let index = number.length - 1; index >= 0; index -= 1) {
      let digit = Number(number[index]);
      if (doubleDigit) {
        digit *= 2;
        if (digit > 9) digit -= 9;
      }
      sum += digit;
      doubleDigit = !doubleDigit;
    }
    return sum > 0 && sum % 10 === 0;
  }

  function cardBrand(number) {
    if (/^4\d{12}(?:\d{3})?$/.test(number)) return 'visa';
    if (number.length !== 16) return '';
    const firstTwo = Number(number.slice(0, 2));
    const firstFour = Number(number.slice(0, 4));
    if ((firstTwo >= 51 && firstTwo <= 55) || (firstFour >= 2221 && firstFour <= 2720)) return 'mastercard';
    return '';
  }

  function expiryIsValid(value) {
    const match = /^(\d{2})\/(\d{2})$/.exec(value.trim());
    if (!match) return false;
    const month = Number(match[1]);
    const year = 2000 + Number(match[2]);
    if (month < 1 || month > 12) return false;
    const now = new Date();
    const expiryBoundary = new Date(year, month, 1);
    const currentMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    return expiryBoundary > currentMonth && year <= now.getFullYear() + 15;
  }

  function validateDepositAmount(amount) {
    const rules = cashierRules(store.getDisplayUser());
    if (!Number.isFinite(amount) || amount < rules.depositMin) {
      ui.showToast(ui.t('err_deposit_min', { amount: ui.formatMoney(rules.depositMin) }), 'err');
      return false;
    }
    if (amount > rules.depositMax) {
      ui.showToast(ui.t('err_deposit_max', { amount: ui.formatMoney(rules.depositMax) }), 'err');
      return false;
    }
    return true;
  }

  function validateWithdrawAmount(amount) {
    const user = store.getDisplayUser();
    const rules = cashierRules(user);
    if (!Number.isFinite(amount) || amount < rules.withdrawMin) {
      ui.showToast(ui.t('err_withdraw_min', { amount: ui.formatMoney(rules.withdrawMin) }), 'err');
      return false;
    }
    if (amount > rules.withdrawMax) {
      ui.showToast(ui.t('err_withdraw_max', { amount: ui.formatMoney(rules.withdrawMax) }), 'err');
      return false;
    }
    if (amount > Number(user.balance || 0)) {
      ui.showToast(ui.t('err_withdraw_balance'), 'err');
      return false;
    }
    return true;
  }

  function cryptoAddressIsValid(network, value) {
    const address = String(value || '').trim();
    if (network === 'trc20') return /^T[1-9A-HJ-NP-Za-km-z]{33}$/.test(address);
    if (['erc20', 'bep20', 'ethereum'].includes(network)) return /^0x[a-fA-F0-9]{40}$/.test(address);
    if (network === 'solana') return /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address);
    if (network === 'bitcoin') {
      return /^(?:bc1[ac-hj-np-z02-9]{25,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$/i.test(address);
    }
    return false;
  }

  function cryptoScope(scope) {
    const withdraw = scope === 'withdraw';
    return {
      asset: withdraw ? selectedWithdrawCryptoAsset : selectedCryptoAsset,
      network: withdraw ? selectedWithdrawCryptoNetwork : selectedCryptoNetwork,
      networkGrid: document.getElementById(withdraw ? 'withdraw-crypto-network-grid' : 'crypto-network-grid'),
      address: document.getElementById(withdraw ? 'withdraw-crypto-address' : 'crypto-address'),
      assetSelector: withdraw ? '[data-withdraw-crypto-asset]' : '[data-crypto-asset]',
      networkSelector: withdraw ? '[data-withdraw-crypto-network]' : '[data-crypto-network]'
    };
  }

  function renderCryptoNetworks(scope) {
    const state = cryptoScope(scope);
    const networks = cryptoAssets[state.asset]?.networks || cryptoAssets.usdt.networks;
    let selected = state.network;
    if (!networks.some(network => network.id === selected)) selected = networks[0].id;
    if (scope === 'withdraw') selectedWithdrawCryptoNetwork = selected;
    else selectedCryptoNetwork = selected;
    if (state.networkGrid) {
      state.networkGrid.innerHTML = networks.map(network => `
        <button class="crypto-network ${network.id === selected ? 'selected' : ''}" type="button"
          ${scope === 'withdraw' ? 'data-withdraw-crypto-network' : 'data-crypto-network'}="${network.id}"
          role="radio" aria-checked="${network.id === selected ? 'true' : 'false'}">${ui.escapeHTML(network.label)}</button>
      `).join('');
    }
    const nextState = cryptoScope(scope);
    const active = networks.find(network => network.id === selected) || networks[0];
    if (nextState.address) {
      nextState.address.value = '';
      nextState.address.placeholder = active.placeholder;
    }
  }

  function setCryptoAsset(scope, asset) {
    if (!cryptoAssets[asset]) return;
    if (scope === 'withdraw') selectedWithdrawCryptoAsset = asset;
    else selectedCryptoAsset = asset;
    const selector = scope === 'withdraw' ? '[data-withdraw-crypto-asset]' : '[data-crypto-asset]';
    document.querySelectorAll(selector).forEach(button => {
      const selected = (scope === 'withdraw' ? button.dataset.withdrawCryptoAsset : button.dataset.cryptoAsset) === asset;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-checked', selected ? 'true' : 'false');
    });
    renderCryptoNetworks(scope);
  }

  function setCryptoNetwork(scope, network) {
    const state = cryptoScope(scope);
    const config = cryptoAssets[state.asset]?.networks.find(item => item.id === network);
    if (!config) return;
    if (scope === 'withdraw') selectedWithdrawCryptoNetwork = network;
    else selectedCryptoNetwork = network;
    document.querySelectorAll(state.networkSelector).forEach(button => {
      const value = scope === 'withdraw' ? button.dataset.withdrawCryptoNetwork : button.dataset.cryptoNetwork;
      const selected = value === network;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-checked', selected ? 'true' : 'false');
    });
    if (state.address) {
      state.address.value = '';
      state.address.placeholder = config.placeholder;
      state.address.focus();
    }
  }

  function validateCryptoCheckout(scope) {
    const state = cryptoScope(scope);
    if (cryptoAddressIsValid(state.network, state.address?.value)) return true;
    const network = cryptoAssets[state.asset]?.networks.find(item => item.id === state.network)?.label || state.network.toUpperCase();
    ui.showToast(ui.t('err_crypto_address_invalid', { network }), 'err');
    state.address?.focus();
    return false;
  }

  function validateCardCheckout() {
    if (selectedPaymentRail === 'sbp') {
      const phone = (document.getElementById('sbp-phone')?.value || '').replace(/\D/g, '');
      const bank = document.getElementById('sbp-bank')?.value || '';
      if (phone.length !== 11 || !/^[78]/.test(phone)) {
        ui.showToast(ui.t('err_sbp_phone_invalid'), 'err');
        return false;
      }
      if (!bank) {
        ui.showToast(ui.t('err_sbp_bank_required'), 'err');
        return false;
      }
      return true;
    }

    const number = (document.getElementById('card-num')?.value || '').replace(/\D/g, '');
    const expiry = document.getElementById('card-exp')?.value || '';
    const cvv = (document.getElementById('card-cvv')?.value || '').replace(/\D/g, '');
    const detectedBrand = cardBrand(number);
    if (!detectedBrand || !cardNumberPassesLuhn(number) || !expiryIsValid(expiry) || !/^\d{3}$/.test(cvv)) {
      ui.showToast(ui.t('err_card_invalid'), 'err');
      return false;
    }
    if (detectedBrand !== selectedPaymentRail) {
      ui.showToast(ui.t('err_card_brand_mismatch', { brand: selectedPaymentRail === 'visa' ? 'VISA' : 'MASTERCARD' }), 'err');
      return false;
    }
    return true;
  }

  function clearCardCheckoutFields() {
    ['sbp-phone', 'card-num', 'card-exp', 'card-cvv'].forEach(id => {
      const input = document.getElementById(id);
      if (input) input.value = '';
    });
    const bank = document.getElementById('sbp-bank');
    if (bank) bank.value = '';
  }

  function setPaymentRail(rail) {
    selectedPaymentRail = ['visa', 'mastercard'].includes(rail) ? rail : 'sbp';
    document.querySelectorAll('[data-payment-rail]').forEach(button => {
      const selected = button.dataset.paymentRail === selectedPaymentRail;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-checked', selected ? 'true' : 'false');
    });
    const sbpFields = document.getElementById('sbp-route-fields');
    const cardFields = document.getElementById('bank-card-route-fields');
    if (sbpFields) sbpFields.hidden = selectedPaymentRail !== 'sbp';
    if (cardFields) cardFields.hidden = selectedPaymentRail === 'sbp';
  }

  function resetCardCheckout(clearFields) {
    cardCheckoutOpen = false;
    const firstStep = document.getElementById('deposit-step-one');
    const checkout = document.getElementById('card-checkout-step');
    if (firstStep) firstStep.hidden = false;
    if (checkout) {
      checkout.classList.remove('is-visible');
      checkout.hidden = true;
    }
    setPaymentRail('sbp');
    if (clearFields) clearCardCheckoutFields();
  }

  function resetCryptoCheckout(clearFields) {
    cryptoCheckoutOpen = false;
    const firstStep = document.getElementById('deposit-step-one');
    const checkout = document.getElementById('crypto-checkout-step');
    if (firstStep) firstStep.hidden = false;
    if (checkout) {
      checkout.classList.remove('is-visible');
      checkout.hidden = true;
    }
    selectedCryptoAsset = 'usdt';
    selectedCryptoNetwork = 'trc20';
    if (clearFields) {
      const address = document.getElementById('crypto-address');
      if (address) address.value = '';
    }
    setCryptoAsset('deposit', 'usdt');
  }

  function resetWithdrawCheckout(clearFields) {
    withdrawCheckoutOpen = '';
    const firstStep = document.getElementById('withdraw-step-one');
    if (firstStep) firstStep.hidden = false;
    ['withdraw-card-step', 'withdraw-crypto-step'].forEach(id => {
      const step = document.getElementById(id);
      if (!step) return;
      step.classList.remove('is-visible');
      step.hidden = true;
    });
    if (clearFields) {
      ['withdraw-card-num', 'withdraw-card-name', 'withdraw-crypto-address'].forEach(id => {
        const field = document.getElementById(id);
        if (field) field.value = '';
      });
    }
    selectedWithdrawCryptoAsset = 'usdt';
    selectedWithdrawCryptoNetwork = 'trc20';
    setCryptoAsset('withdraw', 'usdt');
  }

  function openCardCheckout() {
    const amount = parseAmount('amount-input');
    if (!validateDepositAmount(amount)) return;
    cardCheckoutOpen = true;
    const firstStep = document.getElementById('deposit-step-one');
    const checkout = document.getElementById('card-checkout-step');
    const amountLabel = document.getElementById('card-checkout-amount');
    if (amountLabel) amountLabel.textContent = ui.formatMoney(amount, store.getDisplayUser().currency);
    if (firstStep) firstStep.hidden = true;
    if (checkout) {
      checkout.hidden = false;
      window.requestAnimationFrame(() => checkout.classList.add('is-visible'));
    }
  }

  function openCryptoCheckout() {
    const amount = parseAmount('amount-input');
    if (!validateDepositAmount(amount)) return;
    cryptoCheckoutOpen = true;
    const firstStep = document.getElementById('deposit-step-one');
    const checkout = document.getElementById('crypto-checkout-step');
    const amountLabel = document.getElementById('crypto-checkout-amount');
    if (amountLabel) amountLabel.textContent = ui.formatMoney(amount, store.getDisplayUser().currency);
    if (firstStep) firstStep.hidden = true;
    if (checkout) {
      checkout.hidden = false;
      window.requestAnimationFrame(() => checkout.classList.add('is-visible'));
    }
    setCryptoAsset('deposit', selectedCryptoAsset);
  }

  function withdrawalAmounts() {
    const amount = Math.max(0, parseAmount('withdraw-input'));
    const rules = cashierRules(store.getDisplayUser());
    const fee = amount * rules.commission / 100;
    return { amount, fee, payout: Math.max(0, amount - fee) };
  }

  function openWithdrawCheckout() {
    const values = withdrawalAmounts();
    if (!validateWithdrawAmount(values.amount)) return;
    const crypto = selectedWithdrawMethod().requiresCrypto;
    withdrawCheckoutOpen = crypto ? 'crypto' : 'card';
    const firstStep = document.getElementById('withdraw-step-one');
    const step = document.getElementById(crypto ? 'withdraw-crypto-step' : 'withdraw-card-step');
    const prefix = crypto ? 'withdraw-crypto' : 'withdraw-card';
    const gross = document.getElementById(prefix + '-gross');
    const payout = document.getElementById(prefix + '-payout');
    if (gross) gross.textContent = ui.formatMoney(values.amount);
    if (payout) payout.textContent = ui.formatMoney(values.payout);
    if (firstStep) firstStep.hidden = true;
    if (step) {
      step.hidden = false;
      window.requestAnimationFrame(() => step.classList.add('is-visible'));
    }
    if (crypto) setCryptoAsset('withdraw', selectedWithdrawCryptoAsset);
  }

  function validateWithdrawCard() {
    const number = (document.getElementById('withdraw-card-num')?.value || '').replace(/\D/g, '');
    const name = (document.getElementById('withdraw-card-name')?.value || '').trim();
    if (!cardBrand(number) || !cardNumberPassesLuhn(number)) {
      ui.showToast(ui.t('err_withdraw_card_invalid'), 'err');
      return false;
    }
    if (!/^[\p{L} .'-]{3,64}$/u.test(name)) {
      ui.showToast(ui.t('err_withdraw_name_invalid'), 'err');
      return false;
    }
    return true;
  }

  function showCardOops(context) {
    oopsContext = context === 'withdraw' ? 'withdraw' : 'deposit';
    const overlay = document.getElementById('card-oops-overlay');
    const text = overlay?.querySelector('[data-i18n="cashier_oops_text"], [data-i18n="cashier_oops_withdraw_text"]');
    if (text) {
      const key = oopsContext === 'withdraw' ? 'cashier_oops_withdraw_text' : 'cashier_oops_text';
      text.dataset.i18n = key;
      text.textContent = ui.t(key);
    }
    if (!overlay) return;
    overlay.hidden = false;
    window.requestAnimationFrame(() => overlay.classList.add('is-visible'));
  }

  function closeCardOops() {
    const overlay = document.getElementById('card-oops-overlay');
    if (!overlay) return;
    overlay.classList.remove('is-visible');
    window.setTimeout(() => {
      overlay.hidden = true;
      resetCardCheckout(true);
      resetCryptoCheckout(true);
      resetWithdrawCheckout(true);
    }, 180);
  }

  function validatePromoCode() {
    if (!selectedDepositMethod().requiresPromo) return true;
    const value = (document.getElementById('promo-input')?.value || '').trim().toUpperCase();
    if (value.length < 3) {
      ui.showToast(ui.t('err_promo_required'), 'err');
      return false;
    }
    return true;
  }

  function resetPromoPreview() {
    promoPreview = null;
    const card = document.getElementById('promo-preview-card');
    const amountGroup = document.getElementById('promo-amount-group');
    if (card) {
      card.hidden = true;
      card.innerHTML = '';
      card.classList.remove('ok', 'err');
    }
    if (amountGroup) amountGroup.hidden = true;
  }

  function promoPercentValue(promo) {
    return Number(promo?.percent !== undefined ? promo.percent : Number(promo?.percent_bps || 0) / 100);
  }

  function renderPromoPreviewCard(result, mode) {
    const card = document.getElementById('promo-preview-card');
    const amountGroup = document.getElementById('promo-amount-group');
    if (!card) return;
    if (!result || result.error) {
      card.hidden = false;
      card.classList.toggle('ok', false);
      card.classList.toggle('err', true);
      card.textContent = ui.t(result?.error || 'err_promo_invalid');
      if (amountGroup && (result?.error === 'err_amount_invalid' || result?.error === 'err_promo_min_deposit')) {
        amountGroup.hidden = false;
      }
      return;
    }
    const promo = result.promo || {};
    const rewardType = promo.reward_type || 'fixed';
    const bonus = Number(result.bonus !== undefined ? result.bonus : Number(result.bonus_cents || 0) / 100);
    const deposit = Number(result.deposit !== undefined ? result.deposit : Number(result.deposit_cents || 0) / 100);
    card.hidden = false;
    card.classList.toggle('ok', mode !== 'success');
    card.classList.toggle('err', false);
    if (rewardType === 'percent') {
      if (amountGroup) amountGroup.hidden = false;
      const maxBonus = Number(promo.max_bonus !== undefined ? promo.max_bonus : Number(promo.max_bonus_cents || 0) / 100);
      const minDeposit = Number(promo.min_deposit !== undefined ? promo.min_deposit : Number(promo.min_deposit_cents || 0) / 100);
      card.innerHTML = `
        <strong>${ui.escapeHTML(promo.code || '')}</strong>
        <span>${ui.escapeHTML(ui.t('cashier_promo_percent_rule', {
          percent: ui.formatNumber(promoPercentValue(promo)),
          min: ui.formatMoney(minDeposit),
          max: ui.formatMoney(maxBonus)
        }))}</span>
        ${deposit ? `<em>${ui.escapeHTML(ui.t('cashier_promo_preview_bonus', { bonus: ui.formatMoney(bonus), deposit: ui.formatMoney(deposit) }))}</em>` : ''}
      `;
      return;
    }
    if (amountGroup) amountGroup.hidden = true;
    card.innerHTML = `
      <strong>${ui.escapeHTML(promo.code || '')}</strong>
      <span>${ui.escapeHTML(ui.t('cashier_promo_fixed_rule', { amount: ui.formatMoney(bonus) }))}</span>
    `;
  }

  async function previewPromoCode() {
    if (promoPreviewLoading || !validatePromoCode()) return;
    promoPreviewLoading = true;
    const button = document.getElementById('promo-preview-btn');
    if (button) button.disabled = true;
    const result = await store.previewPromo(
      (document.getElementById('promo-input')?.value || '').trim().toUpperCase(),
      parseAmount('promo-amount-input')
    );
    promoPreviewLoading = false;
    if (button) button.disabled = false;
    if (result && result.error) {
      if (result.error === 'err_amount_invalid') {
        ui.showToast(ui.t('cashier_promo_amount_required'), 'err');
      } else {
        ui.showToast(ui.t(result.error, { amount: errorAmount(result) }), 'err');
      }
      renderPromoPreviewCard(result);
      return;
    }
    promoPreview = result;
    renderPromoPreviewCard(result);
  }

  function renderMethods() {
    const state = store.getState();
    const deposit = document.getElementById('depositMethods');
    if (deposit) {
      deposit.innerHTML = C.cashier.depositMethods.map(method => `
        <button class="method-btn ${method.id === state.cashier.selectedMethod ? 'selected' : ''}" type="button" data-method="${method.id}">
          <span>${ui.escapeHTML(method.icon)}</span>
          <strong>${ui.escapeHTML(ui.methodLabel(method))}</strong>
        </button>
      `).join('');
    }

    const withdraw = document.getElementById('withdrawMethods');
    if (withdraw) {
      withdraw.innerHTML = C.cashier.withdrawMethods.map(method => `
        <button class="method-btn ${method.id === state.cashier.selectedWithdrawMethod ? 'selected' : ''} ${method.comingSoon ? 'is-coming-soon' : ''}" type="button" data-wmethod="${method.id}" ${method.comingSoon ? 'disabled aria-disabled="true"' : ''}>
          <span>${ui.escapeHTML(method.icon)}</span>
          <strong>${ui.escapeHTML(ui.methodLabel(method))}</strong>
          ${method.comingSoon ? `<small>${ui.escapeHTML(ui.t('cashier_coming_soon'))}</small>` : ''}
        </button>
      `).join('');
    }

    const presets = document.getElementById('presetGrid');
    if (presets) {
      presets.innerHTML = C.cashier.presets.map(value => {
        const hot = value === C.cashier.hotPreset;
        return `
          <button class="preset-btn ${hot ? 'hot' : ''}" type="button" data-amount="${value}">
            ${ui.formatMoney(value)}${hot ? ' ' + ui.t('cashier_hot') : ''}
          </button>
        `;
      }).join('');
    }

    const amountGroup = document.getElementById('deposit-amount-group');
    if (amountGroup) amountGroup.hidden = selectedDepositMethod().requiresPromo;
    const promoFields = document.getElementById('promo-fields');
    if (promoFields) promoFields.hidden = !selectedDepositMethod().requiresPromo;
    if (!selectedDepositMethod().requiresPromo) resetPromoPreview();
    const depositButton = document.getElementById('btn-submit-deposit');
    if (depositButton) {
      const continues = selectedDepositMethod().requiresCard || selectedDepositMethod().requiresCrypto;
      depositButton.textContent = ui.t(continues ? 'cashier_continue' : 'cashier_submit_deposit');
    }
    syncBonusHint();
  }

  function syncBonusHint() {
    const bonusHint = document.querySelector('[data-cashier-bonus-hint]');
    if (!bonusHint) return;
    const mode = store.getState().cashier.mode;
    bonusHint.hidden = mode !== 'deposit' || selectedDepositMethod().requiresPromo;
  }

  function renderSummary() {
    const user = store.getDisplayUser();
    const rules = cashierRules(user);
    const withdrawMode = store.getState().cashier.mode === 'withdraw';
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };
    setText('cashier-balance', ui.formatMoney(user.balance, user.currency));
    setText('cashier-min-label', ui.t(withdrawMode ? 'cashier_min_withdraw' : 'cashier_min_deposit'));
    setText('cashier-max-label', ui.t(withdrawMode ? 'cashier_max_withdraw' : 'cashier_max_deposit'));
    setText('cashier-min-deposit-val', ui.formatMoney(withdrawMode ? rules.withdrawMin : rules.depositMin, user.currency));
    setText('cashier-max-deposit-val', ui.formatMoney(withdrawMode ? rules.withdrawMax : rules.depositMax, user.currency));
    setText('cashier-with-time-val', ui.t('cashier_withdraw_time_value', { hours: rules.withdrawHours }));
    setText('cashier-commission-val', withdrawMode ? rules.commission + '%' : '0%');
    setText('cashier-summary-title', ui.t('cashier_tier_conditions', { tier: rules.tier[0].toUpperCase() + rules.tier.slice(1) }));

    const amountInput = document.getElementById('amount-input');
    if (amountInput) {
      amountInput.setAttribute('placeholder', ui.formatMoney(rules.depositMin, user.currency));
      amountInput.min = String(rules.depositMin);
      amountInput.max = String(rules.depositMax);
    }
    const withdrawInput = document.getElementById('withdraw-input');
    if (withdrawInput) {
      withdrawInput.setAttribute('placeholder', ui.formatMoney(rules.withdrawMin, user.currency));
      withdrawInput.min = String(rules.withdrawMin);
      withdrawInput.max = String(rules.withdrawMax);
    }
    renderWithdrawPreview();

    const tags = document.querySelector('[data-payment-tags]');
    if (tags) {
      ui.renderPaymentTags(tags.parentElement || document);
      tags.querySelectorAll('.pay-tag').forEach(tag => {
        tag.hidden = withdrawMode && tag.textContent.trim().toUpperCase() === 'PROMO';
      });
    }
  }

  function renderWithdrawPreview() {
    const user = store.getDisplayUser();
    const rules = cashierRules(user);
    const amount = Math.max(0, parseAmount('withdraw-input'));
    const fee = amount * rules.commission / 100;
    const payout = Math.max(0, amount - fee);
    const preview = document.getElementById('withdraw-preview');
    if (preview) preview.classList.toggle('has-amount', amount > 0);
    const feeValue = document.getElementById('withdraw-preview-fee');
    const payoutValue = document.getElementById('withdraw-preview-payout');
    if (feeValue) feeValue.textContent = ui.formatMoney(fee, user.currency) + ` (${rules.commission}%)`;
    if (payoutValue) payoutValue.textContent = ui.formatMoney(payout, user.currency);
  }

  function resetSuccess(kind) {
    const main = document.getElementById(kind + '-main');
    const success = document.getElementById(kind + '-success');
    if (main) main.hidden = false;
    if (success) success.classList.remove('show');
  }

  function setMode(mode) {
    const next = mode === 'withdraw' ? 'withdraw' : 'deposit';
    store.setCashierMode(next);
    resetSuccess('deposit');
    resetSuccess('withdraw');
    resetCardCheckout(false);
    resetCryptoCheckout(false);
    resetWithdrawCheckout(false);
    document.querySelectorAll('.cashier-tab').forEach(tab => {
      const active = tab.dataset.mode === next;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    const depositForm = document.getElementById('deposit-form');
    const withdrawForm = document.getElementById('withdraw-form');
    if (depositForm) {
      const active = next === 'deposit';
      depositForm.classList.toggle('active', active);
      depositForm.hidden = !active;
    }
    if (withdrawForm) {
      const active = next === 'withdraw';
      withdrawForm.classList.toggle('active', active);
      withdrawForm.hidden = !active;
    }
    syncBonusHint();
    renderSummary();
    const url = new URL(location.href);
    if (next === 'withdraw') url.searchParams.set('mode', 'withdraw');
    else url.searchParams.delete('mode');
    history.replaceState(null, '', url.toString());
  }

  function showSuccess(kind) {
    const main = document.getElementById(kind + '-main');
    const success = document.getElementById(kind + '-success');
    if (main && success) {
      main.hidden = true;
      success.classList.add('show');
    }
  }

  async function submitDeposit() {
    const method = selectedDepositMethod();
    const amount = method.requiresPromo ? parseAmount('promo-amount-input') || null : parseAmount('amount-input');
    const promoCode = (document.getElementById('promo-input')?.value || '').trim().toUpperCase();
    if (method.requiresCard) {
      openCardCheckout();
      return;
    }
    if (method.requiresCrypto) {
      openCryptoCheckout();
      return;
    }
    if (!validatePromoCode()) return;
    if (method.requiresPromo && promoPreview?.promo?.reward_type === 'percent' && !amount) {
      ui.showToast(ui.t('cashier_promo_amount_required'), 'err');
      document.getElementById('promo-amount-group').hidden = false;
      return;
    }

    const result = await store.deposit(amount, method.id, promoCode);
    if (showStoreError(result)) return;
    ui.showToast(ui.t('toast_deposit_success'));
    showSuccess('deposit');
  }

  async function submitWithdraw() {
    const method = selectedWithdrawMethod();
    if (method.id !== 'kawaui-studio') {
      openWithdrawCheckout();
      return;
    }
    const values = withdrawalAmounts();
    if (!validateWithdrawAmount(values.amount)) return;
    const result = await store.withdraw(values.amount, method.id);
    if (showStoreError(result)) return;
    ui.showToast(ui.t('toast_withdraw_success'));
    showSuccess('withdraw');
  }

  function initFormatting() {
    document.getElementById('card-num')?.addEventListener('input', e => {
      e.target.value = e.target.value.replace(/\D/g, '').slice(0, 19).replace(/(.{4})/g, '$1 ').trim();
    });
    document.getElementById('card-exp')?.addEventListener('input', e => {
      const value = e.target.value.replace(/\D/g, '').slice(0, 4);
      e.target.value = value.replace(/^(\d{2})(\d)/, '$1/$2');
    });
    document.getElementById('card-cvv')?.addEventListener('input', e => {
      e.target.value = e.target.value.replace(/\D/g, '').slice(0, 3);
    });
    document.getElementById('withdraw-card-num')?.addEventListener('input', e => {
      e.target.value = e.target.value.replace(/\D/g, '').slice(0, 19).replace(/(.{4})/g, '$1 ').trim();
    });
    document.getElementById('sbp-phone')?.addEventListener('input', e => {
      const digits = e.target.value.replace(/\D/g, '').slice(0, 11).replace(/^8/, '7');
      const local = digits.replace(/^7/, '');
      const groups = [local.slice(0, 3), local.slice(3, 6), local.slice(6, 8), local.slice(8, 10)].filter(Boolean);
      e.target.value = digits ? `+7 ${groups.join(' ').trim()}` : '';
    });
  }

  function init() {
    if (document.body.dataset.page !== 'deposit') return;
    const initialParams = new URL(location.href).searchParams;
    const initialPromoCode = String(initialParams.get('promo') || '').trim().toUpperCase().replace(/\s+/g, '');
    if (initialParams.get('method') === 'promo' || initialPromoCode) {
      store.setCashierMethod('deposit', 'promo');
    }
    if (initialParams.get('mode') === 'withdraw') setMode('withdraw');
    if (initialParams.get('method') === 'kawaui-studio') {
      store.setCashierMethod('withdraw', 'kawaui-studio');
    }

    document.addEventListener('click', e => {
      const tab = e.target.closest('.cashier-tab');
      if (tab) setMode(tab.dataset.mode);
      const method = e.target.closest('[data-method]');
      if (method) {
        resetCardCheckout(true);
        resetCryptoCheckout(true);
        store.setCashierMethod('deposit', method.dataset.method);
        resetPromoPreview();
        resetSuccess('deposit');
      }
      const wmethod = e.target.closest('[data-wmethod]');
      if (wmethod) {
        resetWithdrawCheckout(true);
        store.setCashierMethod('withdraw', wmethod.dataset.wmethod);
        resetSuccess('withdraw');
      }
      const preset = e.target.closest('.preset-btn[data-amount]');
      if (preset) {
        document.getElementById('amount-input').value = preset.dataset.amount;
        resetSuccess('deposit');
      }
      const reset = e.target.closest('[data-cashier-reset]');
      if (reset) resetSuccess(reset.dataset.cashierReset);
      const rail = e.target.closest('[data-payment-rail]');
      if (rail) setPaymentRail(rail.dataset.paymentRail);
      const cryptoAsset = e.target.closest('[data-crypto-asset]');
      if (cryptoAsset) setCryptoAsset('deposit', cryptoAsset.dataset.cryptoAsset);
      const cryptoNetwork = e.target.closest('[data-crypto-network]');
      if (cryptoNetwork) setCryptoNetwork('deposit', cryptoNetwork.dataset.cryptoNetwork);
      const withdrawCryptoAsset = e.target.closest('[data-withdraw-crypto-asset]');
      if (withdrawCryptoAsset) setCryptoAsset('withdraw', withdrawCryptoAsset.dataset.withdrawCryptoAsset);
      const withdrawCryptoNetwork = e.target.closest('[data-withdraw-crypto-network]');
      if (withdrawCryptoNetwork) setCryptoNetwork('withdraw', withdrawCryptoNetwork.dataset.withdrawCryptoNetwork);
      if (e.target.closest('[data-withdraw-back]')) resetWithdrawCheckout(false);
    });

    document.getElementById('promo-preview-btn')?.addEventListener('click', previewPromoCode);
    document.getElementById('promo-input')?.addEventListener('input', event => {
      const next = event.target.value.toUpperCase().replace(/\s+/g, '');
      if (event.target.value !== next) event.target.value = next;
      resetPromoPreview();
    });
    document.getElementById('promo-amount-input')?.addEventListener('input', () => {
      if (promoPreview?.promo?.reward_type === 'percent') {
        window.clearTimeout(previewPromoCode.timer);
        previewPromoCode.timer = window.setTimeout(previewPromoCode, 350);
      }
    });
    document.getElementById('btn-submit-deposit')?.addEventListener('click', submitDeposit);
    document.getElementById('card-checkout-back')?.addEventListener('click', () => resetCardCheckout(false));
    document.getElementById('card-checkout-confirm')?.addEventListener('click', () => {
      if (!cardCheckoutOpen || !validateCardCheckout()) return;
      showCardOops('deposit');
    });
    document.getElementById('crypto-checkout-back')?.addEventListener('click', () => resetCryptoCheckout(false));
    document.getElementById('crypto-checkout-confirm')?.addEventListener('click', () => {
      if (!cryptoCheckoutOpen || !validateCryptoCheckout('deposit')) return;
      showCardOops('deposit');
    });
    document.getElementById('withdraw-card-confirm')?.addEventListener('click', () => {
      if (withdrawCheckoutOpen !== 'card' || !validateWithdrawCard()) return;
      showCardOops('withdraw');
    });
    document.getElementById('withdraw-crypto-confirm')?.addEventListener('click', () => {
      if (withdrawCheckoutOpen !== 'crypto' || !validateCryptoCheckout('withdraw')) return;
      showCardOops('withdraw');
    });
    document.getElementById('card-oops-close')?.addEventListener('click', closeCardOops);
    document.getElementById('card-oops-overlay')?.addEventListener('click', event => {
      if (event.target === event.currentTarget) closeCardOops();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !document.getElementById('card-oops-overlay')?.hidden) closeCardOops();
    });
    document.getElementById('btn-submit-withdraw')?.addEventListener('click', submitWithdraw);
    document.getElementById('withdraw-input')?.addEventListener('input', renderWithdrawPreview);
    initFormatting();
    store.subscribe(() => {
      renderMethods();
      renderSummary();
    });
    renderMethods();
    renderSummary();
    renderCryptoNetworks('deposit');
    renderCryptoNetworks('withdraw');
    setMode(new URL(location.href).searchParams.get('mode') === 'withdraw' ? 'withdraw' : 'deposit');
    if (initialPromoCode) {
      const promoInput = document.getElementById('promo-input');
      if (promoInput) promoInput.value = initialPromoCode;
      if (store.getState().currentUser) window.setTimeout(previewPromoCode, 0);
    }
  }

  B.cashier = { init };
})(window);
