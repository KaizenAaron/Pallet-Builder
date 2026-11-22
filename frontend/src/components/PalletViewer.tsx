// React wrapper around src/scene/PalletScene. Loaded lazily (three.js is large), so it's the
// default export of its own chunk; it also renders the pallet-card thumbnails and hands them back.
import { useEffect, useMemo, useRef, useState } from "react";
import type { PalletResult } from "../api";
import { MOBILE, useMediaQuery } from "../hooks";
import { legend, layerOfStep, layers, buildOrder, stepForLayer, type ColorMap, type PalletDeck, type ScenePlacement } from "../scene/layout";
import { PalletScene, WebGLUnavailableError, type ViewName } from "../scene/PalletScene";
import { renderThumbnails } from "../scene/thumbnails";
import { useFormat } from "../units";

export interface PalletViewerProps {
  cacheKey: string;
  pallets: PalletResult[];
  deck: PalletDeck;
  colors: ColorMap;
  selected: number; // pallet index (1-based)
  onSelect: (index: number) => void;
  highlight: string | null;
  onHighlight: (productId: string | null) => void;
  onThumbnails?: (urls: string[]) => void;
  stale?: boolean;
}

const VIEWS: { id: ViewName; label: string }[] = [
  { id: "iso", label: "3D" },
  { id: "front", label: "Front" },
  { id: "side", label: "Side" },
  { id: "top", label: "Top" },
];

