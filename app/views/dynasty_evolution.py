import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import chi2_contingency, kruskal

from core.db import load_sql_file, query_cached, tables
from core.tracking import track_page_view
from core.ui import AMBER, HERBAL_QUAL, SAGE, TEAL, insight_box, metric_card, style_fig

track_page_view("朝代演变")
t = tables()

st.title("🏯 古方朝代演变分析")
st.caption("跨东汉至清代的 184 首经典名方：功效构成、寒热倾向与高频用药演变，量化检验『伤寒—局方—金元四大家—清代温病』流派特征")

f = t["formula"][t["formula"]["formula_type"] == "经典名方"].copy()
heat = query_cached(load_sql_file("04_方剂寒热指数.sql")).sort_values("dynasty_order")

ERA_MAP = {
    "先秦两汉": "东汉经方", "东汉": "东汉经方",
    "晋南北朝": "晋唐", "唐": "晋唐",
    "宋": "宋代",
    "金": "金元", "元": "金元",
    "明": "明代",
    "清": "清代", "现代": "清代及近代",
}
ERA_ORDER = ["东汉经方", "晋唐", "宋代", "金元", "明代", "清代"]

f_era = f[f["dynasty"] != "现代"].copy()
f_era["时期"] = f_era["dynasty"].map(ERA_MAP)
heat_era = heat[heat["dynasty"] != "现代"].copy()
heat_era["时期"] = heat_era["dynasty"].map(ERA_MAP)

# ---------- 学术流派数据验证指标卡 ----------
def cat_share(era: str, cats: set[str]) -> float:
    sub = f_era[f_era["时期"] == era]
    return float(sub["category"].isin(cats).mean()) if len(sub) else 0.0

def mean_heat(era: str) -> float:
    sub = heat_era[heat_era["时期"] == era]
    return float(sub["heat_index"].mean()) if len(sub) else 0.0

c1, c2, c3, c4 = st.columns(4)
metric_card(c1, "东汉经方 · 寒热均值", f"{mean_heat('东汉经方'):+.2f}",
            f"解表/温里/和解占 {cat_share('东汉经方', {'解表剂','温里剂','和解剂'}):.0%}")
metric_card(c2, "宋代局方 · 寒热均值", f"{mean_heat('宋代'):+.2f}",
            f"祛湿/理气/补益占 {cat_share('宋代', {'祛湿剂','理气剂','补益剂'}):.0%}")
metric_card(c3, "金元时期 · 寒热均值", f"{mean_heat('金元'):+.2f}",
            f"补益/清热/治燥占 {cat_share('金元', {'补益剂','清热剂','治燥剂'}):.0%}")
metric_card(c4, "清代温病 · 寒热均值", f"{mean_heat('清代'):+.2f}",
            f"清热/理血/治燥占 {cat_share('清代', {'清热剂','理血剂','治燥剂'}):.0%}")

# ---------- 主图表（严格按朝代时序 + Top8 合并避免色板撞色） ----------
l, r = st.columns(2)
major_dyn = f["dynasty"].value_counts()
keep_dyn = set(major_dyn[major_dyn >= 5].index)
ordered_dyns = (
    f[f["dynasty"].isin(keep_dyn)][["dynasty_order", "dynasty"]]
    .drop_duplicates()
    .sort_values("dynasty_order")["dynasty"]
    .tolist()
)
f_main = f[f["dynasty"].isin(keep_dyn)].copy()
heat_main = heat[heat["dynasty"].isin(keep_dyn)].copy()

top8_cats = f_main["category"].value_counts().head(8).index.tolist()
f_main["大类"] = f_main["category"].where(f_main["category"].isin(top8_cats), "其他类别")
cat_order = top8_cats + ["其他类别"]

share = f_main.groupby(["dynasty", "大类"]).size().reset_index(name="n")
share["占比"] = share["n"] / share.groupby("dynasty")["n"].transform("sum")
fig_stack = px.bar(
    share, x="dynasty", y="占比", color="大类",
    category_orders={"dynasty": ordered_dyns, "大类": cat_order},
    color_discrete_sequence=HERBAL_QUAL,
    title="主要朝代方剂功效构成（Top 8 类别，样本量 ≥ 5）",
    labels={"dynasty": "", "大类": ""},
)
fig_stack.update_layout(yaxis_tickformat=".0%", legend={"orientation": "h", "y": -0.22, "x": 0.5, "xanchor": "center"})
style_fig(fig_stack, height=450, margin={"l": 10, "r": 10, "t": 45, "b": 85})
l.plotly_chart(fig_stack, width="stretch")

fig_box = px.box(
    heat_main, x="dynasty", y="heat_index", points="all",
    hover_data=["formula", "category"],
    category_orders={"dynasty": ordered_dyns},
    color_discrete_sequence=[SAGE],
    title="各朝代方剂剂量加权寒热指数分布",
    labels={"dynasty": "", "heat_index": "寒热指数"},
)
fig_box.add_hline(y=0, line_dash="dot", line_color="rgba(31,42,36,0.4)")
style_fig(fig_box, height=450, margin={"l": 10, "r": 10, "t": 45, "b": 85})
r.plotly_chart(fig_box, width="stretch")

