"""核心分析逻辑：方剂解析、体检（含马兜铃酸警示）、相似方、关联规则、共现网络、特异性用药。"""
from __future__ import annotations

import re
from collections import Counter
from itertools import combinations

import networkx as nx
import pandas as pd

from core.db import formula_herb_sets

TOKEN = re.compile(r"([\u4e00-\u9fa5]+)\s*(\d+(?:\.\d+)?)?\s*(?:g|G|克)?")
NATURE_ORDER = ["大寒", "寒", "微寒", "凉", "平", "微温", "温", "热", "大热"]
FLAVOR_ORDER = ["辛", "甘", "酸", "苦", "咸", "淡", "涩"]
MERIDIAN_ORDER = ["肺", "大肠", "胃", "脾", "心", "小肠", "膀胱", "肾", "心包", "三焦", "胆", "肝"]
ARISTOLOCHIC_HERBS = {"关木通", "广防己", "寻骨风", "青木香", "天仙藤", "马兜铃"}

PROC_PREFIXES = [
    ("姜汁炒", "姜制"), ("盐水炒", "盐制"), ("酒蒸", "酒蒸"), ("酥炙", "酥炙"), ("微炒", "微炒"),
    ("蜜炙", "蜜炙"), ("酒炒", "酒炒"), ("酒炙", "酒炙"), ("酒制", "酒制"), ("醋炙", "醋炙"),
    ("醋炒", "醋炒"), ("醋制", "醋制"), ("盐炙", "盐炙"), ("盐炒", "盐炒"), ("麸炒", "麸炒"),
    ("土炒", "土炒"), ("清炒", "炒"), ("炒焦", "炒焦"), ("姜炙", "姜制"), ("姜制", "姜制"),
    ("炙", "炙"), ("生", "生用"), ("炒", "炒"), ("焦", "炒焦"), ("酒", "酒制"), ("醋", "醋制"),
    ("盐", "盐制"), ("煅", "煅"), ("制", "炮制"), ("炮", "炮制"), ("煨", "煨"), ("鲜", "鲜用"),
]


# ---------------------------------------------------------------- 解析与标准化
def parse_formula_text(text: str, t: dict) -> pd.DataFrame:
    """把『人参9 白术9g，炙甘草6』解析为结构化组成，并做别名与炮制标准化。"""
    alias = t["alias"].drop_duplicates("alias").set_index("alias")
    known = set(t["herb"]["herb"])
    rows = []
    for name, dose in TOKEN.findall(text):
        herb, proc = name, ""
        if name in alias.index:
            herb = alias.at[name, "herb"]
            proc = alias.at[name, "processing"]
        elif name not in known:
            for pref, p in PROC_PREFIXES:
                if name.startswith(pref) and len(name) > len(pref) + 1:
                    base = name[len(pref):]
                    if base in known:
                        herb, proc = base, p
                        break
                    if base in alias.index:
                        herb, proc = alias.at[base, "herb"], p
                        break
        rows.append({
            "herb_raw": name,
            "herb": herb,
            "processing": proc,
            "dose_g": float(dose) if dose else None,
            "matched": herb in known,
        })
    df = pd.DataFrame(rows, columns=["herb_raw", "herb", "processing", "dose_g", "matched"])
    if not df.empty and df["dose_g"].isna().all():
        df["dose_g"] = 1.0  # 未给剂量时按等量处理
    return df


def formula_components(name: str, t: dict) -> pd.DataFrame:
    df = t["formula_herb"].query("formula == @name")[["herb_raw", "herb", "processing", "dose_g"]].copy()
    df["matched"] = True
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- 方剂体检
def profile(comp: pd.DataFrame, t: dict) -> dict:
    df = comp[comp["matched"]].merge(t["herb"], on="herb", how="left")
    has_dose = df["dose_g"].notna().any()
    df["dose_weight"] = df["dose_g"].fillna(df["dose_g"].median() if has_dose else 1.0)
    total = float(df["dose_weight"].sum())

    nature = df.groupby("nature")["dose_weight"].sum().div(total).reindex(NATURE_ORDER).dropna()
    heat_index = float((df["dose_weight"] * df["nature_score"]).sum() / total)

    # 将“微辛/微苦”等微味归入主五味汇总，便于雷达与柱图比较
    def share(long: pd.DataFrame, col: str, order: list[str], strip_micro: bool = False) -> pd.Series:
        m = long.merge(df[["herb", "dose_weight"]], on="herb")
        if strip_micro:
            m = m.copy()
            m[col] = m[col].str.replace("^微", "", regex=True)
            m = m.drop_duplicates(["herb", col])
        return m.groupby(col)["dose_weight"].sum().div(total).reindex(order).fillna(0)

    return {
        "detail": df,
        "has_dose": has_dose,
        "total_dose": float(df["dose_g"].sum()) if has_dose else None,
        "heat_index": heat_index,
        "nature": nature,
        "flavor": share(t["flavor"], "flavor", FLAVOR_ORDER, strip_micro=True),
        "meridian": share(t["meridian"], "meridian", MERIDIAN_ORDER),
    }


