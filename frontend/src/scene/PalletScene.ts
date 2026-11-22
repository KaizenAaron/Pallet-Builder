// Interactive 3D view of one calculated pallet. Plain TypeScript + three.js, no React — the Odoo
// OWL widget reuses this file as-is in stage 2.
//
// It only *draws* the engine's saved placements; it never computes positions or metrics.
// Engine coordinates (inches): x along the pallet length, y along its width, z up from the deck.
// three.js coordinates: x = engine x, y = up, z = engine y; the deck is centered on the origin.
// Frames are rendered on demand (controls change, state change, resize), so an idle view is free.

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { boxColor, bounds, buildOrder, type ColorMap, type PalletDeck, type ScenePallet, type ScenePlacement } from "./layout";

export type ViewName = "iso" | "front" | "side" | "top";

export class WebGLUnavailableError extends Error {
  constructor() {
    super("3D view isn't available: this browser or device has WebGL turned off.");
  }
}

export interface PalletSceneOptions {
  interactive?: boolean; // orbit controls + hover (off for thumbnails)
  background?: string | null;
}

export type HoverHandler = (p: ScenePlacement | null, clientX: number, clientY: number) => void;

const WOOD = 0xc9a26b;
const WOOD_DARK = 0xa5824f;
const EDGE = 0x2b2f36;

export class PalletScene {
  readonly container: HTMLElement;
  private renderer: THREE.WebGLRenderer;
  private labels: CSS2DRenderer | null = null;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
  private controls: OrbitControls | null = null;
  private root = new THREE.Group(); // pallet + boxes, rebuilt on load()
  private dimGroup = new THREE.Group();
  private meshes: THREE.Mesh[] = []; // in build order
  private placements: ScenePlacement[] = [];
  private deck: PalletDeck = { length: 48, width: 40, deck_height: 5.5 };
  private pallet: ScenePallet | null = null;
  private colors: ColorMap = new Map();
  private step = Infinity;
  private highlight: string | null = null;
  private hovered: THREE.Mesh | null = null;
  private hoverHandler: HoverHandler | null = null;
  private view: ViewName = "iso";
  private dims: { on: boolean; format: (inches: number) => string } = { on: false, format: (v) => `${v} in` };
  private frame = 0;
  private fitted = false;
  private resizeObs: ResizeObserver | null = null;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private disposables: { dispose(): void }[] = [];
  private materials = new Map<string, THREE.MeshLambertMaterial>();
  private geometries = new Map<string, { box: THREE.BoxGeometry; edges: THREE.EdgesGeometry }>();
  private edgeMaterial = new THREE.LineBasicMaterial({ color: EDGE, transparent: true, opacity: 0.55 });
  private edgeMaterialFaded = new THREE.LineBasicMaterial({ color: EDGE, transparent: true, opacity: 0.08 });

  constructor(container: HTMLElement, opts: PalletSceneOptions = {}) {
    this.container = container;
    try {
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      throw new WebGLUnavailableError();
    }
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    if (opts.background) this.renderer.setClearColor(opts.background, 1);
    else this.renderer.setClearColor(0x000000, 0);
    container.appendChild(this.renderer.domElement);
    this.renderer.domElement.style.display = "block";

    this.labels = new CSS2DRenderer();
    Object.assign(this.labels.domElement.style, { position: "absolute", inset: "0", pointerEvents: "none" });
    container.appendChild(this.labels.domElement);

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f99, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(60, 120, 80);
    this.scene.add(sun);
    const fill = new THREE.DirectionalLight(0xffffff, 0.45);
    fill.position.set(-80, 40, -60);
    this.scene.add(fill);
    this.scene.add(this.root);
    this.scene.add(this.dimGroup);
    this.disposables.push(this.edgeMaterial, this.edgeMaterialFaded);

    if (opts.interactive !== false) {
      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = false;
      this.controls.maxPolarAngle = Math.PI * 0.495; // don't go under the floor
      this.controls.addEventListener("change", () => this.requestRender());
      this.renderer.domElement.addEventListener("pointermove", this.onPointerMove);
      this.renderer.domElement.addEventListener("pointerleave", this.onPointerLeave);
    }
    this.resizeObs = new ResizeObserver(() => this.resize());
    this.resizeObs.observe(container);
    this.resize();
  }

