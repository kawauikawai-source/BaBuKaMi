# Bambiku on Render + Neon

This guide publishes two Render Web Services from one repository. `bambiku` owns Kawaui ID, Casino, Studio wallet and Neon data. `bukamiku` serves BuKaMiKu Bank and talks to the central API only from its server-side BFF.

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
5. Apply the Blueprint and wait for both `bambiku` and `bukamiku` to deploy.

The deploy performs these steps automatically:

1. Installs backend dependencies.
2. Builds a public-only frontend into `dist/`.
3. Runs all Alembic migrations against Neon.
4. Starts one Uvicorn worker on Render's assigned port.
5. Waits for `/api/health` to confirm the database and migration revision.

Render generates `BAMBIKU_SECRET_KEY`, the Kawaui ID client secret shared between services, and the BuKaMiKu cookie secret. These values never enter Git or browser JavaScript.

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
6. Open the public URL shown on the `bukamiku` Render service, sign in through Kawaui ID and verify that you return to BuKaMiKu.
7. Preview a soul valuation, sign the contract once, then check the separate Studio balance and history in Kawaui Studio.
8. Create a `Kawaui Studio` withdrawal in Casino and approve it in the existing admin withdrawals tab.

Google and Telegram remain attached only to central Bambiku. BuKaMiKu never needs its own Google callback or BotFather domain.

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
