import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.analysis import (
    formula_components,
    heat_label,
    parse_formula_text,
    profile,
    safety_check,
    similar_formulas,
)
from core.db import tables
from core.tracking import log_event, track_page_view
from core.ui import SAGE, insight_box, metric_card, style_fig

track_page_view("方剂体检")
t = tables()

st.title("🩺 方剂体检")
st.caption("选择经典名方 / 药典中成药或自由输入组成 → 性味归经画像、多维度安全警示与全库相似方对比")

c_mode, c_scope = st.columns([2, 3])
mode = c_mode.radio("输入方式", ["从方剂库选择", "自由输入"], horizontal=True)
if mode == "从方剂库选择":
    cohort = c_scope.radio("方剂队列", ["经典名方 (184)", "现代中成药 (4,360)", "全部 (4,544)"], horizontal=True)
    f_df = t["formula"]
    if cohort.startswith("经典"):
        pool = f_df[f_df["formula_type"] == "经典名方"]
    elif cohort.startswith("现代"):
        pool = f_df[f_df["formula_type"] == "现代中成药"]
    else:
        pool = f_df
    names = pool["formula"].tolist()
    default_idx = names.index("四君子汤") if "四君子汤" in names else 0
    name = st.selectbox("搜索并选择方剂", names, index=default_idx)
    comp = formula_components(name, t)
    meta = f_df.set_index("formula").loc[name]
    st.markdown(
        f"**类型**：{meta.formula_type}　｜　**出处**：《{meta.source}》（{meta.dynasty}）　｜　"
        f"**类别**：{meta.category}　｜　**主治**：{meta.indication}"
    )
    exclude = name
else:
    text = st.text_area(
        "输入组成（药名 + 剂量g，空格或逗号分隔；支持常见炮制品与别名）",
        "人参9 白术9 茯苓9 炙甘草6 陈皮6 半夏9",
        height=85,
    )
    comp = parse_formula_text(text, t)
    name, exclude = "自拟方", None

if comp.empty:
    st.info("请输入至少一味药材")
    st.stop()

unmatched = comp.loc[~comp["matched"], "herb_raw"].tolist()
if unmatched:
    st.warning(f"以下药名未收录于药材主库，已跳过：{'、'.join(unmatched)}")
comp = comp[comp["matched"]]
if comp.empty:
    st.stop()

p = profile(comp, t)
alerts = safety_check(comp, t)

if st.session_state.get("_last_analyzed") != (name, tuple(comp["herb"])):
    st.session_state["_last_analyzed"] = (name, tuple(comp["herb"]))
    log_event("方剂体检", "formula_analyzed", {"mode": mode, "formula": name, "n_herbs": len(comp)})

# ---------- 指标卡（无误导箭头） ----------
c1, c2, c3, c4 = st.columns(4)
metric_card(c1, "药味数", f"{len(comp)} 味")
metric_card(
    c2, "总剂量", f"{p['total_dose']:g} g" if p["has_dose"] else "等量计权",
    "按现代折算剂量" if p["has_dose"] else "成药无克重，等权计算",
)
metric_card(
    c3, "寒热指数", f"{p['heat_index']:+.2f}", heat_label(p["heat_index"]),
    help="按剂量加权的四气得分：大寒 -3 … 平 0 … 大热 +3",
)
high_cnt = int((alerts["等级"] == "高").sum()) if not alerts.empty else 0
metric_card(c4, "安全提示", f"{len(alerts)} 条", f"其中高风险 {high_cnt} 条" if high_cnt else "无高风险配伍禁忌")

# ---------- 组成明细 ----------
with st.expander("组成明细与药名标准化结果", expanded=False):
    d = p["detail"][[
        "herb_raw", "herb", "processing", "dose_g", "category", "nature",
        "flavors", "meridians", "dose_min", "dose_max",
    ]]
    st.dataframe(
        d.rename(columns={
            "herb_raw": "原始名", "herb": "标准名", "processing": "炮制/部位", "dose_g": "剂量(g)",
            "category": "功效分类", "nature": "四气", "flavors": "五味", "meridians": "归经",
            "dose_min": "药典下限", "dose_max": "药典上限",
        }),
        hide_index=True,
        width="stretch",
        height="content",
    )

# ---------- 三图并排（统一草本风格，修复文字旋转与雷达刻度碰撞） ----------
l, m, r = st.columns(3)
nat = p["nature"].rename_axis("四气").reset_index(name="占比")
fig_nat = px.pie(
    nat, names="四气", values="占比", hole=0.48, title="四气构成",
    color="四气",
    color_discrete_map={
        "大寒": "#1f4e79", "寒": "#3c78a8", "微寒": "#6ea0c7", "凉": "#9ec2de",
        "平": "#9fb3a5", "微温": "#e0a96d", "温": "#d4843e", "热": "#c05a3c", "大热": "#8e2d1a",
    },
)
fig_nat.update_traces(textinfo="label+percent", textposition="inside")
fig_nat.update_layout(showlegend=False)
style_fig(fig_nat, height=340, margin={"l": 10, "r": 10, "t": 42, "b": 15})
l.plotly_chart(fig_nat, width="stretch")

