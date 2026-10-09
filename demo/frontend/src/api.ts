import type {
  AiStatus, AppConfig, CorrectionProposal, Job, ProjectInfo, ProjectSummary, ProposedChange, RunResult, StoredOverride,
} from "./types";
import { t } from "./i18n";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      cache: "no-store", // always fresh data when moving between pages
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, t("error.network"));
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not JSON */
    }
    if (res.status === 404 && !msg) msg = t("error.not_found");
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;
const P = (pid: string) => `/api/projects/${enc(pid)}`;

export const api = {
  config: () => req<AppConfig>("GET", "/api/config"),
  companies: () => req<{ name: string; projects: number }[]>("GET", "/api/companies"),
  projects: (company: string) => req<ProjectSummary[]>("GET", `/api/companies/${enc(company)}/projects`),
  project: (pid: string) => req<ProjectInfo>("GET", P(pid)),
  run: (pid: string, kind: "run" | "recalc" = "run") => req<Job>("POST", `${P(pid)}/run?kind=${kind}`),
  job: (id: string) => req<Job>("GET", `/api/jobs/${enc(id)}`),
  revision: (pid: string, rev: number) => req<RunResult>("GET", `${P(pid)}/revisions/${rev}`),
  download: (pid: string, rev: number, kind: string) => `${P(pid)}/revisions/${rev}/download/${kind}`,
  edit: (pid: string, body: { edit_key: string; value: unknown; reason?: string | null; label?: string | null; before?: unknown }) =>
    req<StoredOverride>("POST", `${P(pid)}/edits`, body),
  deleteEdit: (pid: string, id: number) => req<{ ok: boolean }>("DELETE", `${P(pid)}/edits/${id}`),
  interpret: (pid: string, text: string) => req<CorrectionProposal>("POST", `${P(pid)}/corrections/interpret`, { text }),
  accept: (pid: string, correction_id: number, text: string, changes: ProposedChange[]) =>
    req<{ applied: StoredOverride[] }>("POST", `${P(pid)}/corrections/accept`, { correction_id, text, changes }),
  approve: (pid: string, rev: number) => req<Record<string, unknown>>("POST", `${P(pid)}/approve/${rev}`),
  // sources
  pdfUrl: (pid: string, rev: number, fileId: string, page: number, boxes: number[][], maxPx = 1700) =>
    `${P(pid)}/source/pdf?file_id=${enc(fileId)}&page=${page}&rev=${rev}&boxes=${enc(JSON.stringify(boxes))}&max_px=${maxPx}`,
  pdfInfo: (pid: string, rev: number, fileId: string, page: number) =>
    req<{ name: string; path: string; pages: number; page: number; width: number; height: number }>(
      "GET", `${P(pid)}/source/pdfinfo?file_id=${enc(fileId)}&page=${page}&rev=${rev}`),
  sheet: (pid: string, rev: number, fileId: string, row: number, sheet?: string | null) =>
    req<{ name: string; path: string; sheet: string; rows: { row: number; cells: (string | number)[] }[]; highlight_row: number; columns: string[] }>(
      "GET", `${P(pid)}/source/sheet?file_id=${enc(fileId)}&row=${row}&rev=${rev}${sheet ? `&sheet=${enc(sheet)}` : ""}`),
  email: (pid: string, rev: number, fileId: string) =>
    req<{ name: string; path: string; from: string; to: string; cc: string; date: string; subject: string; body: string; attachments: string[] }>(
      "GET", `${P(pid)}/source/email?file_id=${enc(fileId)}&rev=${rev}`),
  imageUrl: (pid: string, rev: number, fileId: string) => `${P(pid)}/source/image?file_id=${enc(fileId)}&rev=${rev}`,
  text: (pid: string, rev: number, fileId: string) =>
    req<{ name: string; path: string; text: string }>("GET", `${P(pid)}/source/text?file_id=${enc(fileId)}&rev=${rev}`),
  ifc: (pid: string, rev: number, fileId: string, guids: string[]) =>
    req<IfcView>("POST", `${P(pid)}/source/ifc?file_id=${enc(fileId)}&rev=${rev}`, { guids }),
  knowledgeRow: (kid: string) =>
    req<{ id: string; sheet: string; row: number; file: string; version: string; data: Record<string, unknown> }>(
      "GET", `/api/knowledge/rows/${enc(kid)}`),
  // technical details
  techStatus: () => req<TechStatus>("GET", "/api/tech/status"),
  techLogs: (projectId?: string) => req<LogEntry[]>("GET", `/api/tech/logs?limit=300${projectId ? `&project_id=${enc(projectId)}` : ""}`),
  logoUrl: "/api/branding/logo",
};

export interface IfcView {
  name: string; path: string; total_elements: number; selected: number;
  elements: Record<string, string | number | null>[];
  plan: { width: number; height: number; background: number[][]; highlight: number[][] };
  application?: string | null; schema?: string | null;
}

export interface TechStatus {
  ai: AiStatus;
  knowledge: { file?: string; version?: string; sheets?: Record<string, number>; status_counts?: Record<string, number>;
               price_lists?: [string, string][]; error?: string };
  dataset: { filemap_decisions: number; values: number; corrections: number; approved_cases: number; guidelines_version: number;
             guidelines: string; calibration_suggestions: Record<string, unknown>[] };
}

export interface LogEntry {
  ts: string; id: string; provider: string; model: string; call: string; prompt_version: string; project_id?: string;
  file?: string | null; input_summary?: { chars?: number; images?: number };
  attempts: { n: number; errors: string[]; raw?: string }[];
  status: string; duration_s: number; input_tokens: number; output_tokens: number; cost_eur: number; cache_hit?: boolean; error?: string;
}
