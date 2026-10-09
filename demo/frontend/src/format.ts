import type { V } from "./types";
import { t } from "./i18n";

let NF = { thousands: " ", decimal: "," };

export function setNumberFormat(nf: { thousands: string; decimal: string }): void {
  NF = { thousands: nf.thousands ?? " ", decimal: nf.decimal ?? "," };
}

/** Number with Maru's separators (1 234 567,89). */
export function num(v: unknown, dec = 0): string {
  if (v === null || v === undefined || v === "") return t("common.none");
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return String(v);
  const neg = n < 0;
  const fixed = Math.abs(n).toFixed(dec);
  const [int, frac] = fixed.split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, NF.thousands);
  return (neg ? "−" : "") + grouped + (frac ? NF.decimal + frac : "");
}

export function eur(v: unknown, dec = 0): string {
  if (v === null || v === undefined) return t("common.none");
  return `€ ${num(v, dec)}`;
}

export function pct(v: unknown, dec = 0): string {
  if (typeof v !== "number") return t("common.none");
  return `${num(v * 100, dec)} %`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${num(n / 1024, 0)} KB`;
  return `${num(n / 1024 / 1024, 1)} MB`;
}

export function date(s?: string | null): string {
  if (!s) return t("common.none");
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const p = (x: number) => String(x).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Sensible decimals per unit. */
export function decimalsFor(unit?: string | null, value?: number): number {
  const a = Math.abs(value ?? 0);
  switch (unit) {
    case "€":
    case "EUR":
      return a >= 100 ? 0 : 2;
    case "€/kg":
    case "€/h":
    case "€/l":
    case "€/m²":
      return 2;
    case "kg":
      return a >= 100 ? 0 : 1;
    case "t":
    case "t CO2e":
    case "h":
    case "m²":
    case "m":
      return 1;
    case "t CO2e/t":
      return 2;
    case "l":
    case "pcs":
    case "trucks":
      return 0;
    default:
      return Number.isInteger(value) ? 0 : a >= 100 ? 0 : 2;
  }
}

export function fmtRaw(value: unknown, unit?: string | null): string {
  if (value === null || value === undefined || value === "") return t("common.none");
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
  if (typeof value === "number") {
    if (unit === "share" || unit === "%") return pct(value, value < 0.1 ? 1 : 0);
    const d = decimalsFor(unit, value);
    if (unit === "€") return eur(value, d);
    return num(value, d);
  }
  if (typeof value === "string" && /^-?\d+\.\d+$/.test(value.trim())) {
    // decimal numbers typed or proposed as text ("1.08") use the same separators; codes like "30480" stay as they are
    return num(Number(value), Math.min(3, value.trim().split(".")[1].length));
  }
  if (value === "true") return t("common.yes");
  if (value === "false") return t("common.no");
  return String(value);
}

/** Value with its unit, e.g. "1 234 kg". */
export function fmtV(v?: V | null, withUnit = true): string {
  if (!v) return t("common.none");
  const s = fmtRaw(v.value, v.unit);
  if (!withUnit || !v.unit || typeof v.value !== "number" || v.unit === "€" || v.unit === "share" || v.unit === "%") return s;
  return `${s} ${v.unit}`;
}
