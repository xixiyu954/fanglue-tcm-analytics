import plotly.express as px
import streamlit as st

from core.db import tables
from core.tracking import track_page_view
from core.ui import SAGE, TEAL, metric_card, style_fig

track_page_view("首页")
t = tables()

st.title("🌿 方略 · 中药方剂配伍与网络药理平台")
st.caption("面向中医药专业学生与科研新手的数据分析工作台 —— 仅供学习与科研辅助，不提供诊疗建议")

q = t["quality"].set_index("check_item")["value"]
c1, c2, c3, c4 = st.columns(4)
metric_card(c1, "标准药材库（味）", f'{int(q["药材主表数量"]):,}', "SymMap v2.0 + 中国药典")
metric_card(c2, "方剂总数（首）", f'{int(q["方剂总数量"]):,}', "184 经典 + 4,360 中成药")
metric_card(c3, "标准化规则（条）", f'{int(q["药名标准化规则数"]):,}', f'{int(q["方剂-药材组成记录"]):,} 条组成记录')
metric_card(c4, "成分—靶点关系（条）", f'{int(q.get("实验成分-靶点关系", 0)):,}',
            f'{int(q.get("具名活性化合物数", 0)):,} 个具名化合物')

st.subheader("平台模块导览")
nav = [
    ("🩺 方剂体检", "任意方剂四气五味与归经画像、十八反/十九畏/马兜铃酸警示、全库相似方比对与报告导出。"),
    ("🔗 配伍规律挖掘", "经典名方与 4,360 首中成药一键切换：帕累托、类 TF-IDF 特异性用药、Apriori 规则与 Louvain 社区。"),
    ("🧩 方剂聚类", "基于 Jaccard 药物组成的层次聚类与 MDS 投影，以 ARI 量化检验数据分组与教材分类的一致性。"),
    ("🏯 古方朝代演变", "跨东汉至清代 184 首经典名方：功效构成与寒热演变、流派验证及 Kruskal-Wallis / 卡方检验。"),
    ("🧬 网络药理学", "活性成分筛选（QED/OB/Lipinski）→ Open Targets 交集 → STRING PPI → g:Profiler 富集 → 四层桑基图。"),
    ("🧪 SQL 实验室 & 📈 用户行为", "只读运行 9 条面试向分析 SQL（CTE / 窗口函数 / 自连接 / 漏斗 / LAG）并追踪平台真实转化与回访。"),
]
cards_html = "".join(
    f'<div class="nav-card"><div class="nav-card-title">{k}</div><div class="nav-card-desc">{v}</div></div>'
    for k, v in nav
)
st.markdown(f'<div class="nav-grid">{cards_html}</div>', unsafe_allow_html=True)

st.subheader("数据分布概况")
scope = st.radio("统计队列", ["经典名方 (184)", "现代中成药 (4,360)", "全部 (4,544)"], horizontal=True)
f_df = t["formula"]
if scope.startswith("经典"):
    f_sub = f_df[f_df["formula_type"] == "经典名方"]
elif scope.startswith("现代"):
    f_sub = f_df[f_df["formula_type"] == "现代中成药"]
else:
    f_sub = f_df

l, r = st.columns(2)
cat = f_sub["category"].value_counts().rename_axis("类别").reset_index(name="方剂数")
fig_cat = px.bar(
    cat, x="方剂数", y="类别", orientation="h", text="方剂数",
    title=f"{scope} · 各类别方剂数量", color_discrete_sequence=[SAGE],
)
fig_cat.update_traces(textposition="outside", cliponaxis=False)
fig_cat.update_layout(yaxis={"categoryorder": "total ascending", "dtick": 1, "title": ""}, xaxis={"title": "方剂数"})
style_fig(fig_cat, height=max(420, 24 * len(cat) + 90), margin={"l": 10, "r": 35, "t": 45, "b": 35})
l.plotly_chart(fig_cat, width="stretch")

