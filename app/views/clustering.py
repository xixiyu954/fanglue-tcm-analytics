import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from scipy.cluster.hierarchy import fcluster, leaves_list, linkage
from scipy.spatial.distance import pdist, squareform
from sklearn.manifold import MDS
from sklearn.metrics import adjusted_rand_score

from core.db import tables
from core.tracking import log_event, track_page_view
from core.ui import HERBAL_QUAL, insight_box, metric_card, style_fig

track_page_view("方剂聚类")
t = tables()

st.title("🧩 方剂聚类")
st.caption("分析问题：仅凭『药物组成』能否把经典名方自然分组？数据驱动的分组与《方剂学》教材分类一致到什么程度？")

classic = t["formula"][t["formula"]["formula_type"] == "经典名方"].copy()
all_cats = sorted(classic["category"].unique())

with st.sidebar:
    st.header("聚类范围与参数")
    sel_cats = st.multiselect(
        "选择功效类别（留空则纳入全部 184 首经典名方）",
        all_cats,
        default=["解表剂", "清热剂", "补益剂", "理血剂", "祛湿剂"],
        help="选择 4–6 类方剂时相似度热力图与 MDS 投影最清晰；留空可对全部 184 首做全局检验",
    )
    method = st.selectbox("层次聚类连接方式", ["average", "complete", "single"], index=0)

sub_f = classic[classic["category"].isin(sel_cats)] if sel_cats else classic
fh = t["formula_herb"][t["formula_herb"]["formula"].isin(sub_f["formula"])]
mat = pd.crosstab(fh["formula"], fh["herb"]).clip(upper=1)
labels = sub_f.set_index("formula").loc[mat.index, "category"]

if len(mat) < 4:
    st.warning("选定方剂少于 4 首，请扩大类别范围")
    st.stop()

with st.sidebar:
    k = st.slider("聚类数 k", 2, min(20, len(mat) - 1), min(int(labels.nunique()), len(mat) - 1))

dist = pdist(mat.values.astype(bool), metric="jaccard")
Z = linkage(dist, method=method)
clusters = fcluster(Z, k, criterion="maxclust")
ari = adjusted_rand_score(labels, clusters)

if st.session_state.get("_last_cluster") != (tuple(sel_cats), method, k):
    st.session_state["_last_cluster"] = (tuple(sel_cats), method, k)
    log_event("方剂聚类", "cluster_run", {"n_formulas": len(mat), "method": method, "k": k})

c1, c2, c3, c4 = st.columns(4)
metric_card(c1, "矩阵维度", f"{mat.shape[0]} × {mat.shape[1]}", "方剂数 × 药材数")
metric_card(c2, "教材类别数", f"{int(labels.nunique())} 类")
metric_card(c3, "当前聚类数 k", f"{k} 簇", f"连接方式：{method}")
metric_card(c4, "调整兰德指数 ARI", f"{ari:.3f}", "1 = 完全一致，0 ≈ 随机")

l, r = st.columns(2)
order = leaves_list(Z)
sim = 1 - squareform(dist)
names = mat.index[order]
hm = px.imshow(
    pd.DataFrame(sim[np.ix_(order, order)], index=names, columns=names),
    color_continuous_scale="YlGn",
    title="方剂 Jaccard 相似度矩阵（按聚类树排序）",
    labels={"color": "Jaccard"},
)
if len(names) > 65:
    hm.update_xaxes(showticklabels=False).update_yaxes(showticklabels=False)
style_fig(hm, height=580, margin={"l": 10, "r": 10, "t": 45, "b": 20})
l.plotly_chart(hm, width="stretch")

coords = MDS(
    n_components=2, metric="precomputed", init="classical_mds", random_state=0, normalized_stress="auto"
).fit_transform(squareform(dist))
emb = pd.DataFrame(coords, columns=["x", "y"], index=mat.index)
emb["教材类别"] = labels
emb["聚类"] = [f"簇{c}" for c in clusters]
emb["方剂"] = emb.index
color_by = r.radio("散点着色维度", ["教材类别", "聚类"], horizontal=True)
fig_mds = px.scatter(
    emb, x="x", y="y", color=color_by,
    text="方剂" if len(emb) <= 60 else None,
    hover_data=["方剂", "教材类别", "聚类"],
    color_discrete_sequence=HERBAL_QUAL,
    title="MDS 二维投影（越近表示药材组成越相似）",
)
fig_mds.update_layout(xaxis_visible=False, yaxis_visible=False, legend_title_text="")
if len(emb) <= 60:
    fig_mds.update_traces(textposition="top center", textfont_size=9)
style_fig(fig_mds, height=540, margin={"l": 10, "r": 10, "t": 45, "b": 15})
r.plotly_chart(fig_mds, width="stretch")

st.subheader("聚类簇 × 教材类别 交叉检验")
ct = pd.crosstab(pd.Series([f"簇{c}" for c in clusters], index=mat.index, name="聚类"), labels.rename("教材类别"))
st.dataframe(ct, width="stretch", height="content")

members = emb.groupby("聚类").agg(
    方剂数=("方剂", "count"),
    主要教材类别=("教材类别", lambda s: s.mode().iat[0]),
    代表方剂=("方剂", lambda s: "、".join(s.head(12)) + (f" 等{len(s)}首" if len(s) > 12 else "")),
)
st.dataframe(members, width="stretch", height="content")
insight_box(
    f"<strong>洞察：</strong>当前 {len(mat)} 首经典名方的调整兰德指数 <strong>ARI = {ari:.3f}</strong>。"
    "同源类方（如四君子汤—参苓白术散—补中益气汤、桂枝汤—小建中汤—当归四逆汤、六味地黄丸—肾气丸）会紧密聚在同簇；"
    "跨类别聚到一起的方剂则量化印证了方剂学中<strong>『同药异用、异病同治』</strong>的配伍规律。"
)
