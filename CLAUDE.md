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

- **Tenancy** (phase 3): every tenant table has a non-null `company_id`. The active company comes
  from the `X-Company-Id` header and is checked against `memberships` in one dependency
  (`get_tenant`) — never read `company_id` from a request body. Postgres row-level security is
  the second line of defense. `tests/test_tenancy.py` must prove company A cannot touch company
  B's data for every tenant endpoint — extend it whenever you add one.
- **Schema management**: `Base.metadata.create_all` runs on startup but only creates *missing*
  tables. Schema changes need an Alembic revision in `backend/alembic/versions/`; `0001` is the
  create-all baseline. Guard later revisions with existence checks so they are safe on both fresh
  and existing databases. Apply with `alembic upgrade head` (idempotent).
- **Connectors** (phase 9): Odoo-specific logic lives only in `backend/app/connectors/`.
- **Serving**: in dev, Vite proxies `/api`; in Docker, nginx (`frontend/nginx.conf`) serves the
  SPA and proxies `/api` to the backend (upload limit 100m for spreadsheet imports — keep it).

## Git

`testing` is the **testing branch** — it's what the user runs to try changes out. After every
commit on a working branch, merge the working branch into `testing` and push it, in addition to
pushing the working branch itself. When `testing` hasn't diverged this is just
`git push origin <working-branch>:testing` (fast-forward); otherwise fetch it, merge the working
branch into it locally, resolve, and push. Do not leave the testing branch behind after a commit.
