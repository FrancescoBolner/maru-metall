// UI text lives in translation files (one JSON per language). Add e.g. et.json and list it in
// config/companies/maru.json → "languages" to offer Estonian.
import en from "./en.json";

type Dict = Record<string, string>;
const dictionaries: Record<string, Dict> = { en };
let current: Dict = en;

export function setLanguage(lang: string): void {
  current = dictionaries[lang] ?? en;
}

export function t(key: string, vars?: Record<string, string | number>): string {
  let s = current[key] ?? en[key as keyof typeof en] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  }
  return s;
}

/** Plural helper: uses "<key>_one" when n === 1. */
export function tn(key: string, n: number, vars?: Record<string, string | number>): string {
  const k = n === 1 && current[`${key}_one`] ? `${key}_one` : key;
  return t(k, { n, ...(vars ?? {}) });
}
