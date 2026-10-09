import { useEffect, useState } from "react";

// Tiny hash router: #/  #/c/<company>  #/p/<pid>  #/p/<pid>/run/<job>  #/p/<pid>/r/<rev>/<tab>  #/tech
export type Route =
  | { page: "companies" }
  | { page: "projects"; company: string }
  | { page: "project"; pid: string }
  | { page: "run"; pid: string; job: string }
  | { page: "report"; pid: string; rev: number; tab: string }
  | { page: "tech" };

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "c" && parts[1]) return { page: "projects", company: parts[1] };
  if (parts[0] === "p" && parts[1]) {
    if (parts[2] === "run" && parts[3]) return { page: "run", pid: parts[1], job: parts[3] };
    if (parts[2] === "r" && parts[3]) return { page: "report", pid: parts[1], rev: Number(parts[3]), tab: parts[4] || "summary" };
    return { page: "project", pid: parts[1] };
  }
  if (parts[0] === "tech") return { page: "tech" };
  return { page: "companies" };
}

export function href(r: Route): string {
  const e = encodeURIComponent;
  switch (r.page) {
    case "companies":
      return "#/";
    case "projects":
      return `#/c/${e(r.company)}`;
    case "project":
      return `#/p/${e(r.pid)}`;
    case "run":
      return `#/p/${e(r.pid)}/run/${e(r.job)}`;
    case "report":
      return `#/p/${e(r.pid)}/r/${r.rev}/${e(r.tab)}`;
    case "tech":
      return "#/tech";
  }
}

export function go(r: Route, replace = false): void {
  const h = href(r);
  if (replace) window.location.replace(h);
  else window.location.hash = h;
  window.location.reload();
}

/** Every page change is a full page load: the same path as a manual reload, which works in every browser. */
export function useRoute(): Route {
  const [initial] = useState<string>(() => window.location.hash);
  useEffect(() => {
    const check = () => {
      if (window.location.hash !== initial) window.location.reload();
    };
    window.addEventListener("hashchange", check);
    window.addEventListener("popstate", check);
    const timer = window.setInterval(check, 200);
    return () => {
      window.removeEventListener("hashchange", check);
      window.removeEventListener("popstate", check);
      window.clearInterval(timer);
    };
  }, [initial]);
  return parse(initial);
}
