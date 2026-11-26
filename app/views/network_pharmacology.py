import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.analysis import formula_components, parse_formula_text
from core.db import tables
from core.netpharm import (
    build_ppi_graph_and_hubs,
    cached_diseases,
    fetch_gprofiler_enrichment,
    fetch_opentargets_targets,
    fetch_string_ppi,
    get_cached_disease_targets,
    overlap_stats,
    screen_formula_compounds_targets,
    search_opentargets_diseases,
)
from core.tracking import log_event, track_page_view
from core.ui import AMBER, SAGE, TEAL, TERRA, insight_box, metric_card, shorten, style_fig

track_page_view("网络药理学")
t = tables()

st.title("🧬 网络药理学一键分析流水线")
st.caption(
    "方剂组成 → 活性成分 ADME/类药性筛选（TCM-MKG + SymMap v2.0）→ 疾病交集靶点（Open Targets）"
    "→ PPI 蛋白互作（STRING 12.5）→ GO/KEGG 富集（g:Profiler）→ 四层调控桑基图"
)

# ======================== 侧边栏：参数配置 ========================
with st.sidebar:
    st.header("1. 方剂输入")
    f_mode = st.radio("方式", ["经典名方", "现代中成药", "自由输入"])
    f_df = t["formula"]
    if f_mode in {"经典名方", "现代中成药"}:
        names = f_df.loc[f_df["formula_type"] == f_mode, "formula"].tolist()
        idx = names.index("四君子汤") if "四君子汤" in names else 0
        fname = st.selectbox("选择方剂", names, index=idx)
        comp_df = formula_components(fname, t)
    else:
        txt = st.text_area("输入药材（空格分隔）", "人参 白术 茯苓 甘草", height=70)
        comp_df = parse_formula_text(txt, t)
        comp_df = comp_df[comp_df["matched"]]
        fname = "自拟方"

    st.header("2. 目标疾病（Open Targets）")
    d_mode = st.radio("疾病来源", ["预置常见研究疾病 (12种)", "实时搜索任意疾病"])
    dis_label, dis_df = "", pd.DataFrame()
    if d_mode.startswith("预置"):
        dc = cached_diseases()
        d_list = dc["disease_zh"].tolist()
        d_idx = d_list.index("溃疡性结肠炎") if "溃疡性结肠炎" in d_list else 0
        dis_label = st.selectbox("选择疾病", d_list, index=d_idx)
        dis_df = get_cached_disease_targets(dis_label)
    else:
        kw = st.text_input("英文疾病名", value="gastritis", help="实时调用 Open Targets GraphQL API，如 type 2 diabetes / liver fibrosis")
        if kw.strip():
            try:
                hits = search_opentargets_diseases(kw.strip())
                if hits:
                    opt = {f"{h['name']} ({h['id']})": h for h in hits}
                    chosen = st.selectbox("匹配疾病", list(opt.keys()))
                    hit = opt[chosen]
                    dis_label = hit["name"]
                    with st.spinner("正在从 Open Targets 拉取疾病靶点…"):
                        dis_df = fetch_opentargets_targets(hit["id"], limit=300)
                else:
                    st.warning("未检索到匹配疾病，请更换英文关键词")
            except Exception as e:
                st.error(f"Open Targets API 请求失败：{e}")

    st.header("3. 活性成分筛选阈值")
    min_qed = st.slider("最小 QED（类药性得分）", 0.0, 0.9, 0.45, 0.05,
                        help="Bickerton et al. Nature Chemistry 定量类药性指标，通常取 ≥ 0.4–0.5")
    min_ob = st.slider("最小 OB（口服生物利用度 %）", 0, 80, 30, 5,
                       help="TCMSP / SymMap 常用阈值 OB ≥ 30%")
    lipinski_only = st.checkbox("仅保留符合 Lipinski 五规则", value=True)
    keep_missing_ob = st.checkbox("保留无 OB 标注但满足 QED 的化合物", value=True)

    st.header("4. PPI 与富集参数")
    top_n_ppi = st.slider("送入 STRING / g:Profiler 的核心靶点数", 10, 80, 35, 5,
                          help="按命中药材数、活性成分数与疾病关联分排序取 Top N")
    string_score = st.select_slider(
        "STRING 蛋白互作置信度", options=[400, 700, 900], value=700,
        format_func=lambda x: {400: "0.4 (中)", 700: "0.7 (高)", 900: "0.9 (极高)"}[x],
    )

