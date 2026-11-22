// Pure helpers for the 3D view (no three.js, no React) — unit-tested in layout.test.ts.
// Shared by the React app now and the Odoo OWL widget in stage 2.

/** One box as stored by the engine (Placement.to_dict()). Inches/pounds; z is up from the deck. */
export interface ScenePlacement {
  uid: number;
  product_id: string;
  sku: string;
  product_name: string;
  box_no: number;
  box_name: string;
  x: number;
  y: number;
  z: number;
  dx: number;
  dy: number;
  dz: number;
  weight: number;
}

export interface ScenePallet {
  index: number;
  length: number; // overall, overhang included
  width: number;
  height: number; // deck included
  layout: ScenePlacement[];
}

export interface PalletDeck {
  length: number;
  width: number;
  deck_height: number;
}

/**
 * Product colors. Tableau-10 plus two — distinguishable for most color-vision types and readable
 * on white. The PDF report (phase 8) must use this exact list in this order.
 */
export const PALETTE = [
  "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC948",
  "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC", "#D37295", "#8CD17D",
] as const;

export type ColorMap = Map<string, string>;

/** Assign colors in shipment-line order, so a product keeps its color on every pallet. */
export function colorMap(productKeys: string[]): ColorMap {
  const map: ColorMap = new Map();
  for (const key of productKeys) {
    if (!map.has(key)) map.set(key, PALETTE[map.size % PALETTE.length]);
  }
  return map;
}

function mix(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => Math.round(c + (255 - c) * amount));
  return "#" + ch.map((c) => c.toString(16).padStart(2, "0")).join("").toUpperCase();
}

/** Box 1 gets the product color; box 2, 3… of a multi-box product get lighter tints of it. */
export function boxColor(colors: ColorMap, productId: string, boxNo: number): string {
  const base = colors.get(productId) ?? PALETTE[PALETTE.length - 3];
  return boxNo <= 1 ? base : mix(base, Math.min(0.6, 0.28 * (boxNo - 1)));
}

const EPS = 1e-6;

/** Bottom-up stacking order: lower z first, then back to front (y), then left to right (x). */
export function buildOrder<T extends ScenePlacement>(layout: T[]): T[] {
  return [...layout].sort((a, b) => a.z - b.z || a.y - b.y || a.x - b.x || a.uid - b.uid);
}

/** Distinct box bottom heights, ascending — one "layer" per level. */
export function layers(layout: ScenePlacement[]): number[] {
  const out: number[] = [];
  for (const z of layout.map((p) => p.z).sort((a, b) => a - b)) {
    if (!out.length || z - out[out.length - 1] > EPS) out.push(z);
  }
  return out;
}

/** For each step count n (boxes shown in build order), the layer (1-based) the n-th box is on. */
export function layerOfStep(ordered: ScenePlacement[], step: number): number {
  if (step <= 0 || !ordered.length) return 0;
  const lv = layers(ordered);
  const z = ordered[Math.min(step, ordered.length) - 1].z;
  return lv.findIndex((l) => Math.abs(l - z) <= EPS) + 1;
}

/** Number of boxes shown when every box up to and including layer `layer` (1-based) is placed. */
export function stepForLayer(ordered: ScenePlacement[], layer: number): number {
  const lv = layers(ordered);
  if (layer <= 0) return 0;
  if (layer >= lv.length) return ordered.length;
  const cutoff = lv[layer - 1];
  return ordered.filter((p) => p.z <= cutoff + EPS).length;
}

export interface Bounds {
  min: [number, number, number];
  max: [number, number, number];
}

/** Bounding box of deck + load in engine coordinates (z includes the deck below z=0). */
export function bounds(layout: ScenePlacement[], deck: PalletDeck): Bounds {
  let min: [number, number, number] = [0, 0, -deck.deck_height];
  let max: [number, number, number] = [deck.length, deck.width, 0];
  for (const p of layout) {
    min = [Math.min(min[0], p.x), Math.min(min[1], p.y), min[2]];
    max = [Math.max(max[0], p.x + p.dx), Math.max(max[1], p.y + p.dy), Math.max(max[2], p.z + p.dz)];
  }
  return { min, max };
}

/** Per-product box counts on one pallet, in color (shipment-line) order. */
export function legend(layout: ScenePlacement[], colors: ColorMap) {
  const rows = new Map<string, { product_id: string; sku: string; product_name: string; count: number; color: string }>();
  for (const p of layout) {
    const r = rows.get(p.product_id);
    if (r) r.count += 1;
    else rows.set(p.product_id, { product_id: p.product_id, sku: p.sku, product_name: p.product_name, count: 1, color: colors.get(p.product_id) ?? PALETTE[0] });
  }
  const order = [...colors.keys()];
  return [...rows.values()].sort((a, b) => {
    const ia = order.indexOf(a.product_id), ib = order.indexOf(b.product_id);
    return (ia < 0 ? 1e9 : ia) - (ib < 0 ? 1e9 : ib) || a.sku.localeCompare(b.sku);
  });
}
