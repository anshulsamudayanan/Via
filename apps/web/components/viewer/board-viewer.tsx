"use client";

import { Badge, Button, cn, EmptyState, ErrorState, Input, Spinner, Table, TBody, TD, TH, THead, TR, Tooltip } from "@via/ui";
import { Expand, Maximize, Minus, Plus, Search, X } from "lucide-react";
import Link from "next/link";
import { type KeyboardEvent, type PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { layerColor, VIEWER_COLORS } from "@/lib/pcb/palette";
import { type LoadedBoard, loadBoard } from "@/lib/pcb/board-loader";
import {
  EMPTY_HIGHLIGHT,
  type Highlight,
  type NetGeometry,
  overlayBounds,
  type ResolvedOverlay,
  resolveComponents,
} from "@/lib/pcb/overlay";
import { componentAt, type RenderComponent, type RenderModel } from "@/lib/pcb/render-model";
import { drawBoard, type ObjectToggles, visibleSides } from "@/lib/pcb/renderer";
import { fitViewport, focusOn, panBy, screenToWorld, type Viewport, zoomAt } from "@/lib/pcb/viewport";
import { useAsync } from "@/lib/use-async";
import { useTheme } from "@/lib/use-theme";

interface Props {
  designId: string;
  revisionId?: string;
  designName: string;
  /** Link to the full-page viewer (shown when embedded). */
  expandHref?: string;
  className?: string;
  /** Finding regions and components/nets to highlight (e.g. the selected finding). */
  highlight?: Highlight;
}

/** Loads the parsed design (in a Web Worker when available) and renders the interactive viewer. */
export function BoardViewer({ designId, revisionId, designName, expandHref, className, highlight }: Props) {
  const client = useApi();
  const board = useAsync((s) => loadBoard(client, designId, revisionId, s), [client, designId, revisionId]);

  if (board.error) {
    return <ErrorState title="Couldn't load the board for viewing" description={errorMessage(board.error)} />;
  }
  if (!board.data) {
    return (
      <div className={cn("flex items-center justify-center rounded-lg border border-border bg-surface", className)}>
        <Spinner label="Loading board" />
      </div>
    );
  }
  return (
    <ViewerCanvas
      board={board.data}
      designName={designName}
      expandHref={expandHref}
      className={className}
      highlight={highlight ?? EMPTY_HIGHLIGHT}
    />
  );
}

const ZOOM_STEP = 1.25;
/**
 * Boards with more primitives than this use snapshot previews while zooming
 * and panning. (Measuring draw time doesn't work: canvas rasterization is
 * deferred to paint, so the JavaScript call returns quickly either way.)
 */
const HEAVY_PRIMITIVES = 40_000;

function ViewerCanvas({
  board,
  designName,
  expandHref,
  className,
  highlight,
}: {
  board: LoadedBoard;
  designName: string;
  expandHref?: string;
  className?: string;
  highlight: Highlight;
}) {
  const model = board.model;
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const vpRef = useRef<Viewport | null>(null);
  const fitScaleRef = useRef(1);
  const sizeRef = useRef({ width: 0, height: 0 });
  const frameRef = useRef<number | null>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(
    () => new Set(model.layers.filter((l) => l.visibleByDefault).map((l) => l.name)),
  );
  const [show, setShow] = useState<ObjectToggles>({ tracks: true, pads: true, vias: true, zones: true });
  const [selected, setSelected] = useState<RenderComponent | null>(null);
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  const [zoomPct, setZoomPct] = useState(100);
  const [panel, setPanel] = useState<"layers" | "components">("layers");

  const [netGeo, setNetGeo] = useState<{ key: string; geometry: NetGeometry } | null>(null);
  const netKey = highlight.nets.join("\u0000");
  useEffect(() => {
    if (!highlight.nets.length) return;
    let live = true;
    void board.nets(highlight.nets).then((geometry) => {
      if (live) setNetGeo({ key: netKey, geometry });
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- netKey identifies highlight.nets
  }, [board, netKey]);
  const overlay = useMemo<ResolvedOverlay | null>(() => {
    const components = resolveComponents(model, highlight.references);
    const net = highlight.nets.length && netGeo?.key === netKey ? netGeo.geometry : null;
    if (!components.length && !net && !highlight.regions.length) return null;
    return { components, net, regions: highlight.regions };
  }, [model, highlight, netGeo, netKey]);

  const optsRef = useRef({ visibleLayers, show, selected, theme, overlay });

  // On very large boards, zoom/pan first shows a scaled snapshot of the last
  // full frame; the full-detail render follows once interaction pauses.
  const snapshotRef = useRef<{ canvas: HTMLCanvasElement; vp: Viewport } | null>(null);
  const heavy = model.counts.tracks + model.counts.pads > HEAVY_PRIMITIVES;
  const idleTimerRef = useRef<number | null>(null);

  const draw = useCallback(() => {
    frameRef.current = null;
    const canvas = canvasRef.current;
    const vp = vpRef.current;
    if (!canvas || !vp) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { width, height } = sizeRef.current;
    const dpr = window.devicePixelRatio || 1;
    drawBoard(ctx, model, { viewport: vp, width, height, dpr, ...optsRef.current });
    if (heavy) {
      const snap = snapshotRef.current?.canvas ?? document.createElement("canvas");
      snap.width = canvas.width;
      snap.height = canvas.height;
      snap.getContext("2d")?.drawImage(canvas, 0, 0);
      snapshotRef.current = { canvas: snap, vp };
    } else {
      snapshotRef.current = null;
    }
  }, [model, heavy]);

  const schedule = useCallback(() => {
    if (frameRef.current === null) frameRef.current = window.requestAnimationFrame(draw);
  }, [draw]);

  /** Cheap preview while interacting: the last full frame, transformed to the new viewport. */
  const drawSnapshot = useCallback(() => {
    frameRef.current = null;
    const canvas = canvasRef.current;
    const vp = vpRef.current;
    const snap = snapshotRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !vp || !snap || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const k = vp.scale / snap.vp.scale;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = VIEWER_COLORS[optsRef.current.theme].background;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(k, 0, 0, k, dpr * (vp.tx - snap.vp.tx * k), dpr * (vp.ty - snap.vp.ty * k));
    ctx.drawImage(snap.canvas, 0, 0);
  }, []);

  const setViewport = useCallback(
    (vp: Viewport) => {
      vpRef.current = vp;
      setZoomPct(Math.round((vp.scale / fitScaleRef.current) * 100));
      if (heavy && snapshotRef.current) {
        if (frameRef.current === null) frameRef.current = window.requestAnimationFrame(drawSnapshot);
        if (idleTimerRef.current !== null) window.clearTimeout(idleTimerRef.current);
        idleTimerRef.current = window.setTimeout(() => {
          idleTimerRef.current = null;
          schedule();
        }, 160);
        return;
      }
      schedule();
    },
    [schedule, drawSnapshot, heavy],
  );

  const fit = useCallback(() => {
    const { width, height } = sizeRef.current;
    if (!width || !height) return;
    const vp = fitViewport(model.bounds, width, height);
    fitScaleRef.current = vp.scale;
    setViewport(vp);
  }, [model, setViewport]);

  // Size the canvas to its container (device pixels) and fit on first layout.
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const resize = () => {
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      sizeRef.current = { width: rect.width, height: rect.height };
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      if (!vpRef.current) fit();
      else schedule();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    return () => observer.disconnect();
  }, [fit, schedule]);

  // Redraw when visibility, selection, highlight or theme change.
  useEffect(() => {
    optsRef.current = { visibleLayers, show, selected, theme, overlay };
    schedule();
  }, [visibleLayers, show, selected, theme, overlay, schedule]);

  // Zoom to a newly focused highlight (e.g. a finding picked from the list).
  useEffect(() => {
    if (!highlight.focus || !overlay) return;
    const b = overlayBounds(overlay);
    const { width, height } = sizeRef.current;
    if (b && width && height) setViewport(focusOn(b, width, height, 0.35, fitScaleRef.current * 40));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the highlight itself changes
  }, [overlay]);

  // Wheel zoom (non-passive so the page doesn't scroll).
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const vp = vpRef.current;
      if (!vp) return;
      const rect = canvas.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015));
      setViewport(zoomAt(vp, factor, e.clientX - rect.left, e.clientY - rect.top, fitScaleRef.current / 5));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [setViewport]);

  useEffect(() => () => {
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    if (idleTimerRef.current !== null) window.clearTimeout(idleTimerRef.current);
  }, []);

  const zoomBy = (factor: number) => {
    const vp = vpRef.current;
    const { width, height } = sizeRef.current;
    if (vp) setViewport(zoomAt(vp, factor, width / 2, height / 2, fitScaleRef.current / 5));
  };

  const select = (c: RenderComponent | null, focus = false) => {
    setSelected(c);
    if (c && focus) {
      const { width, height } = sizeRef.current;
      setViewport(focusOn(c.bbox, width, height, 0.3, fitScaleRef.current * 60));
    }
  };

  function onPointerDown(e: PointerEvent<HTMLCanvasElement>) {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { x: e.clientX, y: e.clientY, moved: false };
  }

  function onPointerMove(e: PointerEvent<HTMLCanvasElement>) {
    const vp = vpRef.current;
    if (!vp) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setCursor(screenToWorld(vp, e.clientX - rect.left, e.clientY - rect.top));
    const drag = dragRef.current;
    if (!drag) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 3) return;
    drag.moved = true;
    drag.x = e.clientX;
    drag.y = e.clientY;
    setViewport(panBy(vp, dx, dy));
  }

  function onPointerUp(e: PointerEvent<HTMLCanvasElement>) {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag || drag.moved) return;
    const vp = vpRef.current;
    if (!vp) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const [x, y] = screenToWorld(vp, e.clientX - rect.left, e.clientY - rect.top);
    select(componentAt(model, x, y, visibleSides(model, visibleLayers), 2 / vp.scale));
  }

  function onKeyDown(e: KeyboardEvent<HTMLCanvasElement>) {
    const vp = vpRef.current;
    if (!vp) return;
    const step = 60;
    const actions: Record<string, () => void> = {
      "+": () => zoomBy(ZOOM_STEP),
      "=": () => zoomBy(ZOOM_STEP),
      "-": () => zoomBy(1 / ZOOM_STEP),
      "0": fit,
      f: fit,
      ArrowLeft: () => setViewport(panBy(vp, step, 0)),
      ArrowRight: () => setViewport(panBy(vp, -step, 0)),
      ArrowUp: () => setViewport(panBy(vp, 0, step)),
      ArrowDown: () => setViewport(panBy(vp, 0, -step)),
    };
    const action = actions[e.key];
    if (action) {
      e.preventDefault();
      action();
    }
  }

  const toggleLayer = (name: string) =>
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const s = board.stats;
  return (
    <div
      className={cn("flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-surface lg:flex-row", className)}
      onKeyDown={(e) => {
        // Escape clears the selection from anywhere in the viewer; zoom/pan keys stay on the canvas.
        if (e.key === "Escape" && selected) {
          e.preventDefault();
          select(null);
        }
      }}
    >
      <div className="relative min-h-72 min-w-0 flex-1" ref={containerRef}>
        <canvas
          ref={canvasRef}
          tabIndex={0}
          role="img"
          aria-label={`Board view of ${designName}: ${s.component_count} components, ${s.copper_layer_count} copper layers, ${s.track_count} tracks, ${s.via_count} vias. Use + and - to zoom, arrow keys to pan, 0 to fit. Escape clears the selection. Select components from the Components list.`}
          className="absolute inset-0 h-full w-full cursor-crosshair touch-none outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => setCursor(null)}
          onKeyDown={onKeyDown}
        />
        <div className="pointer-events-none absolute top-2 left-2 flex gap-1">
          <div className="pointer-events-auto flex gap-0.5 rounded-md border border-border bg-surface-raised/90 p-0.5 shadow-sm backdrop-blur">
            <Tooltip content="Zoom in (+)">
              <Button size="icon" variant="ghost" className="size-7" aria-label="Zoom in" onClick={() => zoomBy(ZOOM_STEP)}>
                <Plus />
              </Button>
            </Tooltip>
            <Tooltip content="Zoom out (-)">
              <Button size="icon" variant="ghost" className="size-7" aria-label="Zoom out" onClick={() => zoomBy(1 / ZOOM_STEP)}>
                <Minus />
              </Button>
            </Tooltip>
            <Tooltip content="Fit board (0)">
              <Button size="icon" variant="ghost" className="size-7" aria-label="Fit board" onClick={fit}>
                <Maximize />
              </Button>
            </Tooltip>
            {expandHref ? (
              <Tooltip content="Open full-page viewer">
                <Button asChild size="icon" variant="ghost" className="size-7">
                  <Link href={expandHref} aria-label="Open full-page viewer">
                    <Expand />
                  </Link>
                </Button>
              </Tooltip>
            ) : null}
          </div>
        </div>
        <div className="pointer-events-none absolute bottom-2 left-2 rounded-sm bg-surface-raised/80 px-1.5 py-0.5 font-mono text-[11px] text-muted tabular-nums">
          {zoomPct}%{cursor ? ` · x ${cursor[0].toFixed(3)}  y ${cursor[1].toFixed(3)} mm` : ""}
        </div>
        {selected ? <SelectionPanel component={selected} onClose={() => select(null)} /> : null}
      </div>
      <aside className="flex max-h-[45vh] w-full shrink-0 flex-col border-t border-border lg:max-h-none lg:w-72 lg:border-t-0 lg:border-l">
        <div role="tablist" aria-label="Viewer panels" className="flex border-b border-border">
          {(["layers", "components"] as const).map((p) => (
            <button
              key={p}
              role="tab"
              aria-selected={panel === p}
              className={cn(
                "-mb-px flex-1 border-b-2 px-3 py-2 text-xs font-medium capitalize",
                panel === p ? "border-accent text-foreground" : "border-transparent text-muted hover:text-foreground",
              )}
              onClick={() => setPanel(p)}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {panel === "layers" ? (
            <LayersPanel model={model} visible={visibleLayers} onToggle={toggleLayer} show={show} onShow={setShow} theme={theme} />
          ) : (
            <ComponentsPanel model={model} selected={selected} onSelect={(c) => select(c, true)} />
          )}
        </div>
      </aside>
    </div>
  );
}

const GROUPS: { title: string; match: (kind: string) => boolean }[] = [
  { title: "Copper", match: (k) => k === "copper" },
  { title: "Technical", match: (k) => ["silkscreen", "solder_mask", "solder_paste", "adhesive", "fabrication", "courtyard"].includes(k) },
  { title: "Board & drawings", match: (k) => ["edge", "margin", "documentation", "user"].includes(k) },
];

function LayersPanel({
  model,
  visible,
  onToggle,
  show,
  onShow,
  theme,
}: {
  model: RenderModel;
  visible: Set<string>;
  onToggle: (name: string) => void;
  show: ObjectToggles;
  onShow: (s: ObjectToggles) => void;
  theme: "dark" | "light";
}) {
  // Draw order is back-to-front; list front-to-back for reading.
  const ordered = [...model.layers].reverse();
  return (
    <div className="space-y-3 p-3 text-sm">
      {GROUPS.map((g) => {
        const layers = ordered.filter((l) => g.match(l.kind));
        if (!layers.length) return null;
        return (
          <fieldset key={g.title} className="space-y-1">
            <legend className="mb-1 text-[12px] font-medium text-subtle">{g.title}</legend>
            {layers.map((l) => (
              <label key={l.name} className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-0.5 hover:bg-surface-hover">
                <input type="checkbox" checked={visible.has(l.name)} onChange={() => onToggle(l.name)} className="accent-[var(--color-accent)]" />
                <span aria-hidden="true" className="size-2.5 shrink-0 rounded-sm" style={{ background: layerColor(l.name, l.kind, l.side, l.innerIndex, theme) }} />
                <span className="truncate font-mono text-xs">{l.name}</span>
              </label>
            ))}
          </fieldset>
        );
      })}
      <fieldset className="space-y-1">
        <legend className="mb-1 text-[12px] font-medium text-subtle">Objects</legend>
        {(
          [
            ["tracks", `Tracks (${model.counts.tracks})`],
            ["pads", `Pads (${model.counts.pads})`],
            ["vias", `Vias (${model.counts.vias})`],
            ["zones", `Zones (${model.counts.zones})`],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-0.5 hover:bg-surface-hover">
            <input type="checkbox" checked={show[key]} onChange={() => onShow({ ...show, [key]: !show[key] })} className="accent-[var(--color-accent)]" />
            <span className="text-xs">{label}</span>
          </label>
        ))}
      </fieldset>
      <p className="text-[11px] leading-relaxed text-subtle">
        Custom and rounded pad shapes are drawn as their bounding rectangles. Zones are drawn from their outlines, not
        filled copper.
      </p>
    </div>
  );
}

function ComponentsPanel({ model, selected, onSelect }: { model: RenderModel; selected: RenderComponent | null; onSelect: (c: RenderComponent) => void }) {
  const [q, setQ] = useState("");
  const term = q.trim().toLowerCase();
  const matches = useMemo(() => {
    const list = term
      ? model.components.filter((c) =>
          [c.reference, c.value ?? "", c.footprint].some((v) => v.toLowerCase().includes(term)),
        )
      : model.components;
    return [...list].sort((a, b) => a.reference.localeCompare(b.reference, undefined, { numeric: true }));
  }, [model, term]);
  const shown = matches.slice(0, 300);
  return (
    <div className="flex h-full flex-col">
      <div className="relative border-b border-border p-2">
        <Search className="pointer-events-none absolute top-1/2 left-4 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
        <Input type="search" aria-label="Search components" placeholder="Reference, value, footprint" className="pl-7" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {matches.length === 0 ? (
        <EmptyState title="No matching components" />
      ) : (
        <ul className="min-h-0 flex-1 divide-y divide-border overflow-y-auto">
          {shown.map((c) => (
            <li key={c.index}>
              <button
                className={cn(
                  "flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-sm hover:bg-surface-hover",
                  selected?.index === c.index && "bg-accent-soft",
                )}
                aria-current={selected?.index === c.index ? "true" : undefined}
                onClick={() => onSelect(c)}
              >
                <span className="w-14 shrink-0 font-mono text-xs font-medium">{c.reference || "(none)"}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted">{c.value ?? ""}</span>
                <span className="text-[10px] text-subtle">{c.side === "bottom" ? "B" : "F"}</span>
              </button>
            </li>
          ))}
          {matches.length > shown.length ? (
            <li className="px-3 py-2 text-xs text-muted">{matches.length - shown.length} more; refine the search.</li>
          ) : null}
        </ul>
      )}
    </div>
  );
}

function SelectionPanel({ component, onClose }: { component: RenderComponent; onClose: () => void }) {
  const c = component.source;
  const rows: [string, string][] = [
    ["Value", c.value ?? "-"],
    ["Footprint", c.footprint],
    ["Side", `${c.side} (${c.layer})`],
    ["Position", `${c.position.x.toFixed(3)}, ${c.position.y.toFixed(3)} mm`],
    ["Rotation", `${c.rotation}°`],
    ["Pads", String(c.pads.length)],
    ...(c.attributes.length ? ([["Attributes", c.attributes.join(", ")]] as [string, string][]) : []),
    // KiCad 6+ repeats the library id as a "Footprint" property; it's already shown above.
    ...Object.entries(c.properties)
      .filter(([k, v]) => !(k === "Footprint" && v === c.footprint))
      .map(([k, v]) => [k, v] as [string, string]),
  ];
  return (
    <section
      aria-label={`Component ${c.reference}`}
      aria-live="polite"
      className="absolute top-2 right-2 bottom-2 flex w-80 max-w-[calc(100%-1rem)] flex-col overflow-hidden rounded-lg border border-border bg-surface-raised/95 shadow-lg backdrop-blur"
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <h3 className="font-mono text-sm font-semibold">{c.reference || "(no reference)"}</h3>
        <Badge tone={c.side === "bottom" ? "warning" : "neutral"}>{c.side}</Badge>
        <Button size="icon" variant="ghost" className="ml-auto size-7" aria-label="Close component details" onClick={onClose}>
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <dl className="divide-y divide-border text-xs">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 px-3 py-1.5">
              <dt className="shrink-0 text-muted">{k}</dt>
              <dd className="truncate text-right" title={v}>{v}</dd>
            </div>
          ))}
        </dl>
        {c.pads.length ? (
          <Table className="text-xs">
            <caption className="sr-only">Pads of {c.reference}</caption>
            <THead>
              <tr>
                <TH className="h-7 px-2">Pad</TH>
                <TH className="h-7 px-2">Net</TH>
                <TH className="h-7 px-2">Type</TH>
              </tr>
            </THead>
            <TBody>
              {c.pads.map((p, i) => (
                <TR key={`${p.number}-${i}`}>
                  <TD className="px-2 py-1 font-mono">{p.number || "-"}</TD>
                  <TD className="max-w-32 truncate px-2 py-1 font-mono" title={p.net ?? ""}>{p.net ?? <span className="text-subtle">no net</span>}</TD>
                  <TD className="px-2 py-1 text-muted">
                    {p.type === "through_hole" ? "THT" : p.type === "npth" ? "NPTH" : p.type.toUpperCase()} · {p.shape}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : null}
      </div>
    </section>
  );
}
