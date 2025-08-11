// script.js — сайт (модалки, auth, профиль, формы, слайдер отзывов)
// Игровая логика вынесена в game.js и здесь отсутствует.

(function(){
'use strict';

// --- КОНФИГ: ключи localStorage ---
const STORAGE_USERS_KEY = 'bibu_users';
const STORAGE_CURRENT_KEY = 'bibu_current';

// DOM refs
const header = document.getElementById('pageHeader');
const main = document.getElementById('mainContent');
const footer = document.getElementById('pageFooter');

// utilities
function loadUsers() { const raw = localStorage.getItem(STORAGE_USERS_KEY); return raw ? JSON.parse(raw) : {}; }
function saveUsers(users) { localStorage.setItem(STORAGE_USERS_KEY, JSON.stringify(users)); }

async function hashPassword(password) {
  const enc = new TextEncoder();
  const data = enc.encode(password);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

function showRegMessage(text, type = 'error') { const el = document.getElementById('regMessage'); if (!el) return; el.textContent = text; el.style.color = (type === 'error') ? 'red' : 'green'; }
function showLoginMessage(text, type = 'error') { const el = document.getElementById('loginMessage'); if (!el) return; el.textContent = text; el.style.color = (type === 'error') ? 'red' : 'green'; }

// Modal/focus utilities
let lastFocused = null;
let activeTrap = null;

function setPageInert(inert) {
    [header, main, footer].forEach(el => {
        if (!el) return;
        try {
            if ('inert' in el) el.inert = inert;
            else if (inert) el.setAttribute('aria-hidden', 'true');
            else el.removeAttribute('aria-hidden');
        } catch(e) {
            if (inert) el.setAttribute('aria-hidden', 'true'); else el.removeAttribute('aria-hidden');
        }
    });
}

function trapFocus(modal) {
    const focusable = Array.from(modal.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])'));
    if (!focusable.length) return () => {};
    let first = focusable[0];
    let last = focusable[focusable.length - 1];
    function handleKey(e) {
        if (e.key === 'Tab') {
            if (e.shiftKey) {
                if (document.activeElement === first) { e.preventDefault(); last.focus(); }
            } else {
                if (document.activeElement === last) { e.preventDefault(); first.focus(); }
            }
        }
        if (e.key === 'Escape') {
            closeModal(modal.id);
        }
    }
    modal.addEventListener('keydown', handleKey);
    return () => modal.removeEventListener('keydown', handleKey);
}

function openModal(id, trigger) {
    const modal = document.getElementById(id);
    if (!modal) return;
    lastFocused = trigger || document.activeElement;
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    setPageInert(true);
    setTimeout(()=>{
        const first = modal.querySelector('input,button,select,textarea,[tabindex]:not([tabindex="-1"])');
        if (first) first.focus();
        if (activeTrap) activeTrap();
        activeTrap = trapFocus(modal);
    }, 150);
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    setPageInert(false);
    if (activeTrap) { try { activeTrap(); } catch(e) {} activeTrap = null; }
    setTimeout(()=>{ if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus(); lastFocused = null; }, 120);
    if (id === 'profileModal') clearProfileMessages();
}

function initModalControls() {
    // openers (elements with data-modal)
    document.querySelectorAll('[data-modal]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const modalId = btn.dataset.modal;
            if (!modalId) return;
            openModal(modalId, btn);
        });
    });

    // closers (elements with data-close)
    document.querySelectorAll('[data-close]').forEach(btn => {
        const id = btn.dataset.close;
        if (!id) return;
        btn.addEventListener('click', (e) => {
            if (e && typeof e.preventDefault === 'function') e.preventDefault();
            closeModal(id);
        });
    });

    // click outside modal-content closes
    window.addEventListener('click', (e) => { document.querySelectorAll('.modal.show').forEach(modal => { if (e.target === modal) closeModal(modal.id); }); });

    // Escape closes active modals
    window.addEventListener('keydown', (e) => { if (e.key === 'Escape') { document.querySelectorAll('.modal.show').forEach(m => closeModal(m.id)); } });
}

