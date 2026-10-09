import { useEffect, useState } from "react";
import { fmtRaw, fmtV, pct } from "../format";
import { t } from "../i18n";
import type { Ref, V } from "../types";
import { KnowledgeRow, RefView } from "./RefView";
import { useReport } from "./ReportContext";
import { TypeChip } from "./common";

export function SourcePanel() {
  const ctx = useReport();
  const top = ctx.panel[ctx.panel.length - 1];
  if (!top) return null;
  return (
    <aside className="panel" aria-label={t("src.title")}>
      <div className="panel-head">
        {ctx.panel.length > 1 && (
          <button className="btn small ghost" onClick={ctx.back} aria-label={t("common.back")}>
            ← {t("common.back")}
          </button>
        )}
        <div className="grow tiny muted" style={{ paddingTop: 6 }}>{t("src.title")}</div>
        <button className="btn small ghost" onClick={ctx.close} aria-label={t("common.close")}>
          {t("common.close")} ✕
        </button>
      </div>
      {top.kind === "value" ? <ValuePanel id={top.id} /> : <RefsPanel title={top.title} refs={top.refs} text={top.text} />}
    </aside>
  );
}

function RefsPanel({ title, refs, text }: { title: string; refs: Ref[]; text?: string }) {
  return (
    <div>
      <h2>{title}</h2>
      {text && <p className="mt-s muted">{text}</p>}
      <RefList refs={refs} />
    </div>
  );
}

function RefList({ refs }: { refs: Ref[] }) {
  const ctx = useReport();
  const [i, setI] = useState(0);
  useEffect(() => setI(0), [refs]);
  if (!refs.length) return null;
  const r = refs[Math.min(i, refs.length - 1)];
  return (
    <section>
      <h3>{t("src.references")} ({refs.length})</h3>
      {refs.length > 1 && (
        <div className="ref-tabs">
          {refs.map((x, k) => (
            <button key={k} className={`ref-tab${k === i ? " active" : ""}`} onClick={() => setI(k)} title={x.label ?? x.path ?? ""}>
              {x.label ?? x.path}
            </button>
          ))}
        </div>
      )}
      {refs.length === 1 && <div className="small" style={{ marginBottom: 6 }}><b>{r.label ?? r.path}</b></div>}
      <RefView pid={ctx.pid} rev={ctx.rev} r={r} />
    </section>
  );
}

function ValuePanel({ id }: { id: string }) {
  const ctx = useReport();
  const v = ctx.res.values[id];
  if (!v) return <div className="muted">{t("error.not_found")}</div>;
  const pend = v.edit_key ? ctx.pendingByKey[v.edit_key] : undefined;
  return (
    <div>
      <h2>{v.label}</h2>
      <div className="row wrap mt-s">
        <span className="bigval">{fmtV(v)}</span>
        <TypeChip type={v.type} />
        {v.type !== "calculated" && <span className="small muted">{t("src.confidence", { p: pct(v.confidence) })}</span>}
        {v.conflict?.length > 0 && <span className="chip conflict">{t("type.conflict")}</span>}
      </div>
      <p className="small muted mt-s">{t(`type.${v.type}.help`)}</p>
      {v.edited && (
        <div className="notice mt-s small">
          {t("src.edited", { before: fmtRaw(v.edited.before, v.unit), after: fmtRaw(v.edited.after, v.unit) })}
          {v.edited.reason ? ` — ${v.edited.reason}` : ""}
        </div>
      )}
      {pend && (
        <div className="notice warn mt-s small">
          {t("review.pending_one")}: {fmtRaw(pend.before, v.unit)} → <b>{fmtRaw(pend.value, v.unit)}</b>
          <button className="linkbtn small" style={{ marginLeft: 8 }} onClick={() => ctx.removeEdit(pend.id)}>{t("common.remove")}</button>
        </div>
      )}

      {v.conflict?.length > 0 && (
        <section>
          <h3>{t("src.conflict")}</h3>
          <p className="small muted" style={{ marginBottom: 8 }}>{t("src.conflict_help")}</p>
          {v.conflict.map((c, k) => (
            <div key={k} className="conflict-opt">
              <div>
                <b>{fmtRaw(c.value, c.unit ?? v.unit)}{c.unit && typeof c.value === "number" ? ` ${c.unit}` : ""}</b>
                {c.note && <span className="muted small"> — {c.note}</span>}
                <div className="row wrap" style={{ gap: 6, marginTop: 4 }}>
                  {c.refs.map((r, j) => (
                    <button key={j} className="reflink" onClick={() => ctx.openRefs(v.label, [r], c.note ?? undefined)}>{r.label ?? r.path}</button>
                  ))}
                </div>
              </div>
              {v.editable && v.edit_key && String(c.value) !== String(v.value) && (
                <button className="btn small" onClick={() => ctx.addEdit(v.edit_key!, c.value, v.label, v.value, `Conflict resolved: ${c.note ?? ""}`)}>
                  {t("src.use_this")}
                </button>
              )}
            </div>
          ))}
        </section>
      )}

      {(v.reasoning || v.question) && (
        <section>
          {v.reasoning && (<><h3>{t("src.reasoning")}</h3><p>{v.reasoning}</p></>)}
          {v.question && (<><h3 className="mt-s" style={{ marginTop: 12 }}>{t("src.question")}</h3><p>{v.question}</p></>)}
        </section>
      )}

      {(v.formula || v.inputs.length > 0) && (
        <section>
          <h3>{t("src.formula")}</h3>
          {v.formula && <div className="formula">{v.formula}</div>}
          {v.inputs.length > 0 && <Inputs ids={v.inputs} />}
        </section>
      )}

      {v.kn.length > 0 && (
        <section>
          <h3>{t("src.knowledge")}</h3>
          <div className="col">
            {v.kn.slice(0, 8).map((k) => <KnowledgeRow key={k} kid={k} />)}
            {v.kn.length > 8 && <div className="small muted">+ {v.kn.length - 8}: {v.kn.slice(8).join(", ")}</div>}
          </div>
        </section>
      )}

      {v.refs.length > 0 ? <RefList refs={v.refs} /> : !v.formula && !v.inputs.length && <p className="small muted mt">{t("src.no_refs")}</p>}

      {v.editable && v.edit_key && ctx.isLatest && <EditBox v={v} />}
    </div>
  );
}

