"use client";

/* eslint-disable @next/next/no-img-element */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  edit,
  fetchEngineStatus,
  fetchStockCars,
  fetchWheels,
  type BodyFinish,
  type EngineStatus,
  type StockCar,
  type Wheel,
} from "./lib/api";

const BODY_COLORS = [
  { name: "Racing Red", hex: "#c01818" },
  { name: "Burgundy", hex: "#6e1423" },
  { name: "Sunset", hex: "#e0641b" },
  { name: "Sunburst", hex: "#e8c100" },
  { name: "Champagne", hex: "#cbb682" },
  { name: "British Green", hex: "#13442b" },
  { name: "Teal", hex: "#0f5e63" },
  { name: "Miami Blue", hex: "#00b3c7" },
  { name: "Deep Blue", hex: "#13357a" },
  { name: "Midnight Purple", hex: "#2e1a47" },
  { name: "Royal Purple", hex: "#5b2a86" },
  { name: "Jet Black", hex: "#15171a" },
  { name: "Gunmetal", hex: "#3a3f45" },
  { name: "Nardo Grey", hex: "#6e7378" },
  { name: "Silver", hex: "#b8bcc2" },
  { name: "Pearl White", hex: "#eef0f2" },
];

const WHEEL_COLORS = [
  { name: "Gloss Black", hex: "#1a1c1f" },
  { name: "Silver", hex: "#c2c6cc" },
  { name: "Chrome", hex: "#d8dde3" },
  { name: "Gunmetal", hex: "#44494f" },
  { name: "Bronze", hex: "#9c6b3f" },
  { name: "Gold", hex: "#cda434" },
  { name: "White", hex: "#e8e8e8" },
  { name: "Candy Red", hex: "#a01010" },
];

const FINISHES: { id: BodyFinish; name: string }[] = [
  { id: "gloss", name: "Gloss" },
  { id: "metallic", name: "Metallic" },
  { id: "matte", name: "Matte" },
  { id: "satin", name: "Satin" },
  { id: "pearl", name: "Pearl" },
];

type HistoryEntry = { img: string; src: string; label: string };
type MobileTab = "photo" | "paint" | "wheels" | "rims";

/** True on phone-sized viewports (reacts to resize/rotation). SSR-safe: starts
 * false so the server-rendered desktop tree matches, then flips after mount. */
function useIsMobile() {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const update = () => setMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return mobile;
}

/** Downscale an upload client-side so we never ship a 12MP photo over the wire. */
function fileToDataUrl(file: File, maxSide = 1600): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
      const w = Math.round(img.width * scale);
      const h = Math.round(img.height * scale);
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("canvas unavailable"));
      ctx.drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL("image/jpeg", 0.92));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("could not read image"));
    };
    img.src = url;
  });
}

