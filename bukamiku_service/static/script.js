/**
 * BuKaMiKu — фронтенд-логика
 * -----------------------------------------------------------
 * Файл разбит на независимые модули-функции, каждая инициализируется
 * в конце файла. При росте проекта — выносить в отдельные файлы
 * (ticker.js, appraisal.js) и импортировать как ES-модули.
 */

/* =============================================================
   1. ТИКЕР КУРСА ДУШИ (header)
   Сейчас — рандомная имитация "живого курса".
   В реальной интеграции: заменить generateFakeRate() на fetch
   к вашему API, например GET /api/soul-rate, раз в N секунд.
============================================================= */
function initSoulRateTicker() {
  const el = document.getElementById('soul-rate');
  if (!el) return;

  const BASE_RATE = 1500; // базовая цена в €, подбирается product-командой
  const FLUCTUATION = 150; // амплитуда случайных колебаний

  function generateFakeRate() {
    const noise = (Math.random() - 0.5) * FLUCTUATION;
    return Math.round(BASE_RATE + noise);
  }

  function render() {
    const rate = generateFakeRate();
    el.textContent = `${rate.toLocaleString('ru-RU')} € / шт.`;

    // Плавная визуальная вспышка изменения курса
    el.classList.remove('is-updating');
    void el.offsetWidth; // reflow trigger
    el.classList.add('is-updating');
  }

  render();
  setInterval(render, 4000); // TODO: заменить на реальный опрос API
}

/* =============================================================
   2. КАЛЬКУЛЯТОР ОЦЕНКИ ДУШИ (#appraisal-form)
   Логика чисто фронтовая заглушка. На бэкенде должен быть
   отдельный эндпоинт расчёта (см. комментарий submitAppraisal),
   потому что окончательную цену считать на клиенте нельзя —
   пользователь может подменить значения в devtools.
============================================================= */
function initAppraisalCalculator() {
  const form = document.getElementById('appraisal-form');
  const resultValue = document.getElementById('appraisal-value');
  if (!form || !resultValue) return;

  // Веса для демо-расчёта. В проде — брать с сервера/конфига.
  const BASE_PRICE = 1300;
  const FATIGUE_MULTIPLIER = {
    'fresh': 1.35,
    'tired': 1.1,
    'burned': 0.9,
    'zombie': 0.75,
  };
  const DEBT_MULTIPLIER = {
    'none': 1.0,
    'small': 1.08,
    'mortgage': 1.22,
  };
  const COMPROMISE_MULTIPLIER = {
    'saint': 1.15,
    'minor': 1.0,
    'career': 0.85,
  };

  function calculate(formData) {
    const fatigue = formData.get('fatigue') || 'tired';
    const debt = formData.get('debt') || 'none';
    const compromise = formData.get('compromise') || 'minor';

    const fatigueFactor = FATIGUE_MULTIPLIER[fatigue] ?? 1;
    const debtFactor = DEBT_MULTIPLIER[debt] ?? 1;
    const compromiseFactor = COMPROMISE_MULTIPLIER[compromise] ?? 1;

    const price = BASE_PRICE * fatigueFactor * debtFactor * compromiseFactor;
    return Math.round(price / 50) * 50; // округление до 50 евро
  }

  let currentDisplayPrice = 0;
  let targetPrice = 0;
  let animFrameId = null;

  function animatePrice() {
    const diff = targetPrice - currentDisplayPrice;
    if (Math.abs(diff) < 1) {
      currentDisplayPrice = targetPrice;
      resultValue.textContent = `${Math.round(currentDisplayPrice).toLocaleString('ru-RU')} €`;
      return;
    }

    currentDisplayPrice += diff * 0.18; // плавный плавающий пересчёт цифр
    resultValue.textContent = `${Math.round(currentDisplayPrice).toLocaleString('ru-RU')} €`;
    animFrameId = requestAnimationFrame(animatePrice);
  }

  function updatePreview() {
    const formData = new FormData(form);
    targetPrice = calculate(formData);

    if (animFrameId) cancelAnimationFrame(animFrameId);
    animFrameId = requestAnimationFrame(animatePrice);
  }

  // Пересчёт при любом изменении полей — живой предпросмотр
  form.addEventListener('input', updatePreview);
  form.addEventListener('change', updatePreview);
  updatePreview(); // начальное значение при загрузке

  // Отправка формы
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    await submitAppraisal(formData);
  });
}

