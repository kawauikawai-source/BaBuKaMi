(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const store = B.store;
  const ui = B.ui;
  let initialized = false;
  let registerStep = 1;

  function validateEmail(email) {
    const key = store.validateEmail(email);
    return key ? ui.t(key) : null;
  }

  function validatePassword(password) {
    const key = store.validatePassword(password);
    return key ? ui.t(key) : null;
  }

  function validateName(name) {
    const key = store.validateName(name);
    return key ? ui.t(key) : null;
  }

  function showFieldError(input, error, message) {
    if (!input || !error) return !message;
    input.classList.toggle('error', Boolean(message));
    input.setAttribute('aria-invalid', message ? 'true' : 'false');
    input.setAttribute('aria-describedby', error.id);
    error.textContent = message || '';
    error.classList.toggle('visible', Boolean(message));
    return !message;
  }

  function initRealtimeValidation(inputId, errorId) {
    const input = document.getElementById(inputId);
    const error = document.getElementById(errorId);
    if (!input || !error) return;
    input.addEventListener('blur', () => showFieldError(input, error, validateEmail(input.value)));
    input.addEventListener('input', () => {
      if (input.classList.contains('error')) showFieldError(input, error, validateEmail(input.value));
    });
  }

  function firstName(user) {
    return String(user?.name || '').split(' ')[0] || '';
  }

  function setSubmitBusy(form, busy) {
    const submit = form?.querySelector('[type="submit"]');
    if (!submit) return;
    submit.disabled = Boolean(busy);
    form.setAttribute('aria-busy', busy ? 'true' : 'false');
  }

  function field(id) {
    return document.getElementById(id);
  }

  function requiredMessage(input, error, key) {
    return showFieldError(input, error, String(input?.value || '').trim() ? '' : ui.t(key));
  }

  function ageFromDate(value) {
    const born = new Date(value + 'T00:00:00');
    if (!value || Number.isNaN(born.getTime())) return -1;
    const today = new Date();
    let age = today.getFullYear() - born.getFullYear();
    const beforeBirthday = today.getMonth() < born.getMonth() ||
      (today.getMonth() === born.getMonth() && today.getDate() < born.getDate());
    if (beforeBirthday) age -= 1;
    return age;
  }

  function validateRegisterStep(step) {
    if (step === 1) {
      const first = field('regFirstName');
      const last = field('regLastName');
      const email = field('regEmail');
      const pass = field('regPass');
      const firstOk = requiredMessage(first, field('regFirstNameErr'), 'err_first_name_empty');
      const lastOk = requiredMessage(last, field('regLastNameErr'), 'err_last_name_empty');
      const emailOk = showFieldError(email, field('regEmailErr'), validateEmail(email.value));
      const passOk = showFieldError(pass, field('regPassErr'), validatePassword(pass.value));
      return firstOk && lastOk && emailOk && passOk;
    }
    if (step === 2) {
      const dob = field('regDob');
      const country = field('regCountry');
      const age = ageFromDate(dob?.value || '');
      const dobMessage = age < 0 ? ui.t('err_dob_required') : age < 18 ? ui.t('err_dob_underage') : '';
      const dobOk = showFieldError(dob, field('regDobErr'), dobMessage);
      const countryOk = requiredMessage(country, field('regCountryErr'), 'err_country_required');
      return dobOk && countryOk;
    }
    return true;
  }

  function updateRegisterReview() {
    const phone = String(field('regPhone')?.value || '').trim();
    const kyc = Boolean(field('regKycOptIn')?.checked);
    ui.setText('regReviewName', [field('regFirstName')?.value, field('regLastName')?.value].filter(Boolean).join(' ').trim());
    ui.setText('regReviewEmail', field('regEmail')?.value || '-');
    ui.setText('regReviewDob', field('regDob')?.value || '-');
    ui.setText('regReviewOptional', [phone || ui.t('register_phone_skipped'), ui.t(kyc ? 'register_kyc_selected' : 'register_kyc_skipped')].join(' · '));
  }

  function setRegisterStep(nextStep) {
    registerStep = Math.max(1, Math.min(4, Number(nextStep) || 1));
    document.querySelectorAll('[data-register-step]').forEach(panel => {
      const active = Number(panel.dataset.registerStep) === registerStep;
      panel.hidden = !active;
      panel.classList.toggle('active', active);
    });
    document.querySelectorAll('[data-register-jump]').forEach(button => {
      const step = Number(button.dataset.registerJump);
      button.classList.toggle('active', step === registerStep);
      button.classList.toggle('complete', step < registerStep);
      button.disabled = step > registerStep;
    });
    const back = document.querySelector('[data-register-back]');
    const next = document.querySelector('[data-register-next]');
    const submit = document.querySelector('[data-register-submit]');
    if (back) back.hidden = registerStep === 1;
    if (next) next.hidden = registerStep === 4;
    if (submit) submit.hidden = registerStep !== 4;
    if (registerStep === 4) updateRegisterReview();
    document.querySelector(`[data-register-step="${registerStep}"] input`)?.focus();
  }

  async function handleLogin(event) {
    event.preventDefault();
    const form = event.target;
    const email = document.getElementById('loginEmail');
    const pass = document.getElementById('loginPass');
    const emailErr = document.getElementById('loginEmailErr');
    const passErr = document.getElementById('loginPassErr');

    const emailOk = showFieldError(email, emailErr, validateEmail(email.value));
    const passOk = showFieldError(pass, passErr, validatePassword(pass.value));
    if (!emailOk || !passOk) return;

    setSubmitBusy(form, true);
    const result = await store.login(email.value, pass.value);
    setSubmitBusy(form, false);
    if (result.error === 'err_user_not_found') {
      showFieldError(email, emailErr, ui.t(result.error));
      return;
    }
    if (result.error === 'err_wrong_password') {
      showFieldError(pass, passErr, ui.t(result.error));
      return;
    }

    if (result.error) {
      ui.showToast(ui.t(result.error), 'err');
      return;
    }
    ui.showToast(ui.t('toast_login', { name: firstName(result.user) }));
    ui.closeModal();
    form.reset();
    ui.redirectAfterAuth?.();
  }

  async function handleRegister(event) {
    event.preventDefault();
    const form = event.target;
    if (registerStep < 4) {
      if (validateRegisterStep(registerStep)) setRegisterStep(registerStep + 1);
      return;
    }
    if (![1, 2].every(validateRegisterStep)) {
      setRegisterStep(validateRegisterStep(1) ? 2 : 1);
      return;
    }

    setSubmitBusy(form, true);
    const result = await store.register({
      firstName: field('regFirstName').value,
      lastName: field('regLastName').value,
      email: field('regEmail').value,
      password: field('regPass').value,
      dob: field('regDob').value,
      country: field('regCountry').value,
      phone: field('regPhone').value,
      kycOptIn: field('regKycOptIn').checked
    });
    setSubmitBusy(form, false);
    if (result.error) {
      if (result.error === 'err_api_unavailable' || result.error === 'err_auth_required' || result.error === 'err_admin_required') {
        ui.showToast(ui.t(result.error), 'err');
        return;
      }
      const target = result.error === 'err_name_empty' ? [field('regFirstName'), field('regFirstNameErr')] : result.error.startsWith('err_pass') ? [field('regPass'), field('regPassErr')] : [field('regEmail'), field('regEmailErr')];
      showFieldError(target[0], target[1], ui.t(result.error));
      return;
    }

    ui.showToast(ui.t('toast_welcome'));
    ui.closeModal();
    form.reset();
    setRegisterStep(1);
    ui.redirectAfterAuth?.();
  }

  function init() {
    if (initialized) return;
    initialized = true;
    document.getElementById('loginForm')?.addEventListener('submit', handleLogin);
    document.getElementById('registerForm')?.addEventListener('submit', handleRegister);
    document.querySelector('[data-register-next]')?.addEventListener('click', () => {
      if (validateRegisterStep(registerStep)) setRegisterStep(registerStep + 1);
    });
    document.querySelector('[data-register-back]')?.addEventListener('click', () => setRegisterStep(registerStep - 1));
    document.querySelectorAll('[data-register-jump]').forEach(button => {
      button.addEventListener('click', () => {
        const target = Number(button.dataset.registerJump);
        if (target < registerStep) setRegisterStep(target);
      });
    });
    document.querySelector('.m-tab[data-tab="register"]')?.addEventListener('click', () => setRegisterStep(1));
    const maxDob = new Date();
    maxDob.setFullYear(maxDob.getFullYear() - 18);
    if (field('regDob')) field('regDob').max = maxDob.toISOString().slice(0, 10);
    initRealtimeValidation('loginEmail', 'loginEmailErr');
    initRealtimeValidation('regEmail', 'regEmailErr');
    setRegisterStep(1);
  }

  B.auth = { init };
})(window);