export default function Configurator() {
  const [source, setSource] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [resultSource, setResultSource] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [bodyColor, setBodyColor] = useState<string | null>(null);
  const [bodyFinish, setBodyFinish] = useState<BodyFinish | null>(null);
  const [wheelId, setWheelId] = useState<string | null>(null);
  const [wheelColor, setWheelColor] = useState<string | null>(null);
  const [wheelSize, setWheelSize] = useState<number | null>(null);
  const [wheels, setWheels] = useState<Wheel[]>([]);
  const [brand, setBrand] = useState("BBS");
  const [stock, setStock] = useState<StockCar[]>([]);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [progressPct, setProgressPct] = useState(0);
  const [progressText, setProgressText] = useState("");
  const [status, setStatus] = useState<EngineStatus>("offline");
  const [waiting, setWaiting] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const isMobile = useIsMobile();
  const [mobileTab, setMobileTab] = useState<MobileTab>("photo");
  const fileRef = useRef<HTMLInputElement>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Rendered-result cache so the size slider can scrub instantly between
  // sizes that have already been rendered for the current settings.
  const renderCache = useRef<Map<string, string>>(new Map());
  const [sweepText, setSweepText] = useState<string | null>(null);

  // Engine status + libraries. Re-fetch wheels when the engine comes up so a
  // freshly scraped catalog appears.
  useEffect(() => {
    let stop = false;
    const refresh = async () => {
      const s = await fetchEngineStatus();
      if (stop) return;
      setWaiting(s.waiting);
      setStatus((prev) => {
        if (prev !== "ready" && s.state === "ready") {
          fetchWheels().then(setWheels).catch(() => {});
          fetchStockCars().then(setStock).catch(() => {});
        }
        return s.state;
      });
    };
    refresh();
    fetchWheels().then(setWheels).catch(() => {});
    fetchStockCars().then(setStock).catch(() => {});
    const iv = setInterval(refresh, 5000);
    return () => {
      stop = true;
      clearInterval(iv);
    };
  }, []);

  const onFile = useCallback(async (file: File) => {
    try {
      const dataUrl = await fileToDataUrl(file);
      setSource(dataUrl);
      setResult(null);
      setError(null);
      setMobileTab("paint"); // phone flow: photo picked -> straight to colours
    } catch {
      setError("That file couldn't be read as an image.");
    }
  }, []);

  type EditParams = {
    bodyColor: string | null;
    bodyFinish: BodyFinish | null;
    wheelId: string | null;
    wheelColor: string | null;
    wheelSize: number | null;
    seed: number;
  };

  const cacheKey = useCallback(
    (p: EditParams) =>
      JSON.stringify([source, p.bodyColor, p.bodyFinish, p.wheelId, p.wheelColor, p.wheelSize, p.seed]),
    [source]
  );

  const runEdit = useCallback(
    async (p: EditParams): Promise<string | null> => {
      if (!source) return null;
      setBusy(true);
      setError(null);
      setElapsed(0);
      setProgressPct(4);
      setProgressText("Sending to the engine…");
      if (isMobile) window.scrollTo({ top: 0, behavior: "smooth" }); // show the preview overlay

      const t0 = Date.now();
      tickRef.current = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500);

      try {
        // Stock cars arrive as URLs; the API needs an actual data URL.
        let imageDataUrl = source;
        if (!imageDataUrl.startsWith("data:")) {
          const blob = await (await fetch(imageDataUrl)).blob();
          imageDataUrl = await new Promise<string>((resolve, reject) => {
            const r = new FileReader();
            r.onload = () => resolve(r.result as string);
            r.onerror = () => reject(new Error("could not load the stock image"));
            r.readAsDataURL(blob);
          });
        }
        const res = await edit(
          {
            imageDataUrl,
            bodyColor: p.bodyColor,
            bodyFinish: p.bodyFinish,
            wheelId: p.wheelId,
            wheelColor: p.wheelColor,
            wheelSize: p.wheelSize,
            seed: p.seed,
          },
          (j) => {
            if (j.status === "queued") {
              setProgressPct(5);
              setProgressText(
                j.position && j.position > 1
                  ? `In the queue — ${j.position} renders ahead of you`
                  : "In the queue — you're next"
              );
            } else if (j.status === "rendering") {
              if (j.progress.step > 0) {
                setProgressPct(Math.min(90, 15 + (j.progress.step / j.progress.total) * 70));
                setProgressText(`Rendering — step ${j.progress.step} of ${j.progress.total}`);
              } else {
                setProgressPct(10);
                setProgressText("Rendering — reading the image…");
              }
            }
          }
        );
        setResult(res.image);
        setResultSource(source);
        renderCache.current.set(cacheKey(p), res.image);
        const label = [
          p.bodyColor && `body ${p.bodyColor}`,
          p.bodyFinish && `${p.bodyFinish} finish`,
          p.wheelId && `wheels ${p.wheelId}`,
          p.wheelColor && `rims ${p.wheelColor}`,
          p.wheelSize && `${p.wheelSize}"`,
        ]
          .filter(Boolean)
          .join(", ");
        setHistory((h) => [{ img: res.image, src: source, label }, ...h].slice(0, 12));
        fetchWheels().then(setWheels).catch(() => {});
        return res.image;
      } catch (e) {
        if (e instanceof ApiError && e.status === 429) {
          setError("The render queue is full right now — try again in a minute.");
        } else {
          setError(
            status === "offline"
              ? "The rendering server isn't running. Start it with start.ps1, then try again."
              : `Render failed: ${e instanceof Error ? e.message : String(e)}`
          );
        }
      } finally {
        if (tickRef.current) clearInterval(tickRef.current);
        tickRef.current = null;
        setBusy(false);
      }
      return null;
    },
    [source, status, isMobile, cacheKey]
  );

  useEffect(
    () => () => {
      if (tickRef.current) clearInterval(tickRef.current);
    },
    []
  );

  // Fresh seed each Apply: results vary between attempts, so a stubborn photo
  // (e.g. a swap the model under-applies at one seed) can succeed on a retry
  // instead of failing identically forever.
  const onApply = () =>
    runEdit({
      bodyColor,
      bodyFinish,
      wheelId,
      wheelColor,
      wheelSize,
      seed: Math.floor(Math.random() * 1_000_000),
    });

  /** Size slider released: serve instantly from cache if this size was already
   * rendered with the current settings; otherwise render it once. */
  const onSizeCommit = (s: number | null) => {
    setWheelSize(s);
    if (!source || busy || status !== "ready") return;
    const p: EditParams = { bodyColor, bodyFinish, wheelId, wheelColor, wheelSize: s, seed: 0 };
    const hit = renderCache.current.get(cacheKey(p));
    if (hit) {
      setResult(hit);
      setResultSource(source);
    } else if (s !== null) {
      runEdit(p);
    }
  };

  /** Pre-render every size for the current settings so the slider scrubs in
   * real time afterwards. Sequential — one render at a time on the GPU. */
  const onSweep = async () => {
    if (!source || busy || status !== "ready") return;
    const sizes = [17, 18, 19, 20, 21, 22, 23, 24];
    for (let i = 0; i < sizes.length; i++) {
      const p: EditParams = { bodyColor, bodyFinish, wheelId, wheelColor, wheelSize: sizes[i], seed: 0 };
      if (renderCache.current.has(cacheKey(p))) continue;
      setSweepText(`${i + 1}/8`);
      setWheelSize(sizes[i]);
      const img = await runEdit(p);
      if (!img) break; // stop the sweep on error
    }
    setSweepText(null);
  };
  const onReroll = () =>
    runEdit({
      bodyColor,
      bodyFinish,
      wheelId,
      wheelColor,
      wheelSize,
      seed: Math.floor(Math.random() * 1_000_000),
    });

  /** Roll the dice: random colour, random finish, random wheel from the whole
   * catalog — selections update in the UI and the render fires immediately. */
  const onRoll = () => {
    if (!source || busy || status !== "ready" || wheels.length === 0) return;
    const hue = Math.floor(Math.random() * 360);
    const sat = 45 + Math.floor(Math.random() * 55);   // vivid enough to read as a respray
    const light = 22 + Math.floor(Math.random() * 50); // avoid pure black/white mud
    const colour = hslToHex(hue, sat, light);
    const finishPool: (BodyFinish | null)[] = [null, "gloss", "metallic", "matte", "satin", "pearl"];
    const finish = finishPool[Math.floor(Math.random() * finishPool.length)];
    const wheel = wheels[Math.floor(Math.random() * wheels.length)];

    setBodyColor(colour);
    setBodyFinish(finish);
    setWheelId(wheel.id);
    setWheelColor(null); // let the product wheel keep its real finish
    setWheelSize(null);
    if (wheel.group) setBrand(wheel.group);
    runEdit({
      bodyColor: colour,
      bodyFinish: finish,
      wheelId: wheel.id,
      wheelColor: null,
      wheelSize: null,
      seed: Math.floor(Math.random() * 1_000_000),
    });
  };

  const canRoll = !!source && !busy && status === "ready" && wheels.length > 0;

  const onDownload = () => {
    if (!result) return;
    const a = document.createElement("a");
    a.href = result;
    a.download = `wheels-${Date.now()}.jpg`;
    a.click();
  };

  const onUseAsSource = () => {
    if (!result) return;
    setSource(result);
    setResult(null);
    setBodyColor(null);
    setBodyFinish(null);
    setWheelId(null);
    setWheelColor(null);
    setWheelSize(null);
  };

  const brands = useMemo(
    () => Array.from(new Set(wheels.map((w) => w.group || ""))).filter(Boolean).sort(),
    [wheels]
  );
  useEffect(() => {
    if (brands.length > 0 && !brands.includes(brand)) setBrand(brands.includes("BBS") ? "BBS" : brands[0]);
  }, [brands, brand]);

  const canApply =
    !!source &&
    !busy &&
    status === "ready" &&
    !!(bodyColor || bodyFinish || wheelId || wheelColor || wheelSize);

  // Always-visible list of what Apply will change, so a leftover selection
  // (e.g. a wheel colour from earlier) can't silently affect the next render.
  const changeSummary = useMemo(() => {
    const bits: string[] = [];
    if (bodyColor) bits.push(`body ${bodyColor}`);
    if (bodyFinish) bits.push(`${bodyFinish} paint`);
    if (wheelId) {
      const w = wheels.find((x) => x.id === wheelId);
      const g = w?.group ?? "";
      bits.push(
        !w ? "new wheels" : w.name.toLowerCase().startsWith(g.toLowerCase()) ? w.name : `${g} ${w.name}`
      );
    }
    if (wheelColor) {
      const c = WHEEL_COLORS.find((x) => x.hex.toLowerCase() === wheelColor.toLowerCase());
      bits.push(`rims ${c ? c.name.toLowerCase() : wheelColor}`);
    }
    if (wheelSize) bits.push(`${wheelSize}″ wheels`);
    return bits.join("  ·  ");
  }, [bodyColor, bodyFinish, wheelId, wheelColor, wheelSize, wheels]);

  // ---------------------------------------------------------- phone layout
  if (isMobile) {
    const TABS: { id: MobileTab; name: string }[] = [
      { id: "photo", name: "Photo" },
      { id: "paint", name: "Paint" },
      { id: "wheels", name: "Wheels" },
      { id: "rims", name: "Rims" },
    ];
    return (
      <main className="flex min-h-screen flex-col bg-neutral-950 text-neutral-100">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        />

        <header className="flex shrink-0 items-center justify-between border-b border-neutral-800 px-4 py-2.5">
          <h1 className="text-base font-semibold tracking-tight">Wheels</h1>
          <div className="flex items-center gap-2">
            {waiting > 0 && (
              <span className="rounded-full border border-amber-700/60 bg-amber-950/40 px-2 py-1 text-[10px] text-amber-300">
                {waiting} in queue
              </span>
            )}
            <StatusBadge status={status} />
          </div>
        </header>

        {/* Preview */}
        <div className="relative h-[44vh] shrink-0 overflow-hidden bg-neutral-900">
          {result && resultSource ? (
            <CompareSlider before={resultSource} after={result} />
          ) : source ? (
            <img src={source} alt="car" className="h-full w-full object-contain" />
          ) : (
            <UploadDrop onFile={onFile} onPick={() => fileRef.current?.click()} />
          )}
          {busy && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-neutral-950/75 px-6 backdrop-blur-sm">
              <div className="w-full max-w-xs">
                <div className="mb-2 flex justify-between text-sm text-neutral-300">
                  <span>{progressText}</span>
                  <span className="tabular-nums">{elapsed}s</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-neutral-800">
                  <div
                    className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Result toolbar + history */}
        {(result || history.length > 0) && (
          <div className="shrink-0 space-y-2 border-b border-neutral-800 px-3 py-2">
            {result && !busy && (
              <div className="flex gap-2">
                <ToolbarButton onClick={onDownload} label="Download" primary />
                <ToolbarButton onClick={onUseAsSource} label="Use as source" />
                <ToolbarButton onClick={onReroll} label="↻ Re-roll" />
              </div>
            )}
            {history.length > 0 && (
              <div className="flex gap-2 overflow-x-auto">
                {history.map((h, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setResult(h.img);
                      setResultSource(h.src);
                    }}
                    className={`h-12 w-16 shrink-0 overflow-hidden rounded-md border ${
                      result === h.img ? "border-indigo-400" : "border-neutral-700"
                    }`}
                  >
                    <img src={h.img} alt={h.label} className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tabs */}
        <nav className="flex shrink-0 gap-1.5 border-b border-neutral-800 px-3 py-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setMobileTab(t.id)}
              className={`flex-1 rounded-lg px-2 py-2 text-sm font-medium transition ${
                mobileTab === t.id
                  ? "bg-indigo-500/20 text-white ring-1 ring-indigo-400"
                  : "text-neutral-400 hover:bg-neutral-900"
              }`}
            >
              {t.name}
            </button>
          ))}
        </nav>

        {/* Active tab content (page scrolls; padding clears the sticky bar) */}
        <section className="flex-1 px-3 pb-40 pt-3">
          {mobileTab === "photo" && (
            <div className="space-y-3">
              <button
                onClick={() => fileRef.current?.click()}
                className="w-full rounded-xl bg-white py-3 font-medium text-neutral-900"
              >
                Upload a photo
              </button>
              {stock.length > 0 && (
                <>
                  <p className="text-xs uppercase tracking-wide text-neutral-500">Or pick a stock car</p>
                  <div className="grid grid-cols-2 gap-2">
                    {stock.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => {
                          setSource(c.image);
                          setResult(null);
                          setMobileTab("paint");
                        }}
                        className="h-24 overflow-hidden rounded-lg border border-neutral-700"
                      >
                        <img src={c.thumb} alt={c.name} className="h-full w-full object-cover" />
                      </button>
                    ))}
                  </div>
                </>
              )}
              {source && (
                <button
                  onClick={() => {
                    setSource(null);
                    setResult(null);
                  }}
                  className="w-full rounded-xl border border-neutral-700 py-2.5 text-sm text-neutral-300"
                >
                  Clear current photo
                </button>
              )}
            </div>
          )}

          {mobileTab === "paint" && (
            <div className="space-y-4">
              <Swatches
                colors={BODY_COLORS}
                selected={bodyColor}
                onSelect={setBodyColor}
                onClear={() => setBodyColor(null)}
              />
              <ColorWheel value={bodyColor} onChange={setBodyColor} />
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-neutral-500">Paint finish</p>
                <div className="flex flex-wrap gap-1.5">
                  <FinishPill active={bodyFinish === null} onClick={() => setBodyFinish(null)} label="Keep" />
                  {FINISHES.map((f) => (
                    <FinishPill
                      key={f.id}
                      active={bodyFinish === f.id}
                      onClick={() => setBodyFinish(f.id)}
                      label={f.name}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          {mobileTab === "wheels" && (
            <div className="space-y-3">
              <select
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                className="w-full cursor-pointer rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2.5 text-sm text-neutral-100 outline-none"
              >
                {brands.map((b) => (
                  <option key={b} value={b}>
                    {b} ({wheels.filter((w) => (w.group || "") === b).length})
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-3 gap-2">
                <div className="aspect-square">
                  <WheelTile selected={wheelId === null} onClick={() => setWheelId(null)} label="Original" />
                </div>
                {wheels
                  .filter((w) => (w.group || "") === brand)
                  .map((w) => (
                    <div key={w.id} className="aspect-square">
                      <WheelTile
                        selected={wheelId === w.id}
                        onClick={() => {
                          setWheelId(w.id);
                          setWheelColor(null); // show the product's real finish
                        }}
                        label={w.name}
                        sub={w.finish}
                        thumb={w.thumb || undefined}
                      />
                    </div>
                  ))}
              </div>
            </div>
          )}

          {mobileTab === "rims" && (
            <div className="space-y-4">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-wide text-neutral-500">Wheel colour</p>
                <Swatches
                  colors={WHEEL_COLORS}
                  selected={wheelColor}
                  onSelect={setWheelColor}
                  onClear={() => setWheelColor(null)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-wide text-neutral-500">
                  Wheel size {wheelSize ? `— ${wheelSize}"` : "— standard"}
                </p>
                <input
                  type="range"
                  min={17}
                  max={24}
                  step={1}
                  value={wheelSize ?? 20}
                  onChange={(e) => setWheelSize(Number(e.target.value))}
                  onPointerUp={(e) => onSizeCommit(Number((e.target as HTMLInputElement).value))}
                  className="w-full accent-indigo-400"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => onSizeCommit(null)}
                    className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300"
                  >
                    Reset size
                  </button>
                  <button
                    onClick={onSweep}
                    disabled={busy}
                    className="rounded border border-dashed border-neutral-600 px-2 py-1 text-xs text-neutral-300 disabled:opacity-40"
                  >
                    {sweepText ? `Rendering ${sweepText}` : "⚡ Render all sizes"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* Sticky action bar (thumb zone) */}
        <div className="fixed inset-x-0 bottom-0 z-30 space-y-2 border-t border-neutral-800 bg-neutral-950/95 px-3 pb-[max(env(safe-area-inset-bottom),0.75rem)] pt-2 backdrop-blur">
          {error && (
            <p className="rounded-lg border border-red-900 bg-red-950/60 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          )}
          <p className="px-1 text-center text-[11px] text-neutral-500">
            {changeSummary ? `Will change: ${changeSummary}` : "No changes selected yet"}
          </p>
          <div className="flex gap-2">
            <button
              onClick={onRoll}
              disabled={!canRoll}
              title="Random colour + random wheels"
              className="shrink-0 rounded-xl border border-dashed border-neutral-600 px-4 text-xl transition disabled:border-neutral-800 disabled:opacity-40"
            >
              🎲
            </button>
            <button
              onClick={onApply}
              disabled={!canApply}
              className="min-w-0 flex-1 rounded-xl bg-indigo-500 py-3.5 font-semibold text-white transition disabled:bg-neutral-800 disabled:text-neutral-500"
            >
              {busy
                ? progressText || "Rendering…"
                : status !== "ready"
                  ? "Engine warming up…"
                  : "Apply changes"}
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col bg-neutral-950 text-neutral-100 lg:h-screen lg:overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-neutral-800 px-6 py-3">
        <h1 className="text-lg font-semibold tracking-tight">
          Wheels <span className="hidden text-neutral-500 sm:inline">· Car Colour &amp; Wheel Visualizer</span>
        </h1>
        <div className="flex items-center gap-2">
          {waiting > 0 && (
            <span className="rounded-full border border-amber-700/60 bg-amber-950/40 px-3 py-1.5 text-xs text-amber-300">
              {waiting} render{waiting > 1 ? "s" : ""} in queue
            </span>
          )}
          <StatusBadge status={status} />
        </div>
      </header>

      {/* Main row: preview + controls rail */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Preview column */}
        <section className="flex min-w-0 flex-1 flex-col gap-2 p-4">
          <div className="relative h-[46vh] min-h-0 overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900 lg:h-auto lg:flex-1">
            {result && resultSource ? (
              <CompareSlider before={resultSource} after={result} />
            ) : source ? (
              <img src={source} alt="car" className="h-full w-full object-contain" />
            ) : (
              <UploadDrop onFile={onFile} onPick={() => fileRef.current?.click()} />
            )}

            {busy && (
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-neutral-950/75 backdrop-blur-sm">
                <div className="w-72">
                  <div className="mb-2 flex justify-between text-sm text-neutral-300">
                    <span>{sweepText ? `Size sweep ${sweepText} — ${progressText}` : progressText}</span>
                    <span className="tabular-nums">{elapsed}s</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-neutral-800">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                </div>
                <p className="text-xs text-neutral-500">
                  {wheelId?.startsWith("cat:")
                    ? "Product-wheel swaps take ~30–60 seconds"
                    : "Typically ~15 seconds on the local GPU"}
                </p>
              </div>
            )}

            {/* Wheel-size slider — sizes render once, then scrub instantly */}
            {source && (
              <div className="absolute right-3 top-1/2 z-10 flex -translate-y-1/2 flex-col items-center gap-2 rounded-xl border border-neutral-700 bg-neutral-950/85 px-2 py-3 backdrop-blur">
                <span className="text-xs font-semibold tabular-nums text-white">
                  {wheelSize ? `${wheelSize}"` : "std"}
                </span>
                <input
                  type="range"
                  min={17}
                  max={24}
                  step={1}
                  value={wheelSize ?? 20}
                  onChange={(e) => setWheelSize(Number(e.target.value))}
                  onPointerUp={(e) => onSizeCommit(Number((e.target as HTMLInputElement).value))}
                  onKeyUp={(e) => {
                    if (e.key === "Enter") onSizeCommit(Number((e.target as HTMLInputElement).value));
                  }}
                  className="accent-indigo-400"
                  style={{ writingMode: "vertical-lr", direction: "rtl", height: "9rem" }}
                  title="Wheel size (17-24 inch)"
                />
                <span className="text-center text-[9px] leading-tight text-neutral-500">
                  wheel
                  <br />
                  size
                </span>
                <button
                  onClick={() => onSizeCommit(null)}
                  className="rounded border border-neutral-700 px-1.5 py-0.5 text-[10px] text-neutral-300 hover:border-neutral-400"
                  title="Back to the original wheel size"
                >
                  reset
                </button>
                <button
                  onClick={onSweep}
                  disabled={busy}
                  className="rounded border border-dashed border-neutral-600 px-1.5 py-0.5 text-[10px] text-neutral-300 hover:border-indigo-400 disabled:opacity-40"
                  title="Pre-render all 8 sizes once - then the slider responds instantly"
                >
                  {sweepText ?? "⚡ all"}
                </button>
              </div>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {result && !busy && (
              <>
                <ToolbarButton onClick={onDownload} label="Download" primary />
                <ToolbarButton onClick={onUseAsSource} label="Use as source" />
                <ToolbarButton onClick={onReroll} label="↻ Re-roll" />
                <span className="ml-auto hidden text-xs text-neutral-500 sm:inline">
                  Drag the divider to compare original ↔ edited
                </span>
              </>
            )}
          </div>

          {history.length > 0 && (
            <div className="flex shrink-0 gap-2 overflow-x-auto pb-1">
              {history.map((h, i) => (
                <button
                  key={i}
                  title={h.label}
                  onClick={() => {
                    setResult(h.img);
                    setResultSource(h.src);
                  }}
                  className={`h-14 w-20 shrink-0 overflow-hidden rounded-md border ${
                    result === h.img ? "border-indigo-400" : "border-neutral-700 hover:border-neutral-400"
                  }`}
                >
                  <img src={h.img} alt={h.label} className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Controls rail */}
        <aside className="w-full shrink-0 space-y-4 overflow-y-auto border-t border-neutral-800 p-4 lg:w-[21rem] lg:border-l lg:border-t-0">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
          />

          <Panel title="Source image">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => fileRef.current?.click()}
                className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-200"
              >
                Upload a photo
              </button>
              {source && (
                <button
                  onClick={() => {
                    setSource(null);
                    setResult(null);
                  }}
                  className="rounded-lg border border-neutral-700 px-4 py-2 text-sm hover:bg-neutral-800"
                >
                  Clear
                </button>
              )}
            </div>
            {stock.length > 0 && (
              <div className="mt-3 flex gap-2 overflow-x-auto">
                {stock.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => {
                      setSource(c.image);
                      setResult(null);
                    }}
                    title={c.name}
                    className="h-14 w-20 shrink-0 overflow-hidden rounded-md border border-neutral-700 hover:border-neutral-400"
                  >
                    <img src={c.thumb} alt={c.name} className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Body colour">
            <Swatches
              colors={BODY_COLORS}
              selected={bodyColor}
              onSelect={setBodyColor}
              onClear={() => setBodyColor(null)}
            />
            <ColorWheel value={bodyColor} onChange={setBodyColor} />
            <div className="mt-4">
              <p className="mb-2 text-xs uppercase tracking-wide text-neutral-500">Paint finish</p>
              <div className="flex flex-wrap gap-1.5">
                <FinishPill active={bodyFinish === null} onClick={() => setBodyFinish(null)} label="Keep" />
                {FINISHES.map((f) => (
                  <FinishPill
                    key={f.id}
                    active={bodyFinish === f.id}
                    onClick={() => setBodyFinish(f.id)}
                    label={f.name}
                  />
                ))}
              </div>
            </div>
          </Panel>

          <Panel title="Wheel colour">
            <Swatches
              colors={WHEEL_COLORS}
              selected={wheelColor}
              onSelect={setWheelColor}
              onClear={() => setWheelColor(null)}
            />
            <p className="mt-3 text-xs text-neutral-500">
              Wheel size: use the slider on the preview — each size renders once, then scrubs instantly.
            </p>
          </Panel>

          {error && (
            <p className="rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          )}

          <button
            onClick={onRoll}
            disabled={!canRoll}
            title="Random colour, random finish, random wheels — rendered instantly"
            className="w-full rounded-xl border border-dashed border-neutral-600 py-2.5 text-sm font-medium text-neutral-300 transition hover:border-indigo-400 hover:text-white disabled:cursor-not-allowed disabled:border-neutral-800 disabled:text-neutral-600"
          >
            🎲 Roll the dice
          </button>
          <p className="px-1 text-center text-xs text-neutral-500">
            {changeSummary ? `Will change: ${changeSummary}` : "No changes selected yet"}
          </p>
          <button
            onClick={onApply}
            disabled={!canApply}
            className="w-full rounded-xl bg-indigo-500 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-500"
          >
            {busy ? "Rendering…" : status !== "ready" ? "Engine warming up…" : "Apply changes"}
          </button>
        </aside>
      </div>

      {/* Bottom wheel strip */}
      <footer className="shrink-0 border-t border-neutral-800 bg-neutral-900/70 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-44 shrink-0 sm:w-56">
            <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Wheel manufacturer</p>
            <select
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              className="w-full cursor-pointer rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-400"
            >
              {brands.map((b) => (
                <option key={b} value={b}>
                  {b} ({wheels.filter((w) => (w.group || "") === b).length})
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-0 flex-1 overflow-x-auto">
            <div className="flex w-max gap-2 pb-1">
              <div className="h-28 w-28 shrink-0">
                <WheelTile selected={wheelId === null} onClick={() => setWheelId(null)} label="Original" />
              </div>
              {wheels
                .filter((w) => (w.group || "") === brand)
                .map((w) => (
                  <div key={w.id} className="h-28 w-28 shrink-0">
                    <WheelTile
                      selected={wheelId === w.id}
                      onClick={() => {
                        setWheelId(w.id);
                        setWheelColor(null); // show the product's real finish; recolour after if wanted
                      }}
                      label={w.name}
                      sub={w.finish}
                      thumb={w.thumb || undefined}
                    />
                  </div>
                ))}
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}

function StatusBadge({ status }: { status: EngineStatus }) {
  const map = {
    ready: { dot: "bg-emerald-400", text: "Engine ready" },
    warming: { dot: "bg-amber-400 animate-pulse", text: "Engine warming up" },
    offline: { dot: "bg-red-500", text: "Engine offline" },
  } as const;
  const m = map[status];
  return (
    <span className="flex items-center gap-2 rounded-full border border-neutral-800 px-3 py-1.5 text-xs text-neutral-300">
      <span className={`h-2 w-2 rounded-full ${m.dot}`} />
      {m.text}
    </span>
  );
}

function CompareSlider({ before, after }: { before: string; after: string }) {
  const [pct, setPct] = useState(50);
  const ref = useRef<HTMLDivElement>(null);

  const onMove = (clientX: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    setPct(Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100)));
  };

  return (
    <div
      ref={ref}
      className="relative h-full w-full touch-none select-none"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        onMove(e.clientX);
      }}
      onPointerMove={(e) => {
        if (e.buttons & 1) onMove(e.clientX);
      }}
    >
      <img src={after} alt="edited" className="absolute inset-0 h-full w-full object-contain" />
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pct}% 0 0)` }}>
        <img src={before} alt="original" className="h-full w-full object-contain" />
      </div>
      <div className="absolute inset-y-0 z-10 w-0.5 bg-white/80" style={{ left: `${pct}%` }}>
        <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-neutral-300 bg-white px-1.5 py-1 text-[10px] font-bold text-neutral-800 shadow">
          ◂▸
        </div>
      </div>
      <span className="absolute left-3 top-3 rounded bg-neutral-950/70 px-2 py-0.5 text-[11px] text-neutral-200">
        Original
      </span>
      <span className="absolute right-3 top-3 rounded bg-neutral-950/70 px-2 py-0.5 text-[11px] text-neutral-200">
        Edited
      </span>
    </div>
  );
}

function ToolbarButton({
  onClick,
  label,
  primary,
}: {
  onClick: () => void;
  label: string;
  primary?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={
        primary
          ? "rounded-lg bg-white px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-200"
          : "rounded-lg border border-neutral-700 px-4 py-2 text-sm hover:bg-neutral-800"
      }
    >
      {label}
    </button>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-400">{title}</h2>
      {children}
    </div>
  );
}

function Swatches({
  colors,
  selected,
  onSelect,
  onClear,
}: {
  colors: { name: string; hex: string }[];
  selected: string | null;
  onSelect: (hex: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={onClear}
        className={`h-9 rounded-lg border px-3 text-xs ${
          selected === null
            ? "border-white text-white"
            : "border-neutral-700 text-neutral-400 hover:border-neutral-500"
        }`}
      >
        Keep
      </button>
      {colors.map((c) => (
        <button
          key={c.hex}
          title={c.name}
          onClick={() => onSelect(c.hex)}
          style={{ backgroundColor: c.hex }}
          className={`h-9 w-9 rounded-lg border-2 transition ${
            selected?.toLowerCase() === c.hex.toLowerCase()
              ? "border-white"
              : "border-white/25 hover:border-neutral-400"
          }`}
        />
      ))}
    </div>
  );
}

function FinishPill({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-xs transition ${
        active
          ? "border-indigo-400 bg-indigo-500/20 text-white"
          : "border-neutral-700 text-neutral-400 hover:border-neutral-500"
      }`}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------- colour wheel

function hslToHex(h: number, s: number, l: number): string {
  const sn = s / 100;
  const ln = l / 100;
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const a = sn * Math.min(ln, 1 - ln);
    const c = ln - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * c)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function hexToHsl(hex: string): { h: number; s: number; l: number } | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const r = parseInt(m[1].slice(0, 2), 16) / 255;
  const g = parseInt(m[1].slice(2, 4), 16) / 255;
  const b = parseInt(m[1].slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l: l * 100 };
  const d = max - min;
  const s = d / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return { h: (h * 60 + 360) % 360, s: Math.min(100, s * 100), l: l * 100 };
}

/** Hue/saturation disc + lightness slider. Any colour, not just presets. */
function ColorWheel({ value, onChange }: { value: string | null; onChange: (hex: string) => void }) {
  const SIZE = 148;
  const R = SIZE / 2;
  const hsl = (value && hexToHsl(value)) || null;
  const [lightness, setLightness] = useState(50);
  const ref = useRef<HTMLDivElement>(null);
  const l = hsl ? Math.round(hsl.l) : lightness;
  const h = hsl?.h ?? 0;
  const s = hsl?.s ?? 0;

  const pick = (clientX: number, clientY: number) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const dx = clientX - (rect.left + R);
    const dy = clientY - (rect.top + R);
    const hue = (Math.atan2(dy, dx) * 180) / Math.PI + 90;
    const sat = Math.min(1, Math.hypot(dx, dy) / R) * 100;
    onChange(hslToHex((hue + 360) % 360, sat, l));
  };

  const ang = ((h - 90) * Math.PI) / 180;
  const dotX = R + Math.cos(ang) * (s / 100) * (R - 6);
  const dotY = R + Math.sin(ang) * (s / 100) * (R - 6);

  return (
    <div className="mt-4 flex items-center gap-4">
      <div
        ref={ref}
        className="relative shrink-0 cursor-crosshair touch-none rounded-full"
        style={{
          width: SIZE,
          height: SIZE,
          background:
            "radial-gradient(circle, #fff 0%, transparent 70%), conic-gradient(red, yellow, lime, cyan, blue, magenta, red)",
          filter: `brightness(${0.35 + (l / 100) * 1.3})`,
        }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          pick(e.clientX, e.clientY);
        }}
        onPointerMove={(e) => {
          if (e.buttons & 1) pick(e.clientX, e.clientY);
        }}
      >
        {value && (
          <span
            className="pointer-events-none absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow"
            style={{ left: dotX, top: dotY, backgroundColor: value }}
          />
        )}
      </div>
      <div className="flex-1">
        <p className="mb-1 text-xs text-neutral-500">Lightness</p>
        <input
          type="range"
          min={5}
          max={95}
          value={l}
          onChange={(e) => {
            const nl = Number(e.target.value);
            setLightness(nl);
            if (hsl) onChange(hslToHex(hsl.h, hsl.s, nl));
          }}
          className="w-full accent-indigo-400"
        />
        <div className="mt-2 flex items-center gap-2 text-sm text-neutral-400">
          <span
            className="inline-block h-6 w-6 rounded border border-neutral-700"
            style={{ backgroundColor: value ?? "transparent" }}
          />
          {value ? <span className="font-mono text-xs text-neutral-300">{value}</span> : "Pick any colour"}
        </div>
      </div>
    </div>
  );
}

function WheelTile({
  selected,
  onClick,
  label,
  sub,
  thumb,
}: {
  selected: boolean;
  onClick: () => void;
  label: string;
  sub?: string;
  thumb?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={sub ? `${label} — ${sub}` : label}
      className={`relative h-full w-full overflow-hidden rounded-lg border-2 bg-neutral-800 ${
        selected ? "border-indigo-400" : "border-transparent hover:border-neutral-500"
      }`}
    >
      {thumb ? (
        <>
          <img src={thumb} alt={label} className="h-full w-full bg-white object-cover" loading="lazy" />
          <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-neutral-950/95 to-transparent px-1 pb-1 pt-4 text-left">
            <span className="block truncate text-[10px] font-medium leading-tight text-neutral-100">
              {label}
            </span>
            {sub && (
              <span className="block truncate text-[9px] leading-tight text-neutral-400">{sub}</span>
            )}
          </span>
        </>
      ) : (
        <span className="flex h-full items-center justify-center px-1 text-center text-[11px] text-neutral-300">
          {label}
        </span>
      )}
    </button>
  );
}

function UploadDrop({ onFile, onPick }: { onFile: (f: File) => void; onPick: () => void }) {
  return (
    <div
      onClick={onPick}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className="flex h-full cursor-pointer flex-col items-center justify-center gap-2 text-center hover:bg-neutral-900/60"
    >
      <p className="text-lg font-medium">Drop a car photo here</p>
      <p className="text-sm text-neutral-500">or click to browse · or pick a stock car</p>
    </div>
  );
}
