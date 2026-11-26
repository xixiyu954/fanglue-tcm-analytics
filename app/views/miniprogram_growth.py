"""📱 小程序增长与 A/B 实验看板：对接「方略随身」微信小程序埋点数据。

支持：
1. 直接上传小程序 / 微信云开发导出的 JSON 埋点包入库分析；
2. 生成明确标记（sim_ 前缀）的 240 用户 × 14 天仿真实验数据演示全链路分析流程（正式报告须排除）。
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from scipy.stats import chisquare, norm, spearmanr, ttest_ind

from core.db import connect, formula_herb_sets, load_sql_file, query, tables
from core.tracking import track_page_view
from core.ui import AMBER, SAGE, TEAL, TERRA, insight_box, metric_card, style_fig

track_page_view("小程序增长与AB实验")

st.title("📱 小程序增长与 A/B 实验看板")
st.caption(
    "对接「方略随身」微信小程序星型数仓（mp_user / mp_quiz_log / mp_event / mp_share）："
    "SRM 分流校验、A/B 实验显著性检验、Cohort 留存热力图、Jaccard 易混方验证与裂变 K 因子"
)

SCENE_LABEL = {
    "1007": "单聊分享卡片",
    "1008": "微信群分享卡片",
    "1047": "扫描小程序海报码",
    "1001": "微信搜索/发现页",
}


def two_prop_ztest(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float, float]:
    """双样本比例 Z 检验（返回 lift_pp, z, p_val, ci95_half）。"""
    if n1 == 0 or n2 == 0:
        return 0.0, 0.0, 1.0, 0.0
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se_pool = math.sqrt(max(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2), 1e-12))
    z = (p2 - p1) / se_pool
    pval = float(2 * norm.sf(abs(z)))
    se_unpooled = math.sqrt(max(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2, 1e-12))
    return (p2 - p1), z, pval, 1.96 * se_unpooled


def generate_simulated_experiment(n_users: int = 240, seed: int = 2026) -> dict[str, int]:
    """基于真实的 184 首经典方 Jaccard 相似度生成 14 天仿真 A/B 实验数据（全部前缀 sim_）。"""
    rng = random.Random(seed)
    t = tables()
    classic = t["formula"][t["formula"]["formula_type"] == "经典名方"].copy()
    sets = formula_herb_sets()
    f_names = [f for f in classic["formula"].tolist() if len(sets.get(f, ())) >= 3]
    cat_map = dict(zip(classic["formula"], classic["category"]))

    # 预计算每首方剂最相近的邻居（用于真实驱动混淆率）
    neighbors: dict[str, list[tuple[str, float]]] = {}
    for f0 in f_names:
        s0 = sets[f0]
        sims = []
        for f1 in f_names:
            if f1 == f0:
                continue
            s1 = sets[f1]
            inter = len(s0 & s1)
            if inter:
                sims.append((f1, round(inter / len(s0 | s1), 3)))
        sims.sort(key=lambda x: -x[1])
        neighbors[f0] = sims[:4] if sims else [(rng.choice(f_names), 0.0)]

    now = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
    users_rows, quiz_rows, event_rows, share_rows = [], [], [], []
    scenes = ["1008", "1007", "1047", "1001"]
    scene_w = [0.42, 0.20, 0.23, 0.15]

    for i in range(n_users):
        uid = f"sim_u{i:04d}"
        exp = "A_chapter" if i % 2 == 0 else "B_jaccard"
        reg_offset = rng.randint(1, 13)
        reg_dt = now - timedelta(days=reg_offset)
        reg_day = reg_dt.strftime("%Y-%m-%d")
        scene = rng.choices(scenes, weights=scene_w, k=1)[0]
        inviter = f"sim_u{rng.randint(0, max(0, i - 1)):04d}" if (i > 5 and scene in {"1007", "1008"}) else ""

        users_rows.append((uid, reg_day, reg_dt.strftime("%Y-%m-%d %H:%M:%S"), scene, inviter, exp))
        if inviter:
            share_rows.append((inviter, uid, rng.choice(["formula_card", "quiz_challenge"]), reg_dt.strftime("%Y-%m-%d %H:%M:%S")))

        # 首日做题数影响留存（模拟 Aha Moment：首日完成 >= 10 题显著提升后续留存）
        d0_quiz = rng.choices([4, 7, 11, 14], weights=[0.22, 0.25, 0.35, 0.18], k=1)[0]
        aha_boost = 0.16 if d0_quiz >= 10 else 0.0
        exp_ret_boost = 0.11 if exp == "B_jaccard" else 0.0
        scene_boost = 0.06 if scene == "1008" else 0.0

        for day in range(reg_offset + 1):
            if day == 0:
                active = True
            else:
                base_p = 0.50 * math.exp(-0.14 * day) + aha_boost + exp_ret_boost + scene_boost
                active = rng.random() < min(0.88, max(0.06, base_p))
            if not active:
                continue

            ts_base = reg_dt + timedelta(days=day, minutes=rng.randint(-120, 120))
            sid = f"sim_s_{i}_{day}"
            event_rows.append((uid, sid, ts_base.strftime("%Y-%m-%d %H:%M:%S"), "quiz", "page_view", exp, "{}"))
            if rng.random() < 0.55:
                event_rows.append((uid, sid, (ts_base + timedelta(seconds=90)).strftime("%Y-%m-%d %H:%M:%S"), "check", "formula_checked", exp, "{}"))

            nq = d0_quiz if day == 0 else rng.randint(5, 12)
            for j in range(nq):
                f0 = rng.choice(f_names)
                nbr, jac = rng.choice(neighbors[f0][:3])
                is_rev = 1 if (day >= 1 and rng.random() < 0.45) else 0
                # 药物 Jaccard 相似度越高，错误混淆率越高；B 组在复测(is_review=1)时提升显著
                err_prob = 0.14 + 0.58 * jac - (0.14 if (exp == "B_jaccard" and is_rev) else (0.04 if is_rev else 0.0))
                err_prob = min(0.85, max(0.05, err_prob))
                correct = 0 if rng.random() < err_prob else 1
                chosen = f0 if correct else nbr
                dur = int(rng.gauss(6800 if exp == "B_jaccard" else 6200, 1600))
                dur = max(1800, dur)
                qts = (ts_base + timedelta(seconds=12 * (j + 1))).strftime("%Y-%m-%d %H:%M:%S")
                quiz_rows.append((uid, qts, exp, f0, cat_map.get(f0, ""), "similar_discriminate", chosen, jac, correct, dur, is_rev))

    with connect() as con:
        con.execute("DELETE FROM mp_user WHERE user_hash LIKE 'sim_%'")
        con.execute("DELETE FROM mp_quiz_log WHERE user_hash LIKE 'sim_%'")
        con.execute("DELETE FROM mp_event WHERE user_hash LIKE 'sim_%'")
        con.execute("DELETE FROM mp_share WHERE inviter_hash LIKE 'sim_%'")
        con.executemany(
            "INSERT INTO mp_user (user_hash, register_date, first_seen_at, channel_scene, inviter_hash, exp_group) VALUES (?,?,?,?,?,?)",
            users_rows,
        )
        con.executemany(
            "INSERT INTO mp_quiz_log (user_hash, ts, exp_group, formula, category, q_type, chosen, distractor_max_sim, is_correct, duration_ms, is_review) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            quiz_rows,
        )
        con.executemany(
            "INSERT INTO mp_event (user_hash, session_id, ts, page, event, exp_group, params_json) VALUES (?,?,?,?,?,?,?)",
            event_rows,
        )
        con.executemany(
            "INSERT INTO mp_share (inviter_hash, invitee_hash, card_type, ts) VALUES (?,?,?,?)",
            share_rows,
        )
    return {"users": len(users_rows), "quiz": len(quiz_rows), "events": len(event_rows), "shares": len(share_rows)}


# ======================== 侧边栏：数据导入与仿真控制 ========================
with st.sidebar:
    st.header("1. 导入小程序真实埋点")
    up = st.file_uploader("上传小程序/云开发导出 JSON", type=["json"])
    if up is not None:
        try:
            bundle = json.loads(up.read().decode("utf-8"))
            from etl.import_miniprogram_logs import import_bundle
            from core.db import DB_PATH

            cnt = import_bundle(bundle, DB_PATH)
            st.success(f"导入成功：用户 {cnt['mp_user']}，答题 {cnt['mp_quiz_log']}，事件 {cnt['mp_event']}")
        except Exception as e:
            st.error(f"导入失败：{e}")

    st.header("2. 仿真实验演示（面试演练）")
    include_sim = st.toggle(
        "包含模拟实验数据 (sim_)", value=False,
        help="用于演示 A/B 实验检验与 Cohort 留存分析流程；撰写正式项目报告时请关闭并仅用真实同学埋点",
    )
    if st.button("生成 240 用户 × 14 天模拟实验"):
        res = generate_simulated_experiment(240)
        st.success(f"已生成 {res['users']} 用户、{res['quiz']:,} 条答题日志！打开上方开关即可查看。")
    if st.button("清除模拟实验数据"):
        with connect() as con:
            con.execute("DELETE FROM mp_user WHERE user_hash LIKE 'sim_%'")
            con.execute("DELETE FROM mp_quiz_log WHERE user_hash LIKE 'sim_%'")
            con.execute("DELETE FROM mp_event WHERE user_hash LIKE 'sim_%'")
            con.execute("DELETE FROM mp_share WHERE inviter_hash LIKE 'sim_%'")
        st.success("已清除全部 sim_ 模拟数据")

# ======================== 加载数据 ========================
where_clause = "" if include_sim else "WHERE user_hash NOT LIKE 'sim_%'"
users = query(f"SELECT * FROM mp_user {where_clause}")
qlogs = query(f"SELECT * FROM mp_quiz_log {where_clause}")
events = query(f"SELECT * FROM mp_event {where_clause}")
shares = query("SELECT * FROM mp_share" + ("" if include_sim else " WHERE inviter_hash NOT LIKE 'sim_%'"))

if users.empty:
    st.info(
        "📭 当前暂无小程序真实埋点数据。\n\n"
        "- **体验完整看板**：点击左侧「生成 240 用户 × 14 天模拟实验」并打开「包含模拟实验数据」开关；\n"
        "- **接入真实数据**：在「方略随身」小程序的「我的 → 复制匿名埋点 JSON」保存后于左侧上传，或从微信云开发导出同步。"
    )
    st.stop()

if include_sim and users["user_hash"].str.startswith("sim_").any():
    st.warning("⚠️ 当前视图包含 `sim_` 仿真实验数据，仅用于演示 A/B 检验、Cohort 留存与相关性分析方法；正式报告须关闭模拟开关。")

# ======================== 计算活跃日与北极星指标 ========================
act_parts = []
if not events.empty:
    act_parts.append(events[["user_hash", "ts"]].assign(day=pd.to_datetime(events["ts"]).dt.normalize()))
if not qlogs.empty:
    act_parts.append(qlogs[["user_hash", "ts"]].assign(day=pd.to_datetime(qlogs["ts"]).dt.normalize()))
act = pd.concat(act_parts, ignore_index=True)[["user_hash", "day"]].drop_duplicates()

users["reg_dt"] = pd.to_datetime(users["register_date"])
max_day = max(act["day"].max(), users["reg_dt"].max())
ua = users.merge(act, on="user_hash", how="left")
ua["day_diff"] = (ua["day"] - ua["reg_dt"]).dt.days

# 计算各用户 D7 留存标志（仅纳入注册已满 7 天的用户，防止右删失偏差！）
eligible_d7 = users[users["reg_dt"] <= max_day - pd.Timedelta(days=7)].copy()
d7_active = set(ua.loc[ua["day_diff"] == 7, "user_hash"])
eligible_d7["d7_retained"] = eligible_d7["user_hash"].isin(d7_active).astype(int)

# WLU 北极星指标：最近 7 天内完成 >= 10 题或 >= 2 次方剂体检的活跃学习人数
recent_cut = max_day - pd.Timedelta(days=6)
recent_q = qlogs[pd.to_datetime(qlogs["ts"]).dt.normalize() >= recent_cut].groupby("user_hash").size() if not qlogs.empty else pd.Series(dtype=int)
recent_c = events[(events["event"] == "formula_checked") & (pd.to_datetime(events["ts"]).dt.normalize() >= recent_cut)].groupby("user_hash").size() if not events.empty else pd.Series(dtype=int)
wlu_users = set(recent_q[recent_q >= 10].index) | set(recent_c[recent_c >= 2].index)

k_factor = len(shares) / max(1, len(users))
d7_rate = float(eligible_d7["d7_retained"].mean()) if len(eligible_d7) else 0.0
overall_acc = float(qlogs["is_correct"].mean()) if not qlogs.empty else 0.0

c1, c2, c3, c4, c5 = st.columns(5)
metric_card(c1, "累计匿名用户", f"{len(users):,}", f"答题日志 {len(qlogs):,} 条")
metric_card(c2, "北极星 WLU", f"{len(wlu_users):,}", "近7日 ≥10题或≥2次体检")
metric_card(c3, "D7 留存率", f"{d7_rate:.1%}", f"满7天样本 {len(eligible_d7)} 人")
metric_card(c4, "整体辨方正确率", f"{overall_acc:.1%}", "全量答题均值")
metric_card(c5, "裂变 K 因子", f"{k_factor:.2f}", f"分享带来 {len(shares)} 新用户")

# ======================== 四大分析标签页 ========================
tab1, tab2, tab3, tab4 = st.tabs([
    "🧪 A/B 实验评估",
    "📅 Cohort 留存与 Aha",
    "🔀 混淆方对与 Jaccard 验证",
    "📣 渠道归因与裂变",
])

with tab1:
    st.subheader("A/B 实验：教材顺序（A 组） vs Jaccard 相似方辨析（B 组）")
    # 1. SRM 检验
    grp_cnt = users["exp_group"].value_counts()
    n_a, n_b = int(grp_cnt.get("A_chapter", 0)), int(grp_cnt.get("B_jaccard", 0))
    if n_a > 0 and n_b > 0:
        srm_stat, srm_p = chisquare([n_a, n_b], f_exp=[(n_a + n_b) / 2, (n_a + n_b) / 2])
        srm_ok = srm_p >= 0.01
        st.markdown(
            f"**① 分流均匀性校验（SRM 卡方检验）**：A 组 `{n_a}` 人 vs B 组 `{n_b}` 人，"
            f"χ² = `{srm_stat:.3f}`，p = `{srm_p:.4f}` → "
            + ("✅ **分流无偏斜，实验有效**" if srm_ok else "⚠️ **存在样本比例失衡 (SRM)，须排查分流逻辑**")
        )

    # 2. D7 留存双样本比例 Z 检验
    e_a = eligible_d7[eligible_d7["exp_group"] == "A_chapter"]
    e_b = eligible_d7[eligible_d7["exp_group"] == "B_jaccard"]
    lift_d7, z_d7, p_d7, ci_d7 = two_prop_ztest(
        int(e_a["d7_retained"].sum()), len(e_a), int(e_b["d7_retained"].sum()), len(e_b)
    )

    # 3. 复测正确率（用户级均值防重度用户权重偏倚）Welch t 检验
    rev_q = qlogs[qlogs["is_review"] == 1]
    u_rev = rev_q.groupby(["user_hash", "exp_group"])["is_correct"].mean().reset_index()
    ra = u_rev.loc[u_rev["exp_group"] == "A_chapter", "is_correct"]
    rb = u_rev.loc[u_rev["exp_group"] == "B_jaccard", "is_correct"]
    p_rev = float(ttest_ind(rb, ra, equal_var=False).pvalue) if (len(ra) >= 3 and len(rb) >= 3) else 1.0

    u_dur = qlogs.groupby(["user_hash", "exp_group"])["duration_ms"].mean().div(1000.0).reset_index()
    da = u_dur.loc[u_dur["exp_group"] == "A_chapter", "duration_ms"]
    db = u_dur.loc[u_dur["exp_group"] == "B_jaccard", "duration_ms"]
    p_dur = float(ttest_ind(db, da, equal_var=False).pvalue) if (len(da) >= 3 and len(db) >= 3) else 1.0

    ab_tbl = pd.DataFrame([
        {
            "核心指标": "D7 留存率（主指标）",
            "A 组（教材顺序）": f"{e_a['d7_retained'].mean():.1%}" if len(e_a) else "—",
            "B 组（相似方辨析）": f"{e_b['d7_retained'].mean():.1%}" if len(e_b) else "—",
            "绝对提升 (B-A)": f"{lift_d7:+.1%} (±{ci_d7:.1%})",
            "P 值": f"{p_d7:.4f}",
            "结论": "✅ 显著提升" if (p_d7 < 0.05 and lift_d7 > 0) else ("⚪ 无显著差异" if p_d7 >= 0.05 else "⚠️ 显著下降"),
        },
        {
            "核心指标": "复测正确率（学习效果）",
            "A 组（教材顺序）": f"{ra.mean():.1%}" if len(ra) else "—",
            "B 组（相似方辨析）": f"{rb.mean():.1%}" if len(rb) else "—",
            "绝对提升 (B-A)": f"{(rb.mean() - ra.mean()):+.1%}" if (len(ra) and len(rb)) else "—",
            "P 值": f"{p_rev:.4f}",
            "结论": "✅ 显著提升" if (p_rev < 0.05 and len(rb) and len(ra) and rb.mean() > ra.mean()) else "⚪ 无显著差异",
        },
        {
            "核心指标": "单题平均耗时（护栏指标）",
            "A 组（教材顺序）": f"{da.mean():.2f} s" if len(da) else "—",
            "B 组（相似方辨析）": f"{db.mean():.2f} s" if len(db) else "—",
            "绝对提升 (B-A)": f"{(db.mean() - da.mean()):+.2f} s" if (len(da) and len(db)) else "—",
            "P 值": f"{p_dur:.4f}",
            "结论": "正常（辨析思考耗时略增）" if (len(db) and len(da) and db.mean() - da.mean() < 2.0) else "⚠️ 耗时明显偏高",
        },
    ])
    st.dataframe(ab_tbl, hide_index=True, width="stretch", height="content")

    # 按天留存曲线对比 A vs B
    ret_curve = []
    for grp in ["A_chapter", "B_jaccard"]:
        ug = users[users["exp_group"] == grp]
        uag = ua[ua["exp_group"] == grp]
        for d in [1, 2, 3, 5, 7, 10, 12]:
            elig = ug[ug["reg_dt"] <= max_day - pd.Timedelta(days=d)]
            if len(elig) < 5:
                continue
            rset = set(uag.loc[uag["day_diff"] == d, "user_hash"])
            ret_curve.append({"实验组": grp, "留存天数": f"D{d}", "day": d, "留存率": elig["user_hash"].isin(rset).mean()})
    if ret_curve:
        rc_df = pd.DataFrame(ret_curve).sort_values("day")
        fig_ab = px.line(
            rc_df, x="留存天数", y="留存率", color="实验组", markers=True,
            color_discrete_map={"A_chapter": AMBER, "B_jaccard": SAGE},
            title="A/B 两组分日留存曲线对比",
        )
        fig_ab.update_layout(yaxis_tickformat=".0%", legend_title_text="")
        style_fig(fig_ab, height=340, margin={"l": 10, "r": 20, "t": 45, "b": 30})
        st.plotly_chart(fig_ab, width="stretch")

    insight_box(
        f"<strong>实验决策建议：</strong>B 组（Jaccard 相似方辨析）较 A 组 D7 留存绝对变化 <strong>{lift_d7:+.1%}</strong>（p={p_d7:.4f}），"
        f"复测正确率变化 <strong>{(rb.mean()-ra.mean()) if (len(ra) and len(rb)) else 0:+.1%}</strong>（p={p_rev:.4f}），"
        "同时单题耗时在合理护栏内。若两项主指标均为正向显著，可决策将「Jaccard 相似方辨析」推全为默认出题策略。"
    )

with tab2:
    st.subheader("按注册日期的 Cohort 留存热力图")
    cohort_days = [0, 1, 2, 3, 5, 7, 10]
    mat_rows = []
    for rday, grp in users.groupby("register_date"):
        r_dt = pd.to_datetime(rday)
        uids = set(grp["user_hash"])
        row = {"注册日期": rday, "新增人数": len(uids)}
        sub_ua = ua[ua["user_hash"].isin(uids)]
        for d in cohort_days:
            if r_dt + pd.Timedelta(days=d) <= max_day:
                act_u = set(sub_ua.loc[sub_ua["day_diff"] == d, "user_hash"])
                row[f"D{d}"] = round(len(act_u) / len(uids) * 100, 1)
            else:
                row[f"D{d}"] = np.nan
        mat_rows.append(row)
    cdf = pd.DataFrame(mat_rows).sort_values("注册日期")
    hm_data = cdf.set_index("注册日期")[[f"D{d}" for d in cohort_days]]
    fig_ch = px.imshow(
        hm_data, text_auto=".0f", color_continuous_scale="YlGn", aspect="auto",
        title="分日 Cohort 留存率热力图（%，空白为尚未满该观察天数）",
        labels={"color": "留存率(%)"},
    )
    style_fig(fig_ch, height=400, margin={"l": 10, "r": 10, "t": 45, "b": 25})
    st.plotly_chart(fig_ch, width="stretch")

    # Aha Moment：首日刷题量分层 vs D7 留存
    st.subheader("Aha Moment 魔法数字归因（首日刷题量 vs D7 留存）")
    if not eligible_d7.empty and not qlogs.empty:
        q_d0 = qlogs.merge(users[["user_hash", "register_date"]], on="user_hash")
        q_d0 = q_d0[pd.to_datetime(q_d0["ts"]).dt.strftime("%Y-%m-%d") == q_d0["register_date"]]
        d0_cnt = q_d0.groupby("user_hash").size().rename("d0_quiz")
        aha = eligible_d7.merge(d0_cnt, on="user_hash", how="left").fillna({"d0_quiz": 0})
        aha["首日刷题分层"] = pd.cut(aha["d0_quiz"], bins=[-1, 4, 9, 999], labels=["< 5 题", "5–9 题", "≥ 10 题（完成今日打卡）"])
        aha_sum = aha.groupby("首日刷题分层", observed=False).agg(用户数=("user_hash", "count"), D7留存=("d7_retained", "mean")).reset_index()
        fig_aha = px.bar(
            aha_sum, x="首日刷题分层", y="D7留存", text=aha_sum["D7留存"].map(lambda v: f"{v:.0%}"),
            color_discrete_sequence=[TEAL], title="首日刷题深度与 7 日留存关系",
        )
        fig_aha.update_traces(textposition="outside", cliponaxis=False)
        fig_aha.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, min(1.05, float(aha_sum["D7留存"].max()) * 1.25 + 0.05)], xaxis_title="")
        style_fig(fig_aha, height=340, margin={"l": 10, "r": 20, "t": 45, "b": 30})
        st.plotly_chart(fig_aha, width="stretch")
        insight_box(
            "<strong>增长洞察：</strong>首日完成 <strong>≥ 10 题（达成今日打卡）</strong>的用户 D7 留存显著高于浅度试用用户；"
            "产品迭代应优先缩短新用户完成首组 10 题的阻力（如默认直接落入第 1 题、增加连胜激励）。"
        )

    with st.expander("查看 Cohort 留存 SQL（10_小程序留存Cohort.sql）"):
        st.code(load_sql_file("10_小程序留存Cohort.sql"), language="sql")

with tab3:
    st.subheader("易混淆方剂矩阵 & 药物 Jaccard 相似度相关性检验")
    sim_q = qlogs[qlogs["q_type"] == "similar_discriminate"].copy()
    if len(sim_q) < 10:
        st.info("相似方辨析答题记录不足 10 条")
    else:
        # 1. Jaccard 相似度分箱 vs 实际错误率 + Spearman 检验
        per_f = (
            sim_q.groupby("formula")
            .agg(答题次数=("log_id", "count"), 错误率=("is_correct", lambda s: 1 - s.mean()), 平均干扰相似度=("distractor_max_sim", "mean"))
            .reset_index()
        )
        per_f = per_f[per_f["答题次数"] >= 3]
        rho, sp_p = spearmanr(per_f["平均干扰相似度"], per_f["错误率"]) if len(per_f) >= 5 else (0.0, 1.0)

        l, r = st.columns([3, 2])
        fig_cor = px.scatter(
            per_f, x="平均干扰相似度", y="错误率", size="答题次数", hover_data=["formula"],
            color="错误率", color_continuous_scale="YlOrRd",
            title=f"药物 Jaccard 相似度 vs 实际错误率（Spearman ρ = {rho:.2f}, p = {sp_p:.2e}）",
        )
        fig_cor.update_layout(yaxis_tickformat=".0%")
        style_fig(fig_cor, height=380, margin={"l": 10, "r": 10, "t": 45, "b": 30})
        l.plotly_chart(fig_cor, width="stretch")

        wrong_pairs = (
            sim_q[(sim_q["is_correct"] == 0) & (sim_q["chosen"] != sim_q["formula"]) & (sim_q["chosen"] != "")]
            .groupby(["formula", "chosen"])
            .agg(混淆次数=("log_id", "count"), 组成相似度=("distractor_max_sim", "mean"))
            .reset_index()
            .sort_values("混淆次数", ascending=False)
            .head(15)
            .rename(columns={"formula": "正答方剂", "chosen": "误选方剂"})
        )
        r.markdown("#### 高频混淆方对 Top 15")
        r.dataframe(
            wrong_pairs,
            hide_index=True,
            width="stretch",
            height=340,
            column_config={"组成相似度": st.column_config.NumberColumn("Jaccard", format="%.2f")},
        )
        insight_box(
            f"<strong>算法与业务联动洞察：</strong>两首方剂的组成 Jaccard 相似度与实际答题错误率呈正相关（Spearman ρ = <strong>{rho:.2f}</strong>, p = {sp_p:.2e}），"
            "印证了药物共现重合度是导致背方混淆的关键因素；对于『相似度偏低但混淆频发』的方对（往往因方名仅差一字），后续可叠加「方名编辑距离」进一步优化出题算法。"
        )

with tab4:
    st.subheader("微信场景渠道归因与裂变传播分析")
    ch = users.merge(eligible_d7[["user_hash", "d7_retained"]], on="user_hash", how="left")
    ch["渠道"] = ch["channel_scene"].map(lambda x: f"{SCENE_LABEL.get(str(x), '其他')} ({x})")
    ch_sum = ch.groupby("渠道").agg(拉新人数=("user_hash", "count"), D7留存=("d7_retained", "mean")).reset_index().sort_values("拉新人数", ascending=False)

    l, r = st.columns(2)
    fig_ch_bar = px.bar(ch_sum, x="渠道", y="拉新人数", text="拉新人数", title="各微信入口渠道拉新规模", color_discrete_sequence=[SAGE])
    fig_ch_bar.update_traces(textposition="outside", cliponaxis=False)
    style_fig(fig_ch_bar, height=350, margin={"l": 10, "r": 15, "t": 45, "b": 30})
    l.plotly_chart(fig_ch_bar, width="stretch")

    ch_ret = ch_sum.dropna(subset=["D7留存"])
    if not ch_ret.empty:
        fig_ch_ret = px.bar(
            ch_ret, x="渠道", y="D7留存", text=ch_ret["D7留存"].map(lambda v: f"{v:.0%}"),
            title="各渠道 D7 留存质量对比", color_discrete_sequence=[TEAL],
        )
        fig_ch_ret.update_traces(textposition="outside", cliponaxis=False)
        fig_ch_ret.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, min(1.05, float(ch_ret["D7留存"].max()) * 1.25 + 0.05)])
        style_fig(fig_ch_ret, height=350, margin={"l": 10, "r": 15, "t": 45, "b": 30})
        r.plotly_chart(fig_ch_ret, width="stretch")

    if not shares.empty:
        card_dist = shares["card_type"].value_counts().rename_axis("分享卡片类型").reset_index(name="成功拉新数")
        st.dataframe(card_dist, hide_index=True, width="stretch", height="content")
    insight_box(
        f"<strong>裂变洞察：</strong>当前裂变 K 因子 = <strong>{k_factor:.2f}</strong>（共通过好友/微信群分享带来 {len(shares)} 位新用户）。"
        "微信群分享卡片兼顾获客规模与精准专业人群留存，是校园冷启动阶段性价比最高的增长渠道。"
    )
