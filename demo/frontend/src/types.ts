// Mirrors backend/app/models.py (RunResult and friends).
export type ValueType = "extracted" | "calculated" | "predicted";
export type RefKind = "pdf_page" | "sheet_cell" | "ifc_elements" | "email" | "text" | "image" | "knowledge_row" | "user_edit";

export interface Ref {
  kind: RefKind;
  file_id?: string | null;
  path?: string | null;
  page?: number | null;
  sheet?: string | null;
  cell?: string | null;
  row?: number | null;
  guids: string[];
  bbox?: number[] | null;
  bboxes: number[][];
  snippet?: string | null;
  label?: string | null;
  kn_id?: string | null;
}

export interface ConflictOption {
  value: unknown;
  unit?: string | null;
  refs: Ref[];
  note?: string | null;
}

export interface Edit {
  before: unknown;
  after: unknown;
  reason?: string | null;
  source: string;
  at?: string | null;
}

export interface V {
  id: string;
  label: string;
  value: unknown;
  unit?: string | null;
  type: ValueType;
  confidence: number;
  refs: Ref[];
  formula?: string | null;
  inputs: string[];
  kn: string[];
  reasoning?: string | null;
  question?: string | null;
  conflict: ConflictOption[];
  edited?: Edit | null;
  editable: boolean;
  edit_key?: string | null;
  allowed?: unknown[] | null;
  group?: string | null;
}

export interface FileEntry {
  id: string;
  path: string;
  name: string;
  ext: string;
  kind: string;
  size: number;
  pages?: number | null;
  sheets?: number | null;
  elements?: number | null;
  date?: string | null;
  sha256: string;
  parent_id?: string | null;
  status: string;
  reason: string;
  decided_by: string;
  duplicate_of?: string | null;
  superseded_by?: string | null;
  used_for: string[];
  read_by?: string | null;
  error?: string | null;
  notes: string[];
}

export interface FileMap {
  root: string;
  entries: FileEntry[];
  level: "idea" | "draft" | "full";
  level_reason: string;
  counts: Record<string, number>;
  total_size: number;
  seconds: number;
}

export interface Fact { key: string; group: string; label: string; value_id: string }

export interface TakeoffLine {
  id: string; category: string; phase?: string | null; profile: string; family: string; grade?: string | null;
  is_plate: boolean; thickness_mm?: number | null; source: string; pieces_id: string; kg_id: string;
  length_id?: string | null; area_id?: string | null; longest_mm?: number | null; surface?: string | null; included: boolean;
}

export interface CategorySummary {
  name: string; phase?: string | null; kg_id: string; pieces_id: string; area_id: string; plate_share_id: string;
  surface_id: string; longest_mm?: number | null; included: boolean; assemblies: number;
}

export interface HoursRow {
  operation: string; category: string; quantity_id?: string | null; hours_id: string; norm: string; kn: string[]; costed_in: string;
}

export interface PaintRow {
  category: string; system: string; area_id: string; coats: number;
  litres: { product: string; value_id: string; eur_per_l?: number; coats?: number; dft?: number }[];
  hours_id: string; cost_id: string; kn: string[];
}

export interface Risk {
  id: string; rank: number; severity: "high" | "medium" | "low"; kind: string; title: string; detail: string;
  value_ids: string[]; refs: Ref[]; question?: string | null;
}

export interface Question { id: string; text: string; reason: string; value_ids: string[] }

export interface Override {
  id: string; target: string; key: string; field: string; value: unknown; reason?: string | null; source: string;
  text?: string | null; created_at?: string | null; label?: string | null; before?: unknown;
}

export interface Change {
  label: string; before: unknown; after: unknown; unit?: string | null; value_id?: string | null; kind: string;
  reason?: string | null; source?: string | null; text?: string | null;
}

export interface OfferLine {
  kind: string; category?: string; phase?: string | null; label: string; surface?: string | null; qty_id?: string | null;
  qty?: number | null; unit: string; price_id: string; unit_price?: number | null; kg?: number;
}

export interface RunResult {
  project_id: string; company: string; project_name: string; project_path: string; revision: number;
  quote_number: string; report_name: string; status: "draft" | "approved"; created_at: string;
  timings: Record<string, number>;
  ai: { calls?: number; cache_hits?: number; failures?: number; input_tokens?: number; output_tokens?: number; cost_eur?: number;
        seconds?: number; provider?: string; model?: string; sends_data_off_machine?: boolean };
  filemap: FileMap; facts: Fact[]; lines: TakeoffLine[]; categories: CategorySummary[];
  features: Record<string, string[]>; hours: HoursRow[];
  hours_totals: { total: string; metal: string; quick?: string; labour_cost?: string;
                  by_operation: Record<string, string>; by_category: Record<string, string> };
  paint: PaintRow[];
  paint_totals: { litres: string; by_product: Record<string, string>; cost: string; galv_cost?: string | null; area: string };
  material: Record<string, any>;
  cost: Record<string, any>;
  offer_lines: OfferLine[];
  carbon: Record<string, any>;
  risks: Risk[]; questions: Question[];
  assumptions: { kind: string; text: string; value_id?: string; refs?: Ref[]; question?: string | null }[];
  summary: Record<string, any>;
  values: Record<string, V>;
  overrides: Override[];
  changes: Change[];
  knowledge: { file?: string; version?: string };
  reports: Record<string, string>;
  warnings: string[];
}

export interface Revision {
  project_id: string; rev: number; quote_number: string; report_name: string; status: "draft" | "approved";
  created_at: string; duration_s?: number | null; ai_cost_eur?: number | null; provider?: string | null; price?: number | null;
  tonnes?: number | null; hours?: number | null; co2?: number | null; level?: string | null; changes?: number | null; kind?: string;
  approved_at?: string | null;
}

export interface StoredOverride {
  id: number; target: string; key: string; field: string; value: unknown; reason?: string | null; source: string;
  text?: string | null; label?: string | null; before?: unknown; created_at: string; applied_in?: number | null; active?: number;
}

export interface ProjectSummary {
  id: string; name: string; short: string; company: string; files: number; size: number; modified: string;
  latest?: Revision | null; running_job?: string | null;
}

export interface ProjectInfo {
  id: string; company: string; name: string; short: string; path: string; files: number; size: number;
  revisions: Revision[]; pending_overrides: StoredOverride[]; overrides: StoredOverride[]; corrections: unknown[];
  running_job?: string | null;
}

export interface Stage { id: string; phase: string; name: string; detail: string; state: string; message: string; seconds?: number | null }

export interface Job {
  job_id: string; project_id: string; kind: string; state: "queued" | "running" | "done" | "failed";
  started_at: number; elapsed: number; message: string; revision?: number | null; error?: string | null;
  stages: Stage[]; files: { path: string; state: string; method?: string | null; note?: string | null }[];
  report_ready_s?: number;
}

export interface AppConfig {
  company: {
    id: string; name: string; legal_name: string; app_title: string; language: string; languages: string[];
    currency: string; currency_symbol: string; number_format: { thousands: string; decimal: string; locale?: string };
    branding: { logo: string; tagline?: string; colors: Record<string, string> };
  };
  ai: AiStatus;
}

export interface AiStatus {
  provider: string; model: string; sends_data_off_machine: boolean; fallback_reason?: string | null;
  configured?: string; key_present?: boolean;
}

export interface ProposedChange { edit_key: string; label: string; before: unknown; after: unknown; explanation?: string }

export interface CorrectionProposal {
  correction_id?: number; changes: ProposedChange[]; not_applied: { text: string; reason: string }[]; provider?: string; error?: string;
}
