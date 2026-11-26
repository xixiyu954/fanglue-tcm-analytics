import streamlit as st

from core.db import SQL_DIR, load_sql_file, run_readonly
from core.tracking import log_event, track_page_view

track_page_view("SQL实验室")

st.title("🧪 SQL 实验室")
st.caption("项目中所有面试向分析 SQL 均存放在 sql/ 目录（覆盖 CTE、窗口函数、索引自连接提升度、漏斗与 LAG 回访），支持在线只读运行")

files = sorted(p.name for p in SQL_DIR.glob("*.sql"))
tab1, tab2, tab3 = st.tabs(["📂 项目分析 SQL (9 条)", "✍️ 自由只读查询", "🗂️ 数据字典 (13 张表)"])

with tab1:
    name = st.selectbox("选择 SQL 文件", files)
    sql = load_sql_file(name)
    st.code(sql, language="sql")
    if st.button("▶ 运行查询", key="run_file", type="primary"):
        try:
            df = run_readonly(sql)
            st.success(f"查询成功，返回 {len(df)} 行")
            st.dataframe(df, width="stretch", hide_index=True)
            log_event("SQL实验室", "sql_run", {"file": name})
        except Exception as e:
            st.error(str(e))

with tab2:
    sql = st.text_area(
        "输入 SELECT / WITH 只读查询",
        "SELECT herb, category, nature, flavors, meridians, dose_min, dose_max\n"
        "FROM herb\n"
        "WHERE meridians LIKE '%脾%' AND dose_max IS NOT NULL\n"
        "ORDER BY herb\n"
        "LIMIT 25;",
        height=180,
    )
    if st.button("▶ 运行查询", key="run_free", type="primary"):
        try:
            df = run_readonly(sql)
            st.success(f"查询成功，返回 {len(df)} 行")
            st.dataframe(df, width="stretch", hide_index=True)
            log_event("SQL实验室", "sql_run", {"file": "free"})
        except Exception as e:
            st.error(str(e))

with tab3:
    st.markdown("""
| 表名 | 粒度 | 关键字段 | 说明 |
|---|---|---|---|
| `herb` | 一味药材一行 | herb, category, nature, nature_score, flavors, meridians, toxicity, dose_min, dose_max, pregnancy, pinyin, latin_name | 736 味标准药材主表（SymMap v2.0 + 药典） |
| `herb_flavor` | 药材 × 五味 | herb, flavor | 第一范式拆分的五味长表 |
| `herb_meridian` | 药材 × 归经 | herb, meridian | 第一范式拆分的归经长表 |
| `formula` | 一首方剂一行 | formula, formula_type, source, dynasty, dynasty_order, category, indication | 4,544 首方剂（经典名方 + 剂型去重中成药） |
| `formula_herb` | 方剂 × 药材 | formula, herb_raw, herb, processing, dose_g, name_normalized | 44,843 条组成明细（保留原始名与炮制方式） |
| `alias` | 一条别名一行 | alias, herb, processing, note | 1,251 条药名标准化映射规则 |
| `incompat_pair` | 一对禁忌药对 | rule_type, herb_a, herb_b | 十八反 / 十九畏展开药对 |
| `data_quality` | 一项质量检查 | check_item, value, detail | ETL 自动生成的数据治理报告 |
| `np_compound` | 一个化合物 | cid, InChIKey, Molecule_name, Molecular_Formula, PubChem_CID, TCMSP_id, OB_score, QED, MolWt, MolLogP, TPSA, lipinski_pass | 2,153 个具名活性化合物（TCM-MKG + SymMap） |
| `np_herb_compound` | 药材 × 化合物 | herb, cid | 20,694 条药材—活性成分关系（覆盖 605 味药） |
| `np_compound_target` | 化合物 × 基因 | cid, gene | 77,177 条实验验证成分—靶点基因关系 |
| `np_disease_target` | 疾病 × 基因 | disease_zh, disease_en, efo_id, gene, score | Open Targets 预置 12 种常见研究疾病靶点 |
| `events` | 一次用户行为 | event_id, session_id, ts, page, event, detail | 平台自身匿名埋点日志（漏斗与回访分析） |
""")
