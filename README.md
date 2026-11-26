# 🌿 方略 · 中药方剂配伍与网络药理学智能分析平台

> 面向中医药专业学生与科研新手的数据分析与网络药理学工作台：把「查药典—算规律—跑网络药理学—做统计检验—分析产品埋点」整合进一个可在线交互的数据产品。
> **声明**：仅供学习与科研辅助，不提供任何临床诊疗或用药建议。

---

## ✨ 核心亮点与数据规模

- **多源数据治理与标准化**：整合 **SymMap v2.0**、《中国药典》、《方剂学》七版与 **TCM-MKG (Zenodo)**，建成 **736 味标准药材**、**1,251 条别名/炮制标准化规则**、**4,544 首方剂**（184 首跨东汉—清经典名方 + 4,360 首药典口服中成药）与 **44,843 条组成记录**。
- **剂型去重与偏差控制**：识别出 TCM-MKG 原始 8,977 条中成药中大量『同名不同剂型（胶囊/颗粒/口服液/片/丸）』会虚增关联规则支持度，在 ETL 中完成剂型归一去重，清洗后保留 4,360 首独立处方并自动生成数据质量报告。
- **网络药理学一键流水线**：本地整合 **605 味药材 → 2,153 种具名活性成分（QED/OB/Lipinski）→ 77,177 条实验靶点关系**，实时对接 **Open Targets**（疾病靶点 + 超几何检验）、**STRING 12.5**（PPI 蛋白互作 + Hub 中心性）与 **g:Profiler**（GO/KEGG 富集），绘制「药材—成分—靶点—通路」四层桑基图，全流程每一步可下载 CSV。
- **业务分析 + 产品埋点双维度**：内置 9 条面试向分析 SQL（CTE、`RANK()`、`ROW_NUMBER()`、自连接提升度、转化漏斗、`LAG()` 回访），同时对平台自身埋点做漏斗与留存分析。

---

## 🏗️ 系统架构

```
data/raw/ (压缩 CSV，< 2 MB)
   │  herbs.csv (736) · aliases.csv (1,251) · formulas.csv (4,544) · formula_herbs.csv (44,843)
   │  np_compounds / np_herb_compound / np_compound_target (77,177) / np_disease_targets (3,600)
   ▼
etl/build_db.py ──▶ data/fanglue.db (SQLite 13 张表 + 索引，冷启动 4 秒自动构建)
   │
   ├── sql/01..09 (*.sql) ───────────────────▶ 🧪 SQL 实验室（只读查询 + 数据字典）
   ├── app/core/analysis.py ─────────────────▶ 🩺 方剂体检 · 🔗 配伍规律 · 🧩 方剂聚类 · 🏯 朝代演变
   ├── app/core/netpharm.py (+ 3 国际 API) ──▶ 🧬 网络药理学一键分析（Open Targets / STRING / g:Profiler）
   └── app/core/tracking.py ─────────────────▶ 📈 用户行为漏斗与回访分析
```

---

## 🚀 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python etl/build_db.py          # 可选：首次启动 streamlit 时也会自动构建
streamlit run streamlit_app.py
```

公网免费部署（Streamlit Community Cloud / Hugging Face Spaces）见 [DEPLOY.md](DEPLOY.md)。

---

## 📊 八大功能模块与分析方法

| 模块 | 回答的分析问题 | 核心方法 / 指标 |
|---|---|---|
| 🌿 数据总览与质量报告 | 数据规模、清洗前后对比、治理透明度 | 缺失率、别名归一率、中成药剂型去重统计 |
| 🩺 方剂体检 | 性味归经结构如何？是否存在配伍/毒性风险？ | 剂量加权寒热指数、归经雷达、十八反/十九畏/马兜铃酸/妊娠校验、Jaccard 相似方 |
| 🔗 配伍规律挖掘 | 核心药物、类别特异性用药与稳定药对是什么？ | 帕累托、类 TF-IDF 特异性倍数、Apriori（支持度/置信度/提升度）、Louvain 社区发现 |
| 🧩 方剂聚类 | 药物组成聚类与教材功效分类一致吗？ | Jaccard 距离、层次聚类、MDS 二维投影、调整兰德指数（ARI） |
| 🏯 古方朝代演变 | 东汉至清代用药寒热与类别演变是否印证学术流派？ | 时期寒热趋势、窗口函数 Top5、Kruskal-Wallis 与卡方独立性检验 |
| 🧬 网络药理学 | 方剂可能通过哪些活性成分、核心靶点与通路起效？ | QED/OB/Lipinski 筛选、超几何显著性检验、STRING PPI + Hub 拓扑、g:Profiler GO/KEGG、四层桑基图 |
| 🧪 SQL 实验室 | 如何用 SQL 完成多表聚合、自连接共现与漏斗留存？ | 9 条生产级只读 SQL + 13 张表完整数据字典 |
| 📈 用户行为分析 | 用户在哪里流失？哪些模块最受欢迎？ | 匿名埋点事件表 → 4 步转化漏斗、页面偏好、日活与 `LAG()` 回访 |

---

## 📝 简历项目描述参考

> **「方略」中药方剂配伍与网络药理学分析平台**｜独立搭建｜在线地址：`https://xxx.streamlit.app`
> - **数据治理与建模**：整合 SymMap v2.0、《方剂学》经典名方及 TCM-MKG 公开数据，建立 13 张规范化 SQLite 数据表，编写 1,251 条别名/炮制品标准化规则，并对 8,977 条原始中成药完成同名不同剂型去重（清洗至 4,360 首独立处方），沉淀 736 味药材、4,544 首方剂、44,843 条组成及 77,177 条实验成分—靶点关系。
> - **统计挖掘与可视化**：基于 SQL（CTE、窗口函数、自连接）与 Python 实现帕累托、类 TF-IDF 特异性用药、Apriori 关联规则、Louvain 社区发现、层次聚类（ARI 验证）及跨东汉—清朝代寒热演变的 Kruskal-Wallis / 卡方检验。
> - **跨学科专业壁垒**：搭建网络药理学一键流水线，联动 Open Targets、STRING 12.5 与 g:Profiler 公共 API，将传统跨 5+ 网站手动搬运流程压缩至秒级，输出超几何富集显著性、PPI 核心靶点与四层调控桑基图。
> - **产品埋点与增长分析**：设计匿名事件埋点表并部署公网，使用 SQL 漏斗与 `LAG()` 回访分析追踪用户转化瓶颈并迭代交互体验。

---

## 📚 数据来源与许可

- **SymMap v2.0**（Wu et al., *Nucleic Acids Research* 2019）：药材主表（`SMHB`）及化合物名称与口服生物利用度（`SMIT`）。
- **TCM-MKG**（Zenodo [23202835](https://zenodo.org/records/23202835)，CC-BY-NC-4.0）：药典口服中成药组成及实验验证的饮片—化合物—靶点基因映射。
- **《方剂学》七版经典名方整理**（参考 [YuanZHAO321/TCM.Skill](https://github.com/YuanZHAO321/TCM.Skill)，CC BY-NC 4.0）。
- **Open Targets Platform**、**STRING v12.5**、**g:Profiler**：实时调用公开学术生物信息 API。