function Inputs({ ids }: { ids: string[] }) {
  const ctx = useReport();
  const [all, setAll] = useState(false);
  const list = ids.filter((i) => ctx.res.values[i]);
  const shown = all ? list : list.slice(0, 12);
  return (
    <div className="inputs mt-s">
      <div className="tiny muted" style={{ padding: "0 8px 4px" }}>{t("src.inputs")}</div>
      {shown.map((i) => {
        const x: V = ctx.res.values[i];
        return (
          <button key={i} onClick={() => ctx.open(i, true)}>
            <span className="lbl">{x.label}</span>
            <span className="row" style={{ gap: 8 }}>
              <span className="num">{fmtV(x)}</span>
              <TypeChip type={x.type} short />
            </span>
          </button>
        );
      })}
      {list.length > 12 && (
        <button className="linkbtn small" style={{ padding: "6px 8px" }} onClick={() => setAll(!all)}>
          {all ? t("common.show_less") : t("common.show_all", { n: list.length })}
        </button>
      )}
    </div>
  );
}

function EditBox({ v }: { v: V }) {
  const ctx = useReport();
  // the total price is changed through its method (part-by-part / quick €/t), never typed in
  const isMethod = v.edit_key === "param:method";
  const current = isMethod ? String(ctx.res.summary.method) : String(v.value ?? "");
  const [value, setValue] = useState<string>(current);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>();
  useEffect(() => {
    setValue(current);
    setReason("");
    setMsg(undefined);
  }, [v.id, current]);
  const allowed = v.allowed && v.allowed.length ? v.allowed.map(String) : null;
  const numeric = typeof v.value === "number" && !isMethod;
  const submit = async () => {
    setBusy(true);
    setMsg(undefined);
    try {
      const val = numeric ? Number(value.replace(",", ".").replace(/\s/g, "")) : value;
      await ctx.addEdit(v.edit_key!, val, isMethod ? t("cost.methods") : v.label, isMethod ? current : v.value, reason || undefined);
      setMsg(t("src.edit_added"));
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section>
      <h3>{isMethod ? t("cost.methods") : t("src.edit")}</h3>
      <div className="editbox col">
        <div className="row">
          {allowed ? (
            <select value={value} onChange={(e) => setValue(e.target.value)} aria-label={v.label}>
              {!allowed.includes(current) && <option value={current}>{current}</option>}
              {allowed.map((a) => <option key={a} value={a}>{isMethod ? t(`report.method.${a}`) : a}</option>)}
            </select>
          ) : (
            <input type="text" inputMode={numeric ? "decimal" : "text"} value={value} onChange={(e) => setValue(e.target.value)} aria-label={v.label} style={{ width: numeric ? 140 : "100%" }} />
          )}
          {v.unit && numeric && <span className="muted">{v.unit}</span>}
        </div>
        <input type="text" placeholder={t("src.edit_reason")} value={reason} onChange={(e) => setReason(e.target.value)} />
        <div className="row">
          <button className="btn primary small" disabled={busy || value === current} onClick={submit}>{t("src.edit_add")}</button>
          {msg && <span className="small muted">{msg}</span>}
        </div>
      </div>
    </section>
  );
}
