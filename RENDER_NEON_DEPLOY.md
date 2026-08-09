# Bambiku on Render + Neon

This guide publishes the test site as one Render Web Service. FastAPI serves both the frontend and `/api`, while Neon stores all persistent data.

## 1. Create the Neon database

1. Sign in to Neon and create a project named `bambiku`.
2. Choose an AWS region in Europe, preferably Frankfurt, to match the Render service.
3. Open **Connect** and disable connection pooling.
4. Copy the direct connection string. It should look like:

```text
postgresql://user:password@ep-example.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

Keep this value private. Do not put it in a source file, screenshot, commit, or chat.

## 2. Put the project in a private Git repository

Render deploys from GitHub, GitLab, or Bitbucket. This folder is not currently initialized as a Git repository.

From the project directory:

```powershell
git init
git add .
git status
```

Before committing, confirm that the following are not listed:

- `.env`
- `backend/.env`
- `backend/.env.production`
- `backend/bambiku.db`
- database backups and log files

Then create a private remote repository and push:

```powershell
git commit -m "Prepare Bambiku for Render and Neon"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_PRIVATE_REPO.git
git push -u origin main
```

## 3. Create the Render Blueprint

1. Sign in to Render and connect the Git provider that owns the private repository.
2. Select **New > Blueprint**.
3. Select the Bambiku repository. Render reads `render.yaml` automatically.
4. Enter the prompted secret values:
   - `BAMBIKU_DATABASE_URL`: the direct Neon connection string from step 1.
   - `BAMBIKU_ADMIN_EMAILS`: the email that should receive admin access after registration.
5. Apply the Blueprint and wait for the first deploy.

The deploy performs these steps automatically:

1. Installs backend dependencies.
2. Builds a public-only frontend into `dist/`.
3. Runs all Alembic migrations against Neon.
4. Starts one Uvicorn worker on Render's assigned port.
5. Waits for `/api/health` to confirm the database and migration revision.

Render generates `BAMBIKU_SECRET_KEY` and supplies the public HTTPS address through `RENDER_EXTERNAL_URL`. No URL, CORS, or cookie values need to be copied manually.

## 4. Verify the deployment

Open the Render URL and check:

```text
https://YOUR-SERVICE.onrender.com/api/health
```

The expected response contains:

```json
{
  "status": "ok",
  "env": "production",
  "database": "ok",
  "migration": "ok"
}
```

Then test in this order:

1. Register using the admin email configured in Render.
2. Sign out, sign in, and reload the page to verify the refresh cookie.
3. Open the profile and admin pages.
4. Add test balance, play one game, redeem a promo, and inspect the audit log.
5. Register a second ordinary account and verify that it has no admin access.

Google and Telegram login remain disabled until their client credentials and public callback URLs are configured.

## Updates and logs

Every push to `main` triggers a Render deploy:

```powershell
git add .
git commit -m "Describe the change"
git push
```

Use the Render service **Logs** tab for startup, migration, application, and database errors. Logs are emitted as JSON in production.

If a deploy fails during `alembic upgrade head`, Render does not start the new application version. Fix the migration or Neon connection and redeploy.

## Free-tier behavior

- Render sleeps after 15 minutes without traffic. The first visitor can wait about one minute for startup.
- Neon can also suspend idle compute. SQLAlchemy verifies pooled connections before use and reconnects when needed.
- Render's local filesystem is ephemeral. All persistent account, wallet, game, promo, and audit data must stay in Neon.
- Do not use SQLite on Render.

## Local development remains unchanged

The Render-only frontend mount is disabled locally. Continue using:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

and, from the project root:

```powershell
python -m http.server 5500 --bind 127.0.0.1
```
