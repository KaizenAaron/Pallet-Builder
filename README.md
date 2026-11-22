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
  - Both modes keep the load **flat**: each box goes where its top ends lowest, filling the space
    beside and on top of big boxes before building higher (no thin towers of small boxes). Several
    variations are tried and the best pallet wins — fewest pallets, then the lowest one.
- **Stability:** a box that isn't marked *this side up* never stands on a narrow face — its
  height may be at most 2× the narrower side it rests on, so long boxes aren't stood on end and
  flat panels aren't stood on edge. If a box is too long to lie flat on the pallet (e.g. a 50"
  box on a 48" deck), it's allowed to stand and the estimate says so; allowing an inch or two of
  overhang on the pallet type lets it lie flat.
- Every pallet is checked by an independent validator: inside the footprint (plus overhang),
  under the height and weight limits, no overlaps, at least 75 % of each box's base supported,
  upright boxes kept upright, and no box carrying more than its load limit.

## Build status

| Phase | What | Status |
|---|---|---|
| 1 | Scaffold: backend, frontend, docker compose, Alembic, CI | ✅ |
| 2 | Packing engine: Layered + constraints + freight class, golden tests | ✅ |
| 3 | Signup, companies, memberships, company switcher, invites, roles, row-level security | ✅ |
| 4 | Products, box index, pallet types, spreadsheet import/template | ✅ |
| 5 | Shipments: lines, calculate, results | ✅ |
| 6 | 3D view | ✅ |
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

**Step 6: Create your account.** Click **Create an account**, fill in your name, email,
a password (10+ characters) and your company name. Your test server has no email set up, so a
yellow box shows the verification link that would have been emailed. Click it and you're in.
The same on-screen fallback is used for password resets and invitations.

**Step 7 (optional): Make yourself a platform admin.** This unlocks the **Platform** page,
which lists every company on the server and can suspend one. In a **second** PowerShell window:

```powershell
cd "C:\Users\Loyd\Desktop\Cowork\Cerno\Pallet Builder\Dev"
docker compose exec backend python cli.py create-platform-admin you@cernogroup.com "a-strong-password" "Your Name"
```

Use the same email you signed up with to upgrade that account (the password is reset to the
one you type), or a new email to create a separate admin login.

**Step 8: Load your box index.** Go to **Products → Import spreadsheet**, click **Download
Excel template**, and fill in the *Boxes* sheet — one row per box (a fixture that ships in two
boxes gets two rows with the same SKU, Box # 1 and 2). The *Instructions* sheet explains every
column with an example. Upload it: you'll see what will be added or updated, and any rows with
problems, **before** anything is saved. Re-importing later updates matching boxes and adds new
ones; an import never deletes. You can also add or edit products one at a time, and
**Export** the whole box index back to Excel.

**Step 9: Check your pallet types** under **Pallet types** — a 48 × 40 is set up for you. Add
others (footprint, deck height, empty-pallet weight, max height, max weight, allowed overhang)
and pick the default.

**Step 10: Estimate a shipment.** Go to **Shipments → New shipment**, fill in the customer,
reference (SO / quote #) and ship date, then add products by typing a SKU or name and setting
quantities — or **Add from file** with a spreadsheet that has SKU and Qty columns. Pick the
pallet type and **Layered** or **Tightest fit**, and press **Calculate**. You get the number of
pallets and, for each one, L × W × H, gross weight (boxes + pallet), density, a suggested
freight class and the list of boxes on it. Switching the packing mode recalculates straight away.

Below the totals is the **3D view**: a tab per pallet, drag to turn it (pinch/scroll to zoom),
and buttons for **3D / Front / Side / Top** views plus a **Dimensions** toggle. The **build
steps** slider and ◀ Layer / Layer ▶ buttons show the pallet being stacked, box by box or layer
by layer — handy for the dock crew. Hover a box for its SKU, size and weight; click a product in
the legend (or a row in a pallet's box list) to highlight just that product. Each pallet card
also shows a still picture; click it to open that pallet in the viewer.

Saved estimates never change on their own: if someone later edits a product's boxes or the
pallet type, the shipment is marked **Out of date** until you press **Recalculate**.

**Step 11: Invite your team** under **Members** (copy the invitation link and open it in a
private window to play the invitee). Create a second company from the company menu at the top
right and switch between them. The 3D view arrives in the next phase.

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
- *"value is not a valid email address"* when signing up: test domains like `.test` or
  `.local` are rejected. Use a real-looking address (e.g. `name@example.com`).

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
    api/           # auth, companies, members, invites, products, pallet types, platform admin
    services/box_import.py   # box-index template, xlsx/csv import (dry run + apply), export
    services/shipments.py    # the only bridge to the engine: inputs, fingerprint, calculate
    models.py      # users, companies, memberships, invites, auth tokens, tenant tables
    tenancy.py     # get_tenant: X-Company-Id + membership check (+ RLS binding)
    rls.py         # Postgres row-level security policies and session hooks
    security.py    # passwords, sessions, link tokens
  cli.py           # create-platform-admin
  alembic/         # migrations
  tests/           # engine golden tests, auth, invites, tenant isolation, RLS (Postgres)
frontend/
  src/scene/       # framework-agnostic three.js scene: layout helpers, PalletScene, thumbnails
docker-compose.yml
```
