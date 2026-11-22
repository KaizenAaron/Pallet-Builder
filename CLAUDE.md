# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Pallet Builder estimates how an order ships: it packs each product's boxes onto pallets and
reports pallet count, per-pallet W×L×H, gross weight, density/freight class, and a 3D view.
**Stage 1** (current) is a standalone multi-tenant SaaS: FastAPI + Postgres backend, Vite/React/
TypeScript frontend, deployed on Render. **Stage 2** ports it to an Odoo 19 App Store module. The
approved plan is the roadmap; build phases are listed in README.md.

## Commands

```bash
# Backend (Python 3.11+, from backend/)
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest                          # all tests (sqlite, no Postgres needed)
.venv/bin/python -m pytest tests/engine -k layered  # engine tests only / single test
DATABASE_URL=sqlite:///./dev.db SECRET_KEY=dev-secret .venv/bin/uvicorn app.main:app --reload

# Migrations (from backend/, same DATABASE_URL as the server)
DATABASE_URL=sqlite:///./dev.db .venv/bin/alembic upgrade head

# Frontend (from frontend/)
npm install
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
npm run build      # tsc -b && vite build — run this to type-check

# Full stack
docker compose up --build                           # app at http://localhost:8081
```

## Non-obvious domain rules (the load-bearing decisions)

- **The engine is the single source of truth** (`backend/app/engine/`). Every pallet number
  (dims, weights, density, class, placements) comes from it; the API stores results and the
  frontend only formats them — never re-derive metrics in the UI.
- **The engine must stay pure Python (stdlib only).** No FastAPI, SQLAlchemy, pydantic or Odoo
  imports inside `app/engine/`. It is copied verbatim into the Odoo addon in stage 2 and its tests
  are the parity guarantee between both codebases. Same for `frontend/src/scene/`: plain
  TypeScript + three.js, no React imports, so the Odoo OWL widget can reuse it.
- **Multi-box products**: one unit ships in *all* of its product's boxes (`qty_per_unit` of each);
  `units_per_box` units share one box. Count = `ceil(qty / units_per_box) × qty_per_unit`.
- **Every placement goes through `PalletState.try_place`** (`engine/pallet_state.py`), which
  enforces footprint+overhang, height, weight, no overlap, ≥75% base support on stackable boxes,
  this-side-up, and `max_load_on_top` (load shared by contact area). A box may not be placed
  touching the underside of an existing box — that keeps each box's supports fixed once placed,
  so incremental load tracking matches the validator.
- **`engine/constraints.validate` is independent of the packers** and re-checks finished
  pallets from placements alone. Every engine test runs every result through it; keep it that way
  when adding packers or rules.
- **Modes**: `layered` = full single-SKU layers (best grid or two-block pattern, heaviest group
  first, non-stackable last), leftovers packed on top with the extreme-point packer. `tightest` =
  best of several extreme-point orderings **and** the layered result, so tightest never needs more
  pallets than layered. Both are deterministic.
- **Golden numbers are pinned**: `tests/engine/test_engine.py` expected values are hand-checked
  (each docstring shows the arithmetic). If a change breaks them, the change is wrong (or needs
  explicit sign-off from the user), not the tests.
- Units are inches and pounds throughout the engine and DB; metric is a display conversion at
  the API boundary only. Freight class is a *suggestion* from the NMFC 13-tier density table
  (`engine/freight.py`).

## Architecture

- **Tenancy**: every tenant table inherits `TenantMixin` (non-null `company_id`). The active
  company comes from the `X-Company-Id` header and is checked against `memberships` in one
  dependency (`tenancy.get_tenant` / `require_role`) — never read `company_id` from a request
  body. Filter tenant queries with `tenancy.scoped(...)`; look up rows by id *and* company so a
  guessed id from another company is a 404. Roles: `owner` > `admin` > `member`; nobody can grant
  or invite above their own role, and a company always keeps at least one owner.
  `tests/test_tenancy.py` must prove company A cannot touch company B's data for every tenant
  endpoint — add new endpoints to `TENANT_READS` / write cases there.
- **Row-level security** (`app/rls.py`) is the second wall, Postgres only. `TenantMixin` tables get
  FORCEd policies keyed on the `app.company_id` setting, which an `after_begin` session hook
  re-applies every transaction (`bind_company`, called by `get_tenant`). Superusers bypass RLS, so
  sessions also `SET LOCAL ROLE pallet_app` when allowed. A new tenant table needs an Alembic
  revision that calls `apply_rls()` again. Code that must see every company (CLI, platform tools)
  uses `db.system_session()`. `memberships`/`invites` are deliberately *not* RLS'd (they're read
  before a company is chosen) — app checks + tests protect them. `tests/test_rls.py` only runs on
  Postgres (CI does; locally: `DATABASE_URL=postgresql+psycopg://… pytest`).
- **Auth**: Argon2 passwords (10+ chars), JWT in the httpOnly `pb_session` cookie (Bearer also
  accepted — tests use cookies via separate TestClients). `users.token_version` is in the JWT;
  bumping it (password change/reset, sign out everywhere) kills all sessions. Signup requires
  email verification. Signup, resend and forgot-password return identical responses whether or
  not the account exists (no enumeration). Verification/reset/invite links are single-use and
  only their SHA-256 is stored.
- **Email links on screen**: when SMTP isn't configured and `EMAIL_LINK_FALLBACK=true`, those
  endpoints return the link as `dev_link` and the UI shows it. Local testing only — it must be
  off on any public server, or anyone could verify an address they don't own. Invite links are
  always returned to the inviter (copy-and-send is a feature, like Sales-Rep-Activity).
- **Rate limiting** (`app/ratelimit.py`) is in-memory per process — fine for one Render instance;
  move it to a shared store before scaling out.
- **Frontend auth**: `src/auth.tsx` holds `me` and the active company (remembered in
  localStorage); `src/api.ts` adds `X-Company-Id`. The active company is pushed to the API client
  synchronously during render — child pages' effects run before the provider's, so doing it in
  an effect sends their first request without the header.
- **Schema management**: `Base.metadata.create_all` runs on startup but only creates *missing*
  tables. Schema changes need an Alembic revision in `backend/alembic/versions/`; `0001` is the
  create-all baseline. Guard later revisions with existence checks so they are safe on both fresh
  and existing databases. Apply with `alembic upgrade head` (idempotent). **Never assume an
  earlier revision created a table**: databases from phase 1 were stamped `0001` when it had no
  models to create, so a revision that touches new tables must create them first
  (`Base.metadata.create_all(bind, checkfirst=True)`, as `0002` does). `tests/test_migrations.py`
  upgrades a phase-1-shaped database to head on Postgres — keep it passing.
- **Connectors** (phase 9): Odoo-specific logic lives only in `backend/app/connectors/`.
- **Serving**: in dev, Vite proxies `/api`; in Docker, nginx (`frontend/nginx.conf`) serves the
  SPA and proxies `/api` to the backend (upload limit 100m for spreadsheet imports — keep it).

## Git

`testing` is the **testing branch** — it's what the user runs to try changes out. After every
commit on a working branch, merge the working branch into `testing` and push it, in addition to
pushing the working branch itself. When `testing` hasn't diverged this is just
`git push origin <working-branch>:testing` (fast-forward); otherwise fetch it, merge the working
branch into it locally, resolve, and push. Do not leave the testing branch behind after a commit.
