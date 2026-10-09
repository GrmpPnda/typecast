# Typecast

A novel-writing web application with AI-assisted editing, structured content management, and professional export capabilities. Built with FastAPI and React.

Typecast runs entirely on your own machine. Your manuscripts stay in a local SQLite database, and the only data that leaves is what you explicitly send to an AI provider or to Google Drive.

![The work detail view, showing chapters, scenes, and codex entries in the navigation sidebar](docs/images/work-detail.png)

## Screenshots

Reading mode paginates the manuscript with CSS columns, in either an ePub viewport mode or fixed PDF page dimensions that mirror the export exactly.

![Reading mode displaying a chapter with a scene break](docs/images/reading-mode.png)

The codex holds characters, locations, items, and lore. Entries feed the AI assistant as context and can be referenced from chat with `@`.

![The codex list filtered by entry type](docs/images/codex.png)

## Features

### Writing & Editing

- Multi-scene chapter editor with TipTap (ProseMirror-based rich text)
- Fullscreen writing mode with distraction-free interface
- Front/back matter sections (dedication, copyright, foreword, etc.)
- Scene management with insert, split, and reorder
- Inline spellcheck via Hunspell dictionary with codex-aware custom words
- Inline comments anchored to text spans with AI-powered review

### AI Assistant

- Streaming chat panel with tool use (create content, review, generate images, write scenes)
- Three personas: Author (creative, style-matching), Reviewer (constructive feedback), Advisor (informational)
- @mentions to reference codex entries, works, chapters, and scenes as context
- Multimodal input (attach images to chat) and image generation (Bedrock, OpenAI)
- Style matching that analyzes and emulates the author's writing patterns
- AI diff highlighting shows changed text after AI edits

### Knowledge Base (Codex)

- Per-work entries for characters, locations, items, lore, timelines
- Image galleries per entry with primary image selection
- Codex entries provide context to the AI assistant via @mentions
- Per-character voice assignment for narration

### Export & Reading

- PDF export via WeasyPrint with full typographic control (margins, headers, footers, fonts, chapter headings, roman numeral front matter, chapters-start-recto)
- ePub export with cover, inline images, and TOC
- DOCX export with profile-based styling
- Markdown, HTML, and plain text export
- Built-in and custom export profiles with per-work defaults
- Reading mode with CSS column pagination (ePub viewport mode, PDF fixed-dimension mode, spread view)
- Send exports straight to Google Drive, converting Word, HTML, text, and Markdown into native Google Docs for beta readers
- Choose the Drive subfolder and file name per export; missing folders are created for you

### Cover Production

- Print-ready full cover generation (front + spine + back) for B&N Press specifications
- Configurable trim size, spine factor, bleed, and ISBN safe zone
- 300 DPI PNG output with guide lines

### Narration

- Text-to-speech via Amazon Polly with per-character voice mapping
- AI-powered dialogue segmentation for multi-voice narration
- 19 English voices across long-form, neural, and generative engines

### Library & Organization

- Series and standalone works with cover images
- Work-level image gallery with inline insertion into scenes
- Global gallery across every work, with search, filtering by source, and reassignment between works
- Custom font upload (TTF, OTF, WOFF, WOFF2) for profiles and title pages
- Structured title page configuration with per-element font control
- Smart chapter ordering (auto-inserts front/back matter at correct positions)
- Four themes (Default, Solarized, Nord, High Contrast), each with light and dark variants and a custom accent colour

### Infrastructure

- JWT-based auth with transparent local-mode auto-login (single user) and multi-user support
- Database-neutral backups (SQLite ↔ PostgreSQL), with restore for recovery and import for moving works between installs, locally or to Google Drive with optional retention
- Structured request logging with configurable levels and request IDs
- Custom error pages (404 and error boundary)
- User ownership model on works, series, and conversations

## Quick Start

### Without Docker

Requires Python 3.11 or newer and Node 18 or newer.