/**
 * Отправка формы на бэкенд.
 */
async function submitAppraisal(formData) {
  if (typeof window.submitStudioAppraisal === 'function') {
    return window.submitStudioAppraisal(formData);
  }
  console.log('Форма готова к отправке. Данные:', Object.fromEntries(formData));
  alert(I18N[currentLang]?.demo_alert || 'Demo: submitAppraisal()');
}

/* =============================================================
   3. АНИМАЦИЯ ПОЯВЛЕНИЯ СЕКЦИЙ ПРИ СКРОЛЛЕ
============================================================= */
function initScrollReveal() {
  const targets = document.querySelectorAll('main > section');
  if (!('IntersectionObserver' in window)) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });

  targets.forEach((el) => observer.observe(el));
}

/* =============================================================
   4. ПЛАВНОЕ УСКОРЕНИЕ ПЕЧАТИ (без рывков/прыжков)
============================================================= */
function initSealSmoothRotation() {
  const seal = document.querySelector('.minimal-seal');
  const rotateGroup = document.querySelector('.seal-text-group');
  if (!seal || !rotateGroup) return;

  let angle = 0;
  let speed = 9.5; // градусов в секунду (~38 сек на круг)
  let targetSpeed = 9.5;
  let lastTime = performance.now();

  function step(now) {
    const delta = (now - lastTime) / 1000;
    lastTime = now;

    // Плавная интерполяция скорости — без резких рывков при наведении
    speed += (targetSpeed - speed) * 0.05;
    angle = (angle + speed * delta) % 360;

    rotateGroup.style.transform = `rotate(${angle}deg)`;
    requestAnimationFrame(step);
  }

  requestAnimationFrame(step);

  seal.addEventListener('mouseenter', () => {
    targetSpeed = 26; // плавно разгоняется при наведении
  });

  seal.addEventListener('mouseleave', () => {
    targetSpeed = 9.5; // плавно замедляется до нормальной скорости
  });
}

