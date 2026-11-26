"""ETL：data/raw/* → 清洗 / 标准化 / 索引 → SQLite 数据库 data/fanglue.db

支持命令行运行 (`python etl/build_db.py`)，也可由应用启动时自动调用（便于云端零配置部署）。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "fanglue.db"

# 四气量化（分析假设，可在报告中讨论敏感性）
NATURE_SCORE = {
    "大寒": -3, "寒": -2, "凉": -1, "微寒": -1, "平": 0,
    "微温": 1, "温": 2, "热": 2.5, "大热": 3,
}
DYNASTY_ORDER = {
    "先秦两汉": 0, "东汉": 1, "晋南北朝": 2, "唐": 3, "宋": 4,
    "金": 5, "元": 6, "明": 7, "清": 8, "现代": 9,
}


def split_multi(df: pd.DataFrame, key: str, col: str, new_col: str) -> pd.DataFrame:
    """把 'a|b|c' 形式的多值字段拆成长表（第一范式）。"""
    out = df[[key, col]].dropna().copy()
    out = out[out[col].astype(str).str.strip() != ""]
    out[new_col] = out[col].astype(str).str.split("|")
    out = out.explode(new_col)[[key, new_col]]
    out[new_col] = out[new_col].str.strip()
    return out[out[new_col] != ""].drop_duplicates().reset_index(drop=True)


def build_database(db_path: Path = DB_PATH, verbose: bool = True) -> pd.DataFrame:
    herbs = pd.read_csv(RAW / "herbs.csv", dtype={"toxicity": str, "pregnancy": str})
    formulas = pd.read_csv(RAW / "formulas.csv")
    fh = pd.read_csv(RAW / "formula_herbs.csv")
    aliases = pd.read_csv(RAW / "aliases.csv").fillna("")
    incompat = pd.read_csv(RAW / "incompatibility.csv")

    # ---------- 1. 基础清洗 ----------
    for df in (herbs, formulas, fh, aliases):
        for c in df.select_dtypes(include=["object", "string"]):
            df[c] = df[c].fillna("").astype(str).str.strip()
    if "formula_type" not in formulas.columns:
        formulas["formula_type"] = "经典名方"
    for col in ("pinyin", "latin_name", "data_source"):
        if col not in herbs.columns:
            herbs[col] = ""
    herbs["nature_score"] = herbs["nature"].map(NATURE_SCORE).fillna(0.0)
    formulas["dynasty_order"] = formulas["dynasty"].map(DYNASTY_ORDER).fillna(99).astype(int)

    # ---------- 2. 药名标准化（保留原名与炮制信息） ----------
    alias_map = aliases.drop_duplicates("alias").set_index("alias")
    if "herb" not in fh.columns:
        fh["herb"] = fh["herb_raw"].map(alias_map["herb"]).fillna(fh["herb_raw"])
    else:
        fh["herb"] = fh["herb"].replace("", pd.NA).fillna(fh["herb_raw"].map(alias_map["herb"])).fillna(fh["herb_raw"])
    if "processing" not in fh.columns:
        fh["processing"] = fh["herb_raw"].map(alias_map["processing"]).fillna("")
    else:
        fh["processing"] = fh["processing"].replace("", pd.NA).fillna(fh["herb_raw"].map(alias_map["processing"])).fillna("")
    fh["name_normalized"] = (fh["herb"] != fh["herb_raw"]).astype(int)

    # ---------- 3. 规则展开：十八反 / 十九畏 → 两两药对 ----------
    pairs = []
    for r in incompat.itertuples():
        for a in str(r.group_a).split("|"):
            for b in str(r.group_b).split("|"):
                pairs.append((r.rule_type, a.strip(), b.strip()))
    incompat_pair = pd.DataFrame(pairs, columns=["rule_type", "herb_a", "herb_b"]).drop_duplicates()

    # ---------- 4. 网络药理学数据（若存在） ----------
    has_np = (RAW / "np_compounds.csv.gz").exists()
    np_comp = pd.read_csv(RAW / "np_compounds.csv.gz") if has_np else pd.DataFrame()
    np_hc = pd.read_csv(RAW / "np_herb_compound.csv.gz") if has_np else pd.DataFrame()
    np_ct = pd.read_csv(RAW / "np_compound_target.csv.gz") if has_np else pd.DataFrame()
    np_dt = pd.read_csv(RAW / "np_disease_targets.csv.gz") if (RAW / "np_disease_targets.csv.gz").exists() else pd.DataFrame()

    # ---------- 5. 数据质量检查 ----------
    known = set(herbs["herb"])
    unmatched = sorted(set(fh["herb"]) - known)
    merged = fh.merge(herbs[["herb", "dose_min", "dose_max"]], on="herb", how="left")
    over = merged[merged["dose_g"].notna() & merged["dose_max"].notna() & (merged["dose_g"] > merged["dose_max"])]
    meta_path = RAW / "etl_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    q_rows = [
        ("药材主表数量", len(herbs), f"含药典用量 {int(herbs['dose_max'].notna().sum())} 味，妊娠标注 {int((herbs['pregnancy'] != '').sum())} 味"),
        ("方剂总数量", len(formulas), f"经典名方 {int((formulas['formula_type'] == '经典名方').sum())} 首 + 现代中成药 {int((formulas['formula_type'] == '现代中成药').sum())} 首"),
        ("中成药剂型去重效果", meta.get("tcm_mkg_kept_dedup", 0),
         f"TCM-MKG 原始 {meta.get('tcm_mkg_total_cpm', 0)} 条 → 口服 {meta.get('tcm_mkg_oral_cpm', 0)} 条 → 剂型去重且药材匹配≥80% 后保留 {meta.get('tcm_mkg_kept_dedup', 0)} 首" if meta else ""),
        ("方剂-药材组成记录", len(fh), f"其中含现代折算剂量记录 {int(fh['dose_g'].notna().sum())} 条"),
        ("药名标准化规则数", len(aliases), f"原始药名 {fh['herb_raw'].nunique()} 种 → 标准化后 {fh['herb'].nunique()} 种（命中 {int(fh['name_normalized'].sum())} 条记录）"),
        ("未匹配到药材库的药名", len(unmatched), "、".join(unmatched[:20])),
        ("重复的方剂-药材记录", int(fh.duplicated(["formula", "herb"]).sum()), ""),
        ("没有组成的方剂", len(set(formulas["formula"]) - set(fh["formula"])), ""),
        ("经典方超药典上限记录", len(over),
         "、".join(f"{r.formula}-{r.herb}({r.dose_g:g}g>{r.dose_max:g}g)" for r in over.head(12).itertuples()) + (f" 等共 {len(over)} 条" if len(over) > 12 else "")),
    ]
    if has_np:
        q_rows.extend([
            ("网络药理覆盖药材", int(np_hc["herb"].nunique()), f"覆盖全部药材的 {np_hc['herb'].nunique()/len(herbs):.1%}"),
            ("具名活性化合物数", len(np_comp), f"来源 TCM-MKG + SymMap v2.0（含 OB 值 {int(np_comp['OB_score'].notna().sum())} 个）"),
            ("实验成分-靶点关系", len(np_ct), f"覆盖 {int(np_ct['gene'].nunique()):,} 个人类基因靶点，药材-成分关系 {len(np_hc):,} 条"),
        ])
    quality = pd.DataFrame(q_rows, columns=["check_item", "value", "detail"])

    # ---------- 6. 写入 SQLite ----------
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        herbs.to_sql("herb", con, if_exists="replace", index=False)
        split_multi(herbs, "herb", "flavors", "flavor").to_sql("herb_flavor", con, if_exists="replace", index=False)
        split_multi(herbs, "herb", "meridians", "meridian").to_sql("herb_meridian", con, if_exists="replace", index=False)
        formulas.to_sql("formula", con, if_exists="replace", index=False)
        fh[["formula", "herb_raw", "herb", "processing", "dose_g", "name_normalized"]].to_sql(
            "formula_herb", con, if_exists="replace", index=False
        )
        aliases.to_sql("alias", con, if_exists="replace", index=False)
        incompat_pair.to_sql("incompat_pair", con, if_exists="replace", index=False)
        quality.to_sql("data_quality", con, if_exists="replace", index=False)

        if has_np:
            np_comp.to_sql("np_compound", con, if_exists="replace", index=False)
            np_hc.to_sql("np_herb_compound", con, if_exists="replace", index=False)
            np_ct.to_sql("np_compound_target", con, if_exists="replace", index=False)
        if not np_dt.empty:
            np_dt.to_sql("np_disease_target", con, if_exists="replace", index=False)

        con.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                ts         TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                page       TEXT,
                event      TEXT NOT NULL,
                detail     TEXT
            );
            CREATE TABLE IF NOT EXISTS mp_user (
                user_hash     TEXT PRIMARY KEY,
                register_date TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                channel_scene TEXT NOT NULL,
                inviter_hash  TEXT DEFAULT '',
                exp_group     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mp_quiz_log (
                log_id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_hash          TEXT NOT NULL,
                ts                 TEXT NOT NULL,
                exp_group          TEXT NOT NULL,
                formula            TEXT NOT NULL,
                category           TEXT DEFAULT '',
                q_type             TEXT NOT NULL,
                chosen             TEXT DEFAULT '',
                distractor_max_sim REAL DEFAULT 0,
                is_correct         INTEGER NOT NULL,
                duration_ms        INTEGER DEFAULT 0,
                is_review          INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS mp_event (
                event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                user_hash   TEXT NOT NULL,
                session_id  TEXT DEFAULT '',
                ts          TEXT NOT NULL,
                page        TEXT DEFAULT '',
                event       TEXT NOT NULL,
                exp_group   TEXT DEFAULT '',
                params_json TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS mp_share (
                share_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_hash TEXT NOT NULL,
                invitee_hash TEXT NOT NULL,
                card_type    TEXT DEFAULT 'formula_card',
                ts           TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fh_formula ON formula_herb(formula);
            CREATE INDEX IF NOT EXISTS idx_fh_herb ON formula_herb(herb);
            CREATE INDEX IF NOT EXISTS idx_f_type ON formula(formula_type);
            CREATE INDEX IF NOT EXISTS idx_mpq_user ON mp_quiz_log(user_hash);
            CREATE INDEX IF NOT EXISTS idx_mpe_user ON mp_event(user_hash);
        """)
        if has_np:
            con.executescript("""
                CREATE INDEX IF NOT EXISTS idx_nphc_herb ON np_herb_compound(herb);
                CREATE INDEX IF NOT EXISTS idx_nphc_cid ON np_herb_compound(cid);
                CREATE INDEX IF NOT EXISTS idx_npct_cid ON np_compound_target(cid);
                CREATE INDEX IF NOT EXISTS idx_npct_gene ON np_compound_target(gene);
            """)
        if not np_dt.empty:
            con.execute("CREATE INDEX IF NOT EXISTS idx_npdt_disease ON np_disease_target(disease_zh);")

    if verbose:
        print(f"数据库已生成：{db_path} ({db_path.stat().st_size / 1024 / 1024:.2f} MB)")
        print(quality.to_string(index=False))
    if unmatched:
        raise SystemExit(f"存在未匹配药名，请补充 aliases.csv 或 herbs.csv：{unmatched[:20]}")
    return quality


if __name__ == "__main__":
    build_database()
