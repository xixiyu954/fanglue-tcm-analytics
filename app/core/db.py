"""数据库访问层（支持云端部署启动时自动从 data/raw/ 建库）。"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "fanglue.db"
SQL_DIR = ROOT / "sql"
REQUIRED_TABLES = {"herb", "formula", "formula_herb", "np_compound", "np_herb_compound", "np_compound_target"}


def ensure_database() -> None:
    """若数据库不存在或缺少升级后的表，自动运行 ETL 建库（耗时约 4 秒）。"""
    need_build = not DB_PATH.exists()
    if not need_build:
        try:
            with sqlite3.connect(DB_PATH) as con:
                existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES.issubset(existing):
                need_build = True
        except Exception:
            need_build = True
    if need_build:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from etl.build_db import build_database

        with st.spinner("首次启动正在构建中药数据库（约 4 秒）…"):
            build_database(DB_PATH, verbose=False)


def connect() -> sqlite3.Connection:
    ensure_database()
    return sqlite3.connect(DB_PATH)


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """实时查询（不缓存），用于事件表或动态参数查询。"""
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)


@st.cache_data(show_spinner=False)
def query_cached(sql: str, params: tuple = ()) -> pd.DataFrame:
    """静态业务表查询（带缓存）。"""
    return query(sql, params)


def run_readonly(sql: str) -> pd.DataFrame:
    """SQL 实验室：只允许 SELECT / WITH 查询，且以只读模式打开数据库。"""
    ensure_database()
    cleaned = re.sub(r"^\s*(?:--[^\n]*\n|/\*.*?\*/\s*)+", "", sql, flags=re.S).strip()
    head = cleaned.lstrip("(").split(None, 1)[0].upper() if cleaned else ""
    if head not in {"SELECT", "WITH"}:
        raise ValueError("仅允许 SELECT / WITH 只读查询")
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        return pd.read_sql_query(sql, con)


def load_sql_file(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


@st.cache_data(show_spinner=False)
def tables() -> dict[str, pd.DataFrame]:
    return {
        "herb": query("SELECT * FROM herb"),
        "formula": query("SELECT * FROM formula ORDER BY formula_type, dynasty_order, formula"),
        "formula_herb": query("SELECT * FROM formula_herb"),
        "alias": query("SELECT * FROM alias"),
        "incompat": query("SELECT * FROM incompat_pair"),
        "quality": query("SELECT * FROM data_quality"),
        "flavor": query("SELECT * FROM herb_flavor"),
        "meridian": query("SELECT * FROM herb_meridian"),
    }


@st.cache_data(show_spinner=False)
def formula_herb_sets() -> dict[str, frozenset[str]]:
    """缓存每首方剂的药材集合，加速全库 4,500+ 方剂相似度检索。"""
    fh = tables()["formula_herb"]
    return {name: frozenset(s) for name, s in fh.groupby("formula")["herb"]}