PDF export uses WeasyPrint, which links against Pango, Cairo, and gdk-pixbuf. Install those first or PDF export will fail at request time with an import error, while every other format keeps working:

```bash
# macOS
brew install pango cairo gdk-pixbuf libffi

# Debian/Ubuntu
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -c requirements.lock -e ".[dev]"   # omit [dev] to skip pytest and ruff
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

The app will be available at `http://localhost:3000`. The Vite dev server proxies `/api` and `/uploads` to the backend on port 8000.

### On Azure

[`infra/README.md`](infra/README.md) deploys Typecast to Azure Container Apps with PostgreSQL, Azure Files, and optional Microsoft single sign-on. GitHub Actions tests, builds, and rolls out every push to `main`; the infrastructure is declared in Bicep.

### With Docker

```bash
cp .env.example .env
# Edit .env with your API keys
docker compose up --build
```

Then open **https://localhost**. The stack serves only HTTPS: port 80 redirects to 443, and the backend is not published at all, so nothing reaches it except through nginx. Set `TYPECAST_AUTH_MODE=multi` in `.env` for anything other people can reach; the first visit then walks you through creating the administrator.

The database and every upload live in the `typecast-data` volume, mounted at `/app/data`. They survive `docker compose down` and rebuilds; `docker compose down -v` deletes the volume and with it your work. Setting `DATABASE_URL` in `.env` moves the database out of that volume, so leave it commented out unless you are pointing at PostgreSQL.

#### Certificates

On first start the frontend generates a **self-signed certificate** for `TYPECAST_TLS_HOSTNAME` (default `localhost`; `localhost` and `127.0.0.1` are always included). Browsers warn about it once. It is kept in the `typecast-certs` volume, so the exception you accept survives rebuilds.

To use a real certificate, put `tls.crt` (full chain) and `tls.key` in a directory and replace the `typecast-certs` line in `docker-compose.yml` with a bind mount:

```yaml
      - ./certs:/etc/nginx/certs:ro
```

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `TYPECAST_TLS_HOSTNAME` | `localhost` | Name on the generated certificate. Set it to the hostname people type |
| `TYPECAST_HTTPS_PORT` | `443` | Host port for HTTPS, and the port plain HTTP redirects to |
| `TYPECAST_HTTP_PORT` | `80` | Host port for the HTTP-to-HTTPS redirect |

nginx deliberately sends no `Strict-Transport-Security` header. Reached through an SSH tunnel the hostname is `localhost`, and once a browser trusts that certificate, HSTS would force HTTPS on every localhost port and break any plain-HTTP development server. Behind a trusted certificate, set `TYPECAST_FORCE_HTTPS=1` on the backend to get HSTS.

To reach an instance on a remote machine without opening ports, tunnel straight to HTTPS: `ssh -L 8443:localhost:443 <host>`, then open https://localhost:8443.

## Configuration