herbs = comp_df["herb"].unique().tolist()
if not herbs or dis_df.empty:
    st.info("请在左侧确认方剂组成与目标疾病")
    st.stop()

# ======================== Step 1: 本地成分-靶点筛选 ========================
hc, compounds, ct = screen_formula_compounds_targets(
    herbs, min_qed=min_qed, min_ob=float(min_ob), lipinski_only=lipinski_only, keep_missing_ob=keep_missing_ob
)
covered_herbs = sorted(hc["herb"].unique()) if not hc.empty else []
uncovered_herbs = [h for h in herbs if h not in set(covered_herbs)]

if compounds.empty or ct.empty:
    st.warning("当前筛选阈值过严，未筛出活性成分或靶点；请调低左侧 QED / OB 阈值。")
    st.stop()

formula_genes = set(ct["gene"].unique())
disease_genes = set(dis_df["gene"].unique())
ov = overlap_stats(formula_genes, disease_genes)

hc_ct = hc[["herb", "cid", "Molecule_name"]].merge(ct, on="cid")
ov_genes = sorted(formula_genes & disease_genes)
ov_tbl = (
    hc_ct[hc_ct["gene"].isin(ov_genes)]
    .groupby("gene")
    .agg(
        命中药材数=("herb", "nunique"),
        命中药材=("herb", lambda s: "、".join(sorted(set(s)))),
        命中成分数=("cid", "nunique"),
        代表成分=("Molecule_name", lambda s: "、".join(list(dict.fromkeys(s))[:4])),
    )
    .reset_index()
    .merge(dis_df[["gene", "score"]], on="gene", how="left")
    .rename(columns={"gene": "靶点基因", "score": "疾病关联分"})
    .sort_values(["命中药材数", "命中成分数", "疾病关联分"], ascending=False)
    .reset_index(drop=True)
)

# ======================== 顶部漏斗指标卡 ========================
st.markdown(f"**当前分析**：`{fname}`（{'、'.join(herbs)}） × `{dis_label}`")
if uncovered_herbs:
    st.caption(f"注：{'、'.join(uncovered_herbs)} 未在有机小分子成分库中检出（多为矿物药、动物胶类或未满足当前阈值），未计入小分子靶点。")

m1, m2, m3, m4, m5 = st.columns(5)
metric_card(m1, "覆盖药材", f"{len(covered_herbs)} / {len(herbs)} 味")
metric_card(m2, "活性成分", f"{len(compounds):,} 个")
metric_card(m3, "方剂预测靶点", f"{ov['n_formula']:,} 个")
metric_card(m4, "疾病交集靶点", f"{ov['n_overlap']} 个", f"疾病库 {ov['n_disease']} 个")
p_txt = f"{ov['p_value']:.2e}" if ov["p_value"] < 0.001 else f"{ov['p_value']:.4f}"
metric_card(
    m5, "靶点富集倍数", f"{ov['fold_enrichment']:.2f}x", f"超几何 p = {p_txt}",
    help="以 20,000 个人类编码基因为背景，检验方剂靶点与疾病靶点的重叠是否显著高于随机",
)

if ov["n_overlap"] < 3:
    st.warning("交集靶点少于 3 个，不足以构建 PPI 网络和通路富集。请放宽左侧 QED/OB 阈值或更换更相关的疾病。")
    st.dataframe(ov_tbl, hide_index=True, width="stretch")
    st.stop()

# ======================== 一键执行在线生信流水线 ========================
run_key = (fname, tuple(herbs), dis_label, min_qed, min_ob, lipinski_only, keep_missing_ob, top_n_ppi, string_score)
top_genes = tuple(ov_tbl["靶点基因"].head(top_n_ppi).tolist())

