// Still images of pallets for the pallet cards. One hidden PalletScene (one WebGL context) renders
// every thumbnail, so a shipment with many pallets doesn't open many 3D canvases.

import type { ColorMap, PalletDeck, ScenePallet } from "./layout";
import { PalletScene } from "./PalletScene";

let shared: { scene: PalletScene; host: HTMLElement } | null = null;
const cache = new Map<string, string>();

function renderer(width: number, height: number): PalletScene {
  if (!shared) {
    const host = document.createElement("div");
    Object.assign(host.style, { position: "fixed", left: "-10000px", top: "0", width: `${width}px`, height: `${height}px`, pointerEvents: "none" });
    document.body.appendChild(host);
    shared = { scene: new PalletScene(host, { interactive: false }), host };
  }
  shared.host.style.width = `${width}px`;
  shared.host.style.height = `${height}px`;
  shared.scene.setSize(width, height);
  return shared.scene;
}

/**
 * PNG data URLs, one per pallet, in order. `cacheKey` should change whenever the layout does
 * (e.g. shipment id + calculated_at), so re-renders only happen after a recalculation.
 */
export function renderThumbnails(
  cacheKey: string,
  pallets: ScenePallet[],
  deck: PalletDeck, // fallback when a pallet carries no deck of its own
  colors: ColorMap,
  width = 480,
  height = 300,
): string[] {
  const scene = renderer(width, height);
  return pallets.map((p) => {
    const key = `${cacheKey}|${p.index}|${width}x${height}`;
    let url = cache.get(key);
    if (!url) {
      scene.load(p, p.deck ?? deck, colors);
      scene.setView("iso");
      url = scene.snapshot();
      cache.set(key, url);
    }
    return url;
  });
}
