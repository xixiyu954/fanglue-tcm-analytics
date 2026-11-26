"""网络药理学分析引擎：
- 本地 SQLite（TCM-MKG + SymMap v2.0）：药材 → 活性成分（QED / OB / Lipinski 筛选）→ 实验靶点基因
- Open Targets Platform GraphQL API：预置 12 种常见疾病 + 任意疾病实时检索
- STRING 12.5 官方 REST API：人类 PPI 蛋白互作网络 + NetworkX 中心性筛选 Hub 核心靶点
- g:Profiler 官方 REST API：GO（BP/MF/CC）与 KEGG 通路富集分析
"""
from __future__ import annotations

import math

import networkx as nx
import pandas as pd
import requests
import streamlit as st
from scipy.stats import hypergeom

from core.db import query, query_cached

OPENTARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
STRING_URL = "https://string-db.org/api/json/network"
GPROFILER_URL = "https://biit.cs.ut.ee/gprofiler/api/gost/profile/"
BACKGROUND_GENES = 20000  # 人类编码基因背景数（用于超几何富集显著性检验）


@st.cache_data(show_spinner=False)
def cached_diseases() -> pd.DataFrame:
    return query_cached(
        "SELECT disease_zh, disease_en, efo_id, COUNT(*) AS n_targets "
        "FROM np_disease_target GROUP BY disease_zh, disease_en, efo_id ORDER BY disease_zh"
    )


@st.cache_data(show_spinner=False)
def get_cached_disease_targets(disease_zh: str) -> pd.DataFrame:
    return query_cached(
        "SELECT gene, score, efo_id, disease_en FROM np_disease_target WHERE disease_zh = ? ORDER BY score DESC",
        (disease_zh,),
    )


@st.cache_data(show_spinner=False, ttl=3600)
def search_opentargets_diseases(keyword: str) -> list[dict]:
    q = """
    query($q: String!) {
      search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: 8}) {
        hits { id name description }
      }
    }
    """
    r = requests.post(OPENTARGETS_URL, json={"query": q, "variables": {"q": keyword}}, timeout=15)
    r.raise_for_status()
    return r.json().get("data", {}).get("search", {}).get("hits", [])


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_opentargets_targets(efo_id: str, limit: int = 300) -> pd.DataFrame:
    q = """
    query($id: String!, $size: Int!) {
      disease(efoId: $id) {
        name
        associatedTargets(page: {index: 0, size: $size}) {
          rows { target { approvedSymbol } score }
        }
      }
    }
    """
    r = requests.post(OPENTARGETS_URL, json={"query": q, "variables": {"id": efo_id, "size": limit}}, timeout=20)
    r.raise_for_status()
    d = r.json().get("data", {}).get("disease") or {}
    rows = d.get("associatedTargets", {}).get("rows", [])
    return pd.DataFrame([
        {"gene": row["target"]["approvedSymbol"], "score": round(float(row["score"]), 4), "efo_id": efo_id}
        for row in rows
    ])