/* =============================================================
   5. ЯЗЫКОВОЙ МОДУЛЬ (i18n: RU / EN)
============================================================= */
const I18N = {
  ru: {
    nav_rates: "Курс",
    nav_appraisal: "Оценка",
    nav_contract: "Договор",
    nav_faq: "Вопросы",
    ticker_label: "Курс души сегодня",

    hero_eyebrow: "Договор бессрочного отчуждения нематериального актива",
    hero_title_1: "Продайте душу.",
    hero_title_2: "Получите деньги.",
    hero_title_3: "Без комиссии банка.",
    hero_sub: "Мы оцениваем душу за 90 секунд, переводим деньги мгновенно и забираем всё остальное на себя. Юридически чисто. Морально — нет.",
    hero_cta_eval: "Оценить мою душу",
    hero_cta_contract: "Читать договор",
    hero_disclaimer: "* Возврату и обмену душа не подлежит. См. п. 6.6 договора.",
    seal_banner_text: "СДЕЛКА ЗАКЛЮЧЕНА",

    rates_eyebrow: "01 — рыночные данные",
    rates_title: "Курс души в реальном времени",
    col_category: "Категория души",
    col_status: "Состояние",
    col_price: "Цена",
    col_trend: "Динамика",

    cat_office: "Душа офисного сотрудника",
    tag_office: "Немного выгорела от созвонов",
    cat_student: "Душа студента перед сессией",
    tag_student: "Держится на кофе и молитвах",
    cat_dreamer: "Душа мечтателя / романтика",
    tag_dreamer: "Свежая, наивная",
    cat_mortgage: "Душа человека с ипотекой",
    tag_mortgage: "Закалена, 15 лет гарантии",
    cat_owl: "Душа совы (после понедельника)",
    tag_owl: "Требует сна, но не получает",
    rates_note: "Курс формируется биржей BuKaMiKu Exchange (внутренний индекс SOULX). Обновление каждые 24 часа, либо по факту экзистенциального кризиса.",

    appraisal_eyebrow: "02 — оценка",
    appraisal_title: "Узнайте стоимость своей души",
    step1_legend: "Шаг 1. Кто продаёт",
    label_firstname: "Имя",
    ph_firstname: "Александр",
    label_lastname: "Фамилия",
    ph_lastname: "Петров",
    label_email: "Электронная почта",
    ph_email: "alex@example.com",
    label_age: "Возраст души",
    label_country: "Страна проживания",
    select_country_default: "Выберите страну",
    opt_de: "Германия",
    opt_fr: "Франция",
    opt_ua: "Украина",
    opt_pl: "Польша",
    opt_kz: "Казахстан",
    opt_es: "Испания",
    opt_us: "США",
    opt_other: "Другая страна",

    step2_legend: "Шаг 2. Состояние товара",
    label_fatigue: "Уровень вашей повседневной усталости",
    fatigue_fresh: "Полный сил и жизненной энергии",
    fatigue_tired: "Устаю к пятнице, восстанавливаюсь к воскресенью",
    fatigue_burned: "Мечтаю об отпуске последние 3 года",
    fatigue_zombie: "Держусь на кофе, мемах и честном слове",

    label_debt: "Наличие кредитов или финансовых обязательств",
    debt_none: "Нет долгов и кредитов",
    debt_small: "Есть небольшая кредитка или рассрочка",
    debt_mortgage: "Ипотека или крупный кредит (поэтому я здесь)",

    label_compromise: "Частота компромиссов с совестью",
    compromise_saint: "Ни разу — я всегда честен перед собой",
    compromise_minor: "Бывает по мелочи (обещал перезвонить и не перезвонил)",
    compromise_career: "Регулярно, это называется «взрослая жизнь»",

    step3_legend: "Шаг 3. Куда переводить деньги",
    payout_desc: "Выплата зачисляется прямо в отдельный кошелёк <strong>Kawaui Studio</strong> после подписания договора.",
    result_label: "Предварительная оценка",
    contract_agree: "Я прочитал(а) и принимаю <a href=\"#contract\">договор отчуждения души</a>, включая п. 6.6",
    btn_submit: "Подписать и получить деньги",

    contract_eyebrow: "03 — юридический блок",
    contract_title: "Договор об отчуждении нематериального актива",
    c1_title: "1. Предмет договора и квалификация актива",
    c1_p1: "1.1. Продавец передаёт, а Покупатель (BuKaMiKu Exchange) принимает в полноправную и бессрочную собственность нематериальный актив Продавца (далее — «Душа») в состоянии «как есть» (as is).",
    c1_p2: "1.2. Продавец подтверждает, что актив не находится в залоге у сторонних метафизических сущностей, не обременён духовными ипотеками и свободен от претензий третьих лиц.",

    c2_title: "2. Цена и порядок расчётов",
    c2_p1: "2.1. Оценка стоимости актива рассчитывается автоматически алгоритмом BuKaMiKu на основе анкеты Продавца в Евро (€).",
    c2_p2: "2.2. Оплата производится единовременно путем зачисления средств в кошелёк Kawaui Studio. Переход прав собственности на Душу происходит в момент нажатия кнопки «Подписать».",

    c3_title: "3. Права, обязанности и гарантии Продавца",
    c3_p1: "3.1. Продавец обязуется не испытывать публичных экзистенциальных сожалений о совершенной сделке и не привлекать обряды экзорцизма для расторжения настоящего договора.",
    c3_p2: "3.2. Потеря бытовой совести, легкое ощущение пустоты во время кофе-пауз и равнодушие к мелодрамам являются нормальными побочными эффектами и не признаются дефектом исполнения.",

    c4_title: "4. Ответственность сторон и форс-мажор",
    c4_p1: "4.1. Стороны освобождаются от ответственности только в случае полного наступления Апокалипсиса или глобального отключения электричества во всех мирах одновременно.",
    c4_p2: "4.2. Наступление рефлексии, кризиса среднего возраста или депрессии не признается обстоятельством непреодолимой силы.",

    c5_title: "5. Конфиденциальность и реестр сделок",
    c5_p1: "5.1. Все данные сделки шифруются и заносятся в астральный реестр BuKaMiKu Exchange. Третьи лица не имеют доступа к вашему договору без подписки VIP.",

    c6_title: "6.6. Особые и бессрочные условия",
    c6_p1: "6.6.1. Договор является бессрочным, безотзывным и действующим во всех известных и неизвестных измерениях, включая явь, навь и промежуточные тарифные зоны.",
    c6_p2: "6.6.2. Возврату, обмену, гарантийному ремонту и выкупу Душа не подлежит ни при каких обстоятельствах.",

    faq_eyebrow: "04 — вопросы",
    faq_title: "Частые вопросы",
    faq_q1: "Это физически больно?",
    faq_a1: "Нет, абсолютная цифровая отчуждаемость! Никаких иголок, ритуалов или вызова демонов в 3 часа ночи. Всё происходит кликом по кнопке. Легкое ощущение внезапной свободы по понедельникам — это норма.",
    faq_q2: "Можно продать часть души или взять аванс?",
    faq_a2: "Да, алгоритм BuKaMiKu поддерживает частичную продажу (от 10% до 90%). Полный выкуп рекомендуется для решения крупных финансовых задач.",
    faq_q3: "Куда переходят деньги после оценки?",
    faq_a3: "Выплата зачисляется в Евро (€) на отдельный кошелёк Kawaui Studio сразу после подписания договора.",
    faq_q4: "А если я уже закладывал душу в микрозаймах?",
    faq_a4: "В форме оценки (Шаг 2) честно укажите информацию о кредитах. Система BuKaMiKu учтёт мотивационную надбавку и пересчитает курс с учётом высокой готовности к сделке.",
    faq_q5: "Можно ли выкупить душу обратно?",
    faq_a5: "См. п. 6.6 договора. Все сделки на бирже BuKaMiKu Exchange являются окончательными, бессрочными и безотзывными.",
    faq_q6: "Узнают ли об этом родственники или коллеги?",
    faq_a6: "Нет, сделке присваивается 128-битный анонимный хэш. Ваше окружение замечает только то, что вы стали спокойнее относиться к дедлайнам и перестали спорить в комментариях.",

    footer_legal: "BuKaMiKu не является банком в смысле закона о банках и банковской деятельности. Все сделки окончательны. Сайт является пародией и не производит реальный обмен душ на деньги.",
    demo_alert: "Демо: здесь будет запрос к API оценки души. См. комментарий submitAppraisal() в script.js"
  },
  en: {
    nav_rates: "Rates",
    nav_appraisal: "Valuation",
    nav_contract: "Agreement",
    nav_faq: "FAQ",
    ticker_label: "Soul rate today",

    hero_eyebrow: "Perpetual Intangible Asset Conveyance Agreement",
    hero_title_1: "Sell your soul.",
    hero_title_2: "Get cash.",
    hero_title_3: "Zero bank fees.",
    hero_sub: "We appraise your soul in 90 seconds, transfer funds instantly, and take care of the rest. Legally sound. Morally not.",
    hero_cta_eval: "Appraise My Soul",
    hero_cta_contract: "Read Agreement",
    hero_disclaimer: "* Souls are non-refundable and non-exchangeable. See clause 6.6.",
    seal_banner_text: "DEAL SEALED",

    rates_eyebrow: "01 — market data",
    rates_title: "Real-Time Soul Rates",
    col_category: "Soul Category",
    col_status: "Condition",
    col_price: "Price",
    col_trend: "Trend",

    cat_office: "Office Worker Soul",
    tag_office: "Slightly burned out from meetings",
    cat_student: "Student Soul Before Exams",
    tag_student: "Fuelled by coffee and prayers",
    cat_dreamer: "Dreamer / Romantic Soul",
    tag_dreamer: "Fresh & naive",
    cat_mortgage: "Mortgage Holder Soul",
    tag_mortgage: "Hardened, 15-year warranty",
    cat_owl: "Night Owl Soul (Post-Monday)",
    tag_owl: "Needs sleep, gets none",
    rates_note: "Exchange rate set by BuKaMiKu Exchange (SOULX Index). Updated every 24 hours or upon existential crisis.",

    appraisal_eyebrow: "02 — appraisal",
    appraisal_title: "Calculate Your Soul Value",
    step1_legend: "Step 1. Seller Details",
    label_firstname: "First Name",
    ph_firstname: "Alexander",
    label_lastname: "Last Name",
    ph_lastname: "Smith",
    label_email: "Email Address",
    ph_email: "alex@example.com",
    label_age: "Soul Age",
    label_country: "Country of Residence",
    select_country_default: "Select Country",
    opt_de: "Germany",
    opt_fr: "France",
    opt_ua: "Ukraine",
    opt_pl: "Poland",
    opt_kz: "Kazakhstan",
    opt_es: "Spain",
    opt_us: "United States",
    opt_other: "Other Country",

    step2_legend: "Step 2. Asset Condition",
    label_fatigue: "Daily Fatigue Level",
    fatigue_fresh: "Full of vitality & energy",
    fatigue_tired: "Tired by Friday, restored by Sunday",
    fatigue_burned: "Dreaming of vacation for 3 years",
    fatigue_zombie: "Powered by coffee, memes & prayers",

    label_debt: "Financial Debts & Loans",
    debt_none: "No debts or loans",
    debt_small: "Small credit card balance",
    debt_mortgage: "Mortgage or heavy loan (that's why I'm here)",

    label_compromise: "Frequency of Conscience Compromises",
    compromise_saint: "Never — completely pure",
    compromise_minor: "Minor things (promised to call back, didn't)",
    compromise_career: "Regularly, it's called adult life",

    step3_legend: "Step 3. Payout Destination",
    payout_desc: "The payout is credited directly to your separate <strong>Kawaui Studio</strong> wallet after signing.",
    result_label: "Estimated Valuation",
    contract_agree: "I have read and accept the <a href=\"#contract\">Soul Conveyance Agreement</a>, including clause 6.6",
    btn_submit: "Sign & Transfer Funds",

    contract_eyebrow: "03 — legal agreement",
    contract_title: "Intangible Asset Conveyance Agreement",
    c1_title: "1. Subject of Agreement & Asset Qualification",
    c1_p1: "1.1. Seller transfers, and Buyer (BuKaMiKu Exchange) accepts into full and perpetual ownership the Seller's intangible asset (hereinafter — 'Soul') on an 'as is' basis.",
    c1_p2: "1.2. Seller confirms the asset is not pledged to third-party metaphysical entities, unencumbered by spiritual mortgages, and free from claims of third parties.",

    c2_title: "2. Valuation & Settlement Terms",
    c2_p1: "2.1. The asset valuation is calculated automatically by the BuKaMiKu algorithm based on the Seller's form in Euros (€).",
    c2_p2: "2.2. Payment is made as a one-time transfer to your Kawaui Studio wallet. Ownership transfers immediately upon clicking 'Sign'.",

    c3_title: "3. Rights, Duties & Warranties",
    c3_p1: "3.1. Seller agrees not to express public existential regret regarding the transaction and agrees not to invoke exorcism rituals to terminate this agreement.",
    c3_p2: "3.2. Loss of everyday conscience, mild emptiness during coffee breaks, and indifference to melodramas are normal side effects and do not constitute breach of contract.",

    c4_title: "4. Liability & Force Majeure",
    c4_p1: "4.1. Parties are released from liability only in the event of a total Apocalypse or global power failure across all realms simultaneously.",
    c4_p2: "4.2. Midlife crisis, deep reflection, or depression shall not be deemed force majeure events.",

    c5_title: "5. Confidentiality & Transaction Registry",
    c5_p1: "5.1. All transaction data is encrypted and recorded in the BuKaMiKu Exchange astral registry. Third parties cannot access your contract without VIP subscription.",

    c6_title: "6.6. Special & Perpetual Terms",
    c6_p1: "6.6.1. This agreement is perpetual, irrevocable, and valid across all known and unknown dimensions, including physical, astral, and intermediate tariff zones.",
    c6_p2: "6.6.2. The Soul is non-refundable, non-exchangeable, and non-buyable under any circumstances.",

    faq_eyebrow: "04 — questions",
    faq_title: "Frequently Asked Questions",
    faq_q1: "Is it physically painful?",
    faq_a1: "No, 100% digital transferability! No needles, rituals, or summoning demons at 3 AM. Everything happens with a single click. A mild sense of sudden freedom on Mondays is normal.",
    faq_q2: "Can I sell part of my soul or get an advance?",
    faq_a2: "Yes, the BuKaMiKu algorithm supports partial conveyance (from 10% to 90%). Full buyout is recommended for major financial goals.",
    faq_q3: "Where do the funds go after valuation?",
    faq_a3: "The payout is credited in Euros (€) to your separate Kawaui Studio wallet immediately after signing.",
    faq_q4: "What if I already pledged my soul to loan companies?",
    faq_a4: "In Step 2 of the form, state your debt status honestly. The BuKaMiKu system will factor in a motivation bonus and recalculate your valuation.",
    faq_q5: "Can I buy my soul back later?",
    faq_a5: "See clause 6.6. All transactions on BuKaMiKu Exchange are final, perpetual, and irrevocable.",
    faq_q6: "Will my friends or coworkers find out?",
    faq_a6: "No, every transaction is assigned a 128-bit anonymous hash. People around you will only notice you became calmer about deadlines and stopped arguing online.",

    footer_legal: "BuKaMiKu is not a licensed banking institution under banking laws. All transactions are final. This website is a parody and does not conduct real soul exchange.",
    demo_alert: "Demo: API request for soul appraisal will take place here. See submitAppraisal() comment in script.js"
  }
};