// AUTH & PROFILE LOGIC
async function register() {
    const nickEl = document.getElementById("regNick");
    const emailEl = document.getElementById("regEmail");
    const passEl = document.getElementById("regPass");
    if (!nickEl || !emailEl || !passEl) return;
    const nick = nickEl.value.trim(); const email = emailEl.value.trim(); const pass = passEl.value;
    showRegMessage('');
    if (!nick || !email || !pass) { showRegMessage('Пожалуйста, заполните все поля.', 'error'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { showRegMessage('Пожалуйста, введите корректный email.', 'error'); return; }
    if (pass.length < 6) { showRegMessage('Пароль должен быть минимум 6 символов.', 'error'); return; }
    const users = loadUsers(); if (users[nick]) { showRegMessage('Пользователь с таким ником уже существует.', 'error'); return; }
    const passHash = await hashPassword(pass);
    users[nick] = { email: email, passHash: passHash, created: Date.now() };
    saveUsers(users);
    showRegMessage('Регистрация успешна! Теперь вы автоматически войдёте.', 'success');
    localStorage.setItem(STORAGE_CURRENT_KEY, nick); updateUIForLoggedIn(nick);
    setTimeout(() => closeModal('registerModal'), 900);
}

async function login() {
    const nickEl = document.getElementById("loginNick");
    const passEl = document.getElementById("loginPass");
    if (!nickEl || !passEl) return;
    const nick = nickEl.value.trim(); const pass = passEl.value;
    showLoginMessage('');
    if (!nick || !pass) { showLoginMessage('Пожалуйста, заполните все поля.', 'error'); return; }
    const users = loadUsers(); const user = users[nick];
    if (!user) { showLoginMessage('Пользователь не найден.', 'error'); return; }
    const passHash = await hashPassword(pass);
    if (passHash !== user.passHash) { showLoginMessage('Неверный пароль.', 'error'); return; }
    localStorage.setItem(STORAGE_CURRENT_KEY, nick); updateUIForLoggedIn(nick); showLoginMessage('Вход успешен!', 'success');
    setTimeout(() => closeModal('loginModal'), 700);
}

function logout() { localStorage.removeItem(STORAGE_CURRENT_KEY); updateUIForLoggedOut(); closeModal('profileModal'); }

function updateUIForLoggedIn(nick) {
    const userArea = document.getElementById('userArea'); if (!userArea) return;
    userArea.innerHTML = '';
    const span = document.createElement('span'); span.textContent = `Привет, ${nick}`;
    const btnProfile = document.createElement('button'); btnProfile.textContent = 'Профиль'; btnProfile.style.padding = '6px 8px';
    btnProfile.addEventListener('click', () => openModal('profileModal', btnProfile)); btnProfile.setAttribute('aria-label', 'Открыть профиль');
    const btn = document.createElement('button'); btn.textContent = 'Выйти'; btn.addEventListener('click', logout); btn.setAttribute('aria-label', 'Выйти из аккаунта');
    userArea.appendChild(span); userArea.appendChild(btnProfile); userArea.appendChild(btn);
    const nav = document.getElementById('mainNav'); if (nav) nav.style.display = 'none';
}
function updateUIForLoggedOut() { const userArea = document.getElementById('userArea'); if (userArea) userArea.innerHTML = ''; const nav = document.getElementById('mainNav'); if (nav) nav.style.display = 'flex'; }

function populateProfilePane() {
    const nick = localStorage.getItem(STORAGE_CURRENT_KEY); const users = loadUsers(); const user = users[nick];
    const accountInfo = document.getElementById('accountInfo'); if (!accountInfo) return;
    if (user) { accountInfo.textContent = `Ник: ${nick}\u00A0 • \u00A0 Почта: ${user.email || '(не указана)'} `; } else { accountInfo.textContent = 'Пользователь не найден.'; }
    ['newEmail','emailPass','curPass','newPass','newPass2','delPass'].forEach(id=>{ const el = document.getElementById(id); if (el) el.value = ''; });
    const chk = document.getElementById('confirmDelete'); if (chk) chk.checked = false;
    switchProfileTab('account');
}
function clearProfileMessages() { ['emailMessage','passMessage','delMessage'].forEach(id=>{ const el=document.getElementById(id); if (el) el.textContent=''; }); }

async function changeEmail() {
    clearProfileMessages();
    const nick = localStorage.getItem(STORAGE_CURRENT_KEY); if (!nick) { const el=document.getElementById('emailMessage'); if (el) el.textContent='Сначала войдите в аккаунт.'; return; }
    const users = loadUsers(); const user = users[nick];
    const newEmailEl = document.getElementById('newEmail'); const passEl = document.getElementById('emailPass');
    if (!newEmailEl || !passEl) return;
    const newEmail = newEmailEl.value.trim(); const pass = passEl.value;
    if (!newEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail)) { document.getElementById('emailMessage').textContent = 'Введите корректный email.'; return; }
    if (!pass) { document.getElementById('emailMessage').textContent = 'Введите текущий пароль.'; return; }
    const passHash = await hashPassword(pass);
    if (passHash !== user.passHash) { document.getElementById('emailMessage').textContent = 'Неверный пароль.'; return; }
    user.email = newEmail; users[nick] = user; saveUsers(users);
    const el = document.getElementById('emailMessage'); if (el) { el.style.color='green'; el.textContent='Почта успешно обновлена.'; }
    populateProfilePane();
}

async function changePassword() {
    clearProfileMessages();
    const nick = localStorage.getItem(STORAGE_CURRENT_KEY); if (!nick) { document.getElementById('passMessage').textContent = 'Сначала войдите в аккаунт.'; return; }
    const users = loadUsers(); const user = users[nick];
    const cur = (document.getElementById('curPass')||{}).value || ''; const np = (document.getElementById('newPass')||{}).value || ''; const np2 = (document.getElementById('newPass2')||{}).value || '';
    if (!cur || !np || !np2) { document.getElementById('passMessage').textContent = 'Заполните все поля.'; return; }
    if (np.length < 6) { document.getElementById('passMessage').textContent = 'Новый пароль должен быть минимум 6 символов.'; return; }
    if (np !== np2) { document.getElementById('passMessage').textContent = 'Пароли не совпадают.'; return; }
    const curHash = await hashPassword(cur); if (curHash !== user.passHash) { document.getElementById('passMessage').textContent = 'Неверный текущий пароль.'; return; }
    const newHash = await hashPassword(np); user.passHash = newHash; users[nick] = user; saveUsers(users);
    const el = document.getElementById('passMessage'); if (el) { el.style.color='green'; el.textContent='Пароль успешно обновлён.'; }
    ['curPass','newPass','newPass2'].forEach(id=>{ const e=document.getElementById(id); if (e) e.value=''; });
}

async function deleteAccount() {
    clearProfileMessages();
    const nick = localStorage.getItem(STORAGE_CURRENT_KEY); if (!nick) { document.getElementById('delMessage').textContent = 'Сначала войдите в аккаунт.'; return; }
    const users = loadUsers(); const user = users[nick];
    const pass = (document.getElementById('delPass')||{}).value || ''; const confirmed = (document.getElementById('confirmDelete')||{}).checked || false;
    if (!confirmed) { document.getElementById('delMessage').textContent = 'Пожалуйста подтвердите удаление.'; return; }
    if (!pass) { document.getElementById('delMessage').textContent = 'Введите пароль для подтверждения.'; return; }
    const passHash = await hashPassword(pass);
    if (passHash !== user.passHash) { document.getElementById('delMessage').textContent = 'Неверный пароль.'; return; }
    delete users[nick]; saveUsers(users); localStorage.removeItem(STORAGE_CURRENT_KEY);
    const el=document.getElementById('delMessage'); if (el) { el.style.color='green'; el.textContent='Аккаунт удалён.'; }
    setTimeout(()=>{ closeModal('profileModal'); updateUIForLoggedOut(); }, 900);
}

// slider basics (simple)
let reviews = 0; let currentIndex = 0; let reviewsTrack = null;
function updateSlider() { if (!reviewsTrack) return; reviewsTrack.style.transform = `translateX(-${currentIndex * 100}%)`; }
function nextReview() { if (reviews === 0) return; currentIndex = (currentIndex + 1) % reviews; updateSlider(); }
function prevReview() { if (reviews === 0) return; currentIndex = (currentIndex - 1 + reviews) % reviews; updateSlider(); }

// tabs
function switchProfileTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b=>{ b.classList.remove('active'); b.setAttribute('aria-selected','false'); });
    document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
    const btn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
    if (btn) { btn.classList.add('active'); btn.setAttribute('aria-selected','true'); }
    const pane = document.getElementById(tab + 'Pane');
    if (pane) pane.classList.add('active');
    setTimeout(() => { const pane = document.querySelector(`#profileModal .tab-pane.active`); if (!pane) return; const first = pane.querySelector('input, button, [tabindex]'); if (first) first.focus(); }, 220);
}

