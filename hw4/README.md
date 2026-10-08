# Campus Customs (HW4)

A Yale-apparel storefront with an AI shopping assistant: a **React + Vite + TypeScript** frontend and a
**Python FastAPI** backend over the course's **SQLite** database, with a **PydanticAI** agent using
`gpt-5.6-luna` through **Portkey**.

**Features:** Home, Products (normalized search + category filters), product detail pages, About Us,
Create account / Log in (hashed passwords, signed session tokens), and a chat assistant that answers only
from the database: prices, descriptions, total and per-size stock, and category cards. It also keeps
saved history for signed-in users, product-page context, an append-only audit trail and a premium
responsive design.

Documentation: [output/harness.md](output/harness.md) (auth, agent, tools, search, memory, safety, limits,
audit) · [output/usability.md](output/usability.md) · [output/design.md](output/design.md) ·
[output/app_check.html](output/app_check.html) · [AI_prompts.md](AI_prompts.md)

## Structure

```
hw4/
├── AI_prompts.md              # prompts per problem + how to verify
├── README.md · requirements.txt · .env.example · .gitignore
├── backend/
│   ├── main.py                # FastAPI app: routes, /api/chat, /api/chat/history, /api/products/search, /images
│   ├── agent.py               # PydanticAI agent (gpt-5.6-luna via Portkey), session context, audit hooks
│   ├── tools.py               # read-only parameterized SQLite tools (search, description, price, stock)
│   ├── search.py              # normalized, deduplicated catalogue search
│   ├── models.py              # request/response + structured tool/agent models
│   ├── audit.py               # append-only, sanitized output/audit_trail.json
│   ├── setup_data.py          # installs the local data pack (database + photos)
│   ├── prompts/prompt.md      # agent instructions + safety rules
│   ├── app/                   # config, db, auth, sessions, security (hashing), errors (safe error shape)
│   ├── data/                  # LOCAL ONLY (git-ignored): campus_customs.db, images/products/*.jpg
│   ├── tests/                 # 214 pytest tests (+ 11 live, opt-in)
│   ├── requirements.txt · requirements-dev.txt · pytest.ini
├── e2e/                       # 70 Playwright browser tests (Microsoft Edge)
├── frontend/                  # React app: src/components, src/pages, api.ts, auth.tsx, index.css
└── output/                    # harness.md, usability.md, design.md, app_check.html, audit_trail.json, screenshots
```

## Setup

Prerequisites: Python 3.11+, Node.js 20+, and the course **data pack** (`data.zip`).

### 1. Local data pack (not in the repository)

