import { useMemo, useState, type ReactNode } from "react";
import { useReport } from "../components/ReportContext";
import { TypeChip, Legend, StatusBadge } from "../components/common";
import { Val } from "../components/Val";
import { bytes, date, eur, fmtRaw, num, pct } from "../format";
import { t } from "../i18n";
import { href } from "../router";
import type { CategorySummary, FileEntry, Ref, V } from "../types";

/* ------------------------------------------------------------------ helpers */
function Card({ title, right, children, pad = true }: { title?: ReactNode; right?: ReactNode; children: ReactNode; pad?: boolean }) {
  return (
    <section className="card">
      {title && (
        <div className="card-head">
          <h2>{title}</h2>
          {right && <div className="right row">{right}</div>}
        </div>
      )}
      {pad ? <div className="card-body">{children}</div> : children}
    </section>
  );
}

function RefLinks({ refs, title, max = 2 }: { refs: Ref[]; title: string; max?: number }) {
  const ctx = useReport();
  if (!refs?.length) return null;
  return (
    <span className="col" style={{ gap: 2 }}>
      {refs.slice(0, max).map((r, i) => (
        <button key={i} className="reflink" onClick={() => ctx.openRefs(title, [r, ...refs.filter((x) => x !== r)])} title={r.snippet ?? ""}>
          {r.label ?? r.path}
        </button>
      ))}
      {refs.length > max && <span className="tiny muted">+{refs.length - max}</span>}
    </span>
  );
}

function sourceLabel(v?: V): string {
  if (!v) return "";
  if (v.refs?.length) return v.refs[0].label ?? v.refs[0].path ?? "";
  if (v.formula) return v.formula;
  return "";
}

const catKey = (c: CategorySummary) => `${c.name.split(" — ")[0]}|${c.phase ?? ""}`;
const SURFACES = ["NONE", "C2M", "C2H", "C3M", "C3H", "C3VH", "C4M", "C4H", "C5M", "HDG"];

