(function () {
  'use strict';

  const form = document.getElementById('appraisal-form');
  const result = document.getElementById('appraisal-value');
  const ticker = document.getElementById('soul-rate');
  let session = null;
  let previewTimer = 0;

  function ageFromBirthdate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const today = new Date();
    let age = today.getFullYear() - date.getFullYear();
    if (today.getMonth() < date.getMonth() || (today.getMonth() === date.getMonth() && today.getDate() < date.getDate())) age -= 1;
    return age >= 18 ? String(age) : '';
  }

  function prefillIdentity(user) {
    if (!form || !user) return;
    const values = {
      firstName: user.first_name,
      lastName: user.last_name,
      email: user.email,
      age: ageFromBirthdate(user.dob),
      country: user.country,
    };
    Object.entries(values).forEach(([name, value]) => {
      const field = form.elements.namedItem(name);
      if (field && value) field.value = value;
    });
  }

  async function loadHistory() {
    if (!session) return;
    const root = document.getElementById('studio-sales');
    if (!root) return;
    try {
      const items = await api('/api/appraisals');
      const recent = items.slice(0, 3);
      root.hidden = !recent.length;
      root.innerHTML = recent.map(item => `<div class="studio-sale"><span>${lang() === 'en' ? 'Sale' : 'Продажа'} #${item.sale_number}</span><strong>${money(item.payout_cents)}</strong></div>`).join('');
    } catch (_) {
      root.hidden = true;
    }
  }

  function lang() {
    return document.documentElement.lang === 'en' ? 'en' : 'ru';
  }

  function money(cents) {
    return `${(Number(cents || 0) / 100).toLocaleString(lang() === 'en' ? 'en-IE' : 'ru-RU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} EUR`;
  }

  function answers() {
    const data = new FormData(form);
    return {
      fatigue: data.get('fatigue') || 'tired',
      debt: data.get('debt') || 'none',
      compromise: data.get('compromise') || 'minor',
    };
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw Object.assign(new Error(payload?.detail?.code || 'request_failed'), { status: response.status });
    }
    return payload;
  }

  async function loadSession() {
    try {
      session = await api('/api/session');
    } catch (_) {
      session = null;
    }
    const gate = document.getElementById('appraisal-access');
    document.body.classList.toggle('is-authenticated', Boolean(session));
    document.body.classList.toggle('is-guest', !session);
    if (form) form.hidden = !session;
    if (gate) gate.hidden = Boolean(session);
    if (session) {
      prefillIdentity(session.user);
    }
    renderHeroAction();
    renderAccessCopy();
  }

  function renderHeroAction() {
    const heroAction = document.getElementById('hero-appraisal-action');
    if (!heroAction) return;
    heroAction.href = session ? '#appraisal' : '/auth/login?next_path=%2F%23appraisal';
    heroAction.textContent = session
      ? (lang() === 'en' ? 'Appraise soul' : 'Оценить душу')
      : (lang() === 'en' ? 'Sign in with Kawaui ID' : 'Войти через Kawaui ID');
  }

  function renderAccessCopy() {
    const gate = document.getElementById('appraisal-access');
    if (!gate || gate.hidden) return;
    const en = lang() === 'en';
    const head = gate.querySelector('.appraisal-access__head');
    const steps = gate.querySelector('.appraisal-access__steps');
    const action = gate.querySelector('.appraisal-access__action');
    if (head) head.innerHTML = en
      ? '<span class="appraisal-access__index">KAWAUI ID // REQUIRED</span><h3>Identify yourself first</h3><p>Rates, agreement and FAQ are public. Valuation and payout require one Kawaui Studio account.</p>'
      : '<span class="appraisal-access__index">KAWAUI ID // ТРЕБУЕТСЯ</span><h3>Сначала представьтесь системе</h3><p>Курс, договор и ответы доступны всем. Для оценки и выплаты нужен единый аккаунт Kawaui Studio.</p>';
    if (steps) steps.innerHTML = en
      ? '<div><b>01</b><span><strong>Kawaui ID</strong><small>Register or sign in</small></span></div><div><b>02</b><span><strong>Valuation</strong><small>90-second application</small></span></div><div><b>03</b><span><strong>Studio Wallet</strong><small>Payout after signing</small></span></div>'
      : '<div><b>01</b><span><strong>Kawaui ID</strong><small>Регистрация или вход</small></span></div><div><b>02</b><span><strong>Оценка</strong><small>90 секунд на анкету</small></span></div><div><b>03</b><span><strong>Studio Wallet</strong><small>Выплата после договора</small></span></div>';
    if (action) action.textContent = en ? 'Create Kawaui ID or sign in' : 'Создать Kawaui ID или войти';
  }

  async function refreshRate() {
    try {
      const data = await api('/api/soul-rate');
      ticker.textContent = `${money(data.rate_cents)} / шт.`;
    } catch (_) {
      // The public page remains usable while the central service wakes up.
    }
  }

  async function refreshPreview() {
    if (!session || !form) return;
    try {
      const data = await api('/api/appraisals/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(answers()),
      });
      result.textContent = money(data.payout_cents);
      result.dataset.sale = String(data.next_sale_number);
    } catch (_) {
      result.textContent = lang() === 'en' ? 'Valuation unavailable' : 'Оценка временно недоступна';
    }
  }

  window.submitStudioAppraisal = async function submitStudioAppraisal() {
    if (!session) {
      location.href = '/auth/login?next_path=%2F%23appraisal';
      return;
    }
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const data = await api('/api/appraisals', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': crypto.randomUUID(),
        },
        body: JSON.stringify(answers()),
      });
      result.textContent = money(data.appraisal.payout_cents);
      session.wallet = data.wallet;
      alert(lang() === 'en'
        ? `Contract signed. ${money(data.appraisal.payout_cents)} credited to Studio.`
        : `Договор подписан. ${money(data.appraisal.payout_cents)} зачислено в Studio.`);
      location.reload();
    } catch (error) {
      alert(error.message === 'err_soul_sale_limit'
        ? (lang() === 'en' ? 'A soul may only be sold three times.' : 'Душу можно продать только три раза.')
        : error.message);
    } finally {
      submit.disabled = false;
    }
  };

  if (form) {
    form.addEventListener('input', () => {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(refreshPreview, 180);
    });
    form.addEventListener('change', () => {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(refreshPreview, 80);
    });
  }
  refreshRate();
  document.addEventListener('bukamiku:language', () => {
    renderHeroAction();
    renderAccessCopy();
  });
  loadSession().then(() => Promise.all([refreshPreview(), loadHistory()]));
})();