  // ---------------------------------------------------------------- public API
  load(pallet: ScenePallet, deck: PalletDeck, colors: ColorMap): void {
    this.clearRoot();
    this.pallet = pallet;
    this.deck = deck;
    this.colors = colors;
    this.placements = buildOrder(pallet.layout);
    this.highlight = null;
    this.step = Infinity;
    this.buildPalletDeck();
    for (const p of this.placements) this.root.add(this.makeBox(p));
    this.applyStyles();
    this.buildDimensions();
    this.setView(this.view);
  }

  /** Show only the first `n` boxes in build order (Infinity = all). */
  setStep(n: number): void {
    this.step = n;
    this.applyStyles();
  }

  /** Emphasize one product's boxes (by product_id); null clears. */
  setHighlight(productId: string | null): void {
    this.highlight = productId;
    this.applyStyles();
  }

  setView(view: ViewName): void {
    this.view = view;
    const b = bounds(this.placements, this.deck);
    const cx = (b.min[0] + b.max[0]) / 2 - this.deck.length / 2;
    const cz = (b.min[1] + b.max[1]) / 2 - this.deck.width / 2;
    const cy = (b.min[2] + b.max[2]) / 2 + this.deck.deck_height;
    const size = new THREE.Vector3(b.max[0] - b.min[0], b.max[2] - b.min[2], b.max[1] - b.min[1]);
    const radius = size.length() / 2;
    const dir = {
      iso: new THREE.Vector3(1.05, 0.85, 1.25),
      front: new THREE.Vector3(0, 0.12, 1),
      side: new THREE.Vector3(1, 0.12, 0),
      top: new THREE.Vector3(0, 1, 0.0001),
    }[view].normalize();
    const fov = THREE.MathUtils.degToRad(this.camera.fov);
    const fit = Math.max(1, 1 / Math.min(1, this.camera.aspect)); // tall containers need more room
    const dist = (radius / Math.sin(fov / 2)) * (view === "iso" ? 1.0 : 1.05) * fit;
    const target = new THREE.Vector3(cx, cy, cz);
    this.camera.position.copy(target).addScaledVector(dir, dist);
    this.camera.near = Math.max(0.5, dist / 100);
    this.camera.far = dist * 10;
    this.camera.updateProjectionMatrix();
    this.camera.lookAt(target);
    if (this.dims.on) this.buildDimensions();
    if (this.container.clientWidth && this.container.clientHeight) this.fitted = true;
    if (this.controls) {
      this.controls.target.copy(target);
      this.controls.minDistance = radius * 0.6;
      this.controls.maxDistance = dist * 4;
      this.controls.update();
    }
    this.requestRender();
  }

  setDimensions(on: boolean, format?: (inches: number) => string): void {
    this.dims = { on, format: format ?? this.dims.format };
    this.buildDimensions();
    this.requestRender();
  }

  onHover(handler: HoverHandler | null): void {
    this.hoverHandler = handler;
  }

  /** Render immediately and return a PNG data URL of the canvas. */
  snapshot(): string {
    this.renderNow();
    return this.renderer.domElement.toDataURL("image/png");
  }

  /** Resize the drawing surface to explicit pixels (used by the offscreen thumbnail renderer). */
  setSize(width: number, height: number): void {
    this.renderer.setSize(width, height, false);
    this.renderer.domElement.style.width = `${width}px`;
    this.renderer.domElement.style.height = `${height}px`;
    this.labels?.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.setView(this.view);
  }

  dispose(): void {
    cancelAnimationFrame(this.frame);
    this.resizeObs?.disconnect();
    this.renderer.domElement.removeEventListener("pointermove", this.onPointerMove);
    this.renderer.domElement.removeEventListener("pointerleave", this.onPointerLeave);
    this.controls?.dispose();
    this.clearRoot();
    this.clearDimensions();
    this.disposables.forEach((d) => d.dispose());
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labels?.domElement.remove();
  }

  // ---------------------------------------------------------------- building
  private toWorld(x: number, y: number, z: number): THREE.Vector3 {
    return new THREE.Vector3(x - this.deck.length / 2, z + this.deck.deck_height, y - this.deck.width / 2);
  }