Configuration is managed through environment variables and the in-app Settings page.

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `TYPECAST_DATA_DIR` | `backend/` | Where the database and `uploads/` live. Point this at a volume to keep your work outside the source tree. The Docker image sets it to `/app/data` |
| `DATABASE_URL` | `<data dir>/typecast.db` | Database connection string. Set explicitly, this overrides `TYPECAST_DATA_DIR` for the database only, which will separate it from the uploads. See PostgreSQL below |
| `TYPECAST_AUTO_MIGRATE` | `1` | Bring the schema to the latest migration on startup. Set to `0` to run `alembic upgrade head` as a separate step instead |
| `TYPECAST_AUTH_MODE` | `local` | Auth mode: `local` (auto-login, single user), `multi` (Typecast passwords), or `proxy` (single sign-on through Azure Easy Auth or oauth2-proxy; see below). `local` logs in every caller, so anything reachable from a network needs `multi` or `proxy` |
| `TYPECAST_ADMIN_EMAIL` | _(none)_ | With `TYPECAST_ADMIN_PASSWORD`, creates the first administrator at startup when the user table is empty, skipping the first-run setup page. Ignored once any user exists |
| `TYPECAST_ADMIN_PASSWORD` | _(none)_ | Password for the bootstrapped administrator (8 characters minimum) |
| `TYPECAST_OPEN_REGISTRATION` | `0` | Allow self-service signup. Off by default; accounts are created by an administrator in Settings |
| `TYPECAST_FORCE_HTTPS` | `0` | Redirect HTTP to HTTPS (308, so a POST stays a POST) and send HSTS. For a deployment where the backend sits directly behind a TLS-terminating proxy, such as Azure Container Apps; the compose stack does this in nginx instead. `/api/health` is exempt so health probes over plain HTTP still succeed. Requires `uvicorn --proxy-headers`, which both Dockerfiles pass |
| `TYPECAST_CORS_ORIGINS` | `*` | Comma-separated origins allowed to call the API |
| `TYPECAST_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `TYPECAST_LOG_FORMAT` | `text` | Log format: `text` or `json` |
| `TYPECAST_LOG_FILE` | _(none)_ | Optional log file path |
| `TYPECAST_STATIC_DIR` | _(none)_ | Directory of a built frontend to serve from `/`. Used by the Docker image; unnecessary in development, where Vite serves the UI |
| `SECRET_KEY` | `change-me-in-production` | Key for token signing and encryption |

AI provider configuration (Anthropic, OpenAI, or Bedrock) is managed through the Settings page. API keys are encrypted at rest.

## Database

Typecast runs on SQLite or PostgreSQL. **You do not create the schema yourself.** On every start it brings the database up to the current migration, so pointing `DATABASE_URL` at an empty database of either kind is all that is required. Starting it twice is harmless.

Three cases are handled, and the third matters if you have been running Typecast since before it used migrations:

| State of the database | What happens on start |
| --- | --- |
| Empty, or the file does not exist | Every table is created at the current revision |
| Already migrated | Any newer revisions are applied, otherwise nothing |
| Has Typecast tables but no `alembic_version` | Stamped as current, **content untouched**. Replaying the baseline would fail on tables that already exist |

### SQLite (default)

Nothing to configure. The file is created at `<data dir>/typecast.db` alongside `uploads/`:

```bash
cd backend
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

### PostgreSQL

Install the driver extra and point at the server. Typecast creates its **tables**, but not the database itself, so create that first:

```bash
cd backend
.venv/bin/python -m pip install -e ".[dev,postgres]"
createdb typecast        # or CREATE DATABASE typecast; managed providers usually do this for you
export DATABASE_URL="postgresql://user:pass@host:5432/typecast?sslmode=require"
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Paste the connection string your provider gives you verbatim. Typecast rewrites it for the async driver: `postgresql://` becomes `postgresql+asyncpg://`, and libpq's `sslmode=require` becomes asyncpg's `ssl=require`. Without that rewrite asyncpg rejects `sslmode` outright, which is the usual first failure. If the database is missing, unreachable, or the password is wrong, startup fails with a message naming the fix rather than a driver stack trace.

The Docker image installs `.[postgres]` already, so only `DATABASE_URL` is needed there.

Two limits to know before choosing Postgres:

