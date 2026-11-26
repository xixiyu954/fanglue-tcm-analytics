import json
import random
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from core.db import connect, load_sql_file, query
from core.tracking import track_page_view
from core.ui import SAGE, TEAL, insight_box, metric_card, style_fig

track_page_view("用户行为")

st.title("📈 用户行为分析")
st.caption("分析问题：用户如何使用平台？哪一步流失最严重？哪些分析模块留得住人？—— 数据来自平台自身匿名埋点")

with st.sidebar:
    include_demo = st.toggle(
        "包含模拟数据", value=False,
        help="模拟数据仅用于演示分析流程，session_id 以 demo_ 开头，正式分析报告中必须排除",
    )
    if st.button("生成 60 个模拟会话"):
        rng = random.Random()
        pages = ["配伍规律", "方剂聚类", "朝代演变", "SQL实验室"]
        rows, now = [], datetime.now()
        for _ in range(60):
            sid = f"demo_{rng.randrange(16**8):08x}"
            day0 = now - timedelta(days=rng.randint(0, 13))
            for d in range(1 + (rng.random() < 0.32) + (rng.random() < 0.12)):
                ts = day0 + timedelta(days=d, minutes=rng.randint(0, 600))
                ev = [("首页", "page_view")]
                if rng.random() < 0.78:
                    tool_page = "方剂体检" if rng.random() < 0.65 else "网络药理学"
                    ev.append((tool_page, "page_view"))
                    if rng.random() < 0.72:
                        ev.append((tool_page, "formula_analyzed" if tool_page == "方剂体检" else "netpharm_run"))
                        if rng.random() < 0.38:
                            ev.append((tool_page, "report_exported"))
                ev += [(p, "page_view") for p in pages if rng.random() < 0.30]
                for j, (pg, e) in enumerate(ev):
                    rows.append((sid, (ts + timedelta(seconds=40 * j)).strftime("%Y-%m-%d %H:%M:%S"), pg, e,
                                 json.dumps({"simulated": True})))
        with connect() as con:
            con.executemany("INSERT INTO events(session_id, ts, page, event, detail) VALUES (?,?,?,?,?)", rows)
        st.success(f"已写入 {len(rows)} 条模拟事件，打开上方『包含模拟数据』开关即可查看")
    if st.button("清除模拟数据"):
        with connect() as con:
            con.execute("DELETE FROM events WHERE session_id LIKE 'demo_%'")
        st.success("已清除全部模拟会话")

ev = query("SELECT * FROM events")
if not include_demo:
    ev = ev[~ev["session_id"].str.startswith("demo_")]
if ev.empty:
    st.info("暂无埋点数据。浏览其他页面即可产生真实事件，或在左侧生成模拟数据体验漏斗与回访分析。")
    st.stop()

ev["ts"] = pd.to_datetime(ev["ts"])
c1, c2, c3, c4 = st.columns(4)
metric_card(c1, "总会话数", f"{ev['session_id'].nunique():,}")
metric_card(c2, "总埋点事件", f"{len(ev):,}")
metric_card(c3, "完成分析会话", f"{ev.loc[ev['event'].isin(['formula_analyzed', 'netpharm_run']), 'session_id'].nunique():,}")
metric_card(c4, "导出报告/CSV", f"{ev.loc[ev['event'] == 'report_exported', 'session_id'].nunique():,}")

# ---------- 转化漏斗 ----------
st.subheader("核心功能转化漏斗")
funnel_sql = load_sql_file("06_用户漏斗.sql")
if include_demo:
    funnel = query(funnel_sql)
else:
    funnel = query(funnel_sql.replace("FROM events", "FROM events WHERE session_id NOT LIKE 'demo_%'"))
funnel["上一步转化率"] = (funnel["sessions"] / funnel["sessions"].shift(1)).fillna(1)
l, r = st.columns([3, 2])
fig_f = px.funnel(funnel, x="sessions", y="step", color_discrete_sequence=[SAGE])
style_fig(fig_f, height=340, margin={"l": 10, "r": 15, "t": 20, "b": 20})
l.plotly_chart(fig_f, width="stretch")

funnel_show = funnel.rename(columns={"step": "漏斗步骤", "sessions": "会话数"}).copy()
funnel_show["上一步转化率"] = funnel_show["上一步转化率"] * 100
r.dataframe(
    funnel_show,
    hide_index=True,
    width="stretch",
    height="content",
    column_config={
        "会话数": st.column_config.NumberColumn("会话数", format="localized"),
        "上一步转化率": st.column_config.NumberColumn("上一步转化率", format="%.0f%%"),
    },
)
worst = funnel.iloc[1:].sort_values("上一步转化率").iloc[0]
insight_box(
    f"<strong>洞察：</strong>当前流失最明显的环节是 <strong>{worst['step']}</strong>（上一步转化率 {worst['上一步转化率']:.0%}），"
    "可针对性优化体验（如增加经典方一键示例、在分析页突出导出按钮）。"
)

with st.expander("查看漏斗 SQL（06_用户漏斗.sql）"):
    st.code(funnel_sql, language="sql")

# ---------- 页面偏好 & 日活 ----------
l, r = st.columns(2)
pv = (
    ev[ev["event"] == "page_view"]
    .groupby("page")["session_id"]
    .nunique()
    .sort_values()
    .rename_axis("页面")
    .reset_index(name="访问会话数")
)
fig_pv = px.bar(pv, x="访问会话数", y="页面", orientation="h", text="访问会话数", title="各页面访问会话数", color_discrete_sequence=[SAGE])
fig_pv.update_traces(textposition="outside", cliponaxis=False)
fig_pv.update_layout(yaxis={"dtick": 1, "title": ""})
style_fig(fig_pv, height=350, margin={"l": 10, "r": 30, "t": 45, "b": 30})
l.plotly_chart(fig_pv, width="stretch")

daily = ev.groupby(ev["ts"].dt.date)["session_id"].nunique().rename_axis("日期").reset_index(name="活跃会话")
fig_d = px.line(daily, x="日期", y="活跃会话", markers=True, title="每日活跃会话趋势", color_discrete_sequence=[TEAL])
style_fig(fig_d, height=350, margin={"l": 10, "r": 20, "t": 45, "b": 30})
r.plotly_chart(fig_d, width="stretch")

# ---------- 会话回访 ----------
st.subheader("会话回访分析（SQL LAG 窗口函数）")
rv = query(load_sql_file("07_会话回访.sql"))
if not include_demo:
    rv = rv[~rv["session_id"].str.startswith("demo_")]
if not rv.empty:
    st.markdown(
        f"有 **{(rv['active_days'] > 1).mean():.0%}** 的会话在不止一天内活跃，"
        f"次日回访比例 **{rv['has_next_day_return'].mean():.0%}**。"
    )
    st.dataframe(rv.head(20), hide_index=True, width="stretch", height="content")
st.caption("注：Streamlit 匿名 session_id 在刷新浏览器后会重新生成；若需严格用户级 7 日留存，后续可接入浏览器 LocalStorage 匿名 UUID 或轻量登录。")