  private material(color: string, faded: boolean): THREE.MeshLambertMaterial {
    const key = `${color}|${faded ? 1 : 0}`;
    let m = this.materials.get(key);
    if (!m) {
      m = new THREE.MeshLambertMaterial({ color });
      if (faded) {
        m.transparent = true;
        m.opacity = 0.12;
        m.depthWrite = false;
      }
      this.materials.set(key, m);
      this.disposables.push(m);
    }
    return m;
  }

  private geometry(dx: number, dy: number, dz: number) {
    const key = `${dx}|${dy}|${dz}`;
    let g = this.geometries.get(key);
    if (!g) {
      const gap = Math.min(0.25, Math.min(dx, dy, dz) * 0.04);
      const box = new THREE.BoxGeometry(dx - gap, dz - gap, dy - gap);
      g = { box, edges: new THREE.EdgesGeometry(box) };
      this.geometries.set(key, g);
      this.disposables.push(box, g.edges);
    }
    return g;
  }

  private makeBox(p: ScenePlacement): THREE.Mesh {
    const g = this.geometry(p.dx, p.dy, p.dz);
    const mesh = new THREE.Mesh(g.box, this.material(boxColor(this.colors, p.product_id, p.box_no), false));
    mesh.position.copy(this.toWorld(p.x + p.dx / 2, p.y + p.dy / 2, p.z + p.dz / 2));
    const edges = new THREE.LineSegments(g.edges, this.edgeMaterial);
    mesh.add(edges);
    mesh.userData = { placement: p, edges };
    this.meshes.push(mesh);
    return mesh;
  }

  private buildPalletDeck(): void {
    const { length: L, width: W, deck_height: D } = this.deck;
    const board = 0.75;
    const wood = new THREE.MeshLambertMaterial({ color: WOOD });
    const woodDark = new THREE.MeshLambertMaterial({ color: WOOD_DARK });
    this.disposables.push(wood, woodDark);
    const add = (sx: number, sy: number, sz: number, x: number, y: number, z: number, mat: THREE.Material) => {
      const geo = new THREE.BoxGeometry(sx, sy, sz);
      this.disposables.push(geo);
      const m = new THREE.Mesh(geo, mat);
      m.position.set(x - L / 2, y, z - W / 2);
      this.root.add(m);
    };
    const tb = Math.min(board, D / 4);
    const stringerH = Math.max(0.5, D - 2 * tb);
    // three stringers along the length
    for (const z of [1, W / 2, W - 1]) add(L, stringerH, 1.5, L / 2, tb + stringerH / 2, z, woodDark);
    // top deck boards across the width
    const n = Math.max(5, Math.round(L / 7));
    const bw = 3.5;
    for (let i = 0; i < n; i++) {
      const x = bw / 2 + (i * (L - bw)) / (n - 1);
      add(bw, tb, W, x, D - tb / 2, W / 2, wood);
    }
    // bottom boards
    for (const x of [bw / 2, L / 2, L - bw / 2]) add(bw, tb, W, x, tb / 2, W / 2, wood);
  }

  private clearRoot(): void {
    this.root.clear();
    this.meshes = [];
    this.hovered = null;
  }

  private clearDimensions(): void {
    for (const child of [...this.dimGroup.children]) {
      if (child instanceof CSS2DObject) child.element.remove();
      if (child instanceof THREE.Line) {
        child.geometry.dispose();
        (child.material as THREE.Material).dispose();
      }
    }
    this.dimGroup.clear();
  }

