import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Box, type Product } from "../api";
import { MOBILE, useMediaQuery } from "../hooks";
import { Alert, Button, Card, Field, Input, useAsync } from "../components/ui";
import { fmt } from "./Products";

// Box rows are edited as strings so half-typed numbers ("12.") don't get mangled.
type NumKey = "qty_per_unit" | "units_per_box" | "length" | "width" | "height" | "weight" | "max_load_on_top";
type BoxDraft = { key: number; box_no: string; name: string; this_side_up: boolean; stackable: boolean } & Record<NumKey, string>;

let nextKey = 1;
const toDraft = (b: Box): BoxDraft => ({
  key: nextKey++,
  box_no: String(b.box_no),
  name: b.name,
  qty_per_unit: String(b.qty_per_unit),
  units_per_box: String(b.units_per_box),
  length: String(b.length),
  width: String(b.width),
  height: String(b.height),
  weight: String(b.weight),
  max_load_on_top: b.max_load_on_top ? String(b.max_load_on_top) : "",
  this_side_up: b.this_side_up,
  stackable: b.stackable,
});
const blankBox = (no: number): BoxDraft => ({
  key: nextKey++,
  box_no: String(no),
  name: "",
  qty_per_unit: "1",
  units_per_box: "1",
  length: "",
  width: "",
  height: "",
  weight: "",
  max_load_on_top: "",
  this_side_up: false,
  stackable: true,
});

function parseBoxes(drafts: BoxDraft[]): Box[] {
  return drafts.map((d, i) => {
    const label = `Box ${d.box_no || i + 1}`;
    const num = (v: string, name: string, opts: { int?: boolean; positive?: boolean; optional?: boolean } = {}) => {
      if (v.trim() === "") {
        if (opts.optional) return 0;
        throw new Error(`${label}: ${name} is required`);
      }
      const n = Number(v);
      if (!Number.isFinite(n) || n < 0 || (opts.positive && n <= 0) || (opts.int && !Number.isInteger(n)))
        throw new Error(`${label}: ${name} must be ${opts.int ? "a whole number" : "a number"}${opts.positive ? " above 0" : ""}`);
      return n;
    };
    return {
      box_no: num(d.box_no, "Box #", { int: true, positive: true }),
      name: d.name,
      qty_per_unit: num(d.qty_per_unit, "Qty per unit", { int: true, positive: true }),
      units_per_box: num(d.units_per_box, "Units per box", { int: true, positive: true }),
      length: num(d.length, "Length", { positive: true }),
      width: num(d.width, "Width", { positive: true }),
      height: num(d.height, "Height", { positive: true }),
      weight: num(d.weight, "Weight"),
      max_load_on_top: num(d.max_load_on_top, "Max load on top", { optional: true }),
      this_side_up: d.this_side_up,
      stackable: d.stackable,
    };
  });
}