// password strength (very simple)
function assessPassword(str) {
    let score = 0; if (!str) return {score, text: ''};
    if (str.length >= 6) score++; if (/[0-9]/.test(str)) score++; if (/[A-Z]/.test(str)) score++; if (/[^A-Za-z0-9]/.test(str)) score++;
    const texts = ['Очень слабый','Слабый','Средний','Хороший','Сильный'];
    return {score, text: texts[score] || ''};
}

// event wiring
document.addEventListener('DOMContentLoaded', () => {
    // modal controls
    initModalControls();

    // Make feature articles accessible via keyboard (Enter / Space) and clickable to open modals
    document.querySelectorAll('.feature[role="button"]').forEach(el => {
      el.addEventListener('click', () => {
        const modalId = el.dataset.modal;
        if (modalId) openModal(modalId, el);
      });
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          const modalId = el.dataset.modal;
          if (modalId) openModal(modalId, el);
          else el.click();
        }
      });
    });

    // login/register buttons
    const loginBtn = document.getElementById('loginBtn'); if (loginBtn) loginBtn.addEventListener('click', login);
    const registerBtn = document.getElementById('registerBtn'); if (registerBtn) registerBtn.addEventListener('click', register);

    // profile actions
    const changeEmailBtn = document.getElementById('changeEmailBtn'); if (changeEmailBtn) changeEmailBtn.addEventListener('click', changeEmail);
    const changePassBtn = document.getElementById('changePassBtn'); if (changePassBtn) changePassBtn.addEventListener('click', changePassword);
    const deleteAccountBtn = document.getElementById('deleteAccountBtn'); if (deleteAccountBtn) deleteAccountBtn.addEventListener('click', deleteAccount);

    // tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => switchProfileTab(btn.dataset.tab)));

    // password strength
    const regPass = document.getElementById('regPass'); const passStrength = document.getElementById('passStrength');
    if (regPass && passStrength) {
        regPass.addEventListener('input', (e) => { const a = assessPassword(e.target.value); passStrength.textContent = a.text; passStrength.setAttribute('aria-hidden', a.text ? 'false' : 'true'); });
    }

    // slider init + autoplay + pause on hover + keyboard
    reviewsTrack = document.getElementById('reviewsTrack'); if (reviewsTrack) { reviews = reviewsTrack.children.length; }
    const nextBtn = document.getElementById('nextReviewBtn'); if (nextBtn) nextBtn.addEventListener('click', () => { nextReview(); stopAutoplay(); startAutoplay(); });
    const prevBtn = document.getElementById('prevReviewBtn'); if (prevBtn) prevBtn.addEventListener('click', () => { prevReview(); stopAutoplay(); startAutoplay(); });

    (function sliderAutoplay(){
      const track = reviewsTrack;
      if (!track) return;
      let children = reviews;
      if (!children) return;
      let idx = 0, timer = null;
      const next = () => { idx = (idx + 1) % children; track.style.transform = `translateX(-${idx * 100}%)`; };
      const start = () => { if (timer) clearInterval(timer); timer = setInterval(next, 4200); };
      const stop = () => { if (timer) clearInterval(timer); timer = null; };
      window.startAutoplay = start;
      window.stopAutoplay = stop;
      start();
      const sliderWrap = track.closest('.reviews-slider');
      if (sliderWrap) {
        sliderWrap.addEventListener('mouseenter', stop);
        sliderWrap.addEventListener('mouseleave', start);
      }
      window.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight') { stop(); next(); start(); }
        if (e.key === 'ArrowLeft') { stop(); idx = (idx -1 + children) % children; track.style.transform = `translateX(-${idx * 100}%)`; start(); }
      });
    })();

    // contact form handling (modal)
    const contactForm = document.getElementById('contactForm');
    if (contactForm) {
        contactForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var name = (document.getElementById('contactName') && document.getElementById('contactName').value || '').trim();
            var email = (document.getElementById('contactEmail') && document.getElementById('contactEmail').value || '').trim();
            var text = (document.getElementById('contactMessage') && document.getElementById('contactMessage').value || '').trim();
            var msgEl = document.getElementById('contactMessageBox');
            if (msgEl) { msgEl.style.display = 'none'; msgEl.textContent = ''; msgEl.className = 'msg'; }
            if (!name || !email || !text) {
                if (msgEl) { msgEl.textContent = 'Пожалуйста, заполните все поля.'; msgEl.classList.add('msg--error'); msgEl.style.display = 'block'; }
                return;
            }
            if (!(email.indexOf('@') > -1 && email.indexOf('.') > -1)) {
                if (msgEl) { msgEl.textContent = 'Пожалуйста, введите корректный email.'; msgEl.classList.add('msg--error'); msgEl.style.display = 'block'; }
                return;
            }
            if (msgEl) { msgEl.textContent = 'Отправка...'; msgEl.style.display = 'block'; }
            // mock send — замените на fetch() к реальному API
            setTimeout(function() {
                if (msgEl) { msgEl.textContent = 'Спасибо за ваше сообщение! Мы свяжемся с вами в ближайшее время.'; msgEl.classList.remove('msg--error'); msgEl.classList.add('msg--success'); msgEl.style.display = 'block'; }
                contactForm.reset();
                setTimeout(function(){ closeModal('contactModal'); }, 1200);
            }, 800);
        });
    }

    // Bank form (demo) handling — no real submissions
    const bankForm = document.getElementById('bankForm');
    if (bankForm) {
      bankForm.addEventListener('submit', function (e) {
        e.preventDefault();
        const msgEl = document.getElementById('bankMessage');
        if (msgEl) { msgEl.style.display = 'none'; msgEl.textContent = ''; }
        const name = (document.getElementById('cardName')||{}).value.trim();
        const number = (document.getElementById('cardNumber')||{}).value.replace(/\s/g,'');
        const exp = (document.getElementById('cardExp')||{}).value.trim();
        const cvc = (document.getElementById('cardCvc')||{}).value.trim();
        const agree = (document.getElementById('agreeMock')||{}).checked;

        if (!name || !number || !exp || !cvc || !agree) {
          if (msgEl) { msgEl.textContent = 'Пожалуйста, заполните все поля и подтвердите, что это демо.'; msgEl.className='msg msg--error'; msgEl.style.display='block'; }
          return;
        }
        if (!/^\d{12,19}$/.test(number)) {
          if (msgEl) { msgEl.textContent = 'Проверьте номер карты.'; msgEl.className='msg msg--error'; msgEl.style.display='block'; }
          return;
        }
        if (!/^\d{3,4}$/.test(cvc)) {
          if (msgEl) { msgEl.textContent = 'Проверьте CVC.'; msgEl.className='msg msg--error'; msgEl.style.display='block'; }
          return;
        }

        if (msgEl) { msgEl.textContent = 'Обработка (демо)...'; msgEl.className='msg'; msgEl.style.display='block'; }
        setTimeout(() => {
          if (msgEl) { msgEl.textContent = 'Спасибо! Демонстрационный платёж обработан.'; msgEl.className='msg msg--success'; msgEl.style.display='block'; }
          bankForm.reset();
          setTimeout(()=> closeModal('bankModal'), 900);
        }, 900);
      });
    }

    // restore login state
    const current = localStorage.getItem(STORAGE_CURRENT_KEY); if (current) updateUIForLoggedIn(current); else updateUIForLoggedOut();
});
})();