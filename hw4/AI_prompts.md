# HW4 – Campus Customs: AI Prompts Log

Each problem lists the prompt and follow-up prompt used, and a **How to verify** section with commands and
the expected output. Unless marked *live*, checks make **no API calls** and use throwaway copies of the
database.

Common setup (from `hw4/`, after following README "Setup"):

```powershell
# backend tests: run from hw4\backend
cd backend; .\.venv\Scripts\python.exe -m pytest <file> -q; cd ..
# browser tests (Microsoft Edge; they start their own servers on 8001/5174): run from hw4\
.\backend\.venv\Scripts\python.exe -m pytest e2e\<file> -q
```

> **Note:** Problem 2's prompt was not part of this log. The course data pack (`data.zip`) was supplied
> later and installed in Problem 6. Fill in Problem 2 if it had its own prompt.

---

## Problem 1 – Project foundation

**Prompt 1:** Set up the Campus Customs project foundation with a React + Vite + TypeScript frontend, Python FastAPI backend, CORS, environment-variable support, a GET /api/health endpoint, README.md, .gitignore, and .env.example. Do not implement products, authentication, database features, or the chatbot yet. Never expose or hardcode API keys.

**Follow-up:** Verify the frontend and backend structure, health endpoint, CORS, secret exclusions, and README run instructions. Fix only setup issues.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_api.py -q -k "health or cors"` → `2 passed`
- With the backend running: `curl.exe -s http://localhost:8000/api/health` → `{"status":"ok","service":"campus-customs-api","environment":"development"}`
- `cd frontend; npm.cmd run build` → ends with `✓ built in …`

## Problem 3 – Storefront

**Prompt 1:** Build the Campus Customs storefront with Home, Products, About Us, Log in, and Create account navigation. Use catalogue data and database image paths. Add product cards with image, name, price, and description; each card must open a single-product detail page. Add a bottom-right chat stub. Use original Campus Customs-style wording, preserve the database, and do not implement the real agent yet.

**Follow-up:** Test navigation, product cards, detail links, images, missing-image handling, responsive layout, and the chat panel. Fix only Problem 3 issues.

**How to verify**
- `.\backend\.venv\Scripts\python.exe -m pytest e2e\test_storefront.py -q` → `15 passed`
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_api.py -q` → `9 passed` (102 products, every image served, missing image → `image_url: null`)

## Problem 4 – Create account and log in

**Prompt 1:** Implement create-account and login pages. Registration needs first name, last name, email, password, and confirmation. Login needs email and password. Use the existing users table, validate input, reject duplicate emails, securely hash passwords, and never return plain-text passwords. Verify test@campuscustoms.yale.edu with password password and a newly created account. Update output/harness.md with the authentication flow.

**Follow-up:** Test seeded login, new registration, new login, incorrect passwords, duplicate emails, password confirmation, and password secrecy. Fix only authentication issues.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_auth.py -q` → `22 passed`
- `.\backend\.venv\Scripts\python.exe -m pytest e2e\test_auth_ui.py -q` → `9 passed`
- Documentation: `output/harness.md` Part A.

## Problem 5 – PydanticAI agent behind FastAPI

**Prompt 1:** Implement the Campus Customs PydanticAI agent behind FastAPI. Create or update backend/main.py, agent.py, tools.py, models.py, and prompts/prompt.md. Connect the frontend chat widget to a structured POST chat endpoint. Use PORTKEY_API_KEY through Portkey with gpt-5.6-luna. Load the prompt from prompt.md, keep secrets server-side, and never invent product or inventory facts. Update output/harness.md and run one clean Uvicorn process with auto-reload disabled.

**Follow-up:** Test the frontend-to-FastAPI-to-agent path, empty messages, structured replies, safe API errors, prompt loading, and API-key protection. Fix only chatbot-backend issues.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_chat.py -q` → `20 passed` (scripted model, no API calls)
- `.\backend\.venv\Scripts\python.exe -m pytest e2e\test_chat_ui.py -q` → `9 passed` (1 *live* call)
- Documentation: `output/harness.md` Part B.

## Problem 6 – Product and inventory tools

**Prompt 1:** Add safe parameterized SQLite tools in backend/tools.py for product description, price, total inventory, and size-specific inventory. Use structured return types, handle unknown products and out-of-stock sizes, update prompts/prompt.md, and document each tool and returned field in output/harness.md. Never guess values or modify the database.

**Follow-up:** Test real descriptions, prices, total stock, size stock, unknown products, missing sizes, and out-of-stock sizes. Confirm the agent calls the correct tool and never invents values.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_tools.py -q` → `51 passed` (every product and all 612 inventory rows vs. direct SQL; all 145 sold-out sizes)
- *live:* `cd backend; .\.venv\Scripts\python.exe -m pytest -m live -q` → `11 passed` (correct tool + no invented numbers)
- Documentation: `output/harness.md` Part C.

## Problem 7 – Structured catalogue search

**Prompt 1:** Add structured catalogue search. For category questions such as "What hoodies do you have?", return database-grounded product matches containing ID, name, image path, price, and short description. Return both the natural-language reply and matches from FastAPI. Render matches as reusable product cards, and ensure every dynamic card opens the correct product-detail page. Update prompt.md and harness.md.

