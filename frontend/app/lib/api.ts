// Client for the Wheels FastAPI backend. Same-origin by default — Next.js proxies
// /api and /static to the backend (see next.config.ts), which is what makes the app
// shareable through a tunnel. Override only for unusual local setups.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type Wheel = {
  id: string;
  name: string;
  thumb: string;
  group?: string;  // "Styles" or a brand name like "BBS"
  finish?: string; // catalog wheels: the product finish, e.g. "Gold With Polished Rim"
};
export type StockCar = { id: string; name: string; thumb: string; image: string };

export type BodyFinish = "gloss" | "metallic" | "matte" | "satin" | "pearl";

export type EditRequest = {
  imageDataUrl: string;       // source image as a data URL
  bodyColor?: string | null;  // hex, e.g. "#b81414"
  bodyFinish?: BodyFinish | null; // paint finish; null = leave to the engine default
  wheelId?: string | null;    // wheel design from the library
  wheelColor?: string | null; // hex
  wheelSize?: number | null;  // 17-24 inches
  seed?: number;              // vary for a different take on the same edit
};

export type EditResponse = {
  image: string;              // result as a data URL
  ms: number;                 // server processing time
};

export type Progress = {
  stage: "idle" | "rendering";
  step: number;
  total: number;
  queued: number;
};

export type EngineStatus = "ready" | "warming" | "offline";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, `${path} failed: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export type JobUpdate = {
  status: "queued" | "rendering" | "done" | "error";
  error: string | null;
  ms: number;
  image: string | null;
  position: number | null; // 0 = rendering now, N = jobs ahead of you
  progress: Progress;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Submit the edit as a job and poll until it finishes. Each poll is a small,
 * fast request — nothing is held open for the 15-60s of GPU work, so proxies
 * and tunnels can't kill the render mid-flight. `onUpdate` fires on every poll
 * with queue position + step progress for the UI. */
export async function edit(
  req: EditRequest,
  onUpdate?: (j: JobUpdate) => void
): Promise<EditResponse> {
  const { job_id } = await postJSON<{ job_id: string }>("/api/edit", {
    image: req.imageDataUrl,
    body_color: req.bodyColor ?? null,
    body_finish: req.bodyFinish ?? null,
    wheel_id: req.wheelId ?? null,
    wheel_color: req.wheelColor ?? null,
    wheel_size: req.wheelSize ?? null,
    seed: req.seed ?? 0,
  });
  for (let misses = 0; ; ) {
    await sleep(1500);
    let j: JobUpdate;
    try {
      const res = await fetch(`${API_BASE}/api/job/${job_id}`, { cache: "no-store" });
      if (!res.ok) throw new ApiError(res.status, `job poll failed: ${res.status}`);
      j = (await res.json()) as JobUpdate;
      misses = 0;
    } catch (e) {
      if (++misses >= 8) throw e; // tolerate brief network/tunnel blips
      continue;
    }
    onUpdate?.(j);
    if (j.status === "done" && j.image) return { image: j.image, ms: j.ms };
    if (j.status === "error") throw new ApiError(500, j.error ?? "render failed");
  }
}

export async function fetchProgress(): Promise<Progress> {
  const res = await fetch(`${API_BASE}/api/progress`, { cache: "no-store" });
  if (!res.ok) throw new Error("progress unavailable");
  return res.json();
}

export async function fetchEngineStatus(): Promise<{ state: EngineStatus; waiting: number }> {
  try {
    const res = await fetch(`${API_BASE}/readyz`, { cache: "no-store" });
    if (!res.ok) return { state: "offline", waiting: 0 };
    const j = (await res.json()) as { ready: boolean; waiting?: number };
    return { state: j.ready ? "ready" : "warming", waiting: j.waiting ?? 0 };
  } catch {
    return { state: "offline", waiting: 0 };
  }
}

export async function fetchWheels(): Promise<Wheel[]> {
  const res = await fetch(`${API_BASE}/api/wheels`);
  if (!res.ok) throw new Error("failed to load wheels");
  return res.json();
}

export async function fetchStockCars(): Promise<StockCar[]> {
  const res = await fetch(`${API_BASE}/api/stock-cars`);
  if (!res.ok) throw new Error("failed to load stock cars");
  return res.json();
}
