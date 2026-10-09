import { Component, useEffect, useState, type ErrorInfo, type ReactNode } from "react";
import { api } from "./api";
import { ErrorBox, Loading } from "./components/common";
import { setNumberFormat } from "./format";
import { setLanguage, t } from "./i18n";
import { href, useRoute, type Route } from "./router";
import type { AppConfig } from "./types";
import { CompaniesPage } from "./pages/Companies";
import { ProjectsPage } from "./pages/Projects";
import { ProjectPage } from "./pages/Project";
import { RunPage } from "./pages/Run";
import { ReportPage } from "./pages/Report";
import { TechPage } from "./pages/Tech";

/** A crash in one page must never leave a blank screen: show what happened and how to continue. */
class PageBoundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page error", error, info.componentStack);
  }
  render() {
    if (this.state.error)
      return (
        <div className="page narrow">
          <ErrorBox message={`${this.state.error.message}. ${t("error.reload_hint")}`} onRetry={() => window.location.reload()} />
        </div>
      );
    return this.props.children;
  }
}

function pageKey(r: Route): string {
  switch (r.page) {
    case "projects":
      return `projects:${r.company}`;
    case "project":
      return `project:${r.pid}`;
    case "run":
      return `run:${r.pid}:${r.job}`;
    case "report":
      return `report:${r.pid}:${r.rev}`;
    default:
      return r.page;
  }
}

export function App() {
  const route = useRoute();
  const [cfg, setCfg] = useState<AppConfig>();
  const [err, setErr] = useState<string>();
  const [crumbs, setCrumbs] = useState<{ label: string; to?: Route }[]>([]);

  const load = () => {
    setErr(undefined);
    api.config()
      .then((c) => {
        setLanguage(c.company.language);
        setNumberFormat(c.company.number_format);
        document.title = `${c.company.name} — ${c.company.app_title}`;
        setCfg(c);
      })
      .catch((e: Error) => setErr(e.message));
  };
  useEffect(load, []);
  useEffect(() => window.scrollTo(0, 0), [route.page]);

  if (err) return <div className="page narrow"><ErrorBox message={err} onRetry={load} /></div>;
  if (!cfg) return <Loading />;

  let page: ReactNode;
  switch (route.page) {
    case "companies":
      page = <CompaniesPage setCrumbs={setCrumbs} />;
      break;
    case "projects":
      page = <ProjectsPage company={route.company} setCrumbs={setCrumbs} />;
      break;
    case "project":
      page = <ProjectPage pid={route.pid} setCrumbs={setCrumbs} />;
      break;
    case "run":
      page = <RunPage pid={route.pid} job={route.job} setCrumbs={setCrumbs} />;
      break;
    case "report":
      page = <ReportPage pid={route.pid} rev={route.rev} tab={route.tab} setCrumbs={setCrumbs} />;
      break;
    case "tech":
      page = <TechPage setCrumbs={setCrumbs} />;
      break;
  }
  const ai = cfg.ai;
  const aiLabel = ai.provider === "offline" ? t("nav.offline_ai") : ai.provider === "local" ? t("nav.local_ai", { model: ai.model }) : t("nav.claude_ai", { model: ai.model });
  return (
    <>
      <header className="topbar">
        <a href="#/" aria-label={cfg.company.name}><img className="logo" src={api.logoUrl} alt={cfg.company.name} /></a>
        <span className="apptitle">{cfg.company.app_title}</span>
        <nav className="crumbs" aria-label="breadcrumb">
          <a href="#/">{t("nav.clients")}</a>
          {crumbs.map((c, i) => (
            <span key={i} className="row" style={{ gap: 6 }}>
              <span className="sep">/</span>
              {c.to && i < crumbs.length - 1 ? <a href={href(c.to)}>{c.label}</a> : <span className="cur" title={c.label}>{c.label}</span>}
            </span>
          ))}
        </nav>
        <span className="ai-badge" title={ai.fallback_reason ?? ""}>{aiLabel}</span>
      </header>
      <PageBoundary key={pageKey(route)}>
        <div key={pageKey(route)}>{page}</div>
      </PageBoundary>
      <footer className="footer">
        {cfg.company.legal_name} · {cfg.company.app_title} · <a href="#/tech">{t("nav.tech")}</a>
      </footer>
    </>
  );
}
