# Bambiku Production-Demo Deployment

This setup is for one VPS/server running frontend, backend, and PostgreSQL with Docker Compose.
Money is still demo-value, but the infrastructure should behave like a real service foundation.

For the public Render + Neon test deployment, use [RENDER_NEON_DEPLOY.md](RENDER_NEON_DEPLOY.md).

## Local Development

Backend:

```powershell
cd C:\Users\kawaui\Documents\Working\BamBiku-Casino.V3\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd C:\Users\kawaui\Documents\Working\BamBiku-Casino.V3
python -m http.server 5500 --bind 127.0.0.1
```

URLs:

- Frontend: `http://127.0.0.1:5500/index.html`
- Backend health: `http://127.0.0.1:8000/api/health`
- Backend docs: `http://127.0.0.1:8000/docs`

Local frontend uses `http://127.0.0.1:8000/api` by default.

## Docker Production-Demo

Prepare env files:

```powershell
Copy-Item .env.compose.example .env
Copy-Item backend\.env.production.example backend\.env.production
```

Edit both real env files before starting:

- replace `POSTGRES_PASSWORD`
- replace `BAMBIKU_SECRET_KEY`
- set `BAMBIKU_ADMIN_EMAILS`
- set `BAMBIKU_PUBLIC_BASE_URL`
- set OAuth redirect URLs only if OAuth is enabled

Do not commit `.env` or `backend/.env.production`.

Start:

```powershell
docker compose up --build -d
```

Open:

- Frontend: `http://127.0.0.1:5500/index.html`
- Same-origin API: `http://127.0.0.1:5500/api/health`
- Direct backend, if exposed: `http://127.0.0.1:8000/api/health`

PostgreSQL is not published on `5432`; only backend can reach it inside the Docker network.

## Staging And Production Modes

Use the same compose file with different env values:

- `BAMBIKU_ENV=staging`
- `BAMBIKU_ENV=production`

For a staging server, keep a separate uncommitted `.env` and `backend/.env.production` copy with staging URLs and secrets.

Recommended production values:

```env
BAMBIKU_LOG_FORMAT=json
BAMBIKU_REFRESH_COOKIE_SECURE=true
BAMBIKU_PUBLIC_BASE_URL=https://your-domain.example
BAMBIKU_API_BASE_URL=https://your-domain.example/api
BAMBIKU_FRONTEND_ORIGINS=https://your-domain.example
```

## Health And Logs

Health returns environment, database state, and migration versions:

```powershell
Invoke-RestMethod http://127.0.0.1:5500/api/health
```

Logs:

```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db
```

Plain logs are useful locally. JSON logs are recommended for staging/production because Docker can ship them to external log tools later.

## Backup PostgreSQL

Create a timestamped SQL backup in `backups/`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-postgres.ps1
```

Optional:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-postgres.ps1 -OutputDir D:\bambiku-backups -ComposeFile docker-compose.yml -DbName bambiku -DbUser bambiku
```

Real backup files are ignored by git.

## Restore PostgreSQL

Restore requires confirmation:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-postgres.ps1 -InputFile .\backups\bambiku-YYYYMMDD-HHMMSS.sql
```

Automation/non-interactive restore:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-postgres.ps1 -InputFile .\backups\bambiku-YYYYMMDD-HHMMSS.sql -Force
```

Restore clears the `public` schema before loading the backup.

## After Server Reboot

```powershell
cd C:\Users\kawaui\Documents\Working\BamBiku-Casino.V3
docker compose up -d
docker compose logs -f backend
```

Then check:

```powershell
Invoke-RestMethod http://127.0.0.1:5500/api/health
```

## Quality Gate

Before shipping changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\quality.ps1
```

The gate checks backend compile/tests/migrations, frontend JS/static checks, required infrastructure files, and PowerShell parse for backup/restore scripts. It does not run Docker.
