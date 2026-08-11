(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  const domains = B.configDomains = B.configDomains || {};

  domains.app = {
    storage: {
      lang: 'bk_lang',
      users: 'bk_users',
      session: 'bk_session',
      demoUser: 'bk_local_user',
      cookie: 'bk_cookie',
      kyc: 'bk_kyc'
    },
    defaults: {
      lang: 'ru',
      currency: 'EUR',
      locale: { ru: 'ru-RU', en: 'en-US' }
    },
    routes: {
      home: 'index.html',
      profile: 'pages/profile.html',
      deposit: 'pages/deposit.html',
      help: 'pages/help.html',
      privacy: 'pages/privacy.html',
      terms: 'pages/terms.html'
    },
    links: {
      supportEmail: 'support@bambiku.com',
      partnersEmail: 'partners@bambiku.com',
      privacyEmail: 'privacy@bambiku.com',
      legalEmail: 'legal@bambiku.com',
      responsibleGaming: 'https://www.begambleaware.org'
    },
    socialProviders: [
      { id: 'google', label: 'Google', i18nKey: 'form_social_google' },
      { id: 'telegram', label: 'Telegram', i18nKey: 'form_social_telegram' }
    ],
    cashier: {
      depositMin: 20,
      cryptoDepositMin: 20,
      depositMax: 1000,
      withdrawMin: 180,
      withdrawMax: 500,
      withdrawTime: '24h',
      commission: '50%',
      tierRules: {
        bronze: { depositMin: 20, depositMax: 1000, withdrawMin: 180, withdrawMax: 500, commission: 50, withdrawHours: 24 },
        silver: { depositMin: 20, depositMax: 1500, withdrawMin: 150, withdrawMax: 750, commission: 30, withdrawHours: 12 },
        gold: { depositMin: 20, depositMax: 2500, withdrawMin: 100, withdrawMax: 1500, commission: 15, withdrawHours: 4 },
        platinum: { depositMin: 20, depositMax: 5000, withdrawMin: 50, withdrawMax: 5000, commission: 5, withdrawHours: 1 }
      },
      hotPreset: 100,
      presets: [20, 50, 100, 200, 500],
      depositMethods: [
        { id: 'card', label: 'Bank Card', label_ru: 'Банковская карта', label_en: 'Bank Card', icon: 'CARD', requiresCard: true },
        { id: 'usdt', label: 'Crypto', label_ru: 'Криптовалюта', label_en: 'Crypto', icon: 'CRYPTO', requiresCrypto: true },
        { id: 'promo', label: 'Promo Code', label_ru: 'Промокод', label_en: 'Promo Code', icon: 'PROMO', requiresCard: false, requiresPromo: true }
      ],
      withdrawMethods: [
        { id: 'card', label: 'Bank Card', label_ru: 'Банковская карта', label_en: 'Bank Card', icon: 'CARD', requiresCard: true },
        { id: 'usdt', label: 'Crypto', label_ru: 'Криптовалюта', label_en: 'Crypto', icon: 'CRYPTO', requiresCrypto: true },
        { id: 'kawaui-studio', label: 'Kawaui Studio', label_ru: 'Kawaui Studio', label_en: 'Kawaui Studio', icon: 'STUDIO' }
      ],
      paymentTags: ['CARD', 'USDT', 'PROMO']
    },
    vipTiers: [
      { name: 'Bronze', level: 1, min: 0, max: 999, icon: 'B', color: '#cd7f32', cashback: '0%' },
      { name: 'Silver', level: 2, min: 1000, max: 4999, icon: 'S', color: '#a8a9ad', cashback: '5%' },
      { name: 'Gold', level: 3, min: 5000, max: 19999, icon: 'G', color: '#d4af37', cashback: '10%' },
      { name: 'Platinum', level: 4, min: 20000, max: Infinity, icon: 'P', color: '#e5e4e2', cashback: '15%' }
    ],
    demoUser: {
      id: 'local-user',
      name: 'Иван Иванов',
      email: 'local.user@bambiku.local',
      phone: '+48 600 000 000',
      dob: '1990-04-12',
      country: 'Poland',
      currency: 'EUR',
      balance: 2450,
      vipPoints: 1840,
      vipTier: 'bronze',
      gamesPlayed: 128,
      totalWon: 8340,
      passwordChangedAt: '2026-04-15',
      security: {
        twoFactor: true,
        emailVerified: true,
        kycStatus: 'not_started'
      },
      history: [
        { id: 'tx-local-1', createdAt: '2026-05-03T11:24:00.000Z', type: 'win', title: 'Kawaui Fortune', amount: 340 },
        { id: 'tx-local-2', createdAt: '2026-05-02T15:12:00.000Z', type: 'deposit', titleKey: 'tx_deposit_title', methodId: 'card', amount: 200 },
        { id: 'tx-local-3', createdAt: '2026-05-01T20:05:00.000Z', type: 'win', title: 'Lucky Bamboo', amount: 125.5 },
        { id: 'tx-local-4', createdAt: '2026-04-30T10:41:00.000Z', type: 'withdraw', titleKey: 'tx_withdraw_title', methodId: 'card', amount: -500 },
        { id: 'tx-local-5', createdAt: '2026-04-29T08:30:00.000Z', type: 'deposit', titleKey: 'tx_deposit_title', methodId: 'card', amount: 1000 },
        { id: 'tx-local-6', createdAt: '2026-04-28T22:11:00.000Z', type: 'win', title: 'Blackjack Pro', amount: 88 }
      ]
    },
    registeredUser: {
      name: '',
      email: '',
      phone: '',
      dob: '',
      country: '',
      currency: 'EUR',
      balance: 0,
      vipPoints: 0,
      vipTier: 'bronze',
      gamesPlayed: 0,
      totalWon: 0,
      passwordChangedAt: '',
      security: {
        twoFactor: false,
        emailVerified: false,
        kycStatus: 'not_started'
      },
      history: []
    }
  };
  domains.app.localUser = domains.app.demoUser;
  domains.app.storage.localUser = domains.app.storage.demoUser;
})(window);