  private buildDimensions(): void {
    this.clearDimensions();
    if (!this.dims.on || !this.pallet) return;
    const b = bounds(this.placements, this.deck);
    const [x0, y0, z0] = b.min;
    const [x1, y1, z1] = b.max;
    const off = Math.max(3, (x1 - x0) * 0.07);
    const mat = () => new THREE.LineBasicMaterial({ color: 0x1f6feb });
    const line = (pts: THREE.Vector3[]) => {
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat());
      this.dimGroup.add(l);
    };
    const label = (text: string, at: THREE.Vector3) => {
      const el = document.createElement("div");
      el.className = "dim-label";
      el.textContent = text;
      const o = new CSS2DObject(el);
      o.position.copy(at);
      this.dimGroup.add(o);
    };
    const w = (x: number, y: number, z: number) => this.toWorld(x, y, z);
    const tick = 1.5;
    // Only the measurements that read correctly from this camera direction.
    const show = {
      iso: { L: true, W: true, H: true },
      front: { L: true, W: false, H: true },
      side: { L: false, W: true, H: true },
      top: { L: true, W: true, H: false },
    }[this.view];
    // length: along the front-bottom edge
    const yF = y1 + off;
    const zB = z0;
    if (show.L) {
      line([w(x0, yF, zB), w(x1, yF, zB)]);
      line([w(x0, yF - tick, zB), w(x0, yF + tick, zB)]);
      line([w(x1, yF - tick, zB), w(x1, yF + tick, zB)]);
      label(`L ${this.dims.format(this.pallet.length)}`, w((x0 + x1) / 2, yF + 2, zB));
    }
    // width: along the right-bottom edge
    const xR = x1 + off;
    if (show.W) {
      line([w(xR, y0, zB), w(xR, y1, zB)]);
      line([w(xR - tick, y0, zB), w(xR + tick, y0, zB)]);
      line([w(xR - tick, y1, zB), w(xR + tick, y1, zB)]);
      label(`W ${this.dims.format(this.pallet.width)}`, w(xR + 2, (y0 + y1) / 2, zB));
    }
    // height: front-right vertical edge, floor to top of load
    if (show.H) {
      line([w(xR, yF, zB), w(xR, yF, z1)]);
      line([w(xR - tick, yF, z1), w(xR + tick, yF, z1)]);
      label(`H ${this.dims.format(this.pallet.height)}`, w(xR + 2, yF, (zB + z1) / 2));
    }
  }

  private applyStyles(): void {
    this.meshes.forEach((mesh, i) => {
      const p = mesh.userData.placement as ScenePlacement;
      mesh.visible = i < this.step;
      const faded = this.highlight !== null && p.product_id !== this.highlight;
      mesh.material = this.material(boxColor(this.colors, p.product_id, p.box_no), faded);
      (mesh.userData.edges as THREE.LineSegments).material = faded ? this.edgeMaterialFaded : this.edgeMaterial;
      if (mesh === this.hovered && !faded) mesh.material = this.hoverMaterial(p);
    });
    this.requestRender();
  }

  private hoverMaterial(p: ScenePlacement): THREE.MeshLambertMaterial {
    const key = `hover|${boxColor(this.colors, p.product_id, p.box_no)}`;
    let m = this.materials.get(key);
    if (!m) {
      m = new THREE.MeshLambertMaterial({ color: boxColor(this.colors, p.product_id, p.box_no), emissive: 0x333333 });
      this.materials.set(key, m);
      this.disposables.push(m);
    }
    return m;
  }

  // ---------------------------------------------------------------- interaction & rendering
  private onPointerMove = (e: PointerEvent) => {
    if (!this.hoverHandler && !this.meshes.length) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects(this.meshes.filter((m) => m.visible), false);
    const hit = (hits.find((h) => {
      const p = (h.object as THREE.Mesh).userData.placement as ScenePlacement;
      return this.highlight === null || p.product_id === this.highlight;
    })?.object ?? null) as THREE.Mesh | null;
    if (hit !== this.hovered) {
      this.hovered = hit;
      this.applyStyles();
    }
    this.hoverHandler?.(hit ? (hit.userData.placement as ScenePlacement) : null, e.clientX, e.clientY);
  };

  private onPointerLeave = () => {
    if (this.hovered) {
      this.hovered = null;
      this.applyStyles();
    }
    this.hoverHandler?.(null, 0, 0);
  };

  private resize(): void {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = `${w}px`;
    this.renderer.domElement.style.height = `${h}px`;
    this.labels?.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.pallet && !this.fitted) this.setView(this.view); // first real size: fit once
    else this.requestRender(); // keep the user's rotation/zoom
  }

  requestRender(): void {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.renderNow();
    });
  }

  private renderNow(): void {
    this.renderer.render(this.scene, this.camera);
    this.labels?.render(this.scene, this.camera);
  }
}