def heat_label(x: float) -> str:
    if x <= -1.5: return "偏寒凉（明显）"
    if x <= -0.5: return "偏寒凉"
    if x < 0.5:   return "寒热平和"
    if x < 1.5:   return "偏温热"
    return "偏温热（明显）"


def safety_check(comp: pd.DataFrame, t: dict) -> pd.DataFrame:
    herbs = set(comp["herb"])
    alerts = []
    for r in t["incompat"].itertuples():
        if r.herb_a in herbs and r.herb_b in herbs:
            alerts.append(("高", r.rule_type, f"{r.herb_a} 与 {r.herb_b} 属于{r.rule_type}配伍禁忌"))
    for h in sorted(herbs & ARISTOLOCHIC_HERBS):
        alerts.append(("高", "肾毒警示", f"{h} 属含马兜铃酸药材，存在明确肾毒性/致癌风险，现代临床多禁用或替代"))
    info = comp.merge(t["herb"], on="herb", how="inner")
    for r in info.itertuples():
        if r.toxicity:
            lvl = "高" if r.toxicity == "大毒" else "中"
            alerts.append((lvl, "毒性", f"{r.herb} 标注为『{r.toxicity}』，注意炮制、先煎与严格控量"))
        if r.pregnancy:
            lvl = "高" if r.pregnancy == "禁用" else "中"
            alerts.append((lvl, "妊娠", f"{r.herb}：孕妇{r.pregnancy}"))
        if pd.notna(r.dose_g) and pd.notna(r.dose_max) and r.dose_g > r.dose_max:
            alerts.append(("中", "剂量", f"{r.herb} {r.dose_g:g}g 高于药典常用量上限 {r.dose_max:g}g"))
        elif pd.notna(r.dose_g) and pd.notna(r.dose_min) and r.dose_g < r.dose_min and r.dose_g != 1.0:
            alerts.append(("低", "剂量", f"{r.herb} {r.dose_g:g}g 低于药典常用量下限 {r.dose_min:g}g"))
    out = pd.DataFrame(alerts, columns=["等级", "类型", "说明"])
    if not out.empty:
        rank = {"高": 0, "中": 1, "低": 2}
        out = out.assign(_r=out["等级"].map(rank)).sort_values(["_r", "类型"]).drop(columns="_r").reset_index(drop=True)
    return out


def similar_formulas(
    herbs: set[str], t: dict, top: int = 5, exclude: str | None = None, scope: str = "经典名方"
) -> pd.DataFrame:
    f_meta = t["formula"]
    if scope != "全部":
        valid = set(f_meta.loc[f_meta["formula_type"] == scope, "formula"])
    else:
        valid = set(f_meta["formula"])
    groups = formula_herb_sets()
    rows = []
    for name in valid:
        if name == exclude:
            continue
        s = groups.get(name)
        if not s:
            continue
        inter = herbs & s
        if not inter:
            continue
        rows.append({
            "方剂": name,
            "Jaccard相似度": len(inter) / len(herbs | s),
            "共有": "、".join(sorted(inter)),
            "该方多出": "、".join(sorted(s - herbs)) or "—",
            "该方缺少": "、".join(sorted(herbs - s)) or "—",
        })
    cols = ["方剂", "Jaccard相似度", "共有", "该方多出", "该方缺少"]
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows).sort_values("Jaccard相似度", ascending=False).head(top)
    return (
        out.merge(f_meta[["formula", "formula_type", "category", "dynasty"]], left_on="方剂", right_on="formula")
        .drop(columns="formula")
        .rename(columns={"formula_type": "来源", "category": "类别", "dynasty": "朝代"})
    )


# ---------------------------------------------------------------- 配伍规律挖掘
def transactions(fh: pd.DataFrame) -> list[frozenset]:
    return [frozenset(s) for s in fh.groupby("formula")["herb"].apply(set)]


