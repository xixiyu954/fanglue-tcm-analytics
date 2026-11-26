"""将小程序导出（或微信云开发导出的）JSON 日志导入 data/fanglue.db 的星型分析表：
  - mp_user        (dim_user)
  - mp_quiz_log    (fact_quiz_log)
  - mp_event       (fact_event)
  - mp_share       (fact_share)

运行：python etl/import_miniprogram_logs.py path/to/export.json
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "fanglue.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mp_user (
    user_hash     TEXT PRIMARY KEY,
    register_date TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    channel_scene TEXT NOT NULL,
    inviter_hash  TEXT DEFAULT '',
    exp_group     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mp_quiz_log (
    log_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_hash          TEXT NOT NULL,
    ts                 TEXT NOT NULL,
    exp_group          TEXT NOT NULL,
    formula            TEXT NOT NULL,
    category           TEXT DEFAULT '',
    q_type             TEXT NOT NULL,
    chosen             TEXT DEFAULT '',
    distractor_max_sim REAL DEFAULT 0,
    is_correct         INTEGER NOT NULL,
    duration_ms        INTEGER DEFAULT 0,
    is_review          INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mp_event (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_hash   TEXT NOT NULL,
    session_id  TEXT DEFAULT '',
    ts          TEXT NOT NULL,
    page        TEXT DEFAULT '',
    event       TEXT NOT NULL,
    exp_group   TEXT DEFAULT '',
    params_json TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS mp_share (
    share_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    inviter_hash TEXT NOT NULL,
    invitee_hash TEXT NOT NULL,
    card_type    TEXT DEFAULT 'formula_card',
    ts           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mpq_user ON mp_quiz_log(user_hash);
CREATE INDEX IF NOT EXISTS idx_mpq_exp  ON mp_quiz_log(exp_group);
CREATE INDEX IF NOT EXISTS idx_mpe_user ON mp_event(user_hash);
"""


def ensure_mp_tables(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)


def import_bundle(bundle: dict, db_path: Path = DB_PATH) -> dict[str, int]:
    counts = {"mp_user": 0, "mp_quiz_log": 0, "mp_event": 0, "mp_share": 0}
    with sqlite3.connect(db_path) as con:
        ensure_mp_tables(con)
        for u in bundle.get("dim_user", []):
            con.execute(
                """INSERT OR IGNORE INTO mp_user
                   (user_hash, register_date, first_seen_at, channel_scene, inviter_hash, exp_group)
                   VALUES (?,?,?,?,?,?)""",
                (
                    u["user_hash"],
                    u.get("register_date") or str(u.get("first_seen_at", ""))[:10],
                    u.get("first_seen_at", ""),
                    str(u.get("channel_scene", "1001")),
                    u.get("inviter_hash", ""),
                    u.get("exp_group", "A_chapter"),
                ),
            )
            counts["mp_user"] += 1

        for q in bundle.get("fact_quiz_log", []):
            con.execute(
                """INSERT INTO mp_quiz_log
                   (user_hash, ts, exp_group, formula, category, q_type, chosen, distractor_max_sim, is_correct, duration_ms, is_review)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    q["user_hash"], q.get("ts", ""), q.get("exp_group", ""), q.get("formula", ""),
                    q.get("category", ""), q.get("q_type", ""), q.get("chosen", ""),
                    float(q.get("distractor_max_sim", 0) or 0), int(q.get("is_correct", 0)),
                    int(q.get("duration_ms", 0)), int(q.get("is_review", 0)),
                ),
            )
            counts["mp_quiz_log"] += 1

        for e in bundle.get("fact_event", []):
            con.execute(
                """INSERT INTO mp_event (user_hash, session_id, ts, page, event, exp_group, params_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    e["user_hash"], e.get("session_id", ""), e.get("ts", ""),
                    e.get("page", ""), e.get("event", ""), e.get("exp_group", ""),
                    e.get("params_json", "{}"),
                ),
            )
            counts["mp_event"] += 1

        for s in bundle.get("fact_share", []):
            con.execute(
                """INSERT INTO mp_share (inviter_hash, invitee_hash, card_type, ts) VALUES (?,?,?,?)""",
                (s["inviter_hash"], s["invitee_hash"], s.get("card_type", "formula_card"), s.get("ts", "")),
            )
            counts["mp_share"] += 1
    return counts


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("用法: python etl/import_miniprogram_logs.py <导出JSON路径>")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    res = import_bundle(data)
    print("导入完成:", res)
