import { useEffect, useState } from "react";
import { api, type PalletType } from "../api";
import { useAuth } from "../auth";
import { MOBILE, useMediaQuery } from "../hooks";
import { Alert, Badge, Button, Card, Field, Input, useAsync } from "../components/ui";

type FormKey = "length" | "width" | "deck_height" | "tare_weight" | "max_total_height" | "max_gross_weight" | "max_overhang";
type Form = { name: string } & Record<FormKey, string>;

const NUMERIC: { key: FormKey; label: string; hint?: string }[] = [
  { key: "length", label: "Length (in)" },
  { key: "width", label: "Width (in)" },
  { key: "deck_height", label: "Deck height (in)", hint: "Height of the empty pallet." },
  { key: "tare_weight", label: "Tare weight (lb)", hint: "Weight of the empty pallet." },
  { key: "max_total_height", label: "Max total height (in)", hint: "Floor to top of the load, deck included." },
  { key: "max_gross_weight", label: "Max gross weight (lb)", hint: "Load plus pallet." },
  { key: "max_overhang", label: "Allowed overhang (in)", hint: "Per side. 0 = load stays on the deck." },
];

const EMPTY: Form = {
  name: "",
  length: "48",
  width: "40",
  deck_height: "5.5",
  tare_weight: "45",
  max_total_height: "72",
  max_gross_weight: "2500",
  max_overhang: "0",
};

const toForm = (p: PalletType): Form => ({
  name: p.name,
  ...(Object.fromEntries(NUMERIC.map(({ key }) => [key, String(p[key])])) as Record<FormKey, string>),
});

export default function PalletTypesPage() {
  const { company } = useAuth();
  const mobile = useMediaQuery(MOBILE);
  const [rows, setRows] = useState<PalletType[]>([]);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const { busy, error, setError, run } = useAsync();
  const isAdmin = company?.role === "owner" || company?.role === "admin";

  useEffect(() => {
    if (company) api<PalletType[]>("/pallet-types").then(setRows).catch((e: Error) => setError(e.message));
  }, [company, setError]);

  function save() {
    void run(async () => {
      const body: Record<string, unknown> = { name: form.name };
      for (const { key, label } of NUMERIC) {
        const n = Number(form[key]);
        if (form[key].trim() === "" || !Number.isFinite(n)) throw new Error(`${label} must be a number`);
        body[key] = n;
      }
      if (editing === "new") await api("/pallet-types", { body });
      else await api(`/pallet-types/${editing}`, { method: "PUT", body });
      setRows(await api<PalletType[]>("/pallet-types"));
      setEditing(null);
    });
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pallet types</h1>
          <p className="muted" style={{ margin: 0 }}>
            Footprint and limits used when building pallets. The default is preselected on new shipments.
          </p>
        </div>
        <span className="spacer" />
        {isAdmin && editing === null && (
          <Button
            variant="primary"
            onClick={() => {
              setForm(EMPTY);
              setEditing("new");
            }}
          >
            + Add pallet type
          </Button>
        )}
      </div>
      {error && <Alert kind="error">{error}</Alert>}

      {editing !== null && (
        <Card title={editing === "new" ? "New pallet type" : `Edit ${form.name}`}>
          <Field label="Name" htmlFor="pt-name">
            <Input id="pt-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. 48 × 40 GMA" />
          </Field>
          <div className="grid-2">
            {NUMERIC.map(({ key, label, hint }) => (
              <Field key={key} label={label} htmlFor={`pt-${key}`} hint={hint}>
                <Input id={`pt-${key}`} inputMode="decimal" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
              </Field>
            ))}
          </div>
          <div className="row">
            <Button variant="primary" disabled={busy || !form.name.trim()} onClick={save}>
              Save
            </Button>
            <Button onClick={() => setEditing(null)}>Cancel</Button>
          </div>
        </Card>
      )}

      <Card>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th className="num">Footprint (in)</th>
                {!mobile && <th className="num">Deck (in)</th>}
                {!mobile && <th className="num">Tare (lb)</th>}
                <th className="num">Max height (in)</th>
                <th className="num">Max gross (lb)</th>
                {!mobile && <th className="num">Overhang (in)</th>}
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td>
                    {p.name} {p.is_default && <Badge tone="admin">default</Badge>}
                  </td>
                  <td className="num">
                    {p.length} × {p.width}
                  </td>
                  {!mobile && <td className="num">{p.deck_height}</td>}
                  {!mobile && <td className="num">{p.tare_weight}</td>}
                  <td className="num">{p.max_total_height}</td>
                  <td className="num">{p.max_gross_weight.toLocaleString()}</td>
                  {!mobile && <td className="num">{p.max_overhang}</td>}
                  {isAdmin && (
                    <td className="num">
                      <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                        {!p.is_default && (
                          <Button size="sm" onClick={() => run(async () => setRows(await api<PalletType[]>(`/pallet-types/${p.id}/default`, { method: "POST" })))}>
                            Make default
                          </Button>
                        )}
                        <Button
                          size="sm"
                          onClick={() => {
                            setForm(toForm(p));
                            setEditing(p.id);
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          disabled={rows.length === 1}
                          title={rows.length === 1 ? "You need at least one pallet type" : undefined}
                          onClick={() =>
                            confirm(`Delete ${p.name}?`) &&
                            run(async () => setRows(await api<PalletType[]>(`/pallet-types/${p.id}`, { method: "DELETE" })))
                          }
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!isAdmin && <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>Only admins can change pallet types.</p>}
      </Card>
    </>
  );
}
