import { describe, expect, it } from "vitest";
import { PALETTE, boxColor, bounds, buildOrder, colorMap, layerOfStep, layers, legend, stepForLayer, type ScenePlacement } from "./layout";

let uid = 0;
const box = (product_id: string, x: number, y: number, z: number, d = 10, box_no = 1): ScenePlacement => ({
  uid: ++uid, product_id, sku: `SKU-${product_id}`, product_name: `P${product_id}`, box_no, box_name: `Box ${box_no}`,
  x, y, z, dx: d, dy: d, dz: d, weight: 5,
});

describe("colors", () => {
  it("assigns palette colors in line order and is stable", () => {
    const c = colorMap(["7", "3", "7", "9"]);
    expect([...c.entries()]).toEqual([["7", PALETTE[0]], ["3", PALETTE[1]], ["9", PALETTE[2]]]);
  });
  it("wraps around after the palette is exhausted", () => {
    const keys = Array.from({ length: PALETTE.length + 2 }, (_, i) => String(i));
    expect(colorMap(keys).get(String(PALETTE.length))).toBe(PALETTE[0]);
  });
  it("tints later boxes of a multi-box product", () => {
    const c = colorMap(["1"]);
    expect(boxColor(c, "1", 1)).toBe(PALETTE[0]);
    const b2 = boxColor(c, "1", 2);
    const b3 = boxColor(c, "1", 3);
    expect(b2).not.toBe(PALETTE[0]);
    expect(b3).not.toBe(b2);
    expect(b2).toMatch(/^#[0-9A-F]{6}$/);
    expect(boxColor(c, "1", 9)).toBe(boxColor(c, "1", 4)); // capped
  });
});

describe("build order and layers", () => {
  const layout = [box("a", 10, 0, 10), box("a", 0, 0, 0), box("b", 10, 0, 0), box("a", 0, 10, 0), box("b", 0, 0, 10)];
  const ordered = buildOrder(layout);
  it("orders bottom-up, back to front, left to right", () => {
    expect(ordered.map((p) => [p.x, p.y, p.z])).toEqual([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10], [10, 0, 10]]);
  });
  it("groups layers by z", () => {
    expect(layers(layout)).toEqual([0, 10]);
    expect(layerOfStep(ordered, 0)).toBe(0);
    expect(layerOfStep(ordered, 3)).toBe(1);
    expect(layerOfStep(ordered, 4)).toBe(2);
    expect(stepForLayer(ordered, 1)).toBe(3);
    expect(stepForLayer(ordered, 2)).toBe(5);
    expect(stepForLayer(ordered, 0)).toBe(0);
  });
});

describe("bounds and legend", () => {
  it("covers deck and overhanging load", () => {
    const b = bounds([box("a", -1, 0, 0), box("a", 40, 35, 20)], { length: 48, width: 40, deck_height: 5.5 });
    expect(b).toEqual({ min: [-1, 0, -5.5], max: [50, 45, 30] });
  });
  it("counts boxes per product in line order", () => {
    const c = colorMap(["b", "a"]);
    const rows = legend([box("a", 0, 0, 0), box("b", 10, 0, 0), box("a", 0, 10, 0)], c);
    expect(rows.map((r) => [r.product_id, r.count, r.color])).toEqual([["b", 1, PALETTE[0]], ["a", 2, PALETTE[1]]]);
  });
});