**Follow-up:** Test matching and non-matching category questions, database accuracy, dynamic cards, images, empty results, ordinary replies, and detail-page routing. Fix only search or rendering issues.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_search.py -q` → `24 passed`
- `.\backend\.venv\Scripts\python.exe -m pytest e2e\test_chat_search_ui.py -q` → `9 passed` (1 *live* call)
- Documentation: `output/harness.md` Part D.

## Problem 8 – Chat memory and context

**Prompt 1:** Persist chat messages and replies for authenticated users and reload them when they return. Guests may chat without persistence. Pass only the logged-in user's name and email to the agent. Pass current product page context so questions such as "Do you have this in pink?" work. Protect users from seeing another user's history, never send passwords, and document storage and context in output/harness.md.

**Follow-up:** Test guest chat, saved and reloaded authenticated history, authorization, name/email context, product-page context, and privacy. Fix only memory or context issues.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_memory.py -q` → `28 passed`
- `.\backend\.venv\Scripts\python.exe -m pytest e2e\test_chat_memory_ui.py -q` → `9 passed` (1 *live* call)
- Documentation: `output/harness.md` Part E.

## Problem 9 – Four usability improvements

**Prompt 1:** Implement exactly four improvements: two frontend improvements (responsive mobile layout and chat suggestions/loading/errors/accessibility) and two backend improvements (normalized deduplicated catalogue search and concise safe error handling). Create output/usability.md explaining what each does, why it helps, and how to verify it. Make every improvement visible in the running app.

**Follow-up:** Review output/usability.md against the running app. Verify all four improvements, including mobile, loading, empty, error, search, and successful states. Fix missing features.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_improvements.py -q` → `38 passed`
- `.\backend\.venv\Scripts\python.exe -m pytest e2e\test_usability_ui.py -q` → `19 passed`
- With both servers running: `.\backend\.venv\Scripts\python.exe output\usability\review_running_app.py` → `14/14 checks passed` (2 *live* calls)

## Problem 10 – Premium storefront design

**Prompt 1:** Give Campus Customs a cohesive premium storefront design. Improve typography, navy/white colors with pink accents, spacing, hierarchy, product cards, detail pages, forms, chat, buttons, loading, empty, and error states. Add accessible responsive layouts, subtle motion, soft-glow borders, and polished cards while preserving all functionality. Create output/design.md explaining the changes and customer benefit.

**Follow-up:** Review Home, Products, details, authentication, and chat on desktop and mobile. Check contrast, keyboard focus, responsiveness, images, and non-disruptive motion. Fix visual issues and update design.md if needed.

**How to verify**
- With both servers running: `.\backend\.venv\Scripts\python.exe output\design\review_design.py` → every line starts with `PASS` (8 contrast checks, images and no sideways scroll on 4 pages × 2 sizes, focus visible, reduced motion)
- All browser tests still pass: `.\backend\.venv\Scripts\python.exe -m pytest e2e -q` → `70 passed`

## Problem 11 – App check evidence

**Prompt 1:** Run the app and create output/app_check.html documenting screenshots of: real database-grounded price and inventory chat, dynamic category product cards, and one Problem 9 usability feature. Put screenshots in output/app_check_images/ and link them with relative paths. Add a heading and one or two explanatory sentences for each test. Do not show secrets or private data.

**Follow-up:** Verify every screenshot loads, every test has a heading and explanation, and the evidence clearly proves inventory accuracy, dynamic cards, and the selected usability feature. Fix broken paths or captions.

**How to verify**
- Open `output/app_check.html` in a browser: 3 sections, each with a heading, explanation, figure and caption; all 3 images load from `app_check_images/`.
- Database values shown in Test 1: `cd backend; .\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('data/campus_customs.db');print(c.execute(\"select price from catalogue where product_id='davenport-college-crewneck'\").fetchone(), c.execute(\"select size,quantity from inventory where product_id='davenport-college-crewneck' and size in ('M','S')\").fetchall())"` → `(58.0,) [('S', 0), ('M', 5)]`

## Problem 12 – Audit trail, safety rules, harness

**Prompt 1:** Add an append-only output/audit_trail.json recording timestamp, tool name, sanitized short arguments/results, and stop reason. Never record keys, passwords, full chat history, or sensitive data, and never erase prior entries. Add safety rules to prompts/prompt.md for grounded answers, privacy, uncertainty, refusal, and secret protection. Finish output/harness.md with models, tools, safety, loop/result limits, model/Portkey setup, run instructions, and audit behavior.

**Follow-up:** Test successful and failed tools, empty results, oversized input, and model/API errors. Confirm audit entries append safely and documentation matches the running system.

**How to verify**
- `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_audit.py -q` → `22 passed`
- All backend tests: `cd backend; .\.venv\Scripts\python.exe -m pytest -q` → `214 passed, 11 deselected`
- Documentation: `output/harness.md` Part F; safety rules in `backend/prompts/prompt.md` → "Safety rules".

## Problem 13 – Public GitHub repository

**Prompt 1:** Prepare the project for a public GitHub repository under a folder named hw4. Verify AI_prompts.md, requirements.txt, .env.example, .gitignore, README.md, frontend, backend, and output files are present. Exclude .env, API keys, campus_customs.db, data/products images, passwords, tokens, and private data. Ensure README explains the local data pack, environment variables, frontend/backend commands, and structure. Show git status and the tracked-file list before pushing.

**Follow-up:** The tracked-file list is safe. Commit the completed Homework 4 project and push it to the configured public GitHub repository. Do not force-push or include ignored files. Report the public repository URL after pushing.

**How to verify**
- `git ls-files hw4 | Select-String "\.env$|campus_customs\.db|images/products/|backup/"` → no output
- `git check-ignore -v hw4/.env hw4/backend/data/campus_customs.db hw4/backend/data/images/products/yale-dad-hoodie.jpg` → each path is listed with the `.gitignore` rule that excludes it