export default function PalletViewer(props: PalletViewerProps) {
  const { pallets, deck, colors, selected, onSelect, highlight, onHighlight, onThumbnails, cacheKey, stale } = props;
  const f = useFormat();
  const mobile = useMediaQuery(MOBILE);
  const host = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<PalletScene | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewName>("iso");
  const [dims, setDims] = useState(false);
  const [hover, setHover] = useState<{ p: ScenePlacement; x: number; y: number } | null>(null);
  const pallet = pallets.find((p) => p.index === selected) ?? pallets[0];
  const ordered = useMemo(() => buildOrder(pallet?.layout ?? []), [pallet]);
  const layerList = useMemo(() => layers(ordered), [ordered]);
  const [step, setStep] = useState(ordered.length);

  // create / destroy the scene
  useEffect(() => {
    if (!host.current) return;
    try {
      const s = new PalletScene(host.current);
      sceneRef.current = s;
      s.onHover((p, x, y) => {
        if (!p) return setHover(null);
        const r = host.current!.getBoundingClientRect();
        setHover({ p, x: x - r.left, y: y - r.top });
      });
    } catch (e) {
      setError(e instanceof WebGLUnavailableError ? e.message : "Couldn't start the 3D view.");
    }
    return () => {
      sceneRef.current?.dispose();
      sceneRef.current = null;
    };
  }, []);

  // thumbnails for the pallet cards (one hidden renderer)
  useEffect(() => {
    if (!onThumbnails || error) return;
    try {
      onThumbnails(renderThumbnails(cacheKey, pallets, deck, colors));
    } catch {
      /* thumbnails are optional */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, error]);

  // load the selected pallet
  useEffect(() => {
    const s = sceneRef.current;
    if (!s || !pallet) return;
    s.load(pallet, deck, colors);
    s.setDimensions(dims, (v) => f.len(v));
    s.setHighlight(highlight);
    setStep(pallet.layout.length);
    setHover(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pallet, deck, colors]);

  useEffect(() => sceneRef.current?.setStep(step), [step]);
  useEffect(() => sceneRef.current?.setHighlight(highlight), [highlight]);
  useEffect(() => sceneRef.current?.setView(view), [view]);
  useEffect(() => sceneRef.current?.setDimensions(dims, (v) => f.len(v)), [dims, f]);

  if (!pallet) return null;
  const total = ordered.length;
  const layerNow = layerOfStep(ordered, step);
  const rows = legend(pallet.layout, colors);
  const goLayer = (l: number) => setStep(stepForLayer(ordered, Math.max(0, Math.min(layerList.length, l))));

  return (
    <section className="card viewer">
      <div className="viewer-tabs" role="tablist" aria-label="Pallets">
        {pallets.map((p) => (
          <button
            key={p.index}
            role="tab"
            aria-selected={p.index === pallet.index}
            className={p.index === pallet.index ? "on" : ""}
            onClick={() => onSelect(p.index)}
          >
            <strong>Pallet {p.index}</strong>
            {!mobile && (
              <span className="muted small">
                {f.dims(p.length, p.width, p.height)} · {f.weight(p.gross_weight, 0)}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="viewer-toolbar">
        <div className="segmented" role="group" aria-label="View">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" className={view === v.id ? "on" : ""} aria-pressed={view === v.id} onClick={() => {
              setView(v.id);
              sceneRef.current?.setView(v.id); // same view again = reset the camera
            }}>
              {v.label}
            </button>
          ))}
        </div>
        <label className="row small" style={{ gap: 6 }}>
          <input type="checkbox" checked={dims} onChange={(e) => setDims(e.target.checked)} />
          Dimensions
        </label>
        <span className="spacer" />
        {stale && <span className="badge badge-pending">showing the last calculation</span>}
      </div>

      <div className="viewer-stage">
        <div ref={host} className="viewer-canvas" style={{ height: mobile ? 360 : 480 }} />
        {error && <div className="viewer-error">{error}</div>}
        {hover && (
          <div className="viewer-tip" style={{ left: Math.min(hover.x + 14, (host.current?.clientWidth ?? 600) - 230), top: hover.y + 14 }}>
            <strong>{hover.p.sku}</strong> <span className="muted">· {hover.p.box_name}</span>
            <div className="small">{hover.p.product_name}</div>
            <div className="small">
              {f.dims(hover.p.dx, hover.p.dy, hover.p.dz)} · {f.weight(hover.p.weight)}
            </div>
            <div className="small muted">Layer {layerList.findIndex((z) => Math.abs(z - hover.p.z) < 1e-6) + 1} of {layerList.length}</div>
          </div>
        )}
        {!error && <div className="viewer-hint small muted">{mobile ? "Drag to turn · pinch to zoom" : "Drag to turn · scroll to zoom · right-drag to pan"}</div>}
      </div>

      <div className="viewer-steps">
        <div className="row" style={{ gap: 6 }}>
          <button className="btn btn-sm" aria-label="Empty pallet" onClick={() => setStep(0)} disabled={step === 0}>⏮</button>
          <button className="btn btn-sm" aria-label="Previous layer" onClick={() => goLayer(layerNow - 1)} disabled={step === 0}>◀ Layer</button>
          <button className="btn btn-sm" aria-label="Next layer" onClick={() => goLayer(step === stepForLayer(ordered, layerNow) ? layerNow + 1 : layerNow)} disabled={step >= total}>Layer ▶</button>
          <button className="btn btn-sm" aria-label="Whole pallet" onClick={() => setStep(total)} disabled={step >= total}>⏭</button>
        </div>
        <input
          type="range"
          min={0}
          max={total}
          value={Math.min(step, total)}
          onChange={(e) => setStep(Number(e.target.value))}
          aria-label="Build step"
          className="viewer-range"
        />
        <span className="small muted" style={{ whiteSpace: "nowrap" }}>
          {step >= total ? `All ${total} boxes · ${layerList.length} layer${layerList.length === 1 ? "" : "s"}` : `Box ${step} of ${total} · layer ${layerNow} of ${layerList.length}`}
        </span>
      </div>

      <div className="viewer-legend">
        {rows.map((r) => (
          <button
            key={r.product_id}
            className={`legend-chip ${highlight === r.product_id ? "on" : ""} ${highlight && highlight !== r.product_id ? "dim" : ""}`}
            onClick={() => onHighlight(highlight === r.product_id ? null : r.product_id)}
            title={highlight === r.product_id ? "Show all products" : `Highlight ${r.sku}`}
          >
            <span className="swatch" style={{ background: r.color }} />
            <strong>{r.sku}</strong>
            <span className="muted">× {r.count}</span>
          </button>
        ))}
        {highlight && (
          <button className="btn btn-sm btn-ghost" onClick={() => onHighlight(null)}>
            Show all
          </button>
        )}
      </div>
    </section>
  );
}
