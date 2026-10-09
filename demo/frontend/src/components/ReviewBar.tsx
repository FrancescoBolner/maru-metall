import { useState } from "react";
import { api } from "../api";
import { fmtRaw } from "../format";
import { t, tn } from "../i18n";
import { go } from "../router";
import type { CorrectionProposal } from "../types";
import { useReport } from "./ReportContext";

/** Sticky review bar: changes waiting, written correction, recalculate. */
export function ReviewBar() {
  const ctx = useReport();
  const [open, setOpen] = useState<"none" | "list" | "write">("none");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [prop, setProp] = useState<CorrectionProposal>();
  const [sel, setSel] = useState<Record<number, boolean>>({});
  const [err, setErr] = useState<string>();
  const n = ctx.pending.length;
  const latestRev = ctx.project?.revisions?.length ? Math.max(...ctx.project.revisions.map((r) => r.rev)) : ctx.rev;
  const nextName = `${ctx.res.quote_number}_rev${latestRev + 1}`;

  const interpret = async () => {
    setBusy(true);
    setErr(undefined);
    setProp(undefined);
    try {
      const p = await api.interpret(ctx.pid, text);
      if (p.error) setErr(p.error);
      setProp(p);
      const s: Record<number, boolean> = {};
      p.changes.forEach((_, i) => (s[i] = true));
      setSel(s);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const accept = async () => {
    if (!prop?.correction_id) return;
    setBusy(true);
    try {
      await api.accept(ctx.pid, prop.correction_id, text, prop.changes.filter((_, i) => sel[i]));
      setProp(undefined);
      setText("");
      setOpen("list");
      ctx.reloadProject();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const recalc = async () => {
    setBusy(true);
    try {
      const j = await api.run(ctx.pid, "recalc");
      go({ page: "run", pid: ctx.pid, job: j.job_id });
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  if (!ctx.isLatest) return null;
  return (
    <div className="pendbar" style={{ flexDirection: "column", alignItems: "stretch" }}>
      <div className="row wrap">
        <b>{t("review.title")}</b>
        {n > 0 ? (
          <button className="linkbtn" onClick={() => setOpen(open === "list" ? "none" : "list")}>{tn("review.pending", n)}</button>
        ) : (
          <span className="small muted">{t("review.direct_hint")}</span>
        )}
        <button className="btn small" onClick={() => setOpen(open === "write" ? "none" : "write")}>{t("review.write")}</button>
        <div className="right row">
          {n > 0 && <span className="small muted">{t("review.recalc_hint", { name: nextName })}</span>}
          <button className="btn primary" disabled={n === 0 || busy} onClick={recalc}>{t("review.recalc")}</button>
        </div>
      </div>
      {err && <div className="errorbox mt-s small">{err}</div>}
      {open === "list" && n > 0 && (
        <ul className="pendlist">
          {ctx.pending.map((o) => (
            <li key={o.id}>
              <span className="grow">
                {o.label ?? `${o.target} ${o.key}`}: {fmtRaw(o.before)} <span className="arrow">→</span> <b>{fmtRaw(o.value)}</b>
                {o.reason && <span className="muted"> — {o.reason}</span>}
              </span>
              <span className="chip plain">{t(`review.source.${o.source}`)}</span>
              <button className="linkbtn small" onClick={() => ctx.removeEdit(o.id)}>{t("common.remove")}</button>
            </li>
          ))}
        </ul>
      )}
      {open === "write" && (
        <div className="mt-s col">
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("review.write_placeholder")} aria-label={t("review.write")} />
          <div className="row">
            <button className="btn" disabled={!text.trim() || busy} onClick={interpret}>{busy && !prop ? t("review.interpreting") : t("review.interpret")}</button>
            {prop?.provider && <span className="tiny faint">{prop.provider}</span>}
          </div>
          {prop && (
            <div className="col">
              {prop.changes.length > 0 ? (
                <>
                  <div className="small"><b>{t("review.proposed")}</b> <span className="muted">— {t("review.proposed_help")}</span></div>
                  <div>
                    {prop.changes.map((c, i) => (
                      <label key={i} className="proposal">
                        <input type="checkbox" checked={!!sel[i]} onChange={(e) => setSel({ ...sel, [i]: e.target.checked })} />
                        <span>
                          <span className="chg">{c.label}: {fmtRaw(c.before)} <span className="arrow">→</span> {fmtRaw(c.after)}</span>
                          {c.explanation && <div className="small muted">{c.explanation}</div>}
                        </span>
                      </label>
                    ))}
                  </div>
                </>
              ) : (
                <div className="notice warn small">{t("review.nothing")}</div>
              )}
              {prop.not_applied.length > 0 && (
                <div className="small">
                  <b>{t("review.not_applied")}</b>
                  <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                    {prop.not_applied.map((x, i) => <li key={i}>“{x.text}” — <span className="muted">{x.reason}</span></li>)}
                  </ul>
                </div>
              )}
              {prop.changes.length > 0 && (
                <div>
                  <button className="btn primary small" disabled={busy || !Object.values(sel).some(Boolean)} onClick={accept}>{t("review.apply")}</button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
