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

## Never done this before? Start here (Windows / PowerShell, step by step)

This runs your own private test copy of Pallet Builder on your computer. You need the same two
programs as Sales-Rep-Activity (Docker Desktop and Git) and a few commands. These steps put the
code in `C:\Users\Loyd\Desktop\Cowork\Cerno\Pallet Builder\Dev`. Change the path if you want it
somewhere else.

Pallet Builder runs at **http://localhost:8081**, so it can run at the same time as
Sales-Rep-Activity (which uses 8080). The two keep completely separate databases.

**Step 1: Open Docker Desktop.** It's already installed from Sales-Rep-Activity. Start it and
wait until it says it's running (whale icon in the system tray). If it isn't installed, get it
from https://www.docker.com/products/docker-desktop/.

**Step 2: Check Git.** Open **PowerShell** and type `git --version`. A version number means
you're set. If not, install it from https://git-scm.com/download/win with the default options,
then reopen PowerShell.

**Step 3: Get the code.** Paste these lines one at a time. The quotes matter because the path
has spaces:

```powershell
New-Item -ItemType Directory -Force "C:\Users\Loyd\Desktop\Cowork\Cerno\Pallet Builder" | Out-Null
cd "C:\Users\Loyd\Desktop\Cowork\Cerno\Pallet Builder"
git clone https://github.com/KaizenAaron/Pallet-Builder.git Dev
cd Dev
git checkout testing
```

If the repository is private, a GitHub sign-in window pops up the first time. Sign in with your
GitHub account. The last line switches to `testing`, the branch where new changes land for you
to try.

**Step 4: Create the settings file.**

```powershell
Copy-Item .env.example .env
notepad .env
```

In Notepad, change `SECRET_KEY=` to any long random sentence (mash the keyboard). Save and
close. Leave everything else as-is.

**Step 5: Start the app.**

```powershell
docker compose up --build
```

The first time takes a few minutes. When the text stops scrolling, open
**http://localhost:8081**. Leave the PowerShell window open; closing it stops the app.

*Right now the page just says "Pallet Builder — API: ok". That means everything is working.
Sign-up, companies and the shipment screens arrive in the next phases.*

**Everyday use:** open Docker Desktop, then:

```powershell
cd "C:\Users\Loyd\Desktop\Cowork\Cerno\Pallet Builder\Dev"
docker compose up
```

To stop it, press `Ctrl+C` in that window. Your data is kept between restarts.

**Getting the latest test version:** stop the app (`Ctrl+C`), then:

```powershell
git pull
docker compose up --build
```

Database updates (migrations) apply automatically when the app starts. There's nothing extra to
run.

**If something goes wrong**

- *"port is already allocated"*: something else is using 8081. Stop the other program, or
  change `"8081:80"` in `docker-compose.yml` to another number like `"8082:80"` and use that
  in the browser.
- *"error during connect" / "cannot find the file specified"*: Docker Desktop isn't running.
  Start it, wait for the whale, try again.
- *Start over with an empty database*: `docker compose down -v`, then `docker compose up`.
  This only wipes Pallet Builder's data, never Sales-Rep-Activity's.

## Running it

### Docker

```bash
cp .env.example .env       # set SECRET_KEY at minimum
docker compose up --build
```

App: http://localhost:8081.

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
