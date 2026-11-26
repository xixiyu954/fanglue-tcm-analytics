"""方略 · 中药方剂配伍与网络药理学分析平台 — 云端/本地统一入口。

运行：streamlit run streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

st.set_page_config(
    page_title="方略 · 中药方剂与网络药理学分析平台",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.db import ensure_database
from core.ui import inject_styles

ensure_database()
inject_styles()

pg = st.navigation({
    "平台总览": [
        st.Page("app/views/home.py", title="数据总览与质量报告", icon="🌿", default=True),
    ],
    "方剂数据挖掘": [
        st.Page("app/views/formula_check.py", title="方剂体检", icon="🩺"),
        st.Page("app/views/pattern_mining.py", title="配伍规律挖掘", icon="🔗"),
        st.Page("app/views/clustering.py", title="方剂聚类", icon="🧩"),
        st.Page("app/views/dynasty_evolution.py", title="古方朝代演变", icon="🏯"),
    ],
    "分子机制分析": [
        st.Page("app/views/network_pharmacology.py", title="网络药理学", icon="🧬"),
    ],
    "工程与产品分析": [
        st.Page("app/views/miniprogram_growth.py", title="小程序增长与 A/B 实验", icon="📱"),
        st.Page("app/views/sql_lab.py", title="SQL 实验室", icon="🧪"),
        st.Page("app/views/user_behavior.py", title="Web 行为分析", icon="📈"),
    ],
})
pg.run()