if scope.startswith("现代"):
    fh_sub = t["formula_herb"][t["formula_herb"]["formula"].isin(f_sub["formula"])]
    size_dist = fh_sub.groupby("formula").size().rename("药味数").reset_index()
    fig_r = px.histogram(
        size_dist, x="药味数", nbins=24, title="现代中成药单方药味数分布",
        color_discrete_sequence=[TEAL], labels={"count": "方剂数"},
    )
    fig_r.update_layout(yaxis_title="方剂数")
    style_fig(fig_r, height=max(420, 24 * len(cat) + 90), margin={"l": 10, "r": 20, "t": 45, "b": 35})
else:
    dyn = (
        f_df[f_df["formula_type"] == "经典名方"]
        .groupby(["dynasty_order", "dynasty"])
        .size()
        .reset_index(name="方剂数")
        .sort_values("dynasty_order")
    )
    fig_r = px.bar(
        dyn, x="dynasty", y="方剂数", text="方剂数",
        title="经典名方 · 各朝代分布", labels={"dynasty": ""},
        color_discrete_sequence=[TEAL],
        category_orders={"dynasty": dyn["dynasty"].tolist()},
    )
    fig_r.update_traces(textposition="outside", cliponaxis=False)
    style_fig(fig_r, height=max(420, 24 * len(cat) + 90), margin={"l": 10, "r": 20, "t": 45, "b": 35})
r.plotly_chart(fig_r, width="stretch")

st.subheader("数据治理与质量报告")
st.caption("ETL 流水线（etl/build_db.py）自动生成：记录中成药同名不同剂型去重、别名标准化与异常校验结果")
q_df = t["quality"].rename(columns={"check_item": "检查项", "value": "数量", "detail": "治理明细"})
st.dataframe(
    q_df,
    width="stretch",
    height="content",
    hide_index=True,
    column_config={
        "检查项": st.column_config.TextColumn("检查项", width="medium"),
        "数量": st.column_config.NumberColumn("数量", format="localized", width="small"),
        "治理明细": st.column_config.TextColumn("治理明细", width="large"),
    },
)

with st.expander("查看药名别名与炮制标准化映射表（1,251 条）"):
    kw = st.text_input("搜索别名或标准药名", placeholder="例如：炙甘草、银花、半夏")
    al = t["alias"]
    if kw.strip():
        al = al[al["alias"].str.contains(kw.strip()) | al["herb"].str.contains(kw.strip())]
    st.dataframe(
        al.head(200).rename(columns={"alias": "原始名称", "herb": "标准名", "processing": "炮制/部位", "note": "说明"}),
        width="stretch",
        hide_index=True,
    )

with st.expander("数据来源与开源许可声明"):
    st.markdown("""
| 数据层 | 来源 | 许可 / 用途 |
|---|---|---|
| 药材主库（736 味） | [SymMap v2.0](http://www.symmap.org/) (`SMHB`) +《中国药典》/《中药学》 | 学术开放下载（Wu et al., *NAR* 2019） |
| 经典名方（184 首） | 《方剂学》七版规划教材整理（参考 [TCM.Skill](https://github.com/YuanZHAO321/TCM.Skill)） | CC BY-NC 4.0（非商业学习研究） |
| 药典中成药 & 成分靶点 | [TCM-MKG](https://zenodo.org/records/23202835) (`D2/D4/D6/D9/D12/D13/D14/D17`) + SymMap `SMIT` | CC-BY-NC-4.0（Zenodo 开放科学库） |
| 疾病靶点 | [Open Targets Platform](https://platform.opentargets.org/) GraphQL API | 开放公共 API |
| 蛋白互作 PPI | [STRING v12.5](https://string-db.org/) REST API | CC BY 4.0 学术公共 API |
| GO / KEGG 富集 | [g:Profiler](https://biit.cs.ut.ee/gprofiler/) REST API | 开放公共生物信息 API |
""")
