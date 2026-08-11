(function (global) {
  'use strict';
  const B = global.Bambiku = global.Bambiku || {};

  function money(cents) {
    const lang = B.store.getState().lang === 'en' ? 'en-IE' : 'ru-RU';
    return new Intl.NumberFormat(lang, { style: 'currency', currency: 'EUR' }).format(Number(cents || 0) / 100);
  }

  function operationLabel(item) {
    const en = B.store.getState().lang === 'en';
    if (item.type === 'soul_sale') return en ? 'Soul sale' : 'Продажа души';
    if (item.type === 'casino_transfer') return en ? 'Casino transfer' : 'Перевод из Casino';
    if (item.type === 'casino_deposit') return en ? 'Transfer to Casino' : 'Перевод в Casino';
    return item.type;
  }

  function statusLabel(status) {
    const en = B.store.getState().lang === 'en';
    return ({
      pending: en ? 'Pending' : 'Ожидает',
      completed: en ? 'Completed' : 'Завершено',
      rejected: en ? 'Rejected' : 'Отклонено'
    })[status] || status;
  }

  function renderHistory(items) {
    const root = document.getElementById('studioWalletHistory');
    if (!root) return;
    if (!items.length) {
      root.innerHTML = `<p class="studio-wallet-empty">${B.store.getState().lang === 'en' ? 'No Studio operations yet.' : 'Операций Studio пока нет.'}</p>`;
      return;
    }
    root.innerHTML = items.map(item => `
      <div class="studio-wallet-row">
        <span><b>${operationLabel(item)}</b><small>${new Date(item.created_at).toLocaleString()}</small></span>
        <span class="studio-wallet-row-result"><small class="studio-wallet-status ${item.status}">${statusLabel(item.status)}</small><strong class="${item.status}">${item.status === 'completed' && item.net_cents > 0 ? '+' : ''}${money(item.net_cents)}</strong></span>
      </div>`).join('');
  }

  function renderSignedOut(balance, note) {
    balance.textContent = 'Kawaui ID';
    note.innerHTML = `<a href="../index.html?auth=login&next=${encodeURIComponent(location.pathname)}">${B.store.getState().lang === 'en' ? 'Sign in to open Studio wallet' : 'Войдите, чтобы открыть Studio wallet'}</a>`;
    renderHistory([]);
  }

  async function initWallet() {
    const balance = document.getElementById('studioWalletBalance');
    const note = document.getElementById('studioWalletNote');
    const user = B.store.getState().currentUser;
    if (!user) {
      renderSignedOut(balance, note);
      return;
    }
    try {
      const data = await B.store.getStudioWallet();
      balance.textContent = money(data.wallet.balance_cents);
      note.textContent = B.store.getState().lang === 'en' ? 'Separate ecosystem balance · EUR' : 'Отдельный баланс экосистемы · EUR';
      renderHistory(data.recent_transactions || []);
    } catch (_) {
      if (!B.store.getState().currentUser) {
        renderSignedOut(balance, note);
        return;
      }
      balance.textContent = '—';
      note.textContent = B.store.getState().lang === 'en' ? 'Studio wallet is temporarily unavailable.' : 'Studio wallet временно недоступен.';
      setTimeout(() => {
        if (!B.store.getState().currentUser) renderSignedOut(balance, note);
      }, 100);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const world = document.getElementById('bukamikuWorld');
    if (world) {
      try {
        const catalog = await B.store.getStudioCatalog();
        const project = (catalog.projects || []).find(item => item.id === 'bukamiku');
        if (project && project.url) world.href = project.url;
      } catch (_) {
        // The local href remains a safe fallback while the central service wakes up.
      }
    }
    await B.store.restoreSession();
    initWallet();
    B.store.subscribe((next, previous) => {
      if (next.lang !== previous.lang || next.currentUser !== previous.currentUser) initWallet();
    });
  });
})(window);
