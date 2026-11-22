import { useEffect, useRef, useState } from "react";
import { api, type ProductSummary } from "../api";

/** Type-ahead search over the company's products (SKU or name). */
export default function ProductPicker({
  onPick,
  exclude = [],
  autoFocus,
}: {
  onPick: (p: ProductSummary) => void;
  exclude?: number[];
  autoFocus?: boolean;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ProductSummary[]>([]);
  const [itemsFor, setItemsFor] = useState<string | null>(null); // query the items belong to
  const [hl, setHl] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      api<{ items: ProductSummary[] }>(`/products?${new URLSearchParams({ q, limit: "12" })}`)
        .then((r) => {
          setItems(r.items);
          setItemsFor(q);
          setHl(0);
        })
        .catch(() => setItems([]));
    }, 150);
    return () => clearTimeout(t);
  }, [q, open]);

  // Only show (and let Enter pick from) results for what's typed now — never a previous search's.
  const fresh = itemsFor === q;
  const visible = fresh ? items.filter((p) => !exclude.includes(p.id)) : [];

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  function pick(p: ProductSummary) {
    onPick(p);
    setQ("");
    setItemsFor(null);
    setOpen(false);
  }

  return (
    <div className="picker" ref={ref}>
      <input
        className="input"
        placeholder="Add a product — type SKU or name…"
        aria-label="Add product"
        value={q}
        autoFocus={autoFocus}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHl((h) => Math.min(h + 1, visible.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHl((h) => Math.max(h - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            if (visible[hl]) pick(visible[hl]);
          } else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <div className="picker-pop" role="listbox">
          {!fresh ? (
            <div className="muted small" style={{ padding: 10 }}>
              Searching…
            </div>
          ) : visible.length === 0 ? (
            <div className="muted small" style={{ padding: 10 }}>
              {q ? "No matching products." : items.length ? "All products are already added." : "No products yet — add them under Products."}
            </div>
          ) : (
            visible.map((p, i) => (
              <button
                key={p.id}
                type="button"
                className={i === hl ? "hl" : ""}
                onMouseEnter={() => setHl(i)}
                onClick={() => pick(p)}
              >
                <strong style={{ minWidth: 110 }}>{p.sku}</strong>
                <span className="muted" style={{ flex: 1 }}>
                  {p.name}
                </span>
                {p.box_count === 0 && <span className="badge badge-pending">no boxes</span>}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
