import { useEffect } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading, StatusBadge, useAsync } from "../components/common";
import { bytes, date, eur, num } from "../format";
import { t, tn } from "../i18n";
import { go, type Route } from "../router";

export function ProjectsPage({ company, setCrumbs }: { company: string; setCrumbs: (c: { label: string; to?: Route }[]) => void }) {
  const { data, error, loading, reload } = useAsync(() => api.projects(company), [company]);
  useEffect(() => setCrumbs([{ label: company }]), [company, setCrumbs]);
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>{company}</h1>
          <p className="sub">{t("projects.subtitle")}</p>
        </div>
      </div>
      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.length === 0 && <div className="card"><Empty title={t("projects.title")}>{t("projects.empty")}</Empty></div>}
      {data && data.length > 0 && (
        <div className="card">
          <table className="t">
            <thead>
              <tr>
                <th>{t("projects.col.project")}</th>
                <th className="n">{t("projects.col.files")}</th>
                <th>{t("projects.col.updated")}</th>
                <th>{t("projects.col.quote")}</th>
                <th className="n">{t("projects.col.price")}</th>
                <th>{t("projects.col.status")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id} className="click" onClick={() => go({ page: "project", pid: p.id })}>
                  <td>
                    <a href={`#/p/${encodeURIComponent(p.id)}`} onClick={(e) => e.stopPropagation()}><b>{p.name}</b></a>
                  </td>
                  <td className="n">{tn("common.files", p.files)} · {bytes(p.size)}</td>
                  <td>{date(p.modified)}</td>
                  <td>{p.latest ? p.latest.report_name : <span className="faint">{t("common.none")}</span>}</td>
                  <td className="n">{p.latest?.price ? eur(p.latest.price) : ""}{p.latest?.tonnes ? <span className="muted small"> · {num(p.latest.tonnes, 1)} t</span> : ""}</td>
                  <td><StatusBadge status={p.running_job ? "running" : p.latest ? p.latest.status : "none"} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
