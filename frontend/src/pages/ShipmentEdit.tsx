import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  apiUpload,
  type PackingMode,
  type PalletResult,
  type PalletType,
  type ShipmentDetail,
} from "../api";
import { MOBILE, useMediaQuery } from "../hooks";
import ProductPicker from "../components/ProductPicker";
import { Alert, Badge, Button, Card, Field, Input, Select, useAsync } from "../components/ui";
import { useFormat } from "../units";
import { StatusBadge } from "./Shipments";
import { colorMap, type ColorMap } from "../scene/layout";

const PalletViewer = lazy(() => import("../components/PalletViewer"));

interface LineDraft {
  key: number;
  product_id: number;
  sku: string;
  product_name: string;
  quantity: string;
  box_count: number;
  product_deleted?: boolean;
}
interface Header {
  customer: string;
  reference: string;
  ship_date: string;
  notes: string;
  pallet_selection: "auto" | "fixed";
  pallet_type_id: number | null;
  packing_mode: PackingMode;
}

let nextKey = 1;
const EMPTY_HEADER: Header = {
  customer: "",
  reference: "",
  ship_date: "",
  notes: "",
  pallet_selection: "auto",
  pallet_type_id: null,
  packing_mode: "layered",
};

export default function ShipmentEditPage() {
  const { id } = useParams();
  const isNew = id === "new";
  const navigate = useNavigate();
  const mobile = useMediaQuery(MOBILE);
  const f = useFormat();
  const [shipment, setShipment] = useState<ShipmentDetail | null>(null);
  const [header, setHeader] = useState<Header>(EMPTY_HEADER);
  const [lines, setLines] = useState<LineDraft[]>([]);
  const [palletTypes, setPalletTypes] = useState<PalletType[]>([]);
  const [dirty, setDirty] = useState(false);
  const [selectedPallet, setSelectedPallet] = useState(1);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [thumbs, setThumbs] = useState<string[]>([]);
  const viewerRef = useRef<HTMLDivElement>(null);
  const [fileNote, setFileNote] = useState<{ unknown: string[]; errors: { row: number; message: string }[] } | null>(null);
  const { busy, error, setError, run } = useAsync();

  function load(s: ShipmentDetail) {
    setShipment(s);
    setHeader({
      customer: s.customer,
      reference: s.reference,
      ship_date: s.ship_date ?? "",
      notes: s.notes,
      pallet_selection: s.pallet_selection,
      pallet_type_id: s.pallet_type_id,
      packing_mode: s.packing_mode,
    });
    setLines(
      s.lines.map((l) => ({
        key: nextKey++,
        product_id: l.product_id ?? -1,
        sku: l.sku,
        product_name: l.product_name,
        quantity: String(l.quantity),
        box_count: l.box_count,
        product_deleted: l.product_deleted,
      })),
    );
    setDirty(false);
  }

  useEffect(() => {
    api<PalletType[]>("/pallet-types")
      .then((pts) => {
        setPalletTypes(pts);

      })
      .catch((e: Error) => setError(e.message));
    if (!isNew) api<ShipmentDetail>(`/shipments/${id}`).then(load).catch((e: Error) => setError(e.message));
  }, [id, isNew, setError]);

  const setH = <K extends keyof Header>(k: K, v: Header[K]) => {
    setHeader((h) => ({ ...h, [k]: v }));
    setDirty(true);
  };

  function body(h: Header = header) {
    const parsed = lines
      .filter((l) => !l.product_deleted)
      .map((l) => {
        const q = Number(l.quantity);
        if (!Number.isInteger(q) || q < 1) throw new Error(`${l.sku}: quantity must be a whole number of at least 1`);
        return { product_id: l.product_id, quantity: q };
      });
    return {
      customer: h.customer,
      reference: h.reference,
      ship_date: h.ship_date || null,
      notes: h.notes,
      pallet_selection: h.pallet_selection,
      pallet_type_id: h.pallet_type_id,
      packing_mode: h.packing_mode,
      lines: parsed,
    };
  }

  async function persist(h: Header = header): Promise<ShipmentDetail> {
    if (isNew || !shipment) {
      const s = await api<ShipmentDetail>("/shipments", { body: body(h) });
      navigate(`/shipments/${s.id}`, { replace: true });
      return s;
    }
    return api<ShipmentDetail>(`/shipments/${shipment.id}`, { method: "PUT", body: body(h) });
  }

  function save() {
    void run(async () => load(await persist()));
  }

  function saveAndCalculate(h: Header = header) {
    void run(async () => {
      let s = dirty || isNew || h !== header ? await persist(h) : shipment!;
      s = await api<ShipmentDetail>(`/shipments/${s.id}/calculate`, { method: "POST" });
      load(s);
    });
  }

  function switchMode(mode: PackingMode) {
    if (mode === header.packing_mode) return;
    const h = { ...header, packing_mode: mode };
    setHeader(h);
    if (lines.length && !isNew) saveAndCalculate(h);
    else setDirty(true);
  }

  function addLine(p: { id: number; sku: string; name: string; box_count: number }, qty = 1) {
    setDirty(true);
    setLines((ls) => {
      const existing = ls.find((l) => l.product_id === p.id);
      if (existing)
        return ls.map((l) => (l === existing ? { ...l, quantity: String((Number(l.quantity) || 0) + qty) } : l));
      return [...ls, { key: nextKey++, product_id: p.id, sku: p.sku, product_name: p.name, quantity: String(qty), box_count: p.box_count }];
    });
  }

  async function addFromFile(file: File) {
    await run(async () => {
      const r = await apiUpload<{
        lines: { product_id: number; sku: string; product_name: string; quantity: number }[];
        unknown_skus: string[];
        errors: { row: number; message: string }[];
      }>("/shipments/parse-lines", file);
      // box counts come from the products list
      const counts = new Map<number, number>();
      if (r.lines.length) {
        const all = await api<{ items: { id: number; box_count: number }[] }>(`/products?limit=1000`);
        all.items.forEach((p) => counts.set(p.id, p.box_count));
      }
      r.lines.forEach((l) => addLine({ id: l.product_id, sku: l.sku, name: l.product_name, box_count: counts.get(l.product_id) ?? 1 }, l.quantity));
      setFileNote({ unknown: r.unknown_skus, errors: r.errors });
    });
  }

  const missingBoxes = lines.filter((l) => !l.product_deleted && l.box_count === 0);
  const results = shipment?.results ?? null;
  const showStale = !!shipment && shipment.status === "calculated" && (shipment.stale || dirty);
  const ptName = useMemo(() => palletTypes.find((p) => p.id === header.pallet_type_id)?.name, [palletTypes, header.pallet_type_id]);
  // Product colors follow the saved shipment's line order (same rule as the PDF report).
  const colors: ColorMap = useMemo(
    () => colorMap((shipment?.lines ?? []).map((l) => (l.product_id != null ? String(l.product_id) : `deleted:${l.sku}`))),
    [shipment],
  );
  const deck = useMemo(() => {
    const ps = shipment?.results?.pallet_spec;
    return { length: ps?.length ?? 48, width: ps?.width ?? 40, deck_height: ps?.deck_height ?? 5.5 };
  }, [shipment]);
  // each pallet is drawn on its own deck (automatic selection can mix pallet types)
  const viewerPallets = useMemo(
    () =>
      (shipment?.results?.pallets ?? []).map((p) =>
        p.pallet_spec?.length ? { ...p, deck: { length: p.pallet_spec.length, width: p.pallet_spec.width, deck_height: p.pallet_spec.deck_height } } : p,
      ),
    [shipment],
  );
  const cacheKey = `${shipment?.id}|${shipment?.calculated_at}`;
  useEffect(() => {
    setSelectedPallet(1);
    setHighlight(null);
    setThumbs([]);
  }, [cacheKey]);
  function openPallet(index: number) {
    setSelectedPallet(index);
    viewerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (!isNew && !shipment) return error ? <Alert kind="error">{error}</Alert> : <p className="muted">Loading…</p>;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="small" style={{ margin: 0 }}>
            <Link to="/shipments">← Shipments</Link>
          </p>
          <h1>
            {isNew ? "New shipment" : shipment!.number} {shipment && <StatusBadge s={{ status: shipment.status, stale: showStale }} />}
          </h1>
        </div>
        <span className="spacer" />
        {shipment && (
          <div className="row">
            <Button
              onClick={() =>
                run(async () => {
                  const s = await api<ShipmentDetail>(`/shipments/${shipment.id}/duplicate`, { method: "POST" });
                  navigate(`/shipments/${s.id}`);
                })
              }
            >
              Duplicate
            </Button>
            <Button
              variant="danger"
              onClick={() =>
                confirm(`Delete ${shipment.number}?`) &&
                run(async () => {
                  await api(`/shipments/${shipment.id}`, { method: "DELETE" });
                  navigate("/shipments");
                })
              }
            >
              Delete
            </Button>
          </div>
        )}
      </div>
      {error && <Alert kind="error">{error}</Alert>}

      <Card title="Details">
        <div className="grid-2">
          <Field label="Customer" htmlFor="customer">
            <Input id="customer" value={header.customer} onChange={(e) => setH("customer", e.target.value)} />
          </Field>
          <Field label="Reference" htmlFor="reference" hint="Sales order or quote number.">
            <Input id="reference" value={header.reference} onChange={(e) => setH("reference", e.target.value)} />
          </Field>
          <Field label="Ship date" htmlFor="ship_date">
            <Input id="ship_date" type="date" value={header.ship_date} onChange={(e) => setH("ship_date", e.target.value)} />
          </Field>
          <Field label="Notes" htmlFor="notes">
            <Input id="notes" value={header.notes} onChange={(e) => setH("notes", e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card
        title={`Products (${lines.length})`}
        actions={
          <label className="btn btn-sm" title="A .csv or .xlsx with SKU and Qty columns">
            Add from file
            <input
              type="file"
              accept=".csv,.xlsx"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) void addFromFile(file);
              }}
            />
          </label>
        }
      >
        {fileNote && (fileNote.unknown.length > 0 || fileNote.errors.length > 0) && (
          <Alert kind="warn">
            {fileNote.unknown.length > 0 && (
              <div>
                Not in your products (skipped): <strong>{fileNote.unknown.join(", ")}</strong>
              </div>
            )}
            {fileNote.errors.map((e) => (
              <div key={e.row}>
                Row {e.row}: {e.message}
              </div>
            ))}
          </Alert>
        )}
        {missingBoxes.length > 0 && (
          <Alert kind="warn">
            {missingBoxes.map((l) => l.sku).join(", ")} {missingBoxes.length === 1 ? "has" : "have"} no box data and will be left
            out of the estimate.{" "}
            {missingBoxes.length === 1 && <Link to={`/products/${missingBoxes[0].product_id}`}>Add boxes</Link>}
          </Alert>
        )}
        {lines.length > 0 && (
          <div className="table-wrap" style={{ marginBottom: 12 }}>
            <table className="table table-edit">
              <thead>
                <tr>
                  <th>SKU</th>
                  {!mobile && <th>Product</th>}
                  <th style={{ width: 120 }}>Quantity</th>
                  <th style={{ width: 40 }} />
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.key}>
                    <td>
                      {l.product_deleted ? (
                        <span className="muted">{l.sku}</span>
                      ) : (
                        <Link to={`/products/${l.product_id}`}>
                          <strong>{l.sku}</strong>
                        </Link>
                      )}{" "}
                      {l.product_deleted ? <Badge tone="expired">deleted</Badge> : l.box_count === 0 && <Badge tone="pending">no boxes</Badge>}
                      {mobile && <div className="muted small">{l.product_name}</div>}
                    </td>
                    {!mobile && <td>{l.product_name}</td>}
                    <td>
                      <Input
                        inputMode="numeric"
                        aria-label={`Quantity for ${l.sku}`}
                        value={l.quantity}
                        disabled={l.product_deleted}
                        onChange={(e) => {
                          setDirty(true);
                          setLines((ls) => ls.map((x) => (x.key === l.key ? { ...x, quantity: e.target.value } : x)));
                        }}
                      />
                    </td>
                    <td>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Remove ${l.sku}`}
                        onClick={() => {
                          setDirty(true);
                          setLines((ls) => ls.filter((x) => x.key !== l.key));
                        }}
                      >
                        ✕
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ProductPicker
          onPick={(p) => addLine(p)}
          exclude={lines.map((l) => l.product_id)}
          autoFocus={isNew}
        />
      </Card>

      <Card title="Pallets">
        <div className="row" style={{ alignItems: "flex-end", gap: 16 }}>
          <div style={{ flex: "1 1 220px", maxWidth: 320 }}>
            <Field label="Pallet type" htmlFor="pt">
              <Select
                id="pt"
                value={header.pallet_selection === "auto" ? "auto" : String(header.pallet_type_id ?? "")}
                onChange={(e) => {
                  const v = e.target.value;
                  setHeader((h) =>
                    v === "auto"
                      ? { ...h, pallet_selection: "auto" }
                      : { ...h, pallet_selection: "fixed", pallet_type_id: v ? Number(v) : null },
                  );
                  setDirty(true);
                }}
              >
                <option value="auto">Automatic — best fit</option>
                {header.pallet_selection === "fixed" && header.pallet_type_id == null && (
                  <option value="">(deleted pallet type)</option>
                )}
                {palletTypes.map((p) => (
                  <option key={p.id} value={p.id}>
                    Only {p.name}
                    {p.is_default ? " (default)" : ""}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="field">
            <label>Packing</label>
            <div className="segmented" role="group" aria-label="Packing mode">
              {(["layered", "tightest"] as PackingMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={header.packing_mode === m ? "on" : ""}
                  aria-pressed={header.packing_mode === m}
                  disabled={busy}
                  onClick={() => switchMode(m)}
                >
                  {m === "layered" ? "Layered" : "Tightest fit"}
                </button>
              ))}
            </div>
          </div>
          <span className="spacer" />
          <div className="field row">
            {(dirty || isNew) && (
              <Button disabled={busy} onClick={save}>
                Save
              </Button>
            )}
            <Button variant="primary" disabled={busy || lines.length === 0} onClick={() => saveAndCalculate()}>
              {busy ? "Calculating…" : results ? "Save & recalculate" : "Calculate"}
            </Button>
          </div>
        </div>
        {header.pallet_selection === "auto" && (
          <p className="small muted" style={{ marginTop: -4 }}>
            Automatic picks the pallet for each pallet from your pallet types (those ticked “Use in automatic
            selection”): fewest pallets first, then the least floor space — a bigger pallet only where a box needs it.
          </p>
        )}
        <p className="small muted" style={{ marginTop: -4, marginBottom: 0 }}>
          {header.packing_mode === "layered"
            ? "Layered: full layers of one box type, heaviest at the bottom — easy to build on the dock."
            : "Tightest fit: mixes boxes freely to use as few pallets as possible (never more than Layered)."}
        </p>
      </Card>

      {showStale && (
        <Alert kind="warn">
          <strong>Out of date.</strong>{" "}
          {dirty ? "You've made changes since this was calculated." : "Box sizes, the pallet type or this shipment changed since it was calculated."}{" "}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              saveAndCalculate();
            }}
          >
            Recalculate
          </a>
        </Alert>
      )}

      {results && shipment && (
        <>
          <div className="stats" style={{ marginTop: 16 }}>
            <Card>
              <div className="stat">
                <span className="stat-value">{results.pallet_count}</span>
                <span className="stat-label">Pallet{results.pallet_count === 1 ? "" : "s"}</span>
              </div>
            </Card>
            <Card>
              <div className="stat">
                <span className="stat-value">{f.weight(results.total_gross_weight, 0)}</span>
                <span className="stat-label">Total gross weight</span>
              </div>
            </Card>
            <Card>
              <div className="stat">
                <span className="stat-value">{f.volume(results.total_cubic_feet)}</span>
                <span className="stat-label">Total volume</span>
              </div>
            </Card>
          </div>
          <p className="small muted">
            {shipment.calculated_mode === "tightest" ? "Tightest fit" : "Layered"} · {results.pallet_spec?.name ?? ptName} ·
            calculated {shipment.calculated_at ? new Date(shipment.calculated_at).toLocaleString() : ""}
          </p>
          {results.warnings.length > 0 && (
            <Alert kind="warn">
              {results.warnings.map((w, i) => (
                <div key={i}>{w}</div>
              ))}
            </Alert>
          )}
          {results.pallets.length > 0 && (
            <div ref={viewerRef} style={{ scrollMarginTop: 72, marginBottom: 16 }}>
              <Suspense fallback={<div className="card muted">Loading 3D view…</div>}>
                <PalletViewer
                  cacheKey={cacheKey}
                  pallets={viewerPallets}
                  deck={deck}
                  colors={colors}
                  selected={selectedPallet}
                  onSelect={setSelectedPallet}
                  highlight={highlight}
                  onHighlight={setHighlight}
                  onThumbnails={setThumbs}
                  stale={showStale}
                />
              </Suspense>
            </div>
          )}
          <div className="pallet-grid">
            {results.pallets.map((p, i) => (
              <PalletCard
                key={p.index}
                p={p}
                count={results.pallet_count}
                thumb={thumbs[i]}
                colors={colors}
                selected={p.index === selectedPallet}
                highlight={highlight}
                onOpen={() => openPallet(p.index)}
                onHighlight={(pid) => {
                  setSelectedPallet(p.index);
                  setHighlight(highlight === pid ? null : pid);
                }}
              />
            ))}
          </div>
        </>
      )}
    </>
  );
}

function PalletCard({
  p,
  count,
  thumb,
  colors,
  selected,
  highlight,
  onOpen,
  onHighlight,
}: {
  p: PalletResult;
  count: number;
  thumb?: string;
  colors: ColorMap;
  selected: boolean;
  highlight: string | null;
  onOpen: () => void;
  onHighlight: (productId: string) => void;
}) {
  const f = useFormat();
  const boxes = p.box_summary.reduce((s, b) => s + b.count, 0);
  return (
    <section className={`pallet-card ${selected ? "selected" : ""}`}>
      <div className="row" style={{ marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>
          Pallet {p.index} <span className="muted small">of {count}</span>
        </h2>
        {p.pallet_spec?.name && <Badge tone="admin">{p.pallet_spec.name}</Badge>}
        <span className="spacer" />
        <Badge>{boxes} boxes</Badge>
      </div>
      <button className="pallet-thumb" onClick={onOpen} aria-label={`Open pallet ${p.index} in the 3D view`}>
        {thumb ? <img src={thumb} alt={`Pallet ${p.index}`} /> : <span className="muted small">3D preview…</span>}
      </button>
      <dl className="kv">
        <dt>L × W × H</dt>
        <dd>{f.dims(p.length, p.width, p.height)}</dd>
        <dt>Gross weight</dt>
        <dd>
          {f.weight(p.gross_weight)} <span className="muted small">({f.weight(p.net_weight)} boxes + pallet)</span>
        </dd>
        <dt>Volume</dt>
        <dd>{f.volume(p.cubic_feet)}</dd>
        <dt>Density</dt>
        <dd>{f.density(p.density)}</dd>
        <dt>Freight class</dt>
        <dd>
          {p.freight_class} <span className="muted small">(suggested, by density)</span>
        </dd>
      </dl>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Box</th>
              <th className="num">Count</th>
              <th className="num">Weight</th>
            </tr>
          </thead>
          <tbody>
            {p.box_summary.map((b) => (
              <tr
                key={`${b.product_id}-${b.box_no}`}
                className={`clickable ${highlight === b.product_id ? "row-on" : ""}`}
                onClick={() => onHighlight(b.product_id)}
                title="Highlight in the 3D view"
              >
                <td>
                  <span className="swatch" style={{ background: colors.get(b.product_id) ?? "#999" }} /> {b.sku}
                </td>
                <td className="small">
                  {b.box_name} <span className="muted">· {f.dims(b.dims[0], b.dims[1], b.dims[2])}</span>
                </td>
                <td className="num">{b.count}</td>
                <td className="num">{f.weight(b.weight)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