/* ------------------------------------------------------------------ 1 summary */
export function SummaryTab() {
  const { res } = useReport();
  const s = res.summary;
  const v = res.values;
  const conf = s.confidence as Record<string, number>;
  const top = res.risks.filter((r) => (s.top_risks as string[]).includes(r.id));
  return (
    <div className="grid2">
      <div className="col" style={{ gap: 16 }}>
        <Card title={t("summary.key_numbers")}>
          <div className="kv">
            <span className="k">{t("report.price")}</span><span><Val id={s.price_id} /> <span className="muted small">({eur(v[s.low_id]?.value)} – {eur(v[s.high_id]?.value)})</span></span>
            <span className="k">{t("summary.steel")}</span><span><Val id="total.kg" dec={0} /> · <Val id={s.pieces_id} /> · {t("takeoff.col.plate").toLowerCase()} <Val id={s.plate_share_id} /></span>
            <span className="k">{t("summary.hours")}</span><span><Val id={s.hours_id} /> <span className="muted small">({t("hours.workshop").toLowerCase()}: <Val id={s.metal_hours_id} />)</span></span>
            <span className="k">{t("summary.labour")}</span><span><Val id={s.labour_cost_id} /></span>
            <span className="k">{t("summary.paint")}</span><span><Val id={s.paint_litres_id} /> · <Val id={s.paint_cost_id} />{s.galv_cost_id && v[s.galv_cost_id] ? <> · HDG <Val id={s.galv_cost_id} /></> : null}</span>
            <span className="k">{t("summary.co2")}</span><span><Val id={s.co2_id} /> · <Val id={s.co2_intensity_id} /></span>
            <span className="k">{v[s.longest_id]?.label ?? t("takeoff.col.longest")}</span><span><Val id={s.longest_id} /></span>
            <span className="k">{t("summary.level")}</span><span>{s.level_reason}</span>
            <span className="k">{t("summary.quantity_source")}</span><span>{s.quantity_source}</span>
          </div>
        </Card>
        <Card title={t("summary.methods")}>
          <table className="t compact">
            <tbody>
              <tr><td>{t("cost.detailed")}{s.method === "detailed" && <span className="chip plain" style={{ marginLeft: 8 }}>{t("cost.chosen")}</span>}</td><td className="n"><Val id={s.detailed_id} /></td></tr>
              <tr><td>{t("cost.quick")}{s.method === "quick" && <span className="chip plain" style={{ marginLeft: 8 }}>{t("cost.chosen")}</span>}</td><td className="n"><Val id={s.quick_id} /></td></tr>
              <tr className="total"><td>{t("summary.gap")}</td><td className="n"><Val id={s.gap_id} /></td></tr>
            </tbody>
          </table>
        </Card>
        {(s.checks as unknown[]).length > 0 && (
          <Card title={t("summary.checks")}>
            <table className="t compact">
              <tbody>
                {(s.checks as { what: string; a: number; b: number; diff: number; ok: boolean }[]).map((c, i) => (
                  <tr key={i}>
                    <td>{c.what}</td>
                    <td className="n">{num(c.a, 0)} / {num(c.b, 0)}</td>
                    <td className="n">{c.diff >= 0 ? "+" : ""}{num(c.diff * 100, 2)} %</td>
                    <td><span className={`sev ${c.ok ? "low" : "high"}`} style={{ color: c.ok ? "var(--ok)" : undefined }}>{c.ok ? t("summary.check_ok") : t("summary.check_bad")}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
      <div className="col" style={{ gap: 16 }}>
        <Card title={t("summary.confidence")}>
          <p className="small muted" style={{ marginBottom: 8 }}>{t("summary.confidence_help")}</p>
          <div className="share-bar" role="img" aria-label="value types">
            <div style={{ width: pct(conf.extracted).replace(" %", "%").replace(",", "."), background: "var(--t-extracted)" }} />
            <div style={{ width: pct(conf.calculated).replace(" %", "%").replace(",", "."), background: "var(--t-calculated)" }} />
            <div style={{ width: pct(conf.predicted).replace(" %", "%").replace(",", "."), background: "var(--t-predicted)" }} />
          </div>
          <div className="row wrap mt-s small">
            <TypeChip type="extracted" /> {pct(conf.extracted)}
            <TypeChip type="calculated" /> {pct(conf.calculated)}
            <TypeChip type="predicted" /> {pct(conf.predicted)}
          </div>
          <p className="small mt-s">{t("summary.predicted_share", { p: pct(s.predicted_share_of_price, 1) })}</p>
        </Card>
        <Card title={t("summary.top_risks")} right={<a className="small" href={href({ page: "report", pid: res.project_id, rev: res.revision, tab: "risks" })}>{t("report.tabs.risks")} →</a>}>
          {top.map((r) => <RiskItem key={r.id} id={r.id} />)}
        </Card>
        {res.questions.length > 0 && (
          <Card title={t("summary.questions")}>
            <ol style={{ margin: 0, paddingLeft: 18 }}>
              {res.questions.map((q) => (
                <li key={q.id} style={{ marginBottom: 6 }}>{q.text} <span className="small muted">— {q.reason}</span></li>
              ))}
            </ol>
          </Card>
        )}
        <Legend />
      </div>
    </div>
  );
}

function RiskItem({ id }: { id: string }) {
  const { res, open } = useReport();
  const r = res.risks.find((x) => x.id === id)!;
  return (
    <div className="risk-item">
      <span className={`sev ${r.severity}`}>{t(`risks.sev.${r.severity}`)}</span>
      <div>
        <div className="title">{r.title}</div>
        <div className="detail">{r.detail}</div>
        <div className="row wrap" style={{ gap: 10, marginTop: 4 }}>
          {r.value_ids.slice(0, 3).map((vid) => res.values[vid] && (
            <button key={vid} className="reflink" onClick={() => open(vid)}>{res.values[vid].label}</button>
          ))}
          <RefLinks refs={r.refs} title={r.title} max={1} />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ 2 takeoff */
export function TakeoffTab() {
  const ctx = useReport();
  const { res } = ctx;
  const [q, setQ] = useState("");
  const [all, setAll] = useState(false);
  const lines = useMemo(() => {
    const s = q.trim().toLowerCase();
    return res.lines.filter((l) => !s || `${l.category} ${l.profile} ${l.grade ?? ""} ${l.phase ?? ""}`.toLowerCase().includes(s));
  }, [q, res.lines]);
  const shown = all ? lines : lines.slice(0, 150);
  const totalKg = res.categories.filter((c) => c.included).reduce((a, c) => a + Number(res.values[c.kg_id]?.value ?? 0), 0);
  const groups = ["quantities", "specs", "scope", "commercial", "logistics", "operations"];
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title={t("takeoff.categories")} pad={false} right={<Legend />}>
        <div className="table-wrap">
          <table className="t">
            <thead>
              <tr>
                <th>{t("takeoff.col.scope")}</th>
                <th>{t("takeoff.col.category")}</th>
                <th className="n">{t("takeoff.col.kg")}</th>
                <th className="n">{t("takeoff.col.pieces")}</th>
                <th className="n">{t("takeoff.col.area")}</th>
                <th className="n">{t("takeoff.col.plate")}</th>
                <th>{t("takeoff.col.surface")}</th>
                <th className="n">{t("takeoff.col.longest")}</th>
              </tr>
            </thead>
            <tbody>
              {res.categories.map((c) => {
                const key = catKey(c);
                const pIn = ctx.pendingByKey[`category:${key}:included`];
                const pSurf = ctx.pendingByKey[`category:${key}:surface`];
                const inScope = pIn ? Boolean(pIn.value) : c.included;
                const surfV = res.values[c.surface_id];
                return (
                  <tr key={c.kg_id} className={c.included ? "" : "off"}>
                    <td>
                      <input type="checkbox" checked={inScope} disabled={!ctx.isLatest} aria-label={`${c.name} ${t("takeoff.col.scope")}`}
                        onChange={(e) => ctx.addEdit(`category:${key}:included`, e.target.checked, `${c.name} — in scope`, c.included)} />
                    </td>
                    <td>{c.name}{pIn && <span className="chip edited noicon" style={{ marginLeft: 6 }}>{inScope ? "in" : "out"}</span>}</td>
                    <td className="n"><Val id={c.kg_id} unit={false} /></td>
                    <td className="n"><Val id={c.pieces_id} unit={false} /></td>
                    <td className="n"><Val id={c.area_id} unit={false} /></td>
                    <td className="n"><Val id={c.plate_share_id} /></td>
                    <td className="nowrap">
                      <Val id={c.surface_id} />{" "}
                      {ctx.isLatest && (
                        <select className="inline" value={String(pSurf?.value ?? surfV?.value ?? "")} aria-label={`${c.name} ${t("takeoff.col.surface")}`}
                          onChange={(e) => ctx.addEdit(`category:${key}:surface`, e.target.value, `${c.name} — surface treatment`, surfV?.value)}>
                          {!SURFACES.includes(String(surfV?.value)) && <option value={String(surfV?.value)}>{String(surfV?.value)}</option>}
                          {SURFACES.map((x) => <option key={x} value={x}>{x}</option>)}
                        </select>
                      )}
                    </td>
                    <td className="n">{num((c.longest_mm ?? 0) / 1000, 1)}</td>
                  </tr>
                );
              })}
              <tr className="total">
                <td />
                <td>{t("takeoff.total")}</td>
                <td className="n"><Val id="total.kg" unit={false} /></td>
                <td className="n"><Val id="total.pieces" unit={false} /></td>
                <td className="n"><Val id="total.area" unit={false} /></td>
                <td className="n"><Val id="total.plate_share" /></td>
                <td />
                <td className="n"><Val id="q.longest" unit={false} /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="tiny muted" style={{ padding: "6px 16px 10px" }}>{num(totalKg, 0)} kg</div>
      </Card>

      <Card title={`${t("takeoff.lines")} (${lines.length})`} pad={false}
        right={<input type="text" placeholder={t("takeoff.filter")} value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} />}>
        <div className="table-wrap tall">
          <table className="t compact">
            <thead>
              <tr>
                <th>{t("takeoff.col.category")}</th>
                <th>{t("takeoff.col.profile")}</th>
                <th>{t("takeoff.col.grade")}</th>
                <th className="n">{t("takeoff.col.pieces")}</th>
                <th className="n">{t("takeoff.col.kg")}</th>
                <th className="n">{t("takeoff.col.area")}</th>
                <th>{t("takeoff.col.type")}</th>
                <th>{t("takeoff.col.source")}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((l) => {
                const kv = res.values[l.kg_id];
                return (
                  <tr key={l.id} className={l.included ? "" : "off"}>
                    <td>{l.category}{l.phase ? <span className="muted small"> · ph {l.phase}</span> : null}</td>
                    <td className="nowrap">{l.profile}</td>
                    <td className="nowrap">{l.grade}</td>
                    <td className="n"><Val id={l.pieces_id} unit={false} /></td>
                    <td className="n"><Val id={l.kg_id} unit={false} dec={1} /></td>
                    <td className="n"><Val id={l.area_id} unit={false} dec={1} /></td>
                    <td>{kv && <TypeChip type={kv.type} />}</td>
                    <td className="small"><button className="reflink" onClick={() => ctx.open(l.kg_id)}>{sourceLabel(kv).slice(0, 70)}</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {lines.length > 150 && (
          <div style={{ padding: "8px 16px" }}>
            <button className="linkbtn small" onClick={() => setAll(!all)}>{all ? t("common.show_less") : t("common.show_all", { n: lines.length })}</button>
          </div>
        )}
      </Card>

      <div className="grid2">
        {groups.filter((g) => res.features[g]?.length).map((g) => (
          <Card key={g} title={t(`takeoff.group.${g}`)} pad={false}>
            <table className="t compact">
              <tbody>
                {res.features[g].filter((id) => res.values[id]).map((id) => {
                  const fv = res.values[id];
                  return (
                    <tr key={id}>
                      <td style={{ width: "42%" }}>{fv.label}</td>
                      <td><Val id={id} />{fv.conflict?.length ? <span className="chip conflict" style={{ marginLeft: 6 }}>{t("type.conflict")}</span> : null}</td>
                      <td style={{ width: 96 }}><TypeChip type={fv.type} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ 3 hours */
export function HoursTab() {
  const { res } = useReport();
  const ht = res.hours_totals;
  const [cat, setCat] = useState("");
  const cats = Array.from(new Set(res.hours.map((h) => h.category)));
  const rows = res.hours.filter((h) => !cat || h.category === cat);
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="grid2">
        <Card title={t("hours.by_operation")} pad={false}>
          <table className="t compact">
            <tbody>
              {Object.entries(ht.by_operation).map(([op, id]) => (
                <tr key={op}><td>{op}</td><td className="n"><Val id={id} /></td></tr>
              ))}
              <tr className="total"><td>{t("hours.total")}</td><td className="n"><Val id={ht.total} /></td></tr>
              <tr className="sub"><td>{t("hours.workshop")}</td><td className="n"><Val id={ht.metal} /></td></tr>
              {ht.labour_cost && <tr className="sub"><td>{t("summary.labour")}</td><td className="n"><Val id={ht.labour_cost} /></td></tr>}
              {ht.quick && <tr className="sub"><td>{t("hours.quick")}</td><td className="n"><Val id={ht.quick} /></td></tr>}
            </tbody>
          </table>
        </Card>
        <Card title={t("hours.by_category")} pad={false}>
          <table className="t compact">
            <tbody>
              {Object.entries(ht.by_category).map(([c, id]) => (
                <tr key={c}><td><button className="linkbtn" onClick={() => setCat(c)}>{c}</button></td><td className="n"><Val id={id} /></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <Card title={t("hours.detail")} pad={false}
        right={
          <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label={t("hours.col.category")}>
            <option value="">{t("hours.col.category")}: all</option>
            {cats.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        }>
        <div className="table-wrap tall">
          <table className="t compact">
            <thead>
              <tr>
                <th>{t("hours.col.operation")}</th>
                <th>{t("hours.col.category")}</th>
                <th className="n">{t("hours.col.quantity")}</th>
                <th className="n">{t("hours.col.hours")}</th>
                <th>{t("hours.col.norm")}</th>
                <th>{t("hours.col.costed")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h, i) => (
                <tr key={i}>
                  <td>{h.operation}</td>
                  <td className="small">{h.category}</td>
                  <td className="n">{h.quantity_id ? <Val id={h.quantity_id} /> : ""}</td>
                  <td className="n"><Val id={h.hours_id} unit={false} /></td>
                  <td className="small muted">{h.norm}{h.kn.length ? <span className="faint"> · {h.kn.slice(0, 2).join(", ")}{h.kn.length > 2 ? "…" : ""}</span> : null}</td>
                  <td className="small">{h.costed_in}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ 4 painting */
export function PaintTab() {
  const { res } = useReport();
  const pt = res.paint_totals;
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title={t("paint.title")} pad={false}>
        <div className="table-wrap">
          <table className="t compact">
            <thead>
              <tr>
                <th>{t("paint.col.category")}</th>
                <th>{t("paint.col.system")}</th>
                <th className="n">{t("paint.col.area")}</th>
                <th className="n">{t("paint.col.coats")}</th>
                <th>{t("paint.col.litres")}</th>
                <th className="n">{t("paint.col.hours")}</th>
                <th className="n">{t("paint.col.cost")}</th>
              </tr>
            </thead>
            <tbody>
              {res.paint.map((p, i) => (
                <tr key={i}>
                  <td>{p.category}</td>
                  <td><span className="chip plain">{p.system}</span></td>
                  <td className="n"><Val id={p.area_id} unit={false} /></td>
                  <td className="n">{p.coats || t("common.none")}</td>
                  <td className="small">
                    {p.litres.length ? p.litres.map((l) => (
                      <div key={l.value_id}>{l.product}: <Val id={l.value_id} /></div>
                    )) : <span className="muted">{t("paint.galvanised")}</span>}
                  </td>
                  <td className="n"><Val id={p.hours_id} unit={false} /></td>
                  <td className="n"><Val id={p.cost_id} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <div className="grid2">
        <Card title={t("paint.by_product")} pad={false}>
          <table className="t compact">
            <tbody>
              {Object.entries(pt.by_product).map(([prod, id]) => (
                <tr key={prod}><td>{prod}</td><td className="n"><Val id={id} /></td></tr>
              ))}
              <tr className="total"><td>{t("hours.total")}</td><td className="n"><Val id={pt.litres} /></td></tr>
            </tbody>
          </table>
        </Card>
        <Card title={t("paint.totals")} pad={false}>
          <table className="t compact">
            <tbody>
              <tr><td>{res.values[pt.area]?.label}</td><td className="n"><Val id={pt.area} /></td></tr>
              <tr><td>{res.values[pt.cost]?.label}</td><td className="n"><Val id={pt.cost} /></td></tr>
              {pt.galv_cost && <tr><td>{res.values[pt.galv_cost]?.label}</td><td className="n"><Val id={pt.galv_cost} /></td></tr>}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ 5 cost */
export function CostTab() {
  const { res } = useReport();
  const c = res.cost;
  const v = res.values;
  const phases: (string | null | undefined)[] = [];
  res.offer_lines.forEach((o) => { if (!phases.includes(o.phase)) phases.push(o.phase); });
  const steelKg = res.offer_lines.reduce((a, o) => a + (o.kg ?? 0), 0);
  let n = 0;
  // pivot cost lines: category × group
  const groups = Object.keys(c.groups ?? {});
  const byCat: Record<string, Record<string, string>> = {};
  for (const l of (c.lines ?? []) as { group: string; category: string; value_id: string }[]) {
    (byCat[l.category] ??= {})[l.group] = l.value_id;
  }
  const params = (c.params ?? {}) as Record<string, string>;
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title={t("cost.offer")} pad={false}>
        <table className="t compact">
          <thead>
            <tr>
              <th style={{ width: 50 }}>No.</th>
              <th>{t("cost.col.item")}</th>
              <th>{t("cost.col.surface")}</th>
              <th className="n">{t("cost.col.qty")}</th>
              <th>{t("cost.col.unit")}</th>
              <th className="n">{t("cost.col.price")}</th>
              <th className="n">{t("cost.col.unit_price")}</th>
            </tr>
          </thead>
          <tbody>
            <tr className="total"><td>1.</td><td>Steel structures manufacturing</td><td /><td className="n">{num(steelKg, 0)}</td><td>kg</td><td className="n"><Val id={c.steel_sale} /></td><td /></tr>
            {phases.map((ph) => (
              <PhaseRows key={String(ph)} ph={ph} start={() => ++n} />
            ))}
            {(c.extras ?? []).map((x: { key: string; label: string; qty?: number; qty_id?: string; unit: string; sale_id: string }, i: number) => (
              <tr key={x.key} className="total">
                <td>{i + 2}.</td><td>{x.label}</td><td />
                <td className="n">{x.qty_id ? <Val id={x.qty_id} unit={false} /> : num(x.qty ?? 1)}</td><td>{x.unit}</td>
                <td className="n"><Val id={x.sale_id} /></td><td />
              </tr>
            ))}
            <tr className="total">
              <td>{(c.extras ?? []).length + 2}.</td>
              <td>{t("cost.transport")}: <span className="small muted">{(c.transport_info?.desc ?? []).join("; ")}</span></td>
              <td /><td className="n">1</td><td>set</td><td className="n"><Val id={c.transport} /></td><td />
            </tr>
            <tr className="total" style={{ fontSize: 15 }}>
              <td /><td>{t("cost.total")}</td><td /><td /><td /><td className="n"><Val id={c.price} /></td><td />
            </tr>
            <tr className="sub"><td /><td>{t("cost.range")}</td><td /><td /><td /><td className="n">{eur(v[c.low]?.value)} – {eur(v[c.high]?.value)}</td><td /></tr>
          </tbody>
        </table>
      </Card>

      <div className="grid2">
        <Card title={t("cost.groups")} pad={false}>
          <table className="t compact">
            <tbody>
              {Object.entries(c.groups ?? {}).map(([g, id]) => (
                <tr key={g}><td>{g}</td><td className="n"><Val id={id as string} /></td></tr>
              ))}
              <tr><td>{t("cost.margin")}</td><td className="n"><Val id={c.margin} /></td></tr>
              <tr className="total"><td>{v[c.steel_sale]?.label}</td><td className="n"><Val id={c.steel_sale} /></td></tr>
              {(c.extras ?? []).map((x: { key: string; label: string; sale_id: string }) => (
                <tr key={x.key}><td>{x.label}</td><td className="n"><Val id={x.sale_id} /></td></tr>
              ))}
              <tr><td>{t("cost.transport")}</td><td className="n"><Val id={c.transport} /></td></tr>
              <tr className="total"><td>{t("cost.total")}</td><td className="n"><Val id={c.price} /></td></tr>
            </tbody>
          </table>
        </Card>
        <Card title={t("cost.params")} pad={false}>
          <table className="t compact">
            <tbody>
              {Object.entries(params).map(([k, id]) => v[id] && (
                <tr key={k}><td>{v[id].label}</td><td className="n"><Val id={id} /></td></tr>
              ))}
              <tr><td>{res.material.waste_share && v[res.material.waste_share]?.label}</td><td className="n"><Val id={res.material.waste_share} /></td></tr>
              <tr><td>{v[res.material.bought_kg]?.label}</td><td className="n"><Val id={res.material.bought_kg} /></td></tr>
            </tbody>
          </table>
          <div className="tiny muted" style={{ padding: "6px 12px 10px" }}>{res.material.remnant_note}</div>
        </Card>
      </div>

      <Card title={t("cost.by_category")} pad={false}>
        <div className="table-wrap">
          <table className="t compact">
            <thead>
              <tr>
                <th>{t("takeoff.col.category")}</th>
                {groups.map((g) => <th key={g} className="n">{g}</th>)}
              </tr>
            </thead>
            <tbody>
              {Object.entries(byCat).map(([cat, m]) => (
                <tr key={cat}>
                  <td>{cat}</td>
                  {groups.map((g) => <td key={g} className="n">{m[g] ? <Val id={m[g]} /> : ""}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title={t("cost.methods")} pad={false}>
        <table className="t compact">
          <thead>
            <tr><th>{t("takeoff.col.category")}</th><th className="n">{t("cost.col.eur_t")}</th><th className="n">{t("cost.col.price")}</th><th className="n">{t("hours.col.hours")}</th><th>{t("cost.col.ref")}</th></tr>
          </thead>
          <tbody>
            {(c.quick_lines ?? []).map((q: { category: string; eur_t_id: string; sale_id: string; hours_id: string; ref_project: string; kn: string }) => (
              <tr key={q.category}>
                <td>{q.category}</td>
                <td className="n"><Val id={q.eur_t_id} unit={false} /></td>
                <td className="n"><Val id={q.sale_id} /></td>
                <td className="n"><Val id={q.hours_id} unit={false} /></td>
                <td className="small muted">{q.ref_project} ({q.kn})</td>
              </tr>
            ))}
            <tr className="total"><td>{t("cost.quick")}</td><td /><td className="n"><Val id={c.quick} /></td><td /><td /></tr>
            <tr className="total"><td>{t("cost.detailed")}</td><td /><td className="n"><Val id={c.detailed} /></td><td /><td /></tr>
            <tr className="total"><td>{t("cost.gap")}</td><td /><td className="n"><Val id={c.gap} /></td><td /><td /></tr>
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function PhaseRows({ ph, start }: { ph: string | null | undefined; start: () => number }) {
  const { res } = useReport();
  const rows = res.offer_lines.filter((o) => o.phase === ph);
  return (
    <>
      {ph && <tr className="sub"><td /><td colSpan={6}><b>Phase {ph}</b></td></tr>}
      {rows.map((o) => {
        const k = start();
        return (
          <tr key={o.price_id}>
            <td className="small muted">1.{k}</td>
            <td>{o.label}</td>
            <td><span className="chip plain">{o.surface}</span></td>
            <td className="n">{o.qty_id ? <Val id={o.qty_id} unit={false} /> : num(o.kg)}</td>
            <td>{o.unit}</td>
            <td className="n"><Val id={o.price_id} /></td>
            <td className="n">{num(o.unit_price, 2)}</td>
          </tr>
        );
      })}
    </>
  );
}

/* ------------------------------------------------------------------ 6 carbon */
export function CarbonTab() {
  const { res } = useReport();
  const cb = res.carbon;
  const parts: [string, string][] = [["Steel", cb.steel_id], ["Paint", cb.paint_id], ["Galvanising", cb.galv_id], ["Transport", cb.transport_id], ["Workshop", cb.workshop_id]];
  return (
    <div className="col" style={{ gap: 16 }}>
      {cb.placeholder && <div className="notice warn small">{t("carbon.placeholder")}</div>}
      <Card title={t("carbon.groups")} pad={false}>
        <table className="t compact">
          <thead>
            <tr>
              <th>{t("carbon.col.group")}</th><th className="n">{t("carbon.col.tonnes")}</th><th className="n">{t("carbon.col.eaf")}</th>
              <th className="n">{t("carbon.col.required")}</th><th className="n">{t("carbon.col.planned")}</th><th className="n">{t("carbon.col.co2")}</th>
            </tr>
          </thead>
          <tbody>
            {(cb.groups ?? []).map((g: { group: string; label: string; tonnes: number; share_id: string; co2_id: string; required: number | null; recycled_planned: number; compliant: boolean | null }) => (
              <tr key={g.group}>
                <td>{g.label}</td>
                <td className="n">{num(g.tonnes, 1)}</td>
                <td className="n"><Val id={g.share_id} /></td>
                <td className="n">{g.required != null ? pct(g.required) : t("common.none")}</td>
                <td className="n">{pct(g.recycled_planned)}{g.compliant === false && <span className="sev high" style={{ marginLeft: 6 }}>{t("carbon.not_met")}</span>}</td>
                <td className="n"><Val id={g.co2_id} unit={false} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="grid2">
        <Card title={t("carbon.parts")} pad={false}>
          <table className="t compact">
            <tbody>
              {parts.filter(([, id]) => id).map(([l, id]) => <tr key={l}><td>{l}</td><td className="n"><Val id={id} /></td></tr>)}
              <tr className="total"><td>{t("carbon.total")}</td><td className="n"><Val id={cb.total_id} /></td></tr>
              <tr className="sub"><td>{t("carbon.intensity")}</td><td className="n"><Val id={cb.intensity_id} /></td></tr>
            </tbody>
          </table>
        </Card>
        <Card title={t("carbon.options")} pad={false}>
          <table className="t compact">
            <tbody>
              {(cb.options ?? []).map((o: { label: string; delta_id: string }) => (
                <tr key={o.delta_id}><td>{o.label}</td><td className="n"><Val id={o.delta_id} /></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <Card title={t("carbon.flags")} pad={false}>
        <table className="t compact">
          <tbody>
            {(cb.flags ?? []).map((f: { flag: string; detail: string; reference: string; severity: string }, i: number) => (
              <tr key={i}>
                <td style={{ width: 90 }}><span className={`sev ${f.severity}`}>{t(`risks.sev.${f.severity}`)}</span></td>
                <td><b>{f.flag}</b><div className="small">{f.detail}</div></td>
                <td className="small muted" style={{ width: "30%" }}>{f.reference}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ 7 risks */
export function RisksTab() {
  const ctx = useReport();
  const { res } = ctx;
  const preds = Object.values(res.values).filter((v) => v.type === "predicted");
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title={t("risks.title")} pad={false}>
        <table className="t">
          <thead>
            <tr><th style={{ width: 30 }}>#</th><th style={{ width: 80 }}>{t("risks.col.severity")}</th><th>{t("risks.col.risk")}</th><th style={{ width: "30%" }}>{t("risks.col.question")}</th></tr>
          </thead>
          <tbody>
            {res.risks.map((r) => (
              <tr key={r.id}>
                <td>{r.rank}</td>
                <td><span className={`sev ${r.severity}`}>{t(`risks.sev.${r.severity}`)}</span><div className="tiny muted">{r.kind}</div></td>
                <td>
                  <b>{r.title}</b>
                  <div className="small">{r.detail}</div>
                  <div className="row wrap" style={{ gap: 10, marginTop: 4 }}>
                    {r.value_ids.slice(0, 4).map((vid) => res.values[vid] && (
                      <button key={vid} className="reflink" onClick={() => ctx.open(vid)}>{res.values[vid].label}</button>
                    ))}
                    <RefLinks refs={r.refs} title={r.title} />
                  </div>
                </td>
                <td className="small">{r.question}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="grid2">
        <Card title={t("risks.questions")}>
          <ol style={{ margin: 0, paddingLeft: 18 }}>
            {res.questions.map((q) => <li key={q.id} style={{ marginBottom: 6 }}>{q.text} <span className="small muted">— {q.reason}</span></li>)}
          </ol>
        </Card>
        <Card title={t("risks.assumptions")}>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {res.assumptions.filter((a) => a.kind !== "predicted" && a.text).map((a, i) => (
              <li key={i} className="small" style={{ marginBottom: 4 }}>
                <span className="chip plain" style={{ marginRight: 6 }}>{a.kind}</span>{a.text}
                {a.value_id && res.values[a.value_id] && <> <button className="reflink" onClick={() => ctx.open(a.value_id!)}>→</button></>}
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <Card title={`${t("risks.predicted")} (${preds.length})`} pad={false}>
        <div className="table-wrap tall">
          <table className="t compact">
            <thead>
              <tr><th>{t("risks.col.value")}</th><th className="n">{t("hours.col.quantity")}</th><th className="n">{t("risks.col.confidence")}</th><th>{t("risks.col.reasoning")}</th></tr>
            </thead>
            <tbody>
              {preds.map((p) => (
                <tr key={p.id}>
                  <td>{p.label}</td>
                  <td className="n"><Val id={p.id} /></td>
                  <td className="n">{pct(p.confidence)}</td>
                  <td className="small">{p.reasoning}{p.question && <div className="muted">? {p.question}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ 8 file map */
function fileRef(e: FileEntry): Ref {
  const base: Ref = { kind: "text", file_id: e.id, path: e.path, guids: [], bboxes: [], label: e.name };
  if (e.kind === "pdf") return { ...base, kind: "pdf_page", page: 1, label: `${e.name} · page 1` };
  if (e.kind === "bom" || e.kind === "sheet") return { ...base, kind: "sheet_cell", row: 1, label: e.name };
  if (e.kind === "email") return { ...base, kind: "email" };
  if (e.kind === "ifc") return { ...base, kind: "ifc_elements" };
  if (e.kind === "image") return { ...base, kind: "image" };
  return base;
}
const VIEWABLE = new Set(["pdf", "bom", "sheet", "email", "ifc", "image", "text"]);
const STATUSES = ["metal-relevant", "partly-relevant", "not-relevant", "duplicate"];

export function FilesTab() {
  const ctx = useReport();
  const fm = ctx.res.filemap;
  const byId = Object.fromEntries(fm.entries.map((e) => [e.id, e]));
  return (
    <Card title={t("files.title")} pad={false}
      right={<span className="small muted">{Object.entries(fm.counts).map(([k, n]) => `${n} ${t(`files.status.${k}`).toLowerCase()}`).join(" · ")} · {bytes(fm.total_size)}</span>}>
      <div className="card-body small muted" style={{ paddingBottom: 0 }}>{t("files.subtitle")}</div>
      <div className="card-body small"><b>{fm.level_reason}</b></div>
      <div className="table-wrap">
        <table className="t compact">
          <thead>
            <tr>
              <th>{t("files.col.file")}</th><th>{t("files.col.type")}</th><th className="n">{t("files.col.size")}</th>
              <th>{t("files.col.status")}</th><th>{t("files.col.why")}</th><th>{t("files.col.read")}</th>
            </tr>
          </thead>
          <tbody>
            {fm.entries.map((e) => {
              const pend = ctx.pendingByKey[`file:${e.id}:status`];
              const child = !!e.parent_id;
              return (
                <tr key={e.id} className={e.status === "duplicate" || e.status === "not-relevant" ? "sub" : ""}>
                  <td style={{ paddingLeft: child ? 26 : undefined, wordBreak: "break-all" }}>
                    {VIEWABLE.has(e.kind) && e.status !== "unreadable" ? (
                      <button className="reflink" style={{ fontSize: 13 }} onClick={() => ctx.openRefs(e.name, [fileRef(e)])}>{child ? "↳ " : ""}{e.name}</button>
                    ) : (
                      <span>{child ? "↳ " : ""}{e.name}</span>
                    )}
                    {!child && e.path !== e.name && <div className="tiny faint">{e.path}</div>}
                    {e.date && <div className="tiny faint">{date(e.date)}</div>}
                  </td>
                  <td className="small">{e.kind}{e.pages ? ` · ${e.pages} p.` : ""}{e.elements ? ` · ${num(e.elements)} el.` : ""}</td>
                  <td className="n small">{bytes(e.size)}</td>
                  <td>
                    {ctx.isLatest && e.status !== "unreadable" ? (
                      <select className="inline" value={String(pend?.value ?? e.status)} aria-label={`${e.name} ${t("files.col.status")}`}
                        onChange={(ev) => ctx.addEdit(`file:${e.id}:status`, ev.target.value, `${e.name} — file status`, e.status)}>
                        {[...new Set([e.status, ...STATUSES])].map((s) => <option key={s} value={s}>{t(`files.status.${s}`)}</option>)}
                      </select>
                    ) : (
                      <span className="small">{t(`files.status.${e.status}`)}</span>
                    )}
                    {pend && <div className="tiny" style={{ color: "var(--navy)" }}>{t("files.pending")}</div>}
                    <div className="tiny faint">{e.decided_by}</div>
                  </td>
                  <td className="small">
                    {e.reason}
                    {e.duplicate_of && byId[e.duplicate_of] && <span className="muted"> ({byId[e.duplicate_of].name})</span>}
                    {e.error && <div style={{ color: "var(--bad)" }}>{e.error}</div>}
                    {e.notes.length > 0 && <div className="tiny muted">{e.notes.join(" · ")}</div>}
                    {e.used_for.length > 0 && <div className="tiny" style={{ color: "var(--t-calculated)" }}>{e.used_for.join(", ")}</div>}
                  </td>
                  <td className="small nowrap">{e.read_by ?? ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ revisions */
export function RevisionsTab() {
  const ctx = useReport();
  const { res, project } = ctx;
  const revs = [...(project?.revisions ?? [])].sort((a, b) => b.rev - a.rev);
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title={t("rev.changes", { name: res.report_name })} pad={false}>
        {res.changes.length === 0 ? (
          <div className="card-body muted">{t("rev.no_changes")}</div>
        ) : (
          <table className="t compact">
            <thead><tr><th>{t("rev.col.change")}</th><th className="n">{t("rev.col.before")}</th><th className="n">{t("rev.col.after")}</th><th>{t("rev.col.why")}</th></tr></thead>
            <tbody>
              {res.changes.map((c, i) => (
                <tr key={i} className={c.kind === "correction" ? "" : "sub"}>
                  <td>{c.value_id && res.values[c.value_id] ? <button className="reflink" style={{ fontSize: 13 }} onClick={() => ctx.open(c.value_id!)}>{c.label}</button> : c.label}</td>
                  <td className="n">{fmtRaw(c.before, c.unit)}{c.unit && typeof c.before === "number" && c.unit !== "€" ? ` ${c.unit}` : ""}</td>
                  <td className="n"><b>{fmtRaw(c.after, c.unit)}{c.unit && typeof c.after === "number" && c.unit !== "€" ? ` ${c.unit}` : ""}</b></td>
                  <td className="small muted">{c.reason ?? ""}{c.source ? <span className="chip plain" style={{ marginLeft: 6 }}>{t(`review.source.${c.source}`)}</span> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title={t("rev.history")} pad={false}>
        <table className="t compact">
          <tbody>
            {revs.map((r) => (
              <tr key={r.rev}>
                <td><a href={href({ page: "report", pid: ctx.pid, rev: r.rev, tab: "revisions" })}><b>{r.report_name}</b></a>{r.rev === ctx.rev && <span className="chip plain" style={{ marginLeft: 6 }}>open</span>}</td>
                <td>{date(r.created_at)}</td>
                <td className="n">{eur(r.price)}</td>
                <td className="n">{r.changes ? `${r.changes} changes` : ""}</td>
                <td className="small muted">{r.kind}</td>
                <td><StatusBadge status={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
