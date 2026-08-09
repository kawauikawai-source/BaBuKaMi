# Quality Gates

Use this file as the release checklist for the production-demo build.

## Local Required

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\quality.ps1
```

The local gate checks:

- Python compile for `backend/app` and `backend/tests`.
- Backend `unittest` suite.
- Alembic `upgrade head` and current revision.
- JavaScript syntax for every file recursively in `js/`.
- JSON validity for every file in `data/`.
- Static release invariants: no `TODO_FIX`, no debug `console.log`, no deprecated FastAPI `on_event`, no deprecated `HTTP_422_UNPROCESSABLE_ENTITY`.
- Text encoding guard: no UTF-8/Windows-1251 mojibake, replacement characters, or obvious broken placeholder text.
- Basic frontend security invariants: safe `target="_blank"` links and sanitized `data-i18n-html` rendering.
- Performance budgets: no page loads more than 8 scripts, 420 KB of raw JavaScript, 1 generated stylesheet, or 300 KB of raw CSS; no raster image exceeds 512 KB.
- Font delivery guard: production CSS must not use a render-blocking Google Fonts import.

## CI Required

GitHub Actions runs `.github/workflows/quality.yml` on push and pull request.

- Python 3.13 installs `backend/requirements.txt`.
- Node 20 runs the same local quality script.
- CI uses a demo SQLite database and placeholder secrets only.
- Docker validation is intentionally not required yet.

## Manual Browser Smoke

Run these checks on the local backend and static frontend before a demo release:

- Register and login.
- Deposit and withdraw.
- Admin tabs: overview, balance, withdrawals, audit.
- Admin balance action updates user data.
- Withdrawal approve/reject updates status and balance correctly.
- Roulette page opens, spin completes, balance updates in game and header.
- Profile history shows cashier/game transactions.

## Accessibility And Security Follow-Up

- Keyboard-only navigation for menu, modal, tabs, cashier, profile, FAQ, and admin tabs.
- Visible focus indicators on all actionable controls.
- Toast and form errors are announced clearly.
- No plaintext credentials are persisted in local storage.
- Hosting config should add CSP/security headers from `SECURITY.md`.