if st.session_state.get("_np_last") != run_key:
    st.session_state["_np_last"] = run_key
    log_event("网络药理学", "netpharm_run", {"formula": fname, "disease": dis_label, "overlap": ov["n_overlap"]})

ppi_edges, ppi_err = pd.DataFrame(), ""
enrich_df, enrich_err = pd.DataFrame(), ""
with st.spinner("正在实时调用 STRING 12.5（PPI 互作）与 g:Profiler（GO/KEGG 富集）…"):
    try:
        ppi_edges = fetch_string_ppi(top_genes, min_score=string_score)
    except Exception as e:
        ppi_err = str(e)
    try:
        enrich_df = fetch_gprofiler_enrichment(top_genes, p_threshold=0.05)
    except Exception as e:
        enrich_err = str(e)

g_ppi, hubs = build_ppi_graph_and_hubs(ppi_edges)

# ======================== 精简标签的四标签页（1280px 完整显示不滚动） ========================
tab1, tab2, tab3, tab4 = st.tabs([
    f"🧪 成分与靶点 ({ov['n_overlap']})",
    f"🕸️ PPI 互作 ({len(ppi_edges)} 边)",
    f"🫧 GO / KEGG 富集 ({len(enrich_df)})",
    "🌊 四层调控桑基图",
])

with tab1:
    l, r = st.columns([1, 1])
    with l:
        st.subheader("筛选后的活性成分")
        show_c = compounds.rename(columns={
            "Molecule_name": "成分名称", "Molecular_Formula": "分子式", "OB_score": "OB(%)",
            "MolWt": "分子量", "MolLogP": "LogP",
        })[["成分名称", "来源药材", "药材数", "靶点数", "OB(%)", "QED", "分子量", "分子式"]]
        st.dataframe(show_c.head(100), hide_index=True, width="stretch", height=390)
        if st.download_button("⬇️ 下载活性成分 CSV", show_c.to_csv(index=False).encode("utf-8-sig"),
                              file_name=f"{fname}_活性成分.csv", mime="text/csv"):
            log_event("网络药理学", "report_exported", {"type": "compounds", "formula": fname})
    with r:
        st.subheader(f"方剂 ∩ {dis_label} 交集靶点")
        st.dataframe(
            ov_tbl,
            hide_index=True,
            width="stretch",
            height=390,
            column_config={"疾病关联分": st.column_config.NumberColumn("关联分", format="%.3f")},
        )
        if st.download_button("⬇️ 下载交集靶点 CSV", ov_tbl.to_csv(index=False).encode("utf-8-sig"),
                              file_name=f"{fname}_{dis_label}_交集靶点.csv", mime="text/csv"):
            log_event("网络药理学", "report_exported", {"type": "overlap_targets", "formula": fname})

    insight_box(
        f"<strong>统计检验洞察：</strong><strong>{fname}</strong> 靶点与 <strong>{dis_label}</strong> 靶点重合 <strong>{ov['n_overlap']}</strong> 个"
        f"（随机期望 {ov['expected']:.1f} 个，富集倍数 <strong>{ov['fold_enrichment']:.2f}x</strong>，超几何检验 p = {p_txt}）。"
        f"多味药协同命中的核心候选靶点包括 <strong>{'、'.join(ov_tbl['靶点基因'].head(6))}</strong>。"
    )

