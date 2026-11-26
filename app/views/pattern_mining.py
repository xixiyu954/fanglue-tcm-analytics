import networkx as nx
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.analysis import (
    association_rules,
    cooccurrence_graph,
    frequent_itemsets,
    specific_herbs,
    transactions,
)
from core.db import tables
from core.tracking import log_event, track_page_view
from core.ui import AMBER, HERBAL_QUAL, SAGE, insight_box, metric_card, style_fig

track_page_view("配伍规律")
t = tables()

st.title("🔗 配伍规律挖掘")
st.caption("分析问题：在经典名方或 4,360 首药典中成药中，哪些药物最核心？某类病证的特异性用药是什么？哪些药对最稳定地协同出现？")

with st.sidebar:
    st.header("1. 选择队列与筛选")
    cohort = st.radio("方剂来源", ["经典名方 (184)", "现代中成药 (4,360)", "全部 (4,544)"])
    f_all = t["formula"]
    if cohort.startswith("经典"):
        f_base = f_all[f_all["formula_type"] == "经典名方"]
        def_sup, def_edge = 0.05, 5
    elif cohort.startswith("现代"):
        f_base = f_all[f_all["formula_type"] == "现代中成药"]
        def_sup, def_edge = 0.04, 60
    else:
        f_base = f_all
        def_sup, def_edge = 0.04, 65

    cats = st.multiselect("功效类别", sorted(f_base["category"].unique()))
    dyns = st.multiselect("朝代", f_base.sort_values("dynasty_order")["dynasty"].unique()) if not cohort.startswith("现代") else []

    st.header("2. 挖掘参数")
    min_sup = st.slider("最小支持度", 0.01, 0.30, def_sup, 0.01)
    min_conf = st.slider("最小置信度", 0.15, 1.0, 0.50, 0.05)
    max_edge = max(15, int(len(f_base) * 0.08))
    min_edge = st.slider("网络最小共现次数", 2, max_edge, min(def_edge, max_edge))

f = f_base
if cats:
    f = f[f["category"].isin(cats)]
if dyns:
    f = f[f["dynasty"].isin(dyns)]

fh_base = t["formula_herb"][t["formula_herb"]["formula"].isin(f_base["formula"])]
fh = fh_base[fh_base["formula"].isin(f["formula"])]
n = f["formula"].nunique()
if n < 3:
    st.warning("筛选后方剂少于 3 首，无法进行有意义的规律挖掘")
    st.stop()

if st.session_state.get("_last_mine") != (cohort, tuple(cats), tuple(dyns), min_sup, min_conf):
    st.session_state["_last_mine"] = (cohort, tuple(cats), tuple(dyns), min_sup, min_conf)
    log_event("配伍规律", "rules_mined", {"cohort": cohort, "cats": cats, "n": n})

st.markdown(f"当前分析队列：**{cohort}** → 筛选后 **{n:,}** 首方剂，涉及 **{fh['herb'].nunique()}** 味标准药材（{len(fh):,} 条组成记录）")

# ---------- 1. 用药频次与核心药物 ----------
st.subheader("① 用药频次与核心药物（帕累托分析）")
freq = (
    fh.groupby("herb")["formula"]
    .nunique()
    .sort_values(ascending=False)
    .rename_axis("药材")
    .reset_index(name="出现方剂数")
)
freq["使用频率"] = freq["出现方剂数"] / n
freq["累计占比"] = freq["出现方剂数"].cumsum() / freq["出现方剂数"].sum()
top = freq.head(20)
fig = go.Figure()
fig.add_bar(
    x=top["药材"], y=top["出现方剂数"], name="出现方剂数",
    marker_color=SAGE, text=top["出现方剂数"], textposition="outside",
)
fig.add_scatter(
    x=top["药材"], y=top["累计占比"], name="累计占比", yaxis="y2",
    mode="lines+markers", line={"color": AMBER, "width": 2.2}, marker={"size": 6},
)
fig.update_layout(
    title="高频药材 Top 20（帕累托图）",
    yaxis={"title": "出现方剂数", "range": [0, top["出现方剂数"].max() * 1.18]},
    yaxis2={"overlaying": "y", "side": "right", "tickformat": ".0%", "range": [0, 1.08], "showgrid": False},
    legend={"orientation": "h", "y": 1.12, "x": 1, "xanchor": "right"},
)
style_fig(fig, height=390, margin={"l": 10, "r": 20, "t": 55, "b": 35})
st.plotly_chart(fig, width="stretch")
core_n = int((freq["累计占比"] <= 0.5).sum()) + 1
insight_box(
    f"<strong>洞察：</strong>前 <strong>{core_n}</strong> 味药材（仅占全部药材的 {core_n / len(freq):.1%}）贡献了 50% 的总用药频次，"
    f"高频核心药为 <strong>{'、'.join(freq.head(5)['药材'])}</strong>。"
)

