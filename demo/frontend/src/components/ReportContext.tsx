import { createContext, useContext } from "react";
import type { ProjectInfo, Ref, RunResult, StoredOverride } from "../types";

export type PanelTarget =
  | { kind: "value"; id: string }
  | { kind: "refs"; title: string; refs: Ref[]; text?: string };

export interface ReportCtx {
  pid: string;
  rev: number;
  res: RunResult;
  project: ProjectInfo | undefined;
  panel: PanelTarget[];            // drill-down stack; last = shown
  open: (id: string, push?: boolean) => void;
  openRefs: (title: string, refs: Ref[], text?: string) => void;
  back: () => void;
  close: () => void;
  pending: StoredOverride[];
  pendingByKey: Record<string, StoredOverride>;
  addEdit: (editKey: string, value: unknown, label: string, before: unknown, reason?: string) => Promise<void>;
  removeEdit: (id: number) => Promise<void>;
  reloadProject: () => void;
  isLatest: boolean;
}

export const ReportContext = createContext<ReportCtx | null>(null);

export function useReport(): ReportCtx {
  const c = useContext(ReportContext);
  if (!c) throw new Error("useReport outside report");
  return c;
}

/** "line:<id>:pieces", "category:<cat>|<phase>:surface", "fact:<key>", "param:<key>", "file:<id>:status" */
export function overrideKey(o: { target: string; key: string; field: string }): string {
  if (o.target === "fact" || o.target === "param") return `${o.target}:${o.key}`;
  return `${o.target}:${o.key}:${o.field}`;
}
