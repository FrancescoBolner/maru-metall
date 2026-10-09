import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ErrorBox, Loading } from "../components/common";
import { num } from "../format";
import { t } from "../i18n";
import { go, href, type Route } from "../router";
import type { Job, ProjectInfo } from "../types";

const PHASES = ["Extract", "Predict", "Present"];

export function RunPage({ pid, job, setCrumbs }: { pid: string; job: string; setCrumbs: (c: { label: string; to?: Route }[]) => void }) {
  const [j, setJ] = useState<Job>();
  const [err, setErr] = useState<string>();
  const [proj, setProj] = useState<ProjectInfo>();
  const navigated = useRef(false);

  useEffect(() => {
    api.project(pid).then((p) => {
      setProj(p);
      setCrumbs([{ label: p.company, to: { page: "projects", company: p.company } }, { label: p.name, to: { page: "project", pid } }, { label: t("run.title") }]);
    }).catch(() => undefined);
  }, [pid, setCrumbs]);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const x = await api.job(job);
        if (!alive) return;
        setJ(x);
        if (x.state === "queued" || x.state === "running") timer = window.setTimeout(poll, 450);
      } catch (e) {
        if (alive) setErr((e as Error).message);
      }
    };
    poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [job]);

  // open the report as soon as it exists (PDF and Excel follow in the background)
  useEffect(() => {
    if (j?.revision && !navigated.current) {
      navigated.current = true;
      const rev = j.revision;
      window.setTimeout(() => go({ page: "report", pid, rev, tab: "summary" }, true), 900);
    }
  }, [j?.revision, pid]);

  if (err) return <main className="page narrow"><ErrorBox message={err} /></main>;
  if (!j) return <Loading />;
  const files = j.files;
  const doneFiles = files.filter((f) => f.state === "done" || f.state === "skipped" || f.state === "failed").length;
  const stagesDone = j.stages.filter((s) => s.state === "done").length;
  return (
    <main className="page">
      <div className="page-head">
        <div className="grow">
          <div className="muted small">{proj?.name}</div>
          <h1>{t("run.title")}</h1>
          <p className="sub">{t("run.subtitle")}</p>
        </div>
        <div className="kpi" style={{ textAlign: "right" }}>
          <div className="k">{t("run.elapsed")}</div>
          <div className="v">{t("common.seconds", { s: num(j.elapsed, 1) })}</div>
        </div>
      </div>
      <div className="bar mb"><div style={{ width: `${(stagesDone / j.stages.length) * 100}%` }} /></div>

      {j.state === "failed" && (
        <div className="mb">
          <ErrorBox message={j.error ?? t("run.failed")} />
          <div className="row mt-s">
            <a className="btn" href={href({ page: "project", pid })}>{t("common.back")}</a>
            <a className="linkbtn small" href="#/tech">{t("nav.tech")}</a>
          </div>
        </div>
      )}
      {j.revision && (
        <div className="notice ok mb row">
          <b>{t("run.ready")}</b>
          {j.state !== "done" && <span className="small muted">{t("run.ready_files")}</span>}
          <a className="btn primary small right" href={href({ page: "report", pid, rev: j.revision, tab: "summary" })}>{t("run.open_report")}</a>
        </div>
      )}

      <div className="phases">
        {PHASES.map((ph) => (
          <section key={ph} className="phase">
            <h3>{t(`run.phase.${ph}`)}</h3>
            {j.stages.filter((s) => s.phase === ph).map((s) => (
              <div key={s.id} className={`stage ${s.state}`}>
                <span className="dot" aria-hidden />
                <div>
                  <div className="name">{s.id}. {s.name}</div>
                  <div className="msg">{s.message || s.detail}</div>
                </div>
                <span className="tiny muted">{s.seconds != null ? t("common.seconds", { s: num(s.seconds, 1) }) : t(`run.${s.state === "running" ? "running" : s.state === "done" ? "done" : "waiting"}`)}</span>
              </div>
            ))}
          </section>
        ))}
      </div>

      <div className="card mt">
        <div className="card-head">
          <h2>{t("run.files")}</h2>
          <span className="muted small">{doneFiles} / {files.length}</span>
        </div>
        <div className="table-wrap tall">
          <table className="t compact">
            <tbody>
              {files.length === 0 && (
                <tr><td className="muted">{t("common.loading")}</td></tr>
              )}
              {files.map((f) => (
                <tr key={f.path}>
                  <td className="small" style={{ wordBreak: "break-all" }}>
                    {f.path.includes("::") ? <span className="muted">↳ {f.path.split("::")[1]}</span> : f.path}
                  </td>
                  <td className="nowrap"><span className={`filestate ${f.state || "queued"}`}>{t(`run.file.${f.state || "queued"}`)}</span></td>
                  <td className="small muted nowrap">{f.method ? t(`run.by.${f.method === "code" ? "code" : f.method === "none" ? "none" : "ai"}`) : ""}</td>
                  <td className="small muted">{f.note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
