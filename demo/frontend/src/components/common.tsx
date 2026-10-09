import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { t } from "../i18n";
import type { ValueType } from "../types";

/** Load data with loading / error state and a reload function. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): {
  data: T | undefined; error: string | undefined; loading: boolean; reload: () => void; setData: (d: T) => void;
} {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(undefined);
    fnRef.current()
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message || String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((x) => x + 1), []);
  return { data, error, loading, reload, setData };
}

export function Loading({ label }: { label?: string }) {
  return (
    <div className="state" role="status">
      <div className="row" style={{ justifyContent: "center" }}>
        <span className="spinner" /> <span>{label ?? t("common.loading")}</span>
      </div>
    </div>
  );
}

export function SkeletonRows({ n = 4 }: { n?: number }) {
  return (
    <div className="col" style={{ padding: 16 }} aria-hidden>
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="skeleton" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="errorbox" role="alert">
      <b>{t("error.title")}</b>
      <div>{message}</div>
      {onRetry && (
        <button className="btn small mt-s" onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="state">
      <h2>{title}</h2>
      {children && <div>{children}</div>}
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export function TypeChip({ type, short }: { type: ValueType; short?: boolean }) {
  const label = t(`type.${type}`);
  return (
    <span className={`chip ${type}`} title={t(`type.${type}.help`)}>
      {short ? label.slice(0, 4) + "." : label}
    </span>
  );
}

export function StatusBadge({ status }: { status: "none" | "draft" | "approved" | "running" }) {
  return <span className={`status ${status}`}>{t(`status.${status}`)}</span>;
}

export function Modal({ title, children, onClose, actions }: { title: string; children: ReactNode; onClose: () => void; actions: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        <div className="muted">{children}</div>
        <div className="actions">{actions}</div>
      </div>
    </div>
  );
}

export function Legend() {
  return (
    <div className="legend">
      <TypeChip type="extracted" />
      <TypeChip type="calculated" />
      <TypeChip type="predicted" />
      <span className="chip conflict">{t("type.conflict")}</span>
      <span className="chip edited">{t("type.edited")}</span>
    </div>
  );
}
