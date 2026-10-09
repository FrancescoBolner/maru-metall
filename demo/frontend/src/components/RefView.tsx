import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type IfcView } from "../api";
import { num } from "../format";
import { t } from "../i18n";
import type { Ref } from "../types";
import { ErrorBox, SkeletonRows, useAsync } from "./common";

/** Renders the exact place a value comes from. */
export function RefView({ pid, rev, r }: { pid: string; rev: number; r: Ref }) {
  return (
    <div className="col">
      <div className="small muted">
        {r.path && <span className="mono">{r.path}</span>}
      </div>
      {r.snippet && r.kind !== "ifc_elements" && r.kind !== "image" && <div className="snippet">{r.snippet}</div>}
      {r.kind === "pdf_page" && r.file_id && <PdfRef pid={pid} rev={rev} r={r} />}
      {r.kind === "sheet_cell" && r.file_id && <SheetRef pid={pid} rev={rev} r={r} />}
      {r.kind === "email" && r.file_id && <EmailRef pid={pid} rev={rev} r={r} />}
      {r.kind === "ifc_elements" && r.file_id && <IfcRef pid={pid} rev={rev} r={r} />}
      {r.kind === "image" && r.file_id && <ImageRef pid={pid} rev={rev} r={r} />}
      {r.kind === "text" && r.file_id && <TextRef pid={pid} rev={rev} r={r} />}
      {r.kind === "knowledge_row" && r.kn_id && <KnowledgeRow kid={r.kn_id} />}
      {r.kind === "user_edit" && <div className="notice">{r.snippet || r.label}</div>}
    </div>
  );
}

function PdfRef({ pid, rev, r }: { pid: string; rev: number; r: Ref }) {
  const page = r.page || 1;
  const boxes = useMemo(() => (r.bboxes?.length ? r.bboxes : r.bbox ? [r.bbox] : []), [r]);
  const info = useAsync(() => api.pdfInfo(pid, rev, r.file_id!, page), [pid, rev, r.file_id, page]);
  const [zoom, setZoom] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const maxPx = zoom ? 4200 : 1700;
  const src = api.pdfUrl(pid, rev, r.file_id!, page, boxes, maxPx);
  // large drawings: show the highlighted region
  const big = info.data ? Math.max(info.data.width, info.data.height) > 1300 : false;
  useEffect(() => {
    setLoaded(false);
  }, [src]);
  useEffect(() => {
    if (!zoom || !loaded || !info.data || !boxes.length || !box.current) return;
    const b = boxes[0];
    const el = box.current;
    const img = el.querySelector("img");
    if (!img) return;
    const sx = img.naturalWidth / info.data.width;
    const cx = ((b[0] + b[2]) / 2) * sx;
    const cy = ((b[1] + b[3]) / 2) * sx;
    el.scrollTo({ left: Math.max(0, cx - el.clientWidth / 2), top: Math.max(0, cy - el.clientHeight / 2) });
  }, [zoom, loaded, info.data, boxes]);
  useEffect(() => {
    if (big && boxes.length) setZoom(true);
  }, [big, boxes.length]);
  return (
    <div className="col">
      <div className="row small">
        <span className="muted">{t("src.page", { p: page })}{info.data ? ` / ${info.data.pages ?? "?"}` : ""}</span>
        {boxes.length > 0 && (
          <button className="btn small ghost right" onClick={() => setZoom(!zoom)}>
            {zoom ? t("src.fit") : t("src.zoom")}
          </button>
        )}
      </div>
      <div ref={box} className={`pdfview${zoom ? " zoomed" : ""}`} style={{ minHeight: 200 }}>
        {!loaded && <SkeletonRows n={3} />}
        <img src={src} alt={`${r.path} page ${page}`} onLoad={() => setLoaded(true)} style={{ display: loaded ? "block" : "none" }} />
      </div>
    </div>
  );
}

function colIndex(cell?: string | null): number[] {
  if (!cell) return [];
  const toIdx = (s: string) => s.replace(/\d/g, "").split("").reduce((a, ch) => a * 26 + (ch.charCodeAt(0) - 64), 0) - 1;
  const [a, b] = cell.split(":");
  const i = toIdx(a);
  const j = b ? toIdx(b) : i;
  const out: number[] = [];
  for (let k = i; k <= j; k++) out.push(k);
  return out;
}