The database (`campus_customs.db`: catalogue, inventory, users, chat messages) and product photos come
from the course's `data.zip`. They are **git-ignored and never committed**. Install them with:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_data.py C:\path\to\data.zip   # -> data/campus_customs.db + data/images/products/
cd ..
```

### 2. Environment variables

```powershell
Copy-Item .env.example .env    # then edit .env (never commit it)
```
Both apps read the single `hw4/.env`.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `APP_ENV` | backend | Environment label (`development`, `production`) |
| `CORS_ORIGINS` | backend | Comma-separated origins allowed to call the API |
| `DATABASE_PATH` | backend | Optional SQLite file override (tests use a throwaway copy) |
| `SESSION_SECRET` | backend | Signs login session tokens (random string, keep secret) |
| `PORTKEY_API_KEY` | backend | Chat agent key (Portkey). Server-side only; if blank, the nearest parent `.env` is used |
| `OPENAI_MODEL` / `PORTKEY_BASE_URL` | backend | Optional: model (default `gpt-5.6-luna`) / gateway URL |
| `AUDIT_PATH` | backend | Optional audit file override (tests use throwaway files) |
| `VITE_API_BASE_URL` | frontend | Base URL of the FastAPI server |

> **Security:** `.env` is git-ignored and must never be committed. Secrets belong only in backend variables.
> Anything prefixed `VITE_` is bundled into public browser code, so never put API keys there.

## Database

`backend/data/campus_customs.db` is the **course database** (from `data.zip`), installed unchanged:

| Table | Rows | Notes |
| --- | --- | --- |
| `catalogue` | 102 | `product_id, name, garment_type, description, colors, search_tags, image_file_path, price` |
| `inventory` | 612 | `product_id, size (XS–XXL), quantity`; 145 sizes are sold out (0) |
| `users` | 3+ | `id, name, email, password_hash, created_at, first_name, last_name` |
| `chat_messages` | 22 | Not used yet |

The app never alters the schema or existing rows. Catalogue and inventory are read through a
**read-only** connection, every query is parameterized, and the only writes are new `users` rows from
registration. Course accounts use PBKDF2 hashes and new accounts use scrypt; both are verified. Product
images live in `backend/data/images/products/` (identical to the zip's). An earlier database I built
from HW3 is kept, git-ignored, in `backend/data/backup/`. See [output/harness.md](output/harness.md).

## API

| Endpoint | Returns |
| --- | --- |
| `GET /api/health` | `{"status": "ok", ...}` |
| `GET /api/products` | all products, sorted by name |
| `GET /api/products/{id}` | one product, or `404` |
| `GET /images/{image_path}` | product photo |
| `POST /api/auth/register` | `{first_name, last_name, email, password, confirm_password}` → `201 {user}`, `409` duplicate, `422` invalid |
| `POST /api/auth/login` | `{email, password}` → `200 {user}` or `401 "Invalid email or password."` |
| `GET /api/chat/history` | Signed-in user's own saved chat (`Authorization: Bearer <token>`); `401` for guests or bad tokens |
| `POST /api/chat` | `{message, history, product_id?}` (+ optional Bearer token: saves the exchange and uses saved history) → `200 {reply, matches, total_matches, view_all_url}` (matches = database product cards: id, name, image_path, image_url, price, short_description); `422` blank message; `502/503/504` with safe messages |

`user` is always `{id, first_name, last_name, email}`, and login/register also return a session `token`.
Passwords and hashes are never returned. Chat memory and context are documented in harness.md Part E.

Each product includes `image_url` (e.g. `/images/products/yale-dad-hoodie.jpg`), or `null` when the image
file is missing. The frontend then shows a "Photo coming soon" placeholder, and it does the same if an
image fails to load.

## Run the backend

All commands start from the `hw4/` folder. They call the venv's Python directly, so they work
even when PowerShell's execution policy blocks scripts like `Activate.ps1`.

```powershell
cd backend
python -m venv .venv                                            # first time only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # first time only
.\.venv\Scripts\python.exe -m uvicorn main:app --port 8000   # one process, auto-reload off
```

Check it at <http://localhost:8000/api/health>. Interactive docs: <http://localhost:8000/docs>

## Run the frontend

In a second terminal (from `hw4/`):

```powershell
cd frontend
npm.cmd install      # first time only
npm.cmd run dev
```

Open <http://localhost:5173>.

> Use `npm.cmd` in PowerShell: plain `npm` resolves to `npm.ps1`, which is blocked under the default
> Windows execution policy. In Command Prompt or macOS/Linux, plain `npm` is fine.

Stop each server with `Ctrl+C` in its terminal.

## Tests

```powershell
# from hw4/ (first time only: install test tools)
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

# API + database tests
cd backend; .\.venv\Scripts\python.exe -m pytest; cd ..

# Browser tests: start their own servers on ports 8001/5174 and shut them down afterwards
.\backend\.venv\Scripts\python.exe -m pytest e2e
```

The browser tests use the Microsoft Edge already installed on Windows (no browser download). They check:

- **Navigation:** every header link (Home, Products, About Us, Log in, Create account) and the 404 page
- **Product cards:** all 102 cards show image, name, price and description, and the type filter works
- **Detail links:** every card links to a unique `/products/<id>` page with the matching product, and unknown ids show a not-found state
- **Images:** all 102 photos load, and blocked images or a `null` `image_url` show the fallback
- **Responsive:** 4+ columns on desktop, 2 on a 375px phone, no horizontal scroll, and a hamburger menu that closes after navigating
- **Chat:** bottom-right launcher, structured replies with product cards, history, typing indicator, blank messages blocked, friendly error bubbles, fits on mobile, plus one **live** call through FastAPI → agent → Portkey
- **Accounts:** seeded login and logout, new registration followed by login, wrong passwords, duplicate emails, password confirmation, field validation, and password secrecy (see [output/harness.md](output/harness.md))

The browser tests run the backend against a throwaway copy of the database, so test accounts never reach
the real `campus_customs.db`.

## How to verify

1. `GET http://localhost:8000/api/health` returns `200` with `"status": "ok"`.
2. `GET http://localhost:8000/api/products` returns 102 products.
3. CORS preflight from the frontend origin is allowed:
   ```powershell
   curl.exe -i -X OPTIONS http://localhost:8000/api/health -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: GET"
   ```
   The response includes `access-control-allow-origin: http://localhost:5173`.
4. `npm.cmd run build` in `frontend/` type-checks and builds without errors.
5. Both test suites above pass.
6. `git status` never shows `.env` (it is matched by `.gitignore`; only `.env.example` is tracked).