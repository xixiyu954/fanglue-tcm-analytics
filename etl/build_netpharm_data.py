"""从 TCM-MKG (Zenodo 23202835) + SymMap v2.0 + Open Targets API 构建网络药理学数据层。

输出到 data/raw/（gzip 压缩 CSV，总计 < 3 MB，便于 Git 管理与云端部署自动建库）：
  - np_compounds.csv.gz        化合物主表（名称、分子式、MW、QED、LogP、TPSA、HBD/HBA、OB、Lipinski）
  - np_herb_compound.csv.gz    药材 → 化合物
  - np_compound_target.csv.gz  化合物 → 靶点基因（GeneSymbol）
  - np_disease_targets.csv.gz  预置 12 种常见疾病的 Open Targets 真实靶点（应用内亦支持实时查询任意疾病）

运行：python etl/build_netpharm_data.py
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EXT = ROOT / "data" / "external"

DISEASES = [
    ("2型糖尿病", "type 2 diabetes mellitus"),
    ("溃疡性结肠炎", "ulcerative colitis"),
    ("支气管哮喘", "asthma"),
    ("原发性高血压", "hypertension"),
    ("冠心病", "coronary artery disease"),
    ("类风湿关节炎", "rheumatoid arthritis"),
    ("非酒精性脂肪性肝病", "metabolic dysfunction-associated steatotic liver disease"),
    ("慢性胃炎", "gastritis"),
    ("抑郁症", "unipolar depression"),
    ("缺血性脑卒中", "ischemic stroke"),
    ("特应性皮炎", "atopic dermatitis"),
    ("慢性阻塞性肺疾病", "chronic obstructive pulmonary disease"),
]


def fetch_opentargets_disease(query_en: str, limit: int = 300) -> tuple[str, str, list[tuple[str, float]]]:
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    q1 = """
    query($q: String!) {
      search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: 3}) {
        hits { id name }
      }
    }
    """
    r1 = requests.post(url, json={"query": q1, "variables": {"q": query_en}}, timeout=15)
    r1.raise_for_status()
    hits = r1.json()["data"]["search"]["hits"]
    if not hits:
        return "", "", []
    efo_id, ename = hits[0]["id"], hits[0]["name"]
    q2 = """
    query($id: String!, $size: Int!) {
      disease(efoId: $id) {
        associatedTargets(page: {index: 0, size: $size}) {
          rows { target { approvedSymbol } score }
        }
      }
    }
    """
    r2 = requests.post(url, json={"query": q2, "variables": {"id": efo_id, "size": limit}}, timeout=20)
    r2.raise_for_status()
    rows = r2.json()["data"]["disease"]["associatedTargets"]["rows"]
    return efo_id, ename, [(row["target"]["approvedSymbol"], round(float(row["score"]), 4)) for row in rows]


def build_herb_compound_target() -> None:
    herbs = pd.read_csv(RAW / "herbs.csv")
    all_herbs = set(herbs["herb"])

    d6 = pd.read_csv(EXT / "tcm_mkg" / "D6_Chinese_herbal_pieces.tsv", sep="\t")
    d9 = pd.read_csv(EXT / "tcm_mkg" / "D9_CHP_InChIKey.tsv", sep="\t")
    d12 = pd.read_csv(
        EXT / "tcm_mkg" / "D12_InChIKey.tsv", sep="\t",
        usecols=["InChIKey", "Molecular_Formula", "QED", "MolWt", "TPSA", "MolLogP", "NumHAcceptors", "NumHDonors"],
    )
    d13 = pd.read_csv(EXT / "tcm_mkg" / "D13_InChIKey_EntrezID.tsv", sep="\t")
    d14 = pd.read_csv(EXT / "tcm_mkg" / "D14_InChIKey_SourceID.tsv", sep="\t")
    d17 = pd.read_csv(
        EXT / "tcm_mkg" / "D17_Target_Symbol_Mapping.tsv", sep="\t",
        usecols=["UniProtID", "GeneSymbol", "EntrezID"],
    )
    smit = pd.read_excel(
        EXT / "symmap" / "SMIT.xlsx",
        usecols=["Molecule_name", "PubChem_CID", "OB_score", "TCMSP_id"],
    )

    # 1. 饮片名/同义词 → 本库标准药名
    chp_to_herb: dict[str, str] = {}
    for r in d6.itertuples():
        name = str(r.Chinese_herbal_pieces).strip()
        if name in all_herbs:
            chp_to_herb[r.CHP_ID] = name
        elif pd.notna(r.Chinese_synonyms):
            for syn in str(r.Chinese_synonyms).split("|"):
                syn = syn.strip()
                if syn in all_herbs:
                    chp_to_herb[r.CHP_ID] = syn
                    break

    hc = d9[d9["CHP_ID"].isin(chp_to_herb)].copy()
    hc["herb"] = hc["CHP_ID"].map(chp_to_herb)
    hc = hc[["herb", "InChIKey"]].drop_duplicates()

    # 2. InChIKey → PubChem_CID (via STITCH) → SymMap SMIT 名称 & OB_score
    stitch = d14[d14["Source"] == "STITCH"].copy()
    stitch["PubChem_CID"] = stitch["SourceID"].str.replace(r"^CID[sm]0*", "", regex=True)
    smit_c = smit.dropna(subset=["PubChem_CID"]).copy()
    smit_c["PubChem_CID"] = smit_c["PubChem_CID"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    smit_c = smit_c.sort_values("OB_score", ascending=False).drop_duplicates("PubChem_CID")
    ik_name = stitch.merge(smit_c, on="PubChem_CID", how="inner").drop_duplicates("InChIKey")[
        ["InChIKey", "PubChem_CID", "Molecule_name", "OB_score", "TCMSP_id"]
    ]

    # 3. 关联分子性质 D12，过滤基础无机/极小分子及超大非类药分子 (120 <= MolWt <= 1000)
    comp = ik_name.merge(d12.drop_duplicates("InChIKey"), on="InChIKey", how="inner")
    comp = comp[comp["InChIKey"].isin(set(hc["InChIKey"]))].copy()
    comp = comp[(comp["MolWt"] >= 120) & (comp["MolWt"] <= 1000)].copy()

    # 计算 Lipinski 五规则违背数
    lip_viol = (
        (comp["MolWt"] > 500).astype(int)
        + (comp["MolLogP"] > 5).astype(int)
        + (comp["NumHDonors"] > 5).astype(int)
        + (comp["NumHAcceptors"] > 10).astype(int)
    )
    comp["lipinski_pass"] = (lip_viol <= 1).astype(int)

    # 4. 关联实验靶点 D13 + D17，并去除极端泛靶点（> 300 靶点的非特异性分子，减少背景噪声）
    d17_c = d17.dropna(subset=["GeneSymbol", "EntrezID"]).drop_duplicates("EntrezID").copy()
    d17_c["EntrezID"] = d17_c["EntrezID"].astype(int)
    ct = d13[d13["InChIKey"].isin(set(comp["InChIKey"]))].drop_duplicates()
    ct = ct.merge(d17_c[["EntrezID", "GeneSymbol"]], on="EntrezID", how="inner")[
        ["InChIKey", "GeneSymbol"]
    ].drop_duplicates()

    tgt_cnt = ct.groupby("InChIKey")["GeneSymbol"].nunique()
    valid_ik = set(tgt_cnt[(tgt_cnt >= 1) & (tgt_cnt <= 300)].index)

    # 为压缩体积同时覆盖全部 600+ 药材，使用紧凑自增 integer cid 主键
    comp = comp[comp["InChIKey"].isin(valid_ik)].sort_values(["OB_score", "QED"], ascending=False).reset_index(drop=True)
    comp.insert(0, "cid", range(1, len(comp) + 1))
    ik_to_cid = dict(zip(comp["InChIKey"], comp["cid"]))

    hc_out = hc[hc["InChIKey"].isin(ik_to_cid)].copy()
    hc_out["cid"] = hc_out["InChIKey"].map(ik_to_cid)
    hc_out = hc_out[["herb", "cid"]].drop_duplicates().sort_values(["herb", "cid"])

    ct_out = ct[ct["InChIKey"].isin(ik_to_cid)].copy()
    ct_out["cid"] = ct_out["InChIKey"].map(ik_to_cid)
    ct_out = ct_out[["cid", "GeneSymbol"]].rename(columns={"GeneSymbol": "gene"}).drop_duplicates().sort_values(["cid", "gene"])

    # 数值列保留合理精度减小体积
    for col in ("QED", "MolWt", "TPSA", "MolLogP", "OB_score"):
        comp[col] = comp[col].round(3)

    comp_cols = [
        "cid", "InChIKey", "Molecule_name", "Molecular_Formula", "PubChem_CID",
        "TCMSP_id", "OB_score", "QED", "MolWt", "MolLogP", "TPSA", "lipinski_pass",
    ]
    comp[comp_cols].to_csv(RAW / "np_compounds.csv.gz", index=False, compression="gzip")
    hc_out.to_csv(RAW / "np_herb_compound.csv.gz", index=False, compression="gzip")
    ct_out.to_csv(RAW / "np_compound_target.csv.gz", index=False, compression="gzip")

    print(f"np_compounds: {len(comp):,} ({(RAW/'np_compounds.csv.gz').stat().st_size/1024:.1f} KB)")
    print(f"np_herb_compound: {len(hc_out):,} edges across {hc_out['herb'].nunique()} herbs ({(RAW/'np_herb_compound.csv.gz').stat().st_size/1024:.1f} KB)")
    print(f"np_compound_target: {len(ct_out):,} edges across {ct_out['gene'].nunique():,} genes ({(RAW/'np_compound_target.csv.gz').stat().st_size/1024:.1f} KB)")


def build_disease_targets() -> None:
    rows = []
    for zh, en in DISEASES:
        try:
            efo_id, ename, tgts = fetch_opentargets_disease(en, limit=300)
            for gene, score in tgts:
                rows.append({
                    "disease_zh": zh, "disease_en": ename, "efo_id": efo_id, "gene": gene, "score": score
                })
            print(f"OpenTargets {zh} ({efo_id} {ename}): {len(tgts)} targets")
            time.sleep(0.2)
        except Exception as e:
            print(f"WARN OpenTargets {zh}: {e}")
    df = pd.DataFrame(rows)
    df.to_csv(RAW / "np_disease_targets.csv.gz", index=False, compression="gzip")
    print(f"np_disease_targets: {len(df):,} rows ({(RAW/'np_disease_targets.csv.gz').stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    build_herb_compound_target()
    build_disease_targets()
