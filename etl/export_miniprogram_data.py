"""从 data/fanglue.db 导出微信小程序轻量数据模块到 miniprogram/data/*.js。

输出（总计约 200 KB，远低于微信小程序 2 MB 主包上限）：
  - miniprogram/data/herbs.js     736 味《中国药典》标准药材（四气五味归经、毒性、妊娠、用量、马兜铃酸）
  - miniprogram/data/formulas.js  184 首经典名方（含组成、寒热指数、预计算 Top 4 Jaccard 相似方干扰项）
  - miniprogram/data/rules.js     常用别名标准化映射、十八反/十九畏规则、马兜铃酸警示列表

运行：python etl/export_miniprogram_data.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "fanglue.db"
MP_DATA = ROOT / "wechat-miniprogram" / "miniprogram" / "data"
ARISTOLOCHIC = {"关木通", "广防己", "寻骨风", "青木香", "天仙藤", "马兜铃"}


def write_js_module(path: Path, payload, comment: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"// {comment}\n// 由 etl/export_miniprogram_data.py 自动生成，请勿手工修改\nmodule.exports = "
    text += json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit("请先运行 python etl/build_db.py 生成数据库")

    with sqlite3.connect(DB_PATH) as con:
        herbs = pd.read_sql_query("SELECT * FROM herb ORDER BY category, herb", con)
        formulas = pd.read_sql_query(
            "SELECT * FROM formula WHERE formula_type = '经典名方' ORDER BY category, dynasty_order, formula", con
        )
        fh = pd.read_sql_query("SELECT * FROM formula_herb", con)
        aliases = pd.read_sql_query("SELECT alias, herb, processing FROM alias", con)
        incompat = pd.read_sql_query("SELECT rule_type, herb_a, herb_b FROM incompat_pair", con)

    # ---------- 1. 药材主表（736 味） ----------
    herb_score = dict(zip(herbs["herb"], herbs["nature_score"].fillna(0.0)))
    herb_list = []
    for r in herbs.itertuples():
        item = {
            "n": r.herb,
            "c": r.category,
            "t": r.nature,
            "s": float(r.nature_score) if pd.notna(r.nature_score) else 0.0,
            "f": [x for x in str(r.flavors).split("|") if x],
            "m": [x for x in str(r.meridians).split("|") if x],
        }
        if r.toxicity:
            item["tx"] = r.toxicity
        if r.pregnancy:
            item["p"] = r.pregnancy
        if pd.notna(r.dose_min) and pd.notna(r.dose_max):
            item["d"] = [round(float(r.dose_min), 3), round(float(r.dose_max), 3)]
        if r.herb in ARISTOLOCHIC:
            item["aa"] = 1
        herb_list.append(item)

    # ---------- 2. 经典名方（184 首）+ 预计算 Jaccard Top 4 相似方 ----------
    classic_names = set(formulas["formula"])
    cfh = fh[fh["formula"].isin(classic_names)].copy()
    fh_by_f: dict[str, list[list]] = {}
    sets_by_f: dict[str, set[str]] = {}
    for fname, grp in cfh.groupby("formula"):
        rows = []
        s = set()
        for r in grp.itertuples():
            d = round(float(r.dose_g), 2) if pd.notna(r.dose_g) else None
            rows.append([r.herb, d, r.herb_raw])
            s.add(r.herb)
        fh_by_f[fname] = rows
        sets_by_f[fname] = s

    formula_list = []
    for idx, r in enumerate(formulas.itertuples(), start=1):
        comp = fh_by_f.get(r.formula, [])
        if len(comp) < 2:
            continue
        # 剂量加权寒热指数
        weights = [c[1] if (c[1] is not None and c[1] > 0) else 1.0 for c in comp]
        tot = sum(weights) or 1.0
        hi = round(sum(w * herb_score.get(c[0], 0.0) for c, w in zip(comp, weights)) / tot, 2)

        # 计算与其余 183 首经典方的 Jaccard 相似度，保留 Top 4 供“相似方辨析”和“方剂体检”秒级调用
        s0 = sets_by_f[r.formula]
        sims = []
        for other, s1 in sets_by_f.items():
            if other == r.formula:
                continue
            inter = s0 & s1
            if not inter:
                continue
            jac = len(inter) / len(s0 | s1)
            sims.append((jac, other, sorted(s1 - s0), sorted(s0 - s1)))
        sims.sort(key=lambda x: (-x[0], x[1]))
        top_sim = [[o, round(j, 3), more[:6], less[:6]] for j, o, more, less in sims[:4]]

        formula_list.append({
            "id": idx,
            "n": r.formula,
            "src": r.source,
            "dyn": r.dynasty,
            "cat": r.category,
            "ind": str(r.indication)[:90],
            "hi": hi,
            "h": comp,
            "sim": top_sim,
        })

    # ---------- 3. 规则表（别名 + 十八反/十九畏 + 马兜铃酸） ----------
    # 保留所有别名到标准名映射（优先经典常用别名，全部 1251 条压缩后仅约 25 KB）
    alias_map = {}
    for r in aliases.itertuples():
        if r.alias and r.herb and r.alias != r.herb:
            alias_map[r.alias] = [r.herb, r.processing] if r.processing else r.herb
    rules_payload = {
        "aliases": alias_map,
        "incompat": [[r.rule_type, r.herb_a, r.herb_b] for r in incompat.itertuples()],
        "aristolochic": sorted(ARISTOLOCHIC),
    }

    s1 = write_js_module(MP_DATA / "herbs.js", herb_list, f"标准中药材库（{len(herb_list)} 味）")
    s2 = write_js_module(MP_DATA / "formulas.js", formula_list, f"经典名方与 Jaccard 相似矩阵（{len(formula_list)} 首）")
    s3 = write_js_module(MP_DATA / "rules.js", rules_payload, "药名别名映射、十八反/十九畏及马兜铃酸规则")
    print(f"herbs.js: {len(herb_list)} 味 ({s1/1024:.1f} KB)")
    print(f"formulas.js: {len(formula_list)} 首 ({s2/1024:.1f} KB)")
    print(f"rules.js: {len(alias_map)} 条别名 + {len(incompat)} 条禁忌 ({s3/1024:.1f} KB)")
    print(f"小程序数据总体积: {(s1+s2+s3)/1024:.1f} KB")


if __name__ == "__main__":
    main()