def frequent_itemsets(trans: list[frozenset], min_support: float, max_len: int = 3, max_items: int = 80) -> pd.DataFrame:
    """Apriori：逐层生成候选项集并按最小支持度剪枝（大样本下限制高频候选数防组合爆炸）。"""
    n = len(trans)
    min_count = max(2, int(round(min_support * n + 1e-9)))
    counts = Counter(item for tr in trans for item in tr)
    top_level = sorted(((i, c) for i, c in counts.items() if c >= min_count), key=lambda x: -x[1])[:max_items]
    level = {frozenset([i]): c for i, c in top_level}
    result: dict[frozenset, int] = dict(level)
    k = 1
    while level and k < max_len:
        k += 1
        items = sorted({i for s in level for i in s})
        candidates = [
            frozenset(c) for c in combinations(items, k)
            if all(frozenset(sub) in level for sub in combinations(c, k - 1))
        ]
        # 仅扫描含至少 k 味候选药的事务，提升数千方剂时的执行速度
        cand_items = set(items)
        filtered_trans = [tr & cand_items for tr in trans]
        filtered_trans = [tr for tr in filtered_trans if len(tr) >= k]
        next_level: dict[frozenset, int] = {}
        for c in candidates:
            cnt = sum(1 for tr in filtered_trans if c <= tr)
            if cnt >= min_count:
                next_level[c] = cnt
        level = next_level
        result.update(level)
    return pd.DataFrame([{"itemset": s, "count": c, "support": c / n, "size": len(s)}
                         for s, c in result.items()])


def association_rules(itemsets: pd.DataFrame, n: int, min_conf: float) -> pd.DataFrame:
    if itemsets.empty:
        return pd.DataFrame(columns=["前项", "后项", "支持度", "置信度", "提升度", "共现方剂数"])
    sup = dict(zip(itemsets["itemset"], itemsets["support"]))
    rows = []
    for s, s_sup in sup.items():
        if len(s) < 2:
            continue
        for r in range(1, len(s)):
            for ante in combinations(sorted(s), r):
                a = frozenset(ante)
                c = s - a
                if a not in sup or c not in sup:
                    continue
                conf = s_sup / sup[a]
                if conf >= min_conf:
                    rows.append({
                        "前项": "+".join(sorted(a)),
                        "后项": "+".join(sorted(c)),
                        "支持度": s_sup,
                        "置信度": conf,
                        "提升度": conf / sup[c],
                        "共现方剂数": round(s_sup * n),
                    })
    cols = ["前项", "后项", "支持度", "置信度", "提升度", "共现方剂数"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols].sort_values(["提升度", "置信度"], ascending=False).reset_index(drop=True)


def specific_herbs(sub_fh: pd.DataFrame, full_fh: pd.DataFrame, min_count: int = 3) -> pd.DataFrame:
    """类 TF-IDF 特异性用药：计算某类别内使用率相对全库使用率的倍数（相对风险 / Lift）。"""
    n_sub = sub_fh["formula"].nunique()
    n_full = full_fh["formula"].nunique()
    if n_sub == 0 or n_full == 0 or n_sub == n_full:
        return pd.DataFrame()
    c_sub = sub_fh.groupby("herb")["formula"].nunique()
    c_full = full_fh.groupby("herb")["formula"].nunique()
    df = pd.DataFrame({"子集方剂数": c_sub, "全库方剂数": c_full}).fillna(0)
    df = df[df["子集方剂数"] >= min_count].copy()
    if df.empty:
        return pd.DataFrame()
    df["子集使用率"] = df["子集方剂数"] / n_sub
    df["全库使用率"] = df["全库方剂数"] / n_full
    df["特异性倍数"] = df["子集使用率"] / df["全库使用率"]
    return (
        df.sort_values(["特异性倍数", "子集方剂数"], ascending=False)
        .rename_axis("药材")
        .reset_index()
    )


def cooccurrence_graph(fh: pd.DataFrame, min_edge: int, max_nodes: int = 45) -> nx.Graph:
    g = nx.Graph()
    freq = fh.groupby("herb")["formula"].nunique()
    # 先保留频次最高的前 max_nodes 味药材，保证大规模中成药库的网络清晰可读
    keep = set(freq.sort_values(ascending=False).head(max_nodes).index)
    edge_cnt: Counter[tuple[str, str]] = Counter()
    for _, herbs in fh[fh["herb"].isin(keep)].groupby("formula")["herb"]:
        hs = sorted(set(herbs))
        for a, b in combinations(hs, 2):
            edge_cnt[(a, b)] += 1
    for (a, b), w in edge_cnt.items():
        if w >= min_edge:
            g.add_edge(a, b, weight=w)
    nx.set_node_attributes(g, {n: int(freq.get(n, 0)) for n in g.nodes}, "freq")
    if g.number_of_edges():
        comms = nx.community.louvain_communities(g, weight="weight", seed=42)
        for i, c in enumerate(sorted(comms, key=len, reverse=True)):
            for node in c:
                g.nodes[node]["community"] = i
    return g
