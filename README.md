# Pallet Builder

Estimate how an order ships before it ships. Add products and quantities (by hand, from a
spreadsheet, or pulled from an Odoo sales order or opportunity). Pallet Builder looks up each
product's boxes, packs them onto pallets, and reports:

- how many pallets, and each pallet's **W × L × H** and **gross weight**
- density and a **suggested freight class**
- the box list per pallet
- an interactive **3D view** of every pallet, plus a printable PDF report

**Stack:** PostgreSQL · Python (FastAPI) · React (Vite + TypeScript) · three.js — deployed on Render.
Stage 2 will port the same engine to an Odoo 19 App Store module.

## How packing works

- **Box index**: each product has one or more boxes. One unit ships in *all* of its boxes
  (e.g. a fixture = box 1 body + box 2 lens). Each box has L × W × H, weight, and rules:
  *this side up*, *stackable*, *max load on top*. Small items can share a box (*units per box*).
- **Pallet types**: footprint (default 48 × 40 in), deck height, tare weight, max total height,
  max gross weight and allowed overhang.
- **Two modes**, switchable per shipment:
  - **Layered** — warehouse-friendly. Full layers of one box type, heaviest at the bottom,
    fragile/non-stackable on top, leftovers as a mixed top layer.
  - **Tightest fit** — mixes boxes freely to use as few pallets as possible. It also considers
    the layered result, so it never needs more pallets than Layered.
- Every pallet is checked by an independent validator: inside the footprint (plus overhang),
  under the height and weight limits, no overlaps, at least 75 % of each box's base supported,
  upright boxes kept upright, and no box carrying more than its load limit.

## Build status

| Phase | What | Status |
|---|---|---|
| 1 | Scaffold: backend, frontend, docker compose, Alembic, CI | ✅ |
| 2 | Packing engine: Layered + constraints + freight class, golden tests | ✅ |
| 3 | Signup, companies, memberships, company switcher, invites, roles, row-level security | ⏳ |
| 4 | Products, box index, pallet types, spreadsheet import/template | ⏳ |
| 5 | Shipments: lines, compute, results | ⏳ |
| 6 | 3D view | ⏳ |
| 7 | Tightest fit | ✅ (engine) |
| 8 | PDF report + share link | ⏳ |
| 9 | Odoo connector (products, sales orders, opportunities) | ⏳ |
| 10 | Render deploy | ⏳ |

## Running it

### Docker

```bash
cp .env.example .env       # set SECRET_KEY at minimum
docker compose up --build
```

App: http://localhost:8080.

### Local development

```bash
# backend (Python 3.11+)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
DATABASE_URL=sqlite:///./dev.db SECRET_KEY=dev-secret .venv/bin/uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev            # http://localhost:5173, proxies /api to :8000

# tests
cd backend && .venv/bin/python -m pytest
```

### Database migrations

Schema changes ship as Alembic revisions (`backend/alembic/versions/`). Startup only creates
*missing* tables, so after pulling an update that changes the schema run:

```bash
docker compose exec backend alembic upgrade head
```

It's idempotent; the Docker backend also runs it on every start.

## Repository layout

```
backend/
  app/
    engine/        # pure-Python packing engine (ported verbatim to Odoo in stage 2)
    api/ connectors/ services/   # filled in by phases 3–9
  alembic/         # migrations
  tests/engine/    # golden + invariant tests for the engine
frontend/
  src/scene/       # framework-agnostic three.js scene (phase 6)
docker-compose.yml
```