# ---------- 历史时期寒热趋势折线 + 自适应侧表 ----------
trend = (
    heat_era.groupby("时期")
    .agg(
        均值=("heat_index", "mean"),
        中位数=("heat_index", "median"),
        偏寒占比=("tendency", lambda s: (s == "偏寒凉").mean()),
        方剂数=("formula", "count"),
    )
    .reindex([e for e in ERA_ORDER if e in heat_era["时期"].unique()])
    .reset_index()
)
st.subheader("历史时期寒热倾向演变")
tl, tr = st.columns([3, 2])
fig_tr = go.Figure()
fig_tr.add_scatter(
    x=trend["时期"], y=trend["均值"], mode="lines+markers+text", name="均值",
    line={"color": SAGE, "width": 2.5}, marker={"size": 7},
    text=[f"{v:+.2f}" for v in trend["均值"]], textposition="top center",
)
fig_tr.add_scatter(
    x=trend["时期"], y=trend["中位数"], mode="lines+markers+text", name="中位数",
    line={"color": AMBER, "width": 2, "dash": "dash"}, marker={"size": 7},
    text=[f"{v:+.2f}" for v in trend["中位数"]], textposition="bottom center",
)
fig_tr.add_hline(y=0, line_dash="dot", line_color="rgba(31,42,36,0.35)")
ymin = min(float(trend[["均值", "中位数"]].min().min()) - 0.35, -1.1)
ymax = max(float(trend[["均值", "中位数"]].max().max()) + 0.35, 0.7)
fig_tr.update_layout(
    title="各历史时期寒热指数走势（越低越偏寒凉）",
    yaxis={"title": "寒热指数", "range": [ymin, ymax]},
    legend={"orientation": "h", "y": 1.12, "x": 1, "xanchor": "right", "title_text": ""},
)
style_fig(fig_tr, height=340, margin={"l": 10, "r": 15, "t": 55, "b": 30})
tl.plotly_chart(fig_tr, width="stretch")

tr.markdown("#### 各时期汇总表")
trend_show = trend.copy()
trend_show["偏寒占比"] = trend_show["偏寒占比"] * 100
tr.dataframe(
    trend_show,
    hide_index=True,
    width="stretch",
    height="content",
    column_config={
        "时期": st.column_config.TextColumn("时期", width="small"),
        "均值": st.column_config.NumberColumn("均值", format="%+.2f", width="small"),
        "中位数": st.column_config.NumberColumn("中位数", format="%+.2f", width="small"),
        "偏寒占比": st.column_config.NumberColumn("偏寒占比", format="%.0f%%", width="small"),
        "方剂数": st.column_config.NumberColumn("方数", format="%d", width="small"),
    },
)

# ---------- 各朝代高频药材 Top 5（修复第一行 X 轴标签与标题前缀） ----------
st.subheader("各朝代高频药材 Top 5（SQL 窗口函数 ROW_NUMBER）")
top = query_cached(load_sql_file("02_各朝代Top5药材.sql"))
top = top[top["dynasty"].isin(keep_dyn)]
fig_facet = px.bar(
    top, x="herb", y="n_formula", text="n_formula",
    facet_col="dynasty", facet_col_wrap=4, facet_row_spacing=0.18, facet_col_spacing=0.05,
    category_orders={"dynasty": ordered_dyns},
    color_discrete_sequence=[TEAL],
    labels={"herb": "", "n_formula": "方剂数"},
)
fig_facet.update_traces(textposition="outside", cliponaxis=False)
fig_facet.update_xaxes(matches=None, showticklabels=True, title_text="", tickfont={"size": 11})
fig_facet.update_yaxes(matches=None, showticklabels=True, title_text="")
fig_facet.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>", font={"size": 13}))
style_fig(fig_facet, height=500, margin={"l": 20, "r": 15, "t": 40, "b": 35})
st.plotly_chart(fig_facet, width="stretch")

with st.expander("查看 SQL（02_各朝代Top5药材.sql）"):
    st.code(load_sql_file("02_各朝代Top5药材.sql"), language="sql")

# ---------- 统计假设检验 ----------
st.subheader("统计假设检验")
groups = [g["heat_index"].values for _, g in heat_main.groupby("dynasty") if len(g) >= 5]
p_kw = 1.0
if len(groups) >= 2:
    h_stat, p_kw = kruskal(*groups)
    sig = "存在统计学显著差异（p < 0.05）" if p_kw < 0.05 else "尚未达到 0.05 显著性水平"
    st.markdown(f"- **Kruskal-Wallis 非参数检验**（各主要朝代寒热指数差异）：H = **{h_stat:.2f}**，p = **{p_kw:.4f}** → {sig}")

ct = pd.crosstab(heat_era["时期"], heat_era["tendency"]).reindex([e for e in ERA_ORDER if e in heat_era["时期"].unique()])
chi2, p_chi, dof, expected = chi2_contingency(ct)
low_pct = float((expected < 5).mean())
st.markdown(
    f"- **卡方独立性检验**（历史时期 × 寒热三档倾向）：χ² = **{chi2:.2f}**，df = {dof}，p = **{p_chi:.4f}**（期望频数 < 5 的单元格占 {low_pct:.0%}）"
)
if low_pct <= 0.25:
    st.success("✅ 合并为历史时期 × 寒热三档后，列联表期望频数满足卡方检验前提条件。")
else:
    st.warning("⚠️ 部分历史时期样本量仍偏少（如晋唐），解释时需结合《方剂学》选方偏倚谨慎说明。")

insight_box(
    f"<strong>分析结论：</strong>东汉经方寒热均值 <strong>{mean_heat('东汉经方'):+.2f}</strong>（桂枝/干姜/附子/麻黄等温散药占比高），"
    f"至清代寒热均值降至 <strong>{mean_heat('清代'):+.2f}</strong>（Kruskal-Wallis p = {p_kw:.4f}），清热、养阴与理血方明显增多，"
    "与清代温病学派兴起、王清任活血化瘀流派在教材中的历史叙述高度吻合。"
    "需说明：教材正方经过历代遴选，存在选样偏倚，不能直接外推为古代存世全部方书的总体分布。"
)