let currentLang = localStorage.getItem('bukamiku_lang') || 'ru';

function setLanguage(lang) {
  if (!I18N[lang]) return;

  // Захват точной позиции скролла до смены текста
  const scrollY = window.scrollY;

  currentLang = lang;
  localStorage.setItem('bukamiku_lang', lang);
  document.documentElement.lang = lang;

  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('is-active', btn.dataset.lang === lang);
  });

  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    if (I18N[lang][key]) {
      el.textContent = I18N[lang][key];
    }
  });

  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    const key = el.dataset.i18nPh;
    if (I18N[lang][key]) {
      el.placeholder = I18N[lang][key];
    }
  });

  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.dataset.i18nHtml;
    if (I18N[lang][key]) {
      el.innerHTML = I18N[lang][key];
    }
  });

  // Фиксация скролла для предотвращения дергания страницы
  window.scrollTo({ top: scrollY, behavior: 'instant' });
}

function initI18n() {
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      setLanguage(btn.dataset.lang);
    });
  });

  setLanguage(currentLang);
}

/* =============================================================
   ИНИЦИАЛИЗАЦИЯ
============================================================= */
document.addEventListener('DOMContentLoaded', () => {
  initSoulRateTicker();
  initAppraisalCalculator();
  initScrollReveal();
  initSealSmoothRotation();
  initI18n();
});