with tab2:
    if ppi_err:
        st.error(f"STRING API 调用失败（可能是网络超时）：{ppi_err}")
    elif ppi_edges.empty:
        st.info("当前置信度阈值下未返回蛋白互作边，可在左侧将 STRING 置信度调低至 0.4。")
    else:
        # 仅绘制最大连通子图，避免孤立散点拉扁主网络并减少中心标签拥挤
        comps = sorted(nx.connected_components(g_ppi), key=len, reverse=True)
        g_main = g_ppi.subgraph(comps[0]).copy()
        minor_nodes = g_ppi.number_of_nodes() - g_main.number_of_nodes()

        l, r = st.columns([3, 2])
        pos = nx.kamada_kawai_layout(g_main) if g_main.number_of_nodes() >= 4 else nx.spring_layout(g_main, seed=42)
        ex, ey = [], []
        for a, b in g_main.edges():
            ex += [pos[a][0], pos[b][0], None]
            ey += [pos[a][1], pos[b][1], None]
        fig_ppi = go.Figure()
        fig_ppi.add_scatter(x=ex, y=ey, mode="lines", line={"width": 0.9, "color": "rgba(120,138,128,0.45)"}, hoverinfo="none", showlegend=False)
        nodes = list(g_main.nodes)
        degs = [g_main.degree(n) for n in nodes]
        max_d = max(degs) or 1
        fig_ppi.add_scatter(
            x=[pos[n][0] for n in nodes],
            y=[pos[n][1] for n in nodes],
            mode="markers+text",
            text=nodes,
            textposition="top center",
            textfont={"size": 10.5, "color": "#1f2a24"},
            showlegend=False,
            marker={
                "size": [12 + 22 * (g_main.degree(n) / max_d) for n in nodes],
                "color": degs,
                "colorscale": "YlOrRd",
                "showscale": True,
                "colorbar": {"title": "Degree", "thickness": 12, "len": 0.75},
                "line": {"width": 1.2, "color": "white"},
            },
            hovertext=[f"{n}｜Degree={g_main.degree(n)}" for n in nodes],
            hoverinfo="text",
        )
        title_ppi = f"STRING 12.5 PPI 核心连通子图（{g_main.number_of_nodes()} 节点，{g_main.number_of_edges()} 边）"
        fig_ppi.update_layout(title=title_ppi, xaxis={"visible": False}, yaxis={"visible": False})
        style_fig(fig_ppi, height=520, margin={"l": 20, "r": 20, "t": 45, "b": 20})
        l.plotly_chart(fig_ppi, width="stretch")
        if minor_nodes > 0:
            l.caption(f"已自动聚焦最大连通网络（另隐藏 {minor_nodes} 个离散小配对节点，完整边表见右侧下载）。")

        r.subheader("Hub 核心靶点拓扑排名")
        hub_show = hubs.head(15).rename(columns={"介数中心性": "介数", "紧密中心性": "紧密度"})
        r.dataframe(
            hub_show,
            hide_index=True,
            width="stretch",
            height=430,
            column_config={
                "靶点": st.column_config.TextColumn("靶点", width="small"),
                "Degree": st.column_config.NumberColumn("Degree", format="%d", width="small"),
                "度中心性": st.column_config.NumberColumn("度中心性", format="%.3f", width="small"),
                "介数": st.column_config.NumberColumn("介数", format="%.3f", width="small"),
                "紧密度": st.column_config.NumberColumn("紧密度", format="%.3f", width="small"),
            },
        )
        if r.download_button("⬇️ 下载完整 PPI 边表 CSV", ppi_edges.to_csv(index=False).encode("utf-8-sig"),
                             file_name=f"{fname}_{dis_label}_PPI.csv", mime="text/csv"):
            log_event("网络药理学", "report_exported", {"type": "ppi", "formula": fname})

        insight_box(
            "<strong>拓扑洞察：</strong>PPI 网络中连接度最高的 Top 5 Hub 核心靶点为 "
            + "、".join(f"<strong>{row.靶点}</strong> (Degree={row.Degree})" for row in hubs.head(5).itertuples())
            + "，处于蛋白互作枢纽位置，可作为优先实验验证候选。"
        )