fl = p["flavor"].rename_axis("五味").reset_index(name="占比")
max_fl = max(float(fl["占比"].max()), 0.1)
fig_fl = px.bar(
    fl, x="五味", y="占比", title="五味分布（微味归并主味）",
    text=fl["占比"].map(lambda v: f"{v:.0%}" if v > 0 else ""),
    color_discrete_sequence=[SAGE],
)
fig_fl.update_traces(textposition="outside", textangle=0, cliponaxis=False)
fig_fl.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, max_fl * 1.24], xaxis_title="", yaxis_title="")
style_fig(fig_fl, height=340, margin={"l": 10, "r": 10, "t": 42, "b": 25})
m.plotly_chart(fig_fl, width="stretch")

mer = p["meridian"]
max_mer = max(float(mer.max()), 0.1)
radar = go.Figure(go.Scatterpolar(
    r=list(mer.values) + [mer.values[0]],
    theta=list(mer.index) + [mer.index[0]],
    fill="toself",
    fillcolor="rgba(46, 125, 91, 0.24)",
    line={"color": SAGE, "width": 2},
    name=name,
))
radar.update_layout(
    title="归经雷达图",
    polar={
        "bgcolor": "rgba(255,255,255,0.65)",
        "radialaxis": {
            "visible": True, "tickformat": ".0%", "angle": 45, "tickangle": 45,
            "nticks": 4, "range": [0, min(1.05, max_mer * 1.15)], "tickfont": {"size": 9, "color": "#5d6d65"},
        },
        "angularaxis": {"tickfont": {"size": 11}},
    },
)
style_fig(radar, height=340, margin={"l": 32, "r": 32, "t": 45, "b": 22})
r.plotly_chart(radar, width="stretch")

# ---------- 安全提示（带视觉分级标签） ----------
st.subheader("⚠️ 安全提示")
if alerts.empty:
    st.success("✅ 未发现十八反、十九畏、马兜铃酸肾毒、妊娠慎用/禁用、毒性及超量提示")
else:
    badge = {"高": "🔴 高", "中": "🟠 中", "低": "🔵 低"}
    alerts_show = alerts.copy()
    alerts_show["等级"] = alerts_show["等级"].map(lambda x: badge.get(x, x))
    st.dataframe(
        alerts_show,
        hide_index=True,
        width="stretch",
        height="content",
        column_config={
            "等级": st.column_config.TextColumn("风险等级", width="small"),
            "类型": st.column_config.TextColumn("规则类型", width="small"),
            "说明": st.column_config.TextColumn("具体说明", width="large"),
        },
    )
st.caption("依据《中国药典》、十八反/十九畏、马兜铃酸肾毒警示及妊娠禁忌自动比对；古方折算剂量与现代标准不同，超量提示用于引导核查而非判定错误。")

# ---------- 相似方（合理列宽防朝代截断） ----------
st.subheader("🔍 相似方剂 Top 5")
sim_scope = st.radio("比对范围", ["经典名方", "全部"], horizontal=True, key="sim_scope")
sim = similar_formulas(set(comp["herb"]), t, top=5, exclude=exclude, scope=sim_scope)
if sim.empty:
    st.info("比对范围内没有共享药材的方剂")
else:
    st.dataframe(
        sim,
        hide_index=True,
        width="stretch",
        height="content",
        column_config={
            "方剂": st.column_config.TextColumn("方剂", width="small"),
            "Jaccard相似度": st.column_config.ProgressColumn("相似度", min_value=0.0, max_value=1.0, format="%.2f", width="small"),
            "共有": st.column_config.TextColumn("共有药材", width="medium"),
            "该方多出": st.column_config.TextColumn("该方多出", width="medium"),
            "该方缺少": st.column_config.TextColumn("该方缺少", width="small"),
            "来源": st.column_config.TextColumn("来源", width="small"),
            "类别": st.column_config.TextColumn("类别", width="small"),
            "朝代": st.column_config.TextColumn("朝代", width="small"),
        },
    )
    best = sim.iloc[0]
    insight_box(
        f"<strong>洞察：</strong>最接近 <strong>{best['方剂']}</strong>（{best['来源']} · 相似度 {best['Jaccard相似度']:.2f}）："
        f"该方多出 <strong>{best['该方多出']}</strong>，缺少 <strong>{best['该方缺少']}</strong>。"
    )

# ---------- 报告导出 ----------
report = [
    f"# {name} 方剂体检报告", "",
    f"- 组成：{'、'.join(f'{r.herb_raw}{r.dose_g:g}g' if r.dose_g == r.dose_g else r.herb_raw for r in comp.itertuples())}",
    f"- 寒热指数：{p['heat_index']:+.2f}（{heat_label(p['heat_index'])}）",
    f"- 主要五味：{'、'.join(p['flavor'].sort_values(ascending=False).head(3).index)}",
    f"- 主要归经：{'、'.join(p['meridian'].sort_values(ascending=False).head(3).index)}",
    "", "## 安全提示",
] + ([f"- [{a.等级}][{a.类型}] {a.说明}" for a in alerts.itertuples()] or ["- 无"]) + [
    "", "## 相似方剂 Top 5",
] + [f"- {s.方剂}（相似度 {s.Jaccard相似度:.2f}）" for s in sim.itertuples()] + [
    "", "> 本报告由「方略」自动生成，仅供学习研究参考，不构成用药建议。",
]

c_dl, c_tip = st.columns([1, 3])
if c_dl.download_button("📄 导出体检报告（Markdown）", "\n".join(report), file_name=f"{name}_体检报告.md"):
    log_event("方剂体检", "report_exported", {"formula": name})
c_tip.info("💡 想进一步分析该方的**活性成分、疾病交集靶点、STRING PPI 与 GO/KEGG 通路**？点击左侧 **🧬 网络药理学**。")
