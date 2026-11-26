"""匿名埋点：记录用户行为事件，用于后续漏斗 / 留存分析。"""
from __future__ import annotations

import json
import uuid

import streamlit as st

from core.db import connect


def session_id() -> str:
    if "sid" not in st.session_state:
        st.session_state.sid = uuid.uuid4().hex[:12]
    return st.session_state.sid


def log_event(page: str, event: str, detail: dict | None = None) -> None:
    try:
        with connect() as con:
            con.execute(
                "INSERT INTO events(session_id, page, event, detail) VALUES (?,?,?,?)",
                (session_id(), page, event, json.dumps(detail or {}, ensure_ascii=False)),
            )
    except Exception:  # 埋点失败不影响主流程
        pass


def track_page_view(page: str) -> None:
    """同一会话内每个页面只记录一次 page_view。"""
    key = f"_viewed_{page}"
    if not st.session_state.get(key):
        st.session_state[key] = True
        log_event(page, "page_view")