with tab3:
    if enrich_err:
        st.error(f"g:Profiler API 调用失败：{enrich_err}")
    elif enrich_df.empty:
        st.info("未检出校正 p < 0.05 的显著富集通路。")
    else:
        kegg = enrich_df[enrich_df["来源"] == "KEGG"].head(15).copy()
        go_top = pd.concat(
            [enrich_df[enrich_df["来源"] == src].head(5) for src in ["GO:BP", "GO:MF", "GO:CC"]],
            ignore_index=True,
        )

        # 全宽上下排布 + 精简长英文名（完整名称保留在 hover），彻底避免长标签挤压绘图区
        if not kegg.empty:
            kegg["简称"] = kegg["通路/功能名称"].map(lambda s: shorten(s, 42))
            fig_kegg = px.scatter(
                kegg, x="GeneRatio", y="简称", size="命中基因数", color="neg_log10_p",
                color_continuous_scale="YlOrRd",
                hover_data={"简称": False, "通路/功能名称": True, "编号": True, "校正P值": ":.2e", "命中基因": True},
                title="KEGG 信号通路富集气泡图（Top 15）",
                labels={"neg_log10_p": "-log10(P)", "简称": ""},
            )
            fig_kegg.update_layout(yaxis={"categoryorder": "total ascending", "dtick": 1})
            style_fig(fig_kegg, height=460, margin={"l": 15, "r": 20, "t": 45, "b": 35})
            st.plotly_chart(fig_kegg, width="stretch")
        else:
            st.info("未检出显著 KEGG 通路")

        if not go_top.empty:
            go_top["简称"] = go_top["通路/功能名称"].map(lambda s: shorten(s, 42))
            fig_go = px.bar(
                go_top, x="neg_log10_p", y="简称", color="来源", orientation="h",
                color_discrete_map={"GO:BP": SAGE, "GO:MF": TEAL, "GO:CC": AMBER},
                hover_data={"简称": False, "通路/功能名称": True, "命中基因数": True, "校正P值": ":.2e", "命中基因": True},
                title="GO 功能富集（BP / MF / CC 各 Top 5）",
                labels={"neg_log10_p": "-log10(校正P值)", "简称": "", "来源": ""},
            )
            fig_go.update_layout(
                yaxis={"categoryorder": "total ascending", "dtick": 1},
                legend={"orientation": "h", "y": 1.09, "x": 1, "xanchor": "right"},
            )
            style_fig(fig_go, height=450, margin={"l": 15, "r": 20, "t": 55, "b": 35})
            st.plotly_chart(fig_go, width="stretch")

        st.subheader("完整 GO / KEGG 富集结果表")
        src_filter = st.multiselect("按来源筛选", ["KEGG", "GO:BP", "GO:MF", "GO:CC"], default=["KEGG", "GO:BP"])
        sub_e = enrich_df[enrich_df["来源"].isin(src_filter)] if src_filter else enrich_df
        st.dataframe(
            sub_e.drop(columns=["neg_log10_p"]).head(60).style.format({"校正P值": "{:.2e}", "GeneRatio": "{:.3f}"}),
            hide_index=True,
            width="stretch",
            height=340,
        )
        if st.download_button("⬇️ 下载完整 GO/KEGG 富集 CSV", enrich_df.to_csv(index=False).encode("utf-8-sig"),
                              file_name=f"{fname}_{dis_label}_GO_KEGG.csv", mime="text/csv"):
            log_event("网络药理学", "report_exported", {"type": "enrichment", "formula": fname})

        if not kegg.empty:
            insight_box(
                "<strong>机制洞察：</strong>核心交集靶点最显著富集的 KEGG 通路为 "
                + "、".join(f"<strong>{row._3}</strong> (p={row.校正P值:.2e})" for row in kegg.head(3).itertuples())
                + "，提示该方可能通过多成分协同调控上述信号通路发挥作用。"
            )

