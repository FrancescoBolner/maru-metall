"""SQLite: projects, quote numbers, revisions, overrides (estimator edits) and written corrections."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from .settings import DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, company TEXT NOT NULL, name TEXT NOT NULL, short TEXT NOT NULL,
  quote_seq INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
  project_id TEXT NOT NULL, rev INTEGER NOT NULL, quote_number TEXT NOT NULL, report_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, approved_at TEXT, duration_s REAL, ai_cost_eur REAL,
  provider TEXT, price REAL, tonnes REAL, hours REAL, co2 REAL, level TEXT, changes INTEGER DEFAULT 0,
  result_path TEXT NOT NULL, kind TEXT DEFAULT 'run',
  PRIMARY KEY (project_id, rev)
);
CREATE TABLE IF NOT EXISTS overrides (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, target TEXT NOT NULL, key TEXT NOT NULL,
  field TEXT NOT NULL, value_json TEXT, reason TEXT, source TEXT NOT NULL, text TEXT, label TEXT, before_json TEXT,
  created_at TEXT NOT NULL, applied_in INTEGER, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS corrections (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, text TEXT NOT NULL, proposal_json TEXT,
  accepted_json TEXT, created_at TEXT NOT NULL, revision INTEGER
);
"""


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    with _lock:
        c = sqlite3.connect(DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_project(pid: str, company: str, name: str, short: str) -> dict[str, Any]:
    with conn() as c:
        r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if r is None:
            c.execute("INSERT INTO projects(id, company, name, short, quote_seq, created_at) VALUES (?,?,?,?,NULL,?)",
                      (pid, company, name, short, now()))
            r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r)


def allocate_quote_seq(pid: str) -> int:
    with conn() as c:
        r = c.execute("SELECT quote_seq FROM projects WHERE id=?", (pid,)).fetchone()
        if r and r["quote_seq"]:
            return int(r["quote_seq"])
        mx = c.execute("SELECT COALESCE(MAX(quote_seq), 0) AS m FROM projects").fetchone()["m"]
        seq = int(mx) + 1
        c.execute("UPDATE projects SET quote_seq=? WHERE id=?", (seq, pid))
        return seq


def get_project(pid: str) -> Optional[dict[str, Any]]:
    with conn() as c:
        r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


def revisions(pid: str) -> list[dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM revisions WHERE project_id=? ORDER BY rev", (pid,))]


def latest_revision(pid: str) -> Optional[dict[str, Any]]:
    with conn() as c:
        r = c.execute("SELECT * FROM revisions WHERE project_id=? ORDER BY rev DESC LIMIT 1", (pid,)).fetchone()
        return dict(r) if r else None


def next_rev(pid: str) -> int:
    with conn() as c:
        r = c.execute("SELECT COALESCE(MAX(rev), 0) AS m FROM revisions WHERE project_id=?", (pid,)).fetchone()
        return int(r["m"]) + 1


def add_revision(row: dict[str, Any]) -> None:
    cols = ",".join(row.keys())
    q = ",".join("?" for _ in row)
    with conn() as c:
        c.execute(f"INSERT OR REPLACE INTO revisions({cols}) VALUES ({q})", tuple(row.values()))


def set_status(pid: str, rev: int, status: str) -> None:
    with conn() as c:
        c.execute("UPDATE revisions SET status=?, approved_at=? WHERE project_id=? AND rev=?",
                  (status, now() if status == "approved" else None, pid, rev))


def add_override(pid: str, o: dict[str, Any]) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO overrides(project_id, target, key, field, value_json, reason, source, text, label, before_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid, o["target"], o["key"], o.get("field", "value"), json.dumps(o.get("value")), o.get("reason"),
             o.get("source", "direct_edit"), o.get("text"), o.get("label"), json.dumps(o.get("before")), now()))
        return int(cur.lastrowid)


def overrides(pid: str, active_only: bool = True) -> list[dict[str, Any]]:
    with conn() as c:
        q = "SELECT * FROM overrides WHERE project_id=?" + (" AND active=1" if active_only else "") + " ORDER BY id"
        out = []
        for r in c.execute(q, (pid,)):
            d = dict(r)
            d["value"] = json.loads(d.pop("value_json") or "null")
            d["before"] = json.loads(d.pop("before_json") or "null")
            out.append(d)
        return out


def deactivate_override(pid: str, oid: int) -> None:
    with conn() as c:
        c.execute("UPDATE overrides SET active=0 WHERE project_id=? AND id=? AND applied_in IS NULL", (pid, oid))


def mark_applied(pid: str, rev: int) -> None:
    with conn() as c:
        c.execute("UPDATE overrides SET applied_in=? WHERE project_id=? AND active=1 AND applied_in IS NULL", (rev, pid))


def add_correction(pid: str, text: str, proposal: Any) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO corrections(project_id, text, proposal_json, created_at) VALUES (?,?,?,?)",
                        (pid, text, json.dumps(proposal, ensure_ascii=False), now()))
        return int(cur.lastrowid)


def accept_correction(cid: int, accepted: Any) -> None:
    with conn() as c:
        c.execute("UPDATE corrections SET accepted_json=? WHERE id=?", (json.dumps(accepted, ensure_ascii=False), cid))


def corrections(pid: str) -> list[dict[str, Any]]:
    with conn() as c:
        out = []
        for r in c.execute("SELECT * FROM corrections WHERE project_id=? ORDER BY id", (pid,)):
            d = dict(r)
            d["proposal"] = json.loads(d.pop("proposal_json") or "null")
            d["accepted"] = json.loads(d.pop("accepted_json") or "null")
            out.append(d)
        return out