# ---------- 1b. 类 TF-IDF 特异性用药 ----------
if cats or dyns:
    st.subheader("①-b 特异性用药对比（类 TF-IDF 相对风险）")
    spec = specific_herbs(fh, fh_base, min_count=max(2, min(5, n // 5)))
    if not spec.empty:
        l, r = st.columns([2, 3])
        l.dataframe(
            spec.head(15).style.format({"子集使用率": "{:.1%}", "全库使用率": "{:.1%}", "特异性倍数": "{:.2f}x"}),
            hide_index=True,
            width="stretch",
            height=360,
        )
        fig_sp = px.bar(
            spec.head(12), x="特异性倍数", y="药材", orientation="h",
            color="子集使用率", color_continuous_scale="YlGn",
            text=spec.head(12)["特异性倍数"].map(lambda v: f"{v:.1f}x"),
            title="最具类别特异性的药材 Top 12（剥离甘草等百搭药）",
        )
        fig_sp.update_traces(textposition="outside", cliponaxis=False)
        fig_sp.update_layout(yaxis={"categoryorder": "total ascending", "dtick": 1, "title": ""})
        style_fig(fig_sp, height=360, margin={"l": 10, "r": 35, "t": 45, "b": 30})
        r.plotly_chart(fig_sp, width="stretch")
        top_s = spec.iloc[0]
        insight_box(
            f"<strong>洞察：</strong>相比『频次最高』常被甘草、当归等百搭药占据，特异性倍数最高的 <strong>{top_s['药材']}</strong>"
            f" 在当前筛选集合中的使用率（{top_s['子集使用率']:.1%}）是全库的 <strong>{top_s['特异性倍数']:.1f} 倍</strong>，最能代表该类方剂的治法特色。"
        )

# ---------- 2. 关联规则 ----------
st.subheader("② 关联规则挖掘（Apriori）")
trans = transactions(fh)
items = frequent_itemsets(trans, min_sup, max_len=3)
rules = association_rules(items, len(trans), min_conf)
c1, c2, c3 = st.columns(3)
metric_card(c1, "频繁项集", f"{len(items):,}")
metric_card(c2, "其中 ≥2 味药组", f'{int((items["size"] >= 2).sum()) if not items.empty else 0:,}')
metric_card(c3, "有效关联规则", f"{len(rules):,}")

if rules.empty:
    st.info("当前参数下没有规则，可调低左侧最小支持度或置信度")
else:
    l, r = st.columns([3, 2])
    l.dataframe(
        rules.head(40).style.format({"支持度": "{:.3f}", "置信度": "{:.2f}", "提升度": "{:.2f}"}),
        hide_index=True,
        width="stretch",
        height=390,
    )
    fig_sc = px.scatter(
        rules.head(200), x="支持度", y="置信度", size="共现方剂数", color="提升度",
        hover_data=["前项", "后项"], color_continuous_scale="Tealgrn",
        title="关联规则分布（气泡大小=共现方剂数，颜色=提升度）",
    )
    style_fig(fig_sc, height=390, margin={"l": 10, "r": 10, "t": 45, "b": 35})
    r.plotly_chart(fig_sc, width="stretch")
    best = rules.iloc[0]
    insight_box(
        f"<strong>洞察：</strong>提升度最高的规则为 <strong>{best['前项']} → {best['后项']}</strong>"
        f"（共现 {best['共现方剂数']} 首，置信度 {best['置信度']:.0%}，提升度 <strong>{best['提升度']:.2f}</strong>），显著高于随机共现水平。"
    )
    with st.expander("指标口径说明"):
        st.markdown(
            "- **支持度**：同时含前项和后项的方剂占当前队列的比例\n"
            "- **置信度**：含前项的方剂中同时含后项的条件概率\n"
            "- **提升度** > 1：配伍正相关；甘草等百搭药支持度虽高，但提升度往往接近 1"
        )

# ---------- 3. 共现网络与社区发现 ----------
st.subheader("③ 药物共现网络与社区发现（Louvain）")
g = cooccurrence_graph(fh, min_edge, max_nodes=45)
if g.number_of_edges() == 0:
    st.info("当前阈值下没有边，请调低左侧『网络最小共现次数』")
else:
    pos = nx.spring_layout(g, weight="weight", seed=7, k=1.15, iterations=100)
    ex, ey = [], []
    for a, b in g.edges():
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]
    net = go.Figure()
    net.add_scatter(x=ex, y=ey, mode="lines", line={"width": 0.7, "color": "rgba(120,138,128,0.35)"}, hoverinfo="none", showlegend=False)
    nodes = list(g.nodes)
    max_f = max(g.nodes[v]["freq"] for v in nodes) or 1
    net.add_scatter(
        x=[pos[v][0] for v in nodes],
        y=[pos[v][1] for v in nodes],
        mode="markers+text",
        text=nodes,
        textposition="top center",
        textfont={"size": 11, "color": "#1f2a24"},
        showlegend=False,
        marker={
            "size": [11 + 25 * (g.nodes[v]["freq"] / max_f) for v in nodes],
            "color": [HERBAL_QUAL[g.nodes[v].get("community", 0) % len(HERBAL_QUAL)] for v in nodes],
            "line": {"width": 1.2, "color": "white"},
        },
        hovertext=[
            f"{v}：社区 {g.nodes[v].get('community', 0) + 1}｜出现 {g.nodes[v]['freq']} 次｜度 {g.degree(v)}"
            for v in nodes
        ],
        hoverinfo="text",
    )
    net.update_layout(xaxis={"visible": False}, yaxis={"visible": False})
    style_fig(net, height=540, margin={"l": 15, "r": 15, "t": 15, "b": 15})
    st.plotly_chart(net, width="stretch")

    comm: dict[int, list[tuple[int, str]]] = {}
    for v, d in g.nodes(data=True):
        comm.setdefault(d.get("community", 0), []).append((d["freq"], v))
    rows = []
    for cid, members in sorted(comm.items()):
        members.sort(reverse=True)
        rows.append({"社区": f"社区 {cid + 1}", "药味数": len(members), "核心药物（按频次）": "、".join(v for _, v in members)})
    st.dataframe(rows, hide_index=True, width="stretch", height="content")
    deg = sorted(nx.degree_centrality(g).items(), key=lambda x: -x[1])[:5]
    insight_box(
        "<strong>洞察：</strong>度中心性最高的枢纽药材为 "
        + "、".join(f"<strong>{k}</strong> ({v:.2f})" for k, v in deg)
        + "；Louvain 算法自动聚出的每个社区对应一组高频协同的『处方骨架』。"
    )
