# BamBiku FastAPI Backend

Local API for registration, login, JWT sessions, and Google OAuth scaffold.
Access tokens are short-lived. Refresh sessions are stored server-side and sent to the browser as an HttpOnly cookie.

Full deployment, Docker, health, logs, and PostgreSQL backup/restore notes are in `..\DEPLOYMENT.md`.

## Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On startup the API runs Alembic migrations when `BAMBIKU_RUN_MIGRATIONS_ON_STARTUP=true`.
Manual migration command:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Run the current static frontend from the project root:

```powershell
python -m http.server 5500 --bind 127.0.0.1
```

API docs:

```text
http://127.0.0.1:8000/docs
```

Frontend:

```text
http://127.0.0.1:5500/index.html
```

Healthcheck:

```text
http://127.0.0.1:8000/api/health
```

## Production-demo Docker

From the project root:

```powershell
Copy-Item .env.compose.example .env
Copy-Item backend\.env.production.example backend\.env.production
docker compose up --build -d
```

Services:

```text
Frontend: http://127.0.0.1:5500/index.html
Backend:  http://127.0.0.1:8000/docs
Health:   http://127.0.0.1:5500/api/health
Postgres: internal Docker network only
```

Create a PostgreSQL backup:

```powershell
.\scripts\backup-postgres.ps1
```

Do not commit real `.env` files or OAuth secrets. Use examples as templates only.

## Google OAuth

Create OAuth credentials in Google Cloud Console, then put values into `backend/.env`:

```text
BAMBIKU_GOOGLE_CLIENT_ID=...
BAMBIKU_GOOGLE_CLIENT_SECRET=...
BAMBIKU_GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
```

The login endpoint is:

```text
GET /api/auth/google/login
```

## Telegram OIDC

In Telegram, open `@BotFather` and go to:

```text
/mybots -> BambikuCasinoBot -> Bot Settings -> Web Login
```

Add your public frontend origin and backend callback URL to Allowed URLs. For local development, use a public HTTPS tunnel such as ngrok because Telegram redirects must use registered public URLs.

Example `.env` values:

```env
BAMBIKU_TELEGRAM_CLIENT_ID=123456789
BAMBIKU_TELEGRAM_CLIENT_SECRET=your-client-secret-from-botfather
BAMBIKU_TELEGRAM_REDIRECT_URI=https://your-domain.example/api/auth/telegram/callback
BAMBIKU_TELEGRAM_SUCCESS_REDIRECT=https://your-domain.example/index.html
BAMBIKU_TELEGRAM_SCOPES=openid profile
```

The frontend Telegram button redirects to:

```text
GET /api/auth/telegram/login
```

The backend uses Authorization Code Flow with PKCE, validates Telegram's `id_token` with JWKS, then creates or logs in a user with provider `telegram`.
