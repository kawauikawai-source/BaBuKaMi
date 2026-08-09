# Frontend Architecture

The frontend remains dependency-free and uses ordered classic scripts. Files are grouped by ownership so each controller has one clear home.

## JavaScript

- `js/config/`: deployment and API runtime configuration.
- `js/core/`: constants, state/API store, shared UI, authentication, and page bootstrap.
- `js/pages/`: controllers for account, cashier, and admin pages.
- `js/games/`: one controller per playable game.

The required script order is: config, constants, store, UI, auth, optional page/game controller, bootstrap.

## CSS

- `css/core/base.css`: tokens, reset, navigation, shared controls, modals, legal shell, and global responsive rules.
- `css/pages/home.css`: home catalog, bonus, and VIP presentation.
- `css/pages/account.css`: shared account tables, forms, cashier, and profile components.
- `css/pages/`: page-specific overrides.
- `css/games/shared.css`: common game console proportions.
- `css/games/`: one theme and layout file per game.
- `css/style.css`: generated runtime compatibility bundle.

New styles belong in the matching module. Run `node scripts/build-css.js` after CSS changes; the quality gate also rebuilds the bundle. Pages load the generated bundle because legacy components intentionally share late cascade overrides across home, account, profile, and game surfaces.

## Runtime Rules

- Static games and i18n data use a versioned session cache.
- API data remains authoritative and refreshes after the static shell renders.
- Background tabs pause continuous game rendering and timers where possible.
- Canvas resolution is capped to protect high-DPI displays from unnecessary work.
- Do not link individual CSS modules directly from HTML until selector ownership is verified visually on every affected page.
