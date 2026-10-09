import { useEffect } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading, useAsync } from "../components/common";
import { t, tn } from "../i18n";
import { href, type Route } from "../router";

export function CompaniesPage({ setCrumbs }: { setCrumbs: (c: { label: string; to?: Route }[]) => void }) {
  const { data, error, loading, reload } = useAsync(() => api.companies(), []);
  useEffect(() => setCrumbs([]), [setCrumbs]);
  return (
    <main className="page narrow">
      <div className="page-head">
        <div>
          <h1>{t("companies.title")}</h1>
          <p className="sub">{t("companies.subtitle")}</p>
        </div>
      </div>
      {loading && <Loading />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.length === 0 && <div className="card"><Empty title={t("companies.title")}>{t("companies.empty")}</Empty></div>}
      {data && data.length > 0 && (
        <div className="tiles">
          {data.map((c) => (
            <a key={c.name} className="tile" href={href({ page: "projects", company: c.name })}>
              <h2>{c.name}</h2>
              <div className="meta">{tn("common.projects", c.projects)}</div>
            </a>
          ))}
        </div>
      )}
    </main>
  );
}