def screen_formula_compounds_targets(
    herbs: list[str],
    min_qed: float = 0.45,
    min_ob: float = 30.0,
    lipinski_only: bool = True,
    keep_missing_ob: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """按 ADME / 类药性阈值筛选方剂活性成分与实验靶点。"""
    if not herbs:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    placeholders = ",".join("?" * len(herbs))
    ob_cond = "(c.OB_score IS NULL OR c.OB_score >= ?)" if keep_missing_ob else "(c.OB_score >= ?)"
    lip_cond = "AND c.lipinski_pass = 1" if lipinski_only else ""

    hc_sql = f"""
        SELECT hc.herb, c.cid, c.Molecule_name, c.InChIKey, c.Molecular_Formula,
               c.PubChem_CID, c.TCMSP_id, c.OB_score, c.QED, c.MolWt, c.MolLogP, c.TPSA, c.lipinski_pass
        FROM np_herb_compound hc
        JOIN np_compound c ON c.cid = hc.cid
        WHERE hc.herb IN ({placeholders})
          AND c.QED >= ?
          AND {ob_cond}
          {lip_cond}
    """
    hc = query(hc_sql, tuple(herbs) + (min_qed, min_ob))
    if hc.empty:
        return hc, pd.DataFrame(), pd.DataFrame()

    cids = sorted(hc["cid"].unique().tolist())
    cid_ph = ",".join("?" * len(cids))
    ct = query(f"SELECT cid, gene FROM np_compound_target WHERE cid IN ({cid_ph})", tuple(cids))

    compounds = (
        hc.groupby(["cid", "Molecule_name", "Molecular_Formula", "OB_score", "QED", "MolWt", "MolLogP", "PubChem_CID", "TCMSP_id"], dropna=False)
        .agg(来源药材=("herb", lambda s: "、".join(sorted(set(s)))), 药材数=("herb", "nunique"))
        .reset_index()
    )
    tgt_counts = ct.groupby("cid")["gene"].nunique().rename("靶点数")
    compounds = compounds.merge(tgt_counts, on="cid", how="left").fillna({"靶点数": 0})
    compounds["靶点数"] = compounds["靶点数"].astype(int)
    compounds = compounds.sort_values(["药材数", "靶点数", "OB_score", "QED"], ascending=False).reset_index(drop=True)
    return hc, compounds, ct


def overlap_stats(formula_genes: set[str], disease_genes: set[str]) -> dict:
    """交集统计 + 超几何分布富集检验（评估方剂靶点与疾病靶点重合是否显著高于随机）。"""
    inter = formula_genes & disease_genes
    k = len(inter)
    M = BACKGROUND_GENES
    n = min(len(disease_genes), M)
    N = min(len(formula_genes), M)
    p_val = float(hypergeom.sf(k - 1, M, n, N)) if k > 0 else 1.0
    expected = (n * N / M) if M else 0.0
    fold = (k / expected) if expected > 0 else 0.0
    return {
        "n_formula": len(formula_genes),
        "n_disease": len(disease_genes),
        "n_overlap": k,
        "expected": expected,
        "fold_enrichment": fold,
        "p_value": p_val,
    }


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_string_ppi(genes: tuple[str, ...], min_score: int = 700) -> pd.DataFrame:
    """调用 STRING 12.5 官方 REST API 获取人类蛋白互作边。"""
    if len(genes) < 2:
        return pd.DataFrame(columns=["protein_a", "protein_b", "score"])
    r = requests.post(
        STRING_URL,
        data={
            "identifiers": "\r".join(genes),
            "species": 9606,
            "required_score": int(min_score),
            "caller_identity": "fanglue_tcm_analytics",
        },
        timeout=25,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        return pd.DataFrame(columns=["protein_a", "protein_b", "score"])
    rows = []
    seen = set()
    for e in data:
        a, b = e.get("preferredName_A", ""), e.get("preferredName_B", "")
        if not a or not b or a == b:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        rows.append({"protein_a": key[0], "protein_b": key[1], "score": round(float(e.get("score", 0)), 3)})
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


def build_ppi_graph_and_hubs(edges: pd.DataFrame) -> tuple[nx.Graph, pd.DataFrame]:
    g = nx.Graph()
    for r in edges.itertuples():
        g.add_edge(r.protein_a, r.protein_b, weight=r.score)
    if g.number_of_nodes() == 0:
        return g, pd.DataFrame(columns=["靶点", "Degree", "度中心性", "介数中心性", "紧密中心性"])
    dc = nx.degree_centrality(g)
    bc = nx.betweenness_centrality(g)
    cc = nx.closeness_centrality(g)
    hubs = pd.DataFrame([
        {
            "靶点": n,
            "Degree": int(g.degree(n)),
            "度中心性": round(dc[n], 3),
            "介数中心性": round(bc[n], 3),
            "紧密中心性": round(cc[n], 3),
        }
        for n in g.nodes
    ]).sort_values(["Degree", "介数中心性"], ascending=False).reset_index(drop=True)
    return g, hubs


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_gprofiler_enrichment(genes: tuple[str, ...], p_threshold: float = 0.05) -> pd.DataFrame:
    """调用 g:Profiler 官方 API 进行 GO (BP/MF/CC) 与 KEGG 富集分析（含每条通路命中的基因列表）。"""
    if len(genes) < 3:
        return pd.DataFrame()
    r = requests.post(
        GPROFILER_URL,
        json={
            "organism": "hsapiens",
            "query": list(genes),
            "sources": ["GO:BP", "GO:MF", "GO:CC", "KEGG"],
            "user_threshold": p_threshold,
            "no_evidences": False,
        },
        timeout=25,
    )
    r.raise_for_status()
    res = r.json().get("result", [])
    if not res:
        return pd.DataFrame()
    # g:Profiler 返回的 intersections 列表与 query 基因一一对应（非空列表表示命中）
    q_list = list(genes)
    rows = []
    for item in res:
        inters = item.get("intersections") or []
        hit_genes = [q_list[i] for i, ev in enumerate(inters) if i < len(q_list) and ev]
        pval = float(item.get("p_value", 1.0))
        rows.append({
            "来源": item.get("source", ""),
            "编号": item.get("native", ""),
            "通路/功能名称": item.get("name", ""),
            "命中基因数": int(item.get("intersection_size", len(hit_genes))),
            "通路总基因数": int(item.get("term_size", 0)),
            "GeneRatio": round(int(item.get("intersection_size", 0)) / max(1, int(item.get("query_size", len(genes)))), 3),
            "校正P值": pval,
            "neg_log10_p": round(-math.log10(max(pval, 1e-300)), 2),
            "命中基因": "、".join(hit_genes),
        })
    return pd.DataFrame(rows).sort_values("校正P值").reset_index(drop=True)
