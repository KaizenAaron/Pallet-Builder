import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, Field, Input, Select, useAsync } from "../components/ui";

interface CompanyForm {
  name: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  phone: string;
  units: "imperial" | "metric";
}

export default function CompanySettingsPage() {
  const { company, refresh } = useAuth();
  const [form, setForm] = useState<CompanyForm | null>(null);
  const [saved, setSaved] = useState(false);
  const { busy, error, setError, run } = useAsync();

  useEffect(() => {
    if (company) api<CompanyForm>("/company").then(setForm).catch((e: Error) => setError(e.message));
  }, [company, setError]);

  if (!form) return error ? <Alert kind="error">{error}</Alert> : <p className="muted">Loading…</p>;
  const set = (k: keyof CompanyForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setSaved(false);
    setForm({ ...form, [k]: e.target.value });
  };

  return (
    <>
      <div className="page-head">
        <h1>Company settings</h1>
      </div>
      <Card>
        {error && <Alert kind="error">{error}</Alert>}
        {saved && <Alert kind="ok">Saved.</Alert>}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const { name, address_line1, address_line2, city, state, postal_code, country, phone, units } = form;
              await api("/company", {
                method: "PUT",
                body: { name, address_line1, address_line2, city, state, postal_code, country, phone, units },
              });
              await refresh();
              setSaved(true);
            });
          }}
        >
          <Field label="Company name" htmlFor="name">
            <Input id="name" required value={form.name} onChange={set("name")} />
          </Field>
          <div className="grid-2">
            <Field label="Address" htmlFor="a1">
              <Input id="a1" value={form.address_line1} onChange={set("address_line1")} />
            </Field>
            <Field label="Address line 2" htmlFor="a2">
              <Input id="a2" value={form.address_line2} onChange={set("address_line2")} />
            </Field>
            <Field label="City" htmlFor="city">
              <Input id="city" value={form.city} onChange={set("city")} />
            </Field>
            <Field label="State / region" htmlFor="state">
              <Input id="state" value={form.state} onChange={set("state")} />
            </Field>
            <Field label="Postal code" htmlFor="zip">
              <Input id="zip" value={form.postal_code} onChange={set("postal_code")} />
            </Field>
            <Field label="Country" htmlFor="country">
              <Input id="country" value={form.country} onChange={set("country")} />
            </Field>
            <Field label="Phone" htmlFor="phone">
              <Input id="phone" value={form.phone} onChange={set("phone")} />
            </Field>
            <Field label="Units" htmlFor="units" hint="How sizes and weights are displayed. Metric display arrives with shipments.">
              <Select id="units" value={form.units} onChange={set("units")}>
                <option value="imperial">Inches & pounds</option>
                <option value="metric">Centimeters & kilograms</option>
              </Select>
            </Field>
          </div>
          <Button variant="primary" disabled={busy}>
            Save
          </Button>
        </form>
      </Card>
    </>
  );
}
