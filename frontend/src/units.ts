// Display-only unit formatting. The engine and API work in inches and pounds; companies that
// prefer metric see converted values here. Never use these to recompute engine numbers.
import { useAuth } from "./auth";

export type Units = "imperial" | "metric";
const IN_TO_CM = 2.54;
const LB_TO_KG = 0.45359237;
const CUFT_TO_M3 = 0.0283168466;
const PCF_TO_KGM3 = 16.0184634;

function num(n: number, digits: number): string {
  return Number(n.toFixed(digits)).toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function makeFormat(units: Units) {
  const metric = units === "metric";
  return {
    units,
    len: (inches: number, digits = 1) => (metric ? `${num(inches * IN_TO_CM, digits)} cm` : `${num(inches, digits)} in`),
    dims: (l: number, w: number, h: number) =>
      metric
        ? `${num(l * IN_TO_CM, 0)} × ${num(w * IN_TO_CM, 0)} × ${num(h * IN_TO_CM, 0)} cm`
        : `${num(l, 1)} × ${num(w, 1)} × ${num(h, 1)} in`,
    weight: (lb: number, digits = 1) => (metric ? `${num(lb * LB_TO_KG, digits)} kg` : `${num(lb, digits)} lb`),
    volume: (cuft: number) => (metric ? `${num(cuft * CUFT_TO_M3, 2)} m³` : `${num(cuft, 1)} ft³`),
    density: (pcf: number) => (metric ? `${num(pcf * PCF_TO_KGM3, 0)} kg/m³` : `${num(pcf, 2)} lb/ft³`),
  };
}

export function useFormat() {
  const { company } = useAuth();
  return makeFormat(company?.units ?? "imperial");
}
