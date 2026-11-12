/** Typed client for the LastFit API. Types come from FastAPI's OpenAPI (`npm run gen:api`). */
import type { components } from "./api-types";

type S = components["schemas"];
export type FootProfile = S["FootProfile"];
export type Foot = S["Foot"];
export type Preferences = S["Preferences"];
export type HistoryEntry = S["HistoryEntry"];
export type Recommendation = S["Recommendation"];
export type Pick = S["Pick"];
export type FitFactor = S["FitFactor"];
export type Task = S["TaskOut"];
export type User = S["UserOut"];
export type Scan = S["ScanOut"];
export type ShoeHit = S["ShoeOut"];
export type FeedbackIn = S["FeedbackIn"];
export type Rating = HistoryEntry["rating"];
export type IssueTag = HistoryEntry["issues"][number];

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function detail(body: unknown): string | null {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((e: { loc?: (string | number)[]; msg?: string }) =>
        `${(e.loc ?? []).filter((p) => p !== "body").join(" › ")}: ${e.msg}`,
      )
      .join("\n");
  }
  return null;
}

async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...rest,
      headers: json === undefined ? rest.headers : { "Content-Type": "application/json", ...rest.headers },
      body: json === undefined ? rest.body : JSON.stringify(json),
    });
  } catch {
    throw new ApiError("We can't reach LastFit right now. Check your connection and try again.", 0);
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(detail(body) ?? `Something went wrong (${res.status}).`, res.status);
  return body as T;
}

/** Upload with progress (fetch can't report upload progress; XHR can). */
function upload<T>(path: string, form: FormData, onProgress?: (pct: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}${path}`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () =>
      xhr.status < 300
        ? resolve(xhr.response as T)
        : reject(new ApiError(detail(xhr.response) ?? `Upload failed (${xhr.status}).`, xhr.status));
    xhr.onerror = () => reject(new ApiError("Upload failed. Check your connection and try again.", 0));
    xhr.send(form);
  });
}

export type ChatEvent =
  | { event: "token"; data: { text: string } }
  | { event: "tool"; data: { name: string } }
  | { event: "picks"; data: Recommendation }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

export const api = {
  status: () => request<{ llm_ready: boolean; reason: string | null }>("/status"),
  createUser: () => request<User>("/users", { method: "POST" }),
  getUser: (id: string) => request<User>(`/users/${id}`),
  uploadScan: (userId: string, files: File[], onProgress?: (pct: number) => void) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    return upload<Scan>(`/users/${userId}/scans`, form, onProgress);
  },
  confirmScan: (userId: string, scanId: number, profile: FootProfile) =>
    request<Scan>(`/users/${userId}/scans/${scanId}/confirm`, { method: "PUT", json: profile }),
  manualScan: (userId: string, profile: FootProfile) =>
    request<Scan>(`/users/${userId}/scans/manual`, { method: "POST", json: profile }),
  putPreferences: (userId: string, prefs: Preferences) =>
    request<Preferences>(`/users/${userId}/preferences`, { method: "PUT", json: prefs }),
  putHistory: (userId: string, history: HistoryEntry[]) =>
    request<HistoryEntry[]>(`/users/${userId}/history`, { method: "PUT", json: history }),
  searchShoes: (q: string) => request<ShoeHit[]>(`/shoes/search?q=${encodeURIComponent(q)}`),
  recommend: (userId: string) => request<Task>(`/users/${userId}/recommend`, { method: "POST" }),
  task: (taskId: string) => request<Task>(`/tasks/${taskId}`),
  feedback: (userId: string, body: FeedbackIn) =>
    request<unknown>(`/users/${userId}/feedback`, { method: "POST", json: body }),

  /** POST /users/{id}/chat and yield its server-sent events. */
  async *chat(userId: string, messages: { role: "user" | "assistant"; content: string }[], signal?: AbortSignal) {
    const res = await fetch(`${BASE}/users/${userId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
      signal,
    });
    if (!res.ok || !res.body) {
      const body = await res.json().catch(() => null);
      throw new ApiError(detail(body) ?? `Chat failed (${res.status}).`, res.status);
    }
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let cut;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const fields = Object.fromEntries(
          block.split("\n").map((line) => [line.slice(0, line.indexOf(":")), line.slice(line.indexOf(":") + 2)]),
        );
        if (fields.event) yield { event: fields.event, data: JSON.parse(fields.data || "{}") } as ChatEvent;
      }
    }
  },
};
