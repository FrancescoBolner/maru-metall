import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { ErrorBox, Loading, useAsync } from "../components/common";
import { date, num } from "../format";
import { t } from "../i18n";
import type { Route } from "../router";

export function TechPage({ setCrumbs }: { setCrumbs: (c: { label: string; to?: Route }[]) => void }) {
  const st = useAsync(() => api.techStatus(), []);
  const logs = useAsync(() => api.techLogs(), []);
  const [openLog, setOpenLog] = useState<string>();
  useEffect(() => setCrumbs([{ label: t("tech.title") }]), [setCrumbs]);
  if (st.loading) return <Loading />;
  if (st.error || !st.data) return <main className="page narrow"><ErrorBox message={st.error ?? ""} onRetry={st.reload} /></main>;
  const { ai, knowledge, dataset } = st.data;
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>{t("tech.title")}</h1>
          <p className="sub">{t("tech.subtitle")}</p>
        </div>
      </div>
      <div className="grid3">
        <section className="card">
          <div className="card-head"><h2>{t("tech.ai")}</h2></div>
          <div className="card-body kv">
            <span className="k">{t("tech.provider")}</span><span>{ai.provider}</span>
            <span className="k">{t("tech.model")}</span><span className="mono">{ai.model}</span>
            <span className="k">{t("tech.off_machine")}</span><span>{ai.sends_data_off_machine ? t("common.yes") : t("common.no")}</span>
            <span className="k">{t("tech.key")}</span><span>{ai.key_present ? t("common.yes") : t("common.no")}</span>
            <span className="k">config</span><span className="mono">{ai.configured}</span>
            {ai.fallback_reason && (<><span className="k">{t("tech.fallback")}</span><span className="small">{ai.fallback_reason}</span></>)}
          </div>
        </section>
        <section className="card">
          <div className="card-head"><h2>{t("tech.knowledge")}</h2></div>
          <div className="card-body">
            {knowledge.error ? <ErrorBox message={knowledge.error} /> : (
              <div className="kv">
                <span className="k">File</span><span className="mono">{knowledge.file}</span>
                <span className="k">{t("tech.kn_version")}</span><span className="mono">{knowledge.version}</span>
                <span className="k">{t("tech.kn_status")}</span>
                <span className="small">{Object.entries(knowledge.status_counts ?? {}).map(([k, n]) => `${k} ${n}`).join(" · ")}</span>
                <span className="k">{t("tech.price_lists")}</span>
                <span className="small">{(knowledge.price_lists ?? []).map(([id, d]) => `${id} (${d})`).join(", ")}</span>
                <span className="k">{t("tech.kn_sheets")}</span>
                <span className="small">{Object.entries(knowledge.sheets ?? {}).map(([k, n]) => `${k} ${n}`).join(" · ")}</span>
              </div>
            )}
          </div>
        </section>
        <section className="card">
          <div className="card-head"><h2>{t("tech.dataset")}</h2></div>
          <div className="card-body kv">
            <span className="k">filemap_decisions.jsonl</span><span className="num">{num(dataset.filemap_decisions)}</span>
            <span className="k">values.jsonl</span><span className="num">{num(dataset.values)}</span>
            <span className="k">corrections.jsonl</span><span className="num">{num(dataset.corrections)}</span>
            <span className="k">approved/ (test cases)</span><span className="num">{num(dataset.approved_cases)}</span>
          </div>
        </section>
      </div>
      <div className="grid2 mt">
        <section className="card">
          <div className="card-head"><h2>{t("tech.guidelines", { v: dataset.guidelines_version })}</h2></div>
          <div className="card-body">{dataset.guidelines ? <pre className="code">{dataset.guidelines}</pre> : <span className="muted">{t("tech.no_guidelines")}</span>}</div>
        </section>
        <section className="card">
          <div className="card-head"><h2>{t("tech.calibration")}</h2></div>
          {dataset.calibration_suggestions.length === 0 ? <div className="card-body muted">{t("tech.no_calibration")}</div> : (
            <table className="t compact">
              <tbody>
                {dataset.calibration_suggestions.map((c, i) => (
                  <tr key={i}>
                    <td className="small">{String(c.knowledge_row)}</td>
                    <td className="small nowrap">{String(c.current)} → <b>{String(c.suggested)}</b></td>
                    <td className="small muted">{String(c.evidence)}</td>
                    <td className="tiny">{String(c.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
      <section className="card mt">
        <div className="card-head"><h2>{t("tech.logs")}</h2><button className="btn small right" onClick={logs.reload}>{t("common.retry")}</button></div>
        {logs.loading ? <Loading /> : logs.error ? <div className="card-body"><ErrorBox message={logs.error} /></div> : !logs.data?.length ? (
          <div className="card-body muted">{t("tech.logs_empty")}</div>
        ) : (
          <div className="table-wrap tall">
            <table className="t compact">
              <thead>
                <tr>
                  <th>{t("tech.col.time")}</th><th>{t("tech.col.call")}</th><th>{t("tech.col.file")}</th><th>{t("tech.col.prompt")}</th>
                  <th>{t("tech.col.status")}</th><th className="n">{t("tech.col.attempts")}</th><th className="n">{t("tech.col.tokens")}</th>
                  <th className="n">{t("tech.col.cost")}</th><th className="n">{t("tech.col.duration")}</th>
                </tr>
              </thead>
              <tbody>
                {logs.data.map((l) => (
                  <Fragment key={l.id}>
                    <tr className="click" onClick={() => setOpenLog(openLog === l.id ? undefined : l.id)}>
                      <td className="small nowrap">{date(l.ts)}</td>
                      <td className="small">{l.call}</td>
                      <td className="small" style={{ wordBreak: "break-all" }}>{l.file ?? ""}</td>
                      <td className="small mono">{l.prompt_version}</td>
                      <td className="small" style={{ color: l.status === "ok" ? "var(--ok)" : "var(--bad)" }}>{l.status}{l.cache_hit ? " (cache)" : ""}</td>
                      <td className="n">{l.attempts?.length ?? 0}</td>
                      <td className="n small">{num(l.input_tokens)} / {num(l.output_tokens)}</td>
                      <td className="n small">{num(l.cost_eur, 4)}</td>
                      <td className="n small">{num(l.duration_s, 2)} s</td>
                    </tr>
                    {openLog === l.id && (
                      <tr>
                        <td colSpan={9}>
                          {l.error && <div className="errorbox small mb">{l.error}</div>}
                          {(l.attempts ?? []).map((a) => (
                            <div key={a.n} className="mb">
                              <div className="small"><b>Attempt {a.n}</b>{a.errors.length ? <span style={{ color: "var(--bad)" }}> — {t("tech.attempt_errors")}: {a.errors.join("; ")}</span> : null}</div>
                              {a.raw && <pre className="code">{a.raw}</pre>}
                            </div>
                          ))}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