with tab4:
    kegg_s = enrich_df[enrich_df["来源"] == "KEGG"].head(8) if not enrich_df.empty else pd.DataFrame()
    if kegg_s.empty:
        st.info("需要至少 1 条显著 KEGG 通路才能绘制四层桑基图。")
    else:
        pw_gene_pairs = []
        for row in kegg_s.itertuples():
            pw = row._3
            for gname in [x.strip() for x in row.命中基因.split("、") if x.strip()]:
                pw_gene_pairs.append((gname, pw))
        pw_genes = {g for g, _ in pw_gene_pairs}
        ranked_genes = [g for g in (hubs["靶点"].tolist() if not hubs.empty else ov_tbl["靶点基因"].tolist()) if g in pw_genes][:10]
        if not ranked_genes:
            ranked_genes = sorted(pw_genes)[:10]
        gene_set = set(ranked_genes)

        sub_hct = hc_ct[hc_ct["gene"].isin(gene_set)].copy()
        top_comps = sub_hct.groupby("Molecule_name")["gene"].nunique().sort_values(ascending=False).head(10).index.tolist()
        sub_hct = sub_hct[sub_hct["Molecule_name"].isin(top_comps)]

        l1 = sorted(sub_hct["herb"].unique())
        l2 = sorted(sub_hct["Molecule_name"].unique())
        l3 = sorted(sub_hct["gene"].unique())
        l4_full = [row._3 for row in kegg_s.itertuples() if any(g in l3 for g in row.命中基因.split("、"))]

        # 精简第 2、4 层显示标签，防止跨越列间碰撞，悬停仍展示完整名
        raw_nodes = l1 + l2 + l3 + l4_full
        disp_labels = (
            l1
            + [shorten(m, 22) for m in l2]
            + l3
            + [shorten(pw, 28) for pw in l4_full]
        )
        idx_map = {name: i for i, name in enumerate(raw_nodes)}
        colors = [SAGE] * len(l1) + [TEAL] * len(l2) + [TERRA] * len(l3) + ["#7c628c"] * len(l4_full)

        def layer_y(n: int) -> list[float]:
            if n <= 1:
                return [0.5]
            return [0.06 + i * (0.88 / (n - 1)) for i in range(n)]

        node_x = [0.01] * len(l1) + [0.27] * len(l2) + [0.55] * len(l3) + [0.80] * len(l4_full)
        node_y = layer_y(len(l1)) + layer_y(len(l2)) + layer_y(len(l3)) + layer_y(len(l4_full))

        src_i, tgt_i, vals = [], [], []
        for h, m in sub_hct[["herb", "Molecule_name"]].drop_duplicates().itertuples(index=False):
            src_i.append(idx_map[h]); tgt_i.append(idx_map[m]); vals.append(1)
        for m, gname in sub_hct[["Molecule_name", "gene"]].drop_duplicates().itertuples(index=False):
            src_i.append(idx_map[m]); tgt_i.append(idx_map[gname]); vals.append(1)
        for gname, pw in pw_gene_pairs:
            if gname in idx_map and pw in idx_map:
                src_i.append(idx_map[gname]); tgt_i.append(idx_map[pw]); vals.append(1)

        sankey = go.Figure(go.Sankey(
            arrangement="fixed",
            node={
                "label": disp_labels,
                "customdata": raw_nodes,
                "hovertemplate": "%{customdata}<extra></extra>",
                "color": colors,
                "x": node_x,
                "y": node_y,
                "pad": 16,
                "thickness": 15,
                "line": {"color": "white", "width": 0.8},
            },
            link={"source": src_i, "target": tgt_i, "value": vals, "color": "rgba(130,150,140,0.26)"},
        ))
        # 四列顶部清晰标题标注
        headers = [(0.01, "① 药材", SAGE), (0.27, "② 活性成分", TEAL), (0.55, "③ 核心靶点", TERRA), (0.80, "④ KEGG 通路", "#7c628c")]
        for hx, htext, hcol in headers:
            sankey.add_annotation(
                x=hx, y=1.06, xref="paper", yref="paper", text=f"<b>{htext}</b>",
                showarrow=False, xanchor="left", font={"size": 12.5, "color": hcol},
            )
        style_fig(sankey, height=620, margin={"l": 10, "r": 160, "t": 55, "b": 15})
        st.plotly_chart(sankey, width="stretch")

st.warning(
    "⚠️ **方法边界与科研声明**：网络药理学属于计算预测方法，受限于文献与数据库覆盖度，所有靶点与通路结果仅作科研机制假设，须经实验验证，不构成临床诊疗建议。"
)