export default function ProductEditPage() {
  const { id } = useParams();
  const isNew = id === "new";
  const navigate = useNavigate();
  const mobile = useMediaQuery(MOBILE);
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [boxes, setBoxes] = useState<BoxDraft[]>(isNew ? [blankBox(1)] : []);
  const [loaded, setLoaded] = useState(isNew);
  const [saved, setSaved] = useState(false);
  const { busy, error, setError, run } = useAsync();

  useEffect(() => {
    if (isNew) return;
    api<Product>(`/products/${id}`)
      .then((p) => {
        setSku(p.sku);
        setName(p.name);
        setBoxes(p.boxes.map(toDraft));
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  }, [id, isNew, setError]);

  const update = (key: number, patch: Partial<BoxDraft>) => {
    setSaved(false);
    setBoxes((bs) => bs.map((b) => (b.key === key ? { ...b, ...patch } : b)));
  };

  function save() {
    void run(async () => {
      const body = { sku, name, boxes: parseBoxes(boxes) }; // throws a readable message on bad input
      const p = isNew
        ? await api<Product>("/products", { body })
        : await api<Product>(`/products/${id}`, { method: "PUT", body });
      setBoxes(p.boxes.map(toDraft));
      setSaved(true);
      if (isNew) navigate(`/products/${p.id}`, { replace: true });
    });
  }

  if (!loaded) return error ? <Alert kind="error">{error}</Alert> : <p className="muted">Loading…</p>;

  const unitWeight = (() => {
    try {
      return parseBoxes(boxes).reduce((s, b) => s + (b.weight * b.qty_per_unit) / b.units_per_box, 0);
    } catch {
      return null;
    }
  })();

  const numInput = (b: BoxDraft, k: NumKey, label: string, placeholder?: string) => (
    <Input
      inputMode="decimal"
      aria-label={`${label} (box ${b.box_no})`}
      placeholder={placeholder}
      value={b[k]}
      onChange={(e) => update(b.key, { [k]: e.target.value } as Partial<BoxDraft>)}
      style={{ minWidth: 60, maxWidth: mobile ? undefined : 84 }}
    />
  );

  return (
    <>
      <div className="page-head">
        <div>
          <p className="small" style={{ margin: 0 }}>
            <Link to="/products">← Products</Link>
          </p>
          <h1>{isNew ? "New product" : sku}</h1>
        </div>
        <span className="spacer" />
        {!isNew && (
          <Button
            variant="danger"
            onClick={() =>
              confirm(`Delete ${sku}? This can't be undone.`) &&
              run(async () => {
                await api(`/products/${id}`, { method: "DELETE" });
                navigate("/products");
              })
            }
          >
            Delete product
          </Button>
        )}
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {saved && <Alert kind="ok">Saved.</Alert>}

      <Card title="Product">
        <div className="grid-2">
          <Field label="SKU" htmlFor="sku" hint="Matches the Internal Reference in Odoo.">
            <Input id="sku" required value={sku} onChange={(e) => (setSaved(false), setSku(e.target.value))} />
          </Field>
          <Field label="Name" htmlFor="pname">
            <Input id="pname" value={name} onChange={(e) => (setSaved(false), setName(e.target.value))} />
          </Field>
        </div>
      </Card>

      <Card
        title="Boxes"
        actions={
          unitWeight != null && boxes.length > 0 ? <span className="muted small">{fmt(unitWeight)} lb per unit</span> : null
        }
      >
        <p className="muted small">
          One unit ships in <strong>all</strong> of these boxes. Sizes in inches, weights in pounds (packed box). “Units per box”
          is for small items packed several to a carton.
        </p>
        {boxes.length === 0 && <Alert kind="warn">No boxes yet — this product will be left out of estimates.</Alert>}

        {mobile ? (
          boxes.map((b) => (
            <div key={b.key} className="card" style={{ padding: 14, marginBottom: 10, boxShadow: "none" }}>
              <div className="row" style={{ marginBottom: 8 }}>
                <strong>Box</strong>
                <div style={{ width: 70 }}>
                  <Input aria-label="Box #" value={b.box_no} onChange={(e) => update(b.key, { box_no: e.target.value })} />
                </div>
                <span className="spacer" />
                <Button size="sm" variant="danger" onClick={() => setBoxes((bs) => bs.filter((x) => x.key !== b.key))}>
                  Remove
                </Button>
              </div>
              <Field label="Box name">
                <Input value={b.name} placeholder={`Box ${b.box_no}`} onChange={(e) => update(b.key, { name: e.target.value })} />
              </Field>
              <div className="grid-3">
                <Field label="L (in)">{numInput(b, "length", "Length")}</Field>
                <Field label="W (in)">{numInput(b, "width", "Width")}</Field>
                <Field label="H (in)">{numInput(b, "height", "Height")}</Field>
                <Field label="Weight (lb)">{numInput(b, "weight", "Weight")}</Field>
                <Field label="Qty / unit">{numInput(b, "qty_per_unit", "Qty per unit")}</Field>
                <Field label="Units / box">{numInput(b, "units_per_box", "Units per box")}</Field>
              </div>
              <Field label="Max load on top (lb)">{numInput(b, "max_load_on_top", "Max load on top", "no limit")}</Field>
              <div className="row">
                <label className="row small" style={{ gap: 6 }}>
                  <input type="checkbox" checked={b.this_side_up} onChange={(e) => update(b.key, { this_side_up: e.target.checked })} />
                  This side up
                </label>
                <label className="row small" style={{ gap: 6 }}>
                  <input type="checkbox" checked={b.stackable} onChange={(e) => update(b.key, { stackable: e.target.checked })} />
                  Stackable
                </label>
              </div>
            </div>
          ))
        ) : (
          boxes.length > 0 && (
            <div className="table-wrap">
              <table className="table table-edit">
                <thead>
                  <tr>
                    <th style={{ width: 64 }}>Box #</th>
                    <th>Box name</th>
                    <th>L (in)</th>
                    <th>W (in)</th>
                    <th>H (in)</th>
                    <th>Weight (lb)</th>
                    <th title="How many of this box one unit needs">Qty / unit</th>
                    <th title="Units of the product that fit in one box">Units / box</th>
                    <th title="Most weight that may rest on this box">Max load (lb)</th>
                    <th title="May turn but never tip over">Upright</th>
                    <th title="Other boxes may go on top">Stackable</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {boxes.map((b) => (
                    <tr key={b.key}>
                      <td style={{ width: 64 }}>
                        <Input aria-label="Box #" value={b.box_no} onChange={(e) => update(b.key, { box_no: e.target.value })} />
                      </td>
                      <td style={{ minWidth: 200 }}>
                        <Input aria-label={`Name (box ${b.box_no})`} value={b.name} placeholder={`Box ${b.box_no}`} onChange={(e) => update(b.key, { name: e.target.value })} />
                      </td>
                      <td>{numInput(b, "length", "Length")}</td>
                      <td>{numInput(b, "width", "Width")}</td>
                      <td>{numInput(b, "height", "Height")}</td>
                      <td>{numInput(b, "weight", "Weight")}</td>
                      <td>{numInput(b, "qty_per_unit", "Qty per unit")}</td>
                      <td>{numInput(b, "units_per_box", "Units per box")}</td>
                      <td>{numInput(b, "max_load_on_top", "Max load on top", "no limit")}</td>
                      <td style={{ textAlign: "center" }}>
                        <input type="checkbox" aria-label={`This side up (box ${b.box_no})`} checked={b.this_side_up} onChange={(e) => update(b.key, { this_side_up: e.target.checked })} />
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <input type="checkbox" aria-label={`Stackable (box ${b.box_no})`} checked={b.stackable} onChange={(e) => update(b.key, { stackable: e.target.checked })} />
                      </td>
                      <td>
                        <Button size="sm" variant="ghost" aria-label={`Remove box ${b.box_no}`} onClick={() => (setSaved(false), setBoxes((bs) => bs.filter((x) => x.key !== b.key)))}>
                          ✕
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <Button
            onClick={() => {
              setSaved(false);
              const max = boxes.reduce((m, b) => Math.max(m, Number(b.box_no) || 0), 0);
              setBoxes([...boxes, blankBox(max + 1)]);
            }}
          >
            + Add box
          </Button>
          <span className="spacer" />
          <Button variant="primary" disabled={busy || !sku.trim()} onClick={save}>
            {busy ? "Saving…" : isNew ? "Create product" : "Save changes"}
          </Button>
        </div>
      </Card>
    </>
  );
}