function SheetRef({ pid, rev, r }: { pid: string; rev: number; r: Ref }) {
  const row = r.row || Number((r.cell || "").replace(/\D/g, "")) || 1;
  const { data, error, loading } = useAsync(() => api.sheet(pid, rev, r.file_id!, row, r.sheet), [pid, rev, r.file_id, row, r.sheet]);
  const cols = colIndex(r.cell);
  const hl = useRef<HTMLTableRowElement>(null);
  useEffect(() => {
    hl.current?.scrollIntoView({ block: "nearest" });
  }, [data]);
  if (loading) return <SkeletonRows />;
  if (error || !data) return <ErrorBox message={error ?? ""} />;
  return (
    <div className="col">
      <div className="small muted">{t("src.sheet", { s: data.sheet, r: row })}{r.cell ? ` · ${r.cell}` : ""}</div>
      <div className="sheetwin">
        <table>
          <thead>
            <tr>
              <th />
              {data.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((x) => (
              <tr key={x.row} ref={x.row === data.highlight_row ? hl : undefined} className={x.row === data.highlight_row ? "hl" : ""}>
                <td className="rn">{x.row}</td>
                {data.columns.map((_, i) => (
                  <td key={i} className={x.row === data.highlight_row && cols.includes(i) ? "hlc" : ""} title={String(x.cells[i] ?? "")}>
                    {typeof x.cells[i] === "number" ? num(x.cells[i], Number.isInteger(x.cells[i]) ? 0 : 2) : x.cells[i]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Highlight a snippet inside a longer text (whitespace and case tolerant). */
export function Highlighted({ text, snippet }: { text: string; snippet?: string | null }) {
  const markRef = useRef<HTMLElement>(null);
  const parts = useMemo(() => {
    if (!snippet) return null;
    const words = snippet.replace(/[“”„"]/g, " ").split(/\s+/).filter(Boolean).slice(0, 14);
    if (!words.length) return null;
    const esc = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    for (let n = esc.length; n >= Math.min(3, esc.length); n--) {
      const re = new RegExp(esc.slice(0, n).join("[\\s\\S]{0,3}?\\s*"), "i");
      const m = re.exec(text);
      if (m) {
        // extend to the end of the snippet's line
        let end = m.index + m[0].length;
        const nl = text.indexOf("\n", end);
        const rest = Math.max(0, snippet.length - m[0].length);
        end = Math.min(nl === -1 ? text.length : nl, end + rest);
        return [text.slice(0, m.index), text.slice(m.index, end), text.slice(end)];
      }
    }
    return null;
  }, [text, snippet]);
  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center" });
  }, [parts]);
  if (!parts) return <>{text}</>;
  return (
    <>
      {parts[0]}
      <mark ref={markRef}>{parts[1]}</mark>
      {parts[2]}
    </>
  );
}

function EmailRef({ pid, rev, r }: { pid: string; rev: number; r: Ref }) {
  const { data, error, loading } = useAsync(() => api.email(pid, rev, r.file_id!), [pid, rev, r.file_id]);
  if (loading) return <SkeletonRows />;
  if (error || !data) return <ErrorBox message={error ?? ""} />;
  return (
    <div className="emailview">
      <div className="hdr">
        <span className="muted">From</span><span>{data.from}</span>
        <span className="muted">To</span><span>{data.to}</span>
        {data.cc && (<><span className="muted">Cc</span><span>{data.cc}</span></>)}
        <span className="muted">Date</span><span>{data.date}</span>
        <span className="muted">Subject</span><span><b>{data.subject}</b></span>
        {data.attachments.length > 0 && (<><span className="muted">Files</span><span>{data.attachments.join(", ")}</span></>)}
      </div>
      <div className="body">
        <Highlighted text={data.body} snippet={r.snippet} />
      </div>
    </div>
  );
}

function TextRef({ pid, rev, r }: { pid: string; rev: number; r: Ref }) {
  const { data, error, loading } = useAsync(() => api.text(pid, rev, r.file_id!), [pid, rev, r.file_id]);
  if (loading) return <SkeletonRows />;
  if (error || !data) return <ErrorBox message={error ?? ""} />;
  return (
    <div className="emailview">
      <div className="body">
        <Highlighted text={data.text} snippet={r.snippet} />
      </div>
    </div>
  );
}

function ImageRef({ pid, rev, r }: { pid: string; rev: number; r: Ref }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <div className="pdfview">
      {!loaded && <SkeletonRows n={3} />}
      <img src={api.imageUrl(pid, rev, r.file_id!)} alt={r.path ?? ""} onLoad={() => setLoaded(true)} />
    </div>
  );
}

function IfcRef({ pid, rev, r }: { pid: string; rev: number; r: Ref }) {
  const { data, error, loading } = useAsync(() => api.ifc(pid, rev, r.file_id!, r.guids ?? []), [pid, rev, r.file_id, (r.guids ?? []).join(",")]);
  const [all, setAll] = useState(false);
  if (loading) return <SkeletonRows />;
  if (error || !data) return <ErrorBox message={error ?? ""} />;
  const rows = all ? data.elements : data.elements.slice(0, 12);
  return (
    <div className="col">
      <div className="small muted">
        {r.guids?.length ? t("src.ifc_selected", { n: num(data.selected), total: num(data.total_elements) }) : `${num(data.total_elements)} elements`}
        {data.application ? ` · ${data.application}` : ""}{data.schema ? ` · ${data.schema}` : ""}
      </div>
      {r.snippet && <div className="snippet">{r.snippet}</div>}
      <IfcPlan plan={data.plan} />
      {data.elements.length > 0 && (
        <div className="table-wrap" style={{ maxHeight: 320, border: "1px solid var(--line)", borderRadius: 4 }}>
          <table className="t compact small">
            <thead>
              <tr>
                <th>GlobalId</th><th>Entity</th><th>Assembly</th><th>Profile</th><th>Grade</th>
                <th className="n">Length mm</th><th className="n">kg</th><th className="n">Phase</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={String(e.guid)}>
                  <td className="mono tiny">{e.guid}</td>
                  <td className="tiny">{String(e.entity ?? "").replace("Ifc", "")}</td>
                  <td>{e.assembly_mark ?? e.assembly_name ?? ""}</td>
                  <td>{e.profile}</td>
                  <td>{e.grade}</td>
                  <td className="n">{num(e.length, 0)}</td>
                  <td className="n">{num(e.weight, 1)}</td>
                  <td className="n">{e.phase ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.elements.length > 12 && (
        <button className="linkbtn small" onClick={() => setAll(!all)}>
          {all ? t("common.show_less") : t("common.show_all", { n: data.elements.length })}
        </button>
      )}
    </div>
  );
}

function IfcPlan({ plan }: { plan: IfcView["plan"] }) {
  const W = Math.max(plan.width, 1);
  const H = Math.max(plan.height, 1);
  const pad = Math.max(W, H) * 0.03;
  const seg = (s: number[], i: number, hl: boolean): ReactNode => {
    const [x1, y1, x2, y2] = s;
    if (Math.abs(x1 - x2) < 0.01 && Math.abs(y1 - y2) < 0.01)
      return <circle key={i} cx={x1} cy={H - y1} r={hl ? Math.max(W, H) * 0.006 : Math.max(W, H) * 0.003} className={hl ? "hl" : "bg"} />;
    return <line key={i} x1={x1} y1={H - y1} x2={x2} y2={H - y2} className={hl ? "hl" : "bg"} />;
  };
  return (
    <div className="planview">
      <div className="tiny muted" style={{ padding: "6px 8px 0" }}>{t("src.ifc_plan")} · {num(plan.width, 0)} × {num(plan.height, 0)} m</div>
      <svg viewBox={`${-pad} ${-pad} ${W + 2 * pad} ${H + 2 * pad}`} style={{ width: "100%", height: 260, display: "block" }} preserveAspectRatio="xMidYMid meet">
        <style>{`.bg{stroke:#b9c4cf;stroke-width:1;vector-effect:non-scaling-stroke;fill:#b9c4cf}.hl{stroke:#d26a00;stroke-width:3;vector-effect:non-scaling-stroke;fill:#d26a00}`}</style>
        {plan.background.map((s, i) => seg(s, i, false))}
        {plan.highlight.map((s, i) => seg(s, i + 100000, true))}
      </svg>
    </div>
  );
}

export function KnowledgeRow({ kid }: { kid: string }) {
  const { data, error, loading } = useAsync(() => api.knowledgeRow(kid), [kid]);
  if (loading) return <SkeletonRows n={2} />;
  if (error || !data) return <ErrorBox message={error ?? ""} />;
  const entries = Object.entries(data.data).filter(([, v]) => v !== null && v !== "");
  const status = String(data.data.status ?? "");
  return (
    <div className="knrow">
      <div className="h">
        <b>{data.id}</b>
        <span className="muted">{data.file} · {t("src.kn_row", { sheet: data.sheet, row: data.row })}</span>
        {status && <span className={`chip noicon ${status === "derived" ? "calculated" : status === "placeholder" ? "conflict" : "predicted"}`} style={{ marginLeft: "auto" }}>{status}</span>}
      </div>
      <table className="t compact small">
        <tbody>
          {entries.filter(([k]) => k !== "id" && k !== "status").map(([k, v]) => (
            <tr key={k}>
              <td className="muted" style={{ width: "34%" }}>{k}</td>
              <td>{typeof v === "number" ? num(v, Number.isInteger(v) ? 0 : 3) : String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