- **Uploads stay on the filesystem** whichever database you use. The data directory still needs persistent storage.
- Backups work the same on both. See [Moving between installs](#moving-between-installs).

### Single sign-on with Microsoft Entra ID

`TYPECAST_AUTH_MODE=proxy` hands sign-in to an authenticating proxy in front of the app. On Azure that is the built-in authentication of App Service and Container Apps ("Easy Auth"): Azure signs people in with their Microsoft account and forwards who they are on every request. Typecast never runs an OAuth flow, and there is no Typecast password at all.

**How accounts work.** The first person to sign in to an empty install becomes the administrator (or name them in advance with `TYPECAST_ADMIN_EMAIL`, which is safer). Administrators add everyone else in Settings → Users by the email they sign in with; the account links to that person the first time they sign in, and from then on is matched by their Entra object ID, so a later change of email or UPN does not lose it. Anyone who signs in without an account sees "ask an administrator". Everything else about accounts and privacy works exactly as in `multi` mode.

**Set up on Azure Container Apps** (App Service is the same under Settings → Authentication):

1. Container app → **Authentication** → **Add identity provider** → **Microsoft**. Let it create a new app registration, choose **Current tenant – Single tenant**, require authentication, and redirect unauthenticated requests to sign in.
2. Make the identity token available to the app. Typecast verifies the signed ID token Easy Auth forwards in `X-MS-TOKEN-AAD-ID-TOKEN`, which requires Easy Auth's **token store**. Check your platform's documentation for what enabling it needs (Container Apps backs it with a blob storage container), and confirm the header arrives before relying on it.
3. Restrict who can sign in. In the Entra admin center, open the new app under **Enterprise applications**, set **Assignment required** to **Yes**, and add the people who should have access under **Users and groups**. Without this, everyone in your tenant can sign in, and would only then be told they have no account.
4. Set the container's environment:

   ```bash
   TYPECAST_AUTH_MODE=proxy
   TYPECAST_OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
   TYPECAST_OIDC_AUDIENCE=<application (client) id of the app registration>
   TYPECAST_ADMIN_EMAIL=you@yourdomain.com
   TYPECAST_FORCE_HTTPS=1
   SECRET_KEY=<a long random value>
   ```

   If sign-ins fail with "issued by an unexpected provider", the app registration is issuing v1 tokens; accept both forms with `TYPECAST_OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0,https://sts.windows.net/<tenant-id>/`.

**Why the token matters.** Easy Auth also forwards plain identity headers, and setting `TYPECAST_PROXY_TRUST_HEADERS=1` instead of the two `OIDC` variables makes Typecast trust those. That is only safe if no request can ever reach the container except through Easy Auth, because anyone who can reach it another way can set those headers and become anyone. A verified token cannot be forged without Microsoft's private key, so it stays safe even if a back door exists. Proxy mode refuses to start with neither configured.

Easy Auth does not refresh the ID token it forwards, so Typecast checks its signature, issuer, and audience, and that it was issued within `TYPECAST_OIDC_MAX_TOKEN_AGE` (default 12 hours), but not its one-hour expiry. Otherwise everyone would be signed out an hour into a sign-in session that lasts much longer. When the window passes, the next request sends the browser back through sign-in, which normally completes without a prompt.

**Elsewhere** (including the docker-compose stack), put [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/) with its Entra ID provider in front of nginx, run it with `--pass-authorization-header`, and set `TYPECAST_PROXY_PRESET=oauth2-proxy` alongside the same `OIDC` variables. Header names and sign-in/out URLs can each be overridden with `TYPECAST_PROXY_ID_HEADER`, `TYPECAST_PROXY_NAME_HEADER`, `TYPECAST_PROXY_TOKEN_HEADER`, `TYPECAST_PROXY_LOGIN_URL`, and `TYPECAST_PROXY_LOGOUT_URL`. **Never enable proxy mode with trusted headers on a server people can reach directly.**

### Moving between installs

Backups are database-neutral: a ZIP of every table as JSON plus the `uploads/` directory, with a manifest recording the schema revision. An archive taken from a SQLite install loads into a PostgreSQL one and the other way round. Settings → Backup & Restore offers two ways to load one, and they do different things:

| | **Import into my account** | **Restore from Backup** |
| --- | --- | --- |
| For | Moving your works to another install | Recovering an install from its own backup |
| Existing data | Kept; the backup's works are added | Replaced entirely |
| Accounts | Not imported. Everything belongs to whoever imports | Replaced with the backup's |
| Stored API keys | Not imported | Restored if this server can decrypt them |
| Google Drive connection | Not imported | Restored if this server can decrypt it |

To move from a local install to a hosted one: **Download Backup** locally, sign in to the hosted install as an administrator, **Import into my account**, then re-enter your API keys in Settings and reconnect Google Drive. Import checks the whole archive first and shows what will arrive before it writes anything.

A few things to know:

- **API keys never travel in readable form.** They are encrypted with a key derived from `SECRET_KEY`, so another server cannot decrypt them. Import skips them; restore drops any it cannot read rather than storing values that would break every AI call.
- **Built-in export profiles are matched by name.** Each install creates its own copies with its own IDs, so a work set to "Standard ePub" points at the new install's "Standard ePub" after import. Your custom profiles come across as they are.
- **The same backup cannot be imported twice.** IDs are preserved, which keeps every reference and every image path in your prose intact, so an overlap refuses the whole import with nothing changed.
- **Restoring a single-user backup onto a multi-user server is refused.** It would install the local account, whose default password is published. Use Import.
- An uploaded file that already exists with different contents is kept as it is, and the import reports it.
- Backups taken before this format (a copy of the SQLite file) still restore, but only on a SQLite install. To move one elsewhere, restore it locally and download a fresh backup.
- Backup, restore, and import all require an administrator.

### Migrations

Alembic lives in `backend/alembic`. After changing a model:

```bash
cd backend
.venv/bin/python -m alembic revision --autogenerate -m "what changed"
```

Review the generated file, then restart the app to apply it. `tests/test_db_portability.py` fails if a model has no migration creating its table, or if a revision uses a dialect-specific type.

Set `TYPECAST_AUTO_MIGRATE=0` to disable migrating on startup and run `alembic upgrade head` as a deployment step instead. Worth doing if several replicas start at once, since they would otherwise race to apply the same revision.

One Postgres-specific gotcha for later: adding a value to an existing enum needs `ALTER TYPE ... ADD VALUE`, which autogenerate does not write for you.

### Multi-user deployments

`TYPECAST_AUTH_MODE=local` auto-logs in every caller with no credentials. That is deliberate for a local single-user app and wrong for anything reachable over a network, so set `TYPECAST_AUTH_MODE=multi`.

**First run creates the administrator in the browser.** Start the app in `multi` mode against an empty database and every route sends you to a one-time setup page that creates the first account as an administrator and signs you in. The page disappears the moment any account exists, and the endpoint behind it refuses to run again, so it cannot be used to add a second admin.

For automated deployments, set `TYPECAST_ADMIN_EMAIL` and `TYPECAST_ADMIN_PASSWORD` instead and the administrator is created at startup with no setup page. Either way, the variables and the page are both ignored once an account exists.

Self-service signup is disabled by default. The administrator creates everyone else from Settings → Users, where you can grant or revoke admin, deactivate, reset passwords, and delete accounts. Deactivating revokes access on the next request, including tokens already issued. Every user can change their own password under Settings → Account.

Deleting an account destroys everything it owns, because the ownership foreign keys cascade. The API refuses to delete an account holding any works, series, or conversations and tells you what would be lost; deactivate instead to keep the manuscripts.

**Every API route requires a signed-in account**, and every resource is private to the account that owns it. A work, series, chapter, scene, codex entry, or conversation that belongs to someone else answers 404, the same as one that does not exist, including when its ID arrives in a request body, an @mention, or an AI tool call. Install-wide settings (AI and narration configuration, fonts, export profiles, Google Drive, backups) can be read by any account but changed only by an administrator. Administrators manage accounts; they do not see other people's manuscripts.

Uploaded images and fonts under `/uploads` are the exception: an `<img>` tag cannot send a sign-in token, so they are served to anyone with the URL. Their paths contain random IDs and cannot be guessed or listed.

Set `SECRET_KEY` to a real random value. It signs auth tokens and derives the key encrypting stored AI provider keys, so the default defeats both.

### Google Drive

Sending exports to Drive uses your own Google Cloud OAuth client, so nothing is routed through a third-party service. Set it up once:

1. In the [Google Cloud console](https://console.cloud.google.com/apis/credentials), create a project and enable the Google Drive API.
2. Create an OAuth client of type **Web application**.
3. Add `http://localhost:8000/api/gdrive/callback` as an authorised redirect URI. Running with `--ssl` changes the scheme, so register the `https://` form too if you use both modes. Settings shows the exact URI for your current mode.
4. Paste the client ID and secret into Settings → Google Drive, save, then click Connect.

Typecast requests only the `drive.file` scope, which limits it to files it creates — it cannot read anything else in your Drive. Publish the OAuth app in the console rather than leaving it in **Testing**, or Google expires the authorisation every 7 days.

Each export can name a destination. The folder box takes a path relative to your `Typecast` folder, using `/` to nest, and any missing level is created on send. Leave it blank for the top level. The file name box defaults to the work title, and the extension is added from the export format so the two cannot disagree. Because the `drive.file` scope hides folders Typecast did not create, the destination has to be typed rather than picked from your existing Drive.

Once connected, Settings → Backup & Restore can also push backup archives to a `Backups` subfolder and restore from them. Retention is off by default; turning it on deletes older archives from Drive after each successful upload. Restoring replaces the local database and every upload, so anything written since that archive was taken is lost.

## Tech Stack

**Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), SQLite via aiosqlite, Pydantic v2, WeasyPrint, Pillow, ebooklib, python-docx, boto3

**Frontend:** React 18, TypeScript, Vite, TanStack Query, TipTap editor, Tailwind CSS, Lucide icons, Axios

## Project Structure

```text
backend/
  app/
    api/          # FastAPI routers (auth, works, chapters, scenes, codex, etc.)
    db/           # Engine, session, base model, migrations
    models/       # SQLAlchemy ORM models
    schemas/      # Pydantic request/response schemas
    services/     # AI providers, image gen, narration, export, crypto, auth
    repositories/ # Generic SQLAlchemy repository pattern
    paths.py      # Database and uploads locations (honours TYPECAST_DATA_DIR)
  uploads/        # Static files (covers, images, codex, fonts)
frontend/
  src/
    api/          # API client functions (REST + SSE streaming)
    components/   # Shared components (Sidebar, WorkNav, Editor, AIChatPanel, etc.)
    extensions/   # TipTap extensions (spellcheck, comments, ai-diff)
    pages/        # Route-level page components
    types/        # TypeScript interfaces
```

## Development

```bash
# Type check frontend
cd frontend && npx tsc --noEmit

# Lint frontend
cd frontend && npm run lint

# Lint backend
cd backend && .venv/bin/python -m ruff check app/

# Run backend tests (657 tests)
cd backend && .venv/bin/python -m pytest
```

Dependencies are pinned in `backend/requirements.lock`, which CI, the container images, and the commands above all install, so everything runs the versions the tests ran against. To take upgrades, run `backend/scripts/lock-deps.sh`: it resolves fresh versions in a clean Linux container and replaces the lock only if the full suite passes.

Invoke the backend tools as `.venv/bin/python -m <tool>` rather than `.venv/bin/pytest`. Console scripts carry an absolute shebang from wherever the virtualenv was first created, so they fail with `bad interpreter` if the project directory is ever moved. The module form does not. If you hit that error, either recreate the virtualenv or rewrite the shebangs in `.venv/bin/` and the `VIRTUAL_ENV` assignments in `.venv/bin/activate`.

There is currently no frontend test suite. UI changes are verified with `tsc --noEmit` and in the browser.

## License

Copyright (C) 2026 Brendan Saunders

Typecast is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the [GNU General Public License](LICENSE) for more details.

Your manuscripts are your own. The GPL covers this software, not anything you write with it.

### Third-party licences

Version 3 rather than 2 is deliberate: four dependencies are Apache-2.0, which GPLv2 cannot incorporate.

ePub export uses [EbookLib](https://github.com/aerkalov/ebooklib), which is AGPL-3.0-or-later. Section 13 of the GPL permits the combination, and running Typecast on your own machine triggers no additional obligation. If you host it as a service other people use, the AGPL's requirement to offer source to those users applies to that component.
