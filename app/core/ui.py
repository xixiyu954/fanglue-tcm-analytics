"""全站统一视觉规范（草本墨绿风）：主题配色、Plotly 图表美化、指标卡、结论卡。"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

SAGE = "#2e7d5b"
SAGE_LIGHT = "#6ba88a"
TEAL = "#3a7d8c"
AMBER = "#c98a2e"
TERRA = "#c05a3c"
SLATE = "#526973"
INK = "#1f2a24"

# 9 色柔和草本定性色板（避免默认亮蓝/刺眼大红，且 9 类互不撞色）
HERBAL_QUAL = [
    "#2e7d5b",  # 黛绿
    "#3d7a8a",  # 靛青
    "#c98a2e",  # 姜黄
    "#c05a3c",  # 丹砂
    "#6b7b4c",  # 苔青
    "#7c628c",  # 紫苏
    "#5c8a72",  # 竹青
    "#b06c49",  # 桂皮
    "#8b958e",  # 烟灰（其他）
]

FONT_FAMILY = '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif'


def inject_styles() -> None:
    st.markdown(
        """
<style>
/* 主容器顶部留白适度收紧，标题更利落 */
.block-container {
    padding-top: 1.8rem;
    padding-bottom: 2.5rem;
}
h1 {
    font-size: 1.85rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em;
    margin-bottom: 0.2rem !important;
}
h2 {
    font-size: 1.28rem !important;
    font-weight: 650 !important;
    margin-top: 1.4rem !important;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid rgba(46, 125, 91, 0.14);
}
h3 {
    font-size: 1.08rem !important;
    font-weight: 600 !important;
}

/* 等高功能导览卡片网格 */
.nav-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin: 0.6rem 0 1.2rem 0;
}
@media (max-width: 960px) {
    .nav-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
    .nav-grid { grid-template-columns: 1fr; }
}
.nav-card {
    background: #f3f6f0;
    border: 1px solid rgba(46, 125, 91, 0.16);
    border-left: 3.5px solid #2e7d5b;
    border-radius: 10px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    height: 100%;
}
.nav-card-title {
    font-weight: 650;
    font-size: 0.98rem;
    color: #1f2a24;
    margin-bottom: 6px;
}
.nav-card-desc {
    font-size: 0.85rem;
    line-height: 1.5;
    color: #42524a;
}

/* 分析结论洞察卡 */
.insight-box {
    background: #eef4ee;
    border-left: 4px solid #2e7d5b;
    border-radius: 0 8px 8px 0;
    padding: 11px 15px;
    margin: 0.6rem 0 1rem 0;
    font-size: 0.92rem;
    line-height: 1.6;
    color: #1f2a24;
}

/* Metric 卡片精修：防副文本被过度截断 */
[data-testid="stMetric"] {
    background: #ffffff;
    border-radius: 10px !important;
    padding: 12px 14px !important;
}
[data-testid="stMetricDelta"] {
    font-size: 0.80rem !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(container, label: str, value, sub: str | None = None, help: str | None = None) -> None:
    """统一边框指标卡：关闭默认上升箭头，避免静态说明误导。"""
    container.metric(
        label=label,
        value=value,
        delta=sub,
        delta_color="off",
        delta_arrow="off",
        border=True,
        help=help,
    )


def insight_box(html_or_text: str) -> None:
    st.markdown(f'<div class="insight-box">{html_or_text}</div>', unsafe_allow_html=True)


def shorten(text: str, limit: int = 32) -> str:
    s = str(text).strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def style_fig(fig: go.Figure, *, height: int | None = None, margin: dict | None = None) -> go.Figure:
    """应用统一草本纸张背景、网格线与字体。"""
    layout: dict = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(255,255,255,0.65)",
        "font": {"family": FONT_FAMILY, "color": INK, "size": 12},
        "title_font": {"family": FONT_FAMILY, "color": INK, "size": 14},
        "hoverlabel": {"font": {"family": FONT_FAMILY, "size": 12}},
    }
    if height is not None:
        layout["height"] = height
    if margin is not None:
        layout["margin"] = margin
    fig.update_layout(**layout)
    fig.update_xaxes(gridcolor="rgba(31,42,36,0.07)", zerolinecolor="rgba(31,42,36,0.15)")
    fig.update_yaxes(gridcolor="rgba(31,42,36,0.07)", zerolinecolor="rgba(31,42,36,0.15)")
    return fig
