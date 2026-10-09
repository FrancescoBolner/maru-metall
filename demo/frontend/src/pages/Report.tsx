import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ErrorBox, Loading, Modal, StatusBadge, useAsync } from "../components/common";
import { overrideKey, ReportContext, type PanelTarget, type ReportCtx } from "../components/ReportContext";
import { ReviewBar } from "../components/ReviewBar";
import { SourcePanel } from "../components/SourcePanel";
import { Val } from "../components/Val";
import { date, eur, num } from "../format";
import { t } from "../i18n";
import { href, type Route } from "../router";
import type { Job, Ref, StoredOverride } from "../types";
import { CarbonTab, CostTab, FilesTab, HoursTab, PaintTab, RevisionsTab, RisksTab, SummaryTab, TakeoffTab } from "./ReportTabs";

const TABS = ["summary", "takeoff", "hours", "painting", "cost", "carbon", "risks", "files", "revisions"] as const;

export function ReportPage({ pid, rev, tab, setCrumbs }: { pid: string; rev: number; tab: string; setCrumbs: (c: { label: string; to?: Route }[]) => void }) {
  const resQ = useAsync(() => api.revision(pid, rev), [pid, rev]);
  const projQ = useAsync(() => api.project(pid), [pid]);
  const [panel, setPanel] = useState<PanelTarget[]>([]);
  const [job, setJob] = useState<Job>();
  const [approveOpen, setApproveOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  const [actionErr, setActionErr] = useState<string>();

  const res = resQ.data;
  const project = projQ.data;
  useEffect(() => {
    if (res) {
      setCrumbs([
        { label: res.company, to: { page: "projects", company: res.company } },
        { label: res.project_name, to: { page: "project", pid } },
        { label: res.report_name },
      ]);
    }
  }, [res, pid, setCrumbs]);

  // PDF/Excel are written after the report is shown: follow the job, then reload
  useEffect(() => {
    const jid = project?.running_job;
    if (!jid) return;
    let alive = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const x = await api.job(jid);
        if (!alive) return;
        setJob(x);
        if (x.state === "queued" || x.state === "running") timer = window.setTimeout(poll, 800);
        else {
          resQ.reload();
          projQ.reload();
        }
      } catch {
        /* job gone: nothing to follow */
      }
    };
    poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.running_job]);

  const pending = useMemo<StoredOverride[]>(() => project?.pending_overrides ?? [], [project]);
  const pendingByKey = useMemo(() => {
    const m: Record<string, StoredOverride> = {};
    for (const o of pending) m[overrideKey(o)] = o;
    return m;
  }, [pending]);

  const latestRev = project?.revisions?.length ? Math.max(...project.revisions.map((r) => r.rev)) : rev;
  const isLatest = rev >= latestRev;

  const open = useCallback((id: string, push = false) => setPanel((p) => (push ? [...p, { kind: "value", id }] : [{ kind: "value", id }])), []);
  const openRefs = useCallback((title: string, refs: Ref[], text?: string) => setPanel([{ kind: "refs", title, refs, text }]), []);
  const addEdit = useCallback(async (editKey: string, value: unknown, label: string, before: unknown, reason?: string) => {
    await api.edit(pid, { edit_key: editKey, value, label, before, reason });
    projQ.reload();
  }, [pid, projQ]);
  const removeEdit = useCallback(async (id: number) => {
    await api.deleteEdit(pid, id);
    projQ.reload();
  }, [pid, projQ]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !approveOpen) setPanel([]);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [approveOpen]);

  if (resQ.loading && !res) return <Loading />;
  if (resQ.error || !res) return <main className="page narrow"><ErrorBox message={resQ.error ?? ""} onRetry={resQ.reload} /></main>;

  const ctx: ReportCtx = {
    pid, rev, res, project, panel, open, openRefs,
    back: () => setPanel((p) => p.slice(0, -1)),
    close: () => setPanel([]),
    pending, pendingByKey, addEdit, removeEdit, reloadProject: projQ.reload, isLatest,
  };
  const s = res.summary;
  const v = res.values;
  const filesBusy = job && (job.state === "running" || job.state === "queued") && job.revision === rev;
  const approve = async () => {
    setApproving(true);
    setActionErr(undefined);
    try {
      await api.approve(pid, rev);
      setApproveOpen(false);
      resQ.reload();
      projQ.reload();
    } catch (e) {
      setActionErr((e as Error).message);
    } finally {
      setApproving(false);
    }
  };
  const latestName = project?.revisions?.find((r) => r.rev === latestRev)?.report_name;
  const activeTab = (TABS as readonly string[]).includes(tab) ? tab : "summary";
  const tabCount: Record<string, number | undefined> = {
    risks: res.risks.length, files: res.filemap.entries.length, revisions: project?.revisions.length, takeoff: res.lines.length,
  };

  return (
    <ReportContext.Provider value={ctx}>
      <main className="page" style={{ maxWidth: panel.length ? "none" : undefined }}>
        <div className={`report-layout${panel.length ? " with-panel" : ""}`}>
          <div className="report-main">
            {!isLatest && latestName && (
              <div className="notice warn mb row">
                {t("report.not_latest", { name: latestName })}
                <a className="btn small right" href={href({ page: "report", pid, rev: latestRev, tab: activeTab })}>{t("report.open_latest")}</a>
              </div>
            )}
            <div className="headline">
              <div>
                <div className="small muted">{t("report.price")}</div>
                <div className="price"><Val id={s.price_id} /></div>
                <div className="range">
                  {t("report.range", { low: eur(v[s.low_id]?.value), high: eur(v[s.high_id]?.value) })} · {t(`report.method.${s.method}`)}
                </div>
              </div>
              <div className="kpis">
                <Kpi k={t("summary.steel")}><Val id="total.kg" dec={0} /></Kpi>
                <Kpi k={t("summary.hours")}><Val id={s.hours_id} dec={0} /></Kpi>
                <Kpi k={t("summary.labour")}><Val id={s.labour_cost_id} /></Kpi>
                <Kpi k={t("summary.paint")}><Val id={s.paint_litres_id} /></Kpi>
                <Kpi k={t("summary.co2")}><Val id={s.co2_id} /></Kpi>
                <Kpi k={t("summary.eur_per_kg")}><span className="num">{num(s.eur_per_kg, 2)} €/kg</span></Kpi>
              </div>
              <div className="actions">
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <StatusBadge status={res.status} />
                  {res.status === "draft" && isLatest && (
                    <button className="btn primary small" onClick={() => setApproveOpen(true)}>{t("report.approve")}</button>
                  )}
                </div>
                <div className="downloads">
                  {filesBusy ? (
                    <span className="small muted row"><span className="spinner" /> {t("report.download.preparing")}</span>
                  ) : res.reports.client_pdf ? (
                    <>
                      <a className="btn small" href={api.download(pid, rev, "client_pdf")}>{t("report.download.client")}</a>
                      <a className="btn small" href={api.download(pid, rev, "internal_pdf")}>{t("report.download.internal")}</a>
                      <a className="btn small" href={api.download(pid, rev, "xlsx")}>{t("report.download.excel")}</a>
                    </>
                  ) : (
                    <span className="small muted">{t("report.download.failed")}</span>
                  )}
                </div>
              </div>
            </div>
            <div className="metaline">
              <span>{res.filemap.level_reason}</span>
              <span>{t("summary.quantity_source")}: {s.quantity_source}</span>
              <span>{t("report.time_to_report", { s: num(res.timings.total, 1) })}</span>
              <span>{t("report.ai_cost", { c: num(res.ai.cost_eur ?? 0, 2) })} · {res.ai.provider}{res.ai.calls ? ` · ${res.ai.calls} calls` : ""}</span>
              <span>{res.knowledge.file} ({res.knowledge.version})</span>
              <span>{date(res.created_at)}</span>
            </div>
            {res.warnings.length > 0 && (
              <div className="notice warn mt-s small"><b>{t("report.warnings")}:</b> {res.warnings.join(" · ")}</div>
            )}
            {actionErr && <div className="mt-s"><ErrorBox message={actionErr} /></div>}

            <nav className="tabs" role="tablist">
              {TABS.map((x) => (
                <a key={x} role="tab" aria-selected={activeTab === x} className={`tab${activeTab === x ? " active" : ""}`}
                  href={href({ page: "report", pid, rev, tab: x })}>
                  {t(`report.tabs.${x}`)}{tabCount[x] ? <span className="count">{tabCount[x]}</span> : null}
                </a>
              ))}
            </nav>

            {activeTab === "summary" && <SummaryTab />}
            {activeTab === "takeoff" && <TakeoffTab />}
            {activeTab === "hours" && <HoursTab />}
            {activeTab === "painting" && <PaintTab />}
            {activeTab === "cost" && <CostTab />}
            {activeTab === "carbon" && <CarbonTab />}
            {activeTab === "risks" && <RisksTab />}
            {activeTab === "files" && <FilesTab />}
            {activeTab === "revisions" && <RevisionsTab />}

            <ReviewBar />
          </div>
          {panel.length > 0 && <SourcePanel />}
        </div>
      </main>
      {approveOpen && (
        <Modal title={t("report.approve_title")} onClose={() => setApproveOpen(false)}
          actions={
            <>
              <button className="btn" onClick={() => setApproveOpen(false)}>{t("common.cancel")}</button>
              <button className="btn primary" disabled={approving || pending.length > 0} onClick={approve}>
                {approving ? <span className="spinner" /> : null}{t("report.approve")}
              </button>
            </>
          }>
          <p>{t("report.approve_text")}</p>
          {pending.length > 0 && <p className="mt-s" style={{ color: "var(--bad)" }}>{t("report.approve_pending")}</p>}
        </Modal>
      )}
    </ReportContext.Provider>
  );
}

function Kpi({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="kpi">
      <div className="k">{k}</div>
      <div className="v">{children}</div>
    </div>
  );
}

