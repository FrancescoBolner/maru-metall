import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading, StatusBadge, useAsync } from "../components/common";
import { bytes, date, eur, num } from "../format";
import { t, tn } from "../i18n";
import { go, href, type Route } from "../router";

export function ProjectPage({ pid, setCrumbs }: { pid: string; setCrumbs: (c: { label: string; to?: Route }[]) => void }) {
  const { data, error, loading, reload } = useAsync(() => api.project(pid), [pid]);
  const [busy, setBusy] = useState(false);
  const [runErr, setRunErr] = useState<string>();
  useEffect(() => {
    if (data) setCrumbs([{ label: data.company, to: { page: "projects", company: data.company } }, { label: data.name }]);
  }, [data, setCrumbs]);

  const run = async () => {
    setBusy(true);
    setRunErr(undefined);
    try {
      const j = await api.run(pid, "run");
      go({ page: "run", pid, job: j.job_id });
    } catch (e) {
      setRunErr((e as Error).message);
      setBusy(false);
    }
  };

  if (loading) return <Loading />;
  if (error || !data) return <main className="page narrow"><ErrorBox message={error ?? ""} onRetry={reload} /></main>;
  const revs = [...data.revisions].sort((a, b) => b.rev - a.rev);
  return (
    <main className="page">
      <div className="page-head">
        <div className="grow">
          <div className="muted small">{data.company}</div>
          <h1>{data.name}</h1>
          <p className="sub small">
            {t("project.folder")}: <span className="mono">{data.path}</span> · {tn("common.files", data.files)} · {bytes(data.size)}
          </p>
        </div>
        {data.running_job ? (
          <a className="btn primary" href={href({ page: "run", pid, job: data.running_job })}>{t("project.watch")}</a>
        ) : revs.length > 0 ? (
          <>
            <a className="btn primary" href={href({ page: "report", pid, rev: revs[0].rev, tab: "summary" })}>{t("common.open")} {revs[0].report_name}</a>
            <button className="btn" onClick={run} disabled={busy} title={t("project.run_again_hint")}>{t("project.run_again")}</button>
          </>
        ) : null}
      </div>
      {runErr && <div className="mb"><ErrorBox message={runErr} /></div>}
      {data.running_job && <div className="notice mb">{t("project.running")}</div>}
      {revs.length === 0 && !data.running_job && (
        <div className="card">
          <Empty
            title={t("project.no_quote")}
            actions={<button className="btn primary" onClick={run} disabled={busy}>{busy ? <span className="spinner" /> : null}{t("project.prepare")}</button>}
          >
            <p style={{ maxWidth: 560, margin: "0 auto" }}>{t("project.prepare_hint")}</p>
          </Empty>
        </div>
      )}
      {revs.length > 0 && (
        <div className="card">
          <div className="card-head"><h2>{t("project.revisions")}</h2></div>
          <table className="t">
            <thead>
              <tr>
                <th>{t("project.col.report")}</th>
                <th>{t("project.col.created")}</th>
                <th className="n">{t("project.col.price")}</th>
                <th className="n">{t("project.col.tonnes")}</th>
                <th className="n">{t("project.col.hours")}</th>
                <th className="n">{t("project.col.changes")}</th>
                <th className="n">{t("project.col.time")}</th>
                <th>{t("project.col.status")}</th>
              </tr>
            </thead>
            <tbody>
              {revs.map((r) => (
                <tr key={r.rev} className="click" onClick={() => go({ page: "report", pid, rev: r.rev, tab: "summary" })}>
                  <td><a href={href({ page: "report", pid, rev: r.rev, tab: "summary" })} onClick={(e) => e.stopPropagation()}><b>{r.report_name}</b></a></td>
                  <td>{date(r.created_at)}</td>
                  <td className="n">{eur(r.price)}</td>
                  <td className="n">{num(r.tonnes, 1)} t</td>
                  <td className="n">{num(r.hours, 0)} h</td>
                  <td className="n">{r.changes || ""}</td>
                  <td className="n">{r.duration_s != null ? t("common.seconds", { s: num(r.duration_s, 1) }) : ""}</td>
                  <td><StatusBadge status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.pending_overrides.length > 0 && (
        <div className="notice warn mt">
          {tn("review.pending", data.pending_overrides.length)} — {t("project.run_again_hint")}
        </div>
      )}
    </main>
  );
}
