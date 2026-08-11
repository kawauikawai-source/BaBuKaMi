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
    const right = document.querySelector('.header__right');
    if (!right || document.getElementById('studio-session')) return;
    const control = document.createElement(session ? 'button' : 'a');
    control.id = 'studio-session';
    control.className = 'studio-session';
    if (session) {
      control.type = 'button';
      control.textContent = `${session.user.name || session.user.email} | ${money(session.wallet.balance_cents)}`;
      control.addEventListener('click', async () => {
        await fetch('/auth/logout', { method: 'POST' });
        location.reload();
      });
      prefillIdentity(session.user);
    } else {
      control.href = '/auth/login?next_path=%2F%23appraisal';
      control.textContent = lang() === 'en' ? 'Kawaui ID login' : 'Войти через Kawaui ID';
    }
    right.appendChild(control);
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
  loadSession().then(() => Promise.all([refreshPreview(), loadHistory()]));
})();
