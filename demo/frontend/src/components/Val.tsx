import { fmtRaw, fmtV, num } from "../format";
import { t } from "../i18n";
import { useReport } from "./ReportContext";
import { TypeChip } from "./common";

/** A clickable, traceable value. Click → source panel. */
export function Val({ id, unit = true, dec, chip, fallback }: { id?: string | null; unit?: boolean; dec?: number; chip?: boolean; fallback?: string }) {
  const ctx = useReport();
  const v = id ? ctx.res.values[id] : undefined;
  if (!v) return <span className="faint">{fallback ?? t("common.none")}</span>;
  const active = ctx.panel.length > 0 && ctx.panel[ctx.panel.length - 1].kind === "value" &&
    (ctx.panel[ctx.panel.length - 1] as { id: string }).id === id;
  const pend = v.edit_key ? ctx.pendingByKey[v.edit_key] : undefined;
  const text = dec !== undefined && typeof v.value === "number" ? num(v.value, dec) + (unit && v.unit && v.unit !== "€" ? ` ${v.unit}` : "") : fmtV(v, unit);
  const cls = ["val", v.type, v.conflict?.length ? "conflict" : "", v.edited ? "edited" : "", active ? "active" : ""].join(" ");
  const title = `${v.label} · ${t(`type.${v.type}`)}${v.type === "predicted" ? ` (${Math.round(v.confidence * 100)} %)` : ""}`;
  return (
    <>
      <button type="button" className={cls} onClick={() => ctx.open(v.id)} title={title}>
        {text}
        {v.conflict?.length ? <span className="mark">!</span> : null}
      </button>
      {pend && (
        <span className="chip edited noicon" style={{ marginLeft: 6 }} title={t("review.pending_one")}>
          → {fmtRaw(pend.value, v.unit)}
        </span>
      )}
      {chip && <> <TypeChip type={v.type} /></>}
    </>
  );
}

/** Plain formatted value (no click), e.g. inside labels. */
export function useVal(id?: string | null): number | undefined {
  const ctx = useReport();
  const v = id ? ctx.res.values[id] : undefined;
  return typeof v?.value === "number" ? v.value : undefined;
}
