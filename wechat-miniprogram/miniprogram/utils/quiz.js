// 每日辨方出题引擎：A/B 实验策略（章节顺序 vs Jaccard 相似方辨析）+ SM-2 间隔重复
const { FORMULAS, HERB_MAP, RULES } = require('./analysis');
const telemetry = require('./telemetry');

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = a[i];
    a[i] = a[j];
    a[j] = tmp;
  }
  return a;
}

// SM-2 间隔重复更新：记录每首方剂的熟练度、复习间隔与下次复习日期
function updateSM2(formulaName, isCorrect) {
  const state = telemetry.getSM2State();
  const cur = state[formulaName] || { rep: 0, ef: 2.5, interval: 0, wrong: 0, right: 0 };
  const q = isCorrect ? 4 : 1;
  if (isCorrect) {
    cur.right += 1;
    cur.rep += 1;
    if (cur.rep === 1) cur.interval = 1;
    else if (cur.rep === 2) cur.interval = 4;
    else cur.interval = Math.round(cur.interval * cur.ef);
  } else {
    cur.wrong += 1;
    cur.rep = 0;
    cur.interval = 1;
  }
  cur.ef = Math.max(1.3, Number((cur.ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))).toFixed(2)));
  const due = new Date();
  due.setDate(due.getDate() + cur.interval);
  cur.next_review = due.toISOString().slice(0, 10);
  cur.last_seen = telemetry.todayStr();
  state[formulaName] = cur;
  telemetry.saveSM2State(state);
  return cur;
}

// 挑选待学习/待复习方剂：优先到期复习，其次按 A/B 分组策略挑选
function pickNextFormula(expGroup, recentNames = [], focusCategory = '') {
  const sm2 = telemetry.getSM2State();
  const today = telemetry.todayStr();
  const recentSet = {};
  recentNames.forEach((n) => { recentSet[n] = true; });

  let pool = FORMULAS.filter((f) => f.h.length >= 3 && (!focusCategory || f.cat === focusCategory));
  if (pool.length < 4) pool = FORMULAS.filter((f) => f.h.length >= 3);

  // 1. 到期需复习（SM-2）
  const dueList = pool.filter((f) => sm2[f.n] && sm2[f.n].next_review <= today && !recentSet[f.n]);
  if (dueList.length) {
    // 优先错得多的方剂
    dueList.sort((a, b) => (sm2[b.n].wrong - sm2[a.n].wrong));
    return { formula: dueList[0], isReview: true };
  }

  // 2. 新方剂：A 组按教材章节顺序，B 组优先挑有高 Jaccard 易混邻居的方剂
  const unseen = pool.filter((f) => !sm2[f.n] && !recentSet[f.n]);
  if (unseen.length) {
    if (expGroup === 'B_jaccard') {
      const highConfuse = unseen.filter((f) => f.sim && f.sim.length && f.sim[0][1] >= 0.25);
      const src = highConfuse.length ? highConfuse : unseen;
      return { formula: src[Math.floor(Math.random() * Math.min(12, src.length))], isReview: false };
    }
    return { formula: unseen[0], isReview: false };
  }

  // 3. 兜底随机抽未刚做过的
  const avail = pool.filter((f) => !recentSet[f.n]);
  const pick = avail.length ? avail[Math.floor(Math.random() * avail.length)] : pool[0];
  return { formula: pick, isReview: Boolean(sm2[pick.n]) };
}

// 题型 1：看组成选方名（A 组同章节干扰项，B 组 Jaccard 最高相似方干扰项）
function buildSimilarFormulaQuestion(f, expGroup, isReview) {
  let distractors = [];
  let maxSim = 0;

  if (expGroup === 'B_jaccard' && f.sim && f.sim.length) {
    f.sim.slice(0, 3).forEach((s) => {
      distractors.push({ name: s[0], sim: s[1], more: s[2], less: s[3] });
      if (s[1] > maxSim) maxSim = s[1];
    });
  }
  // 补齐到 3 个干扰项（同类别优先）
  const used = { [f.n]: true };
  distractors.forEach((d) => { used[d.name] = true; });
  const sameCat = shuffle(FORMULAS.filter((x) => x.cat === f.cat && !used[x.n]));
  const others = shuffle(FORMULAS.filter((x) => !used[x.n]));
  const fillPool = sameCat.concat(others);
  for (let i = 0; i < fillPool.length && distractors.length < 3; i++) {
    const cand = fillPool[i];
    if (used[cand.n]) continue;
    used[cand.n] = true;
    // 计算该干扰项与正答的 Jaccard 相似度供数据分析使用
    const s0 = {};
    f.h.forEach((x) => { s0[x[0]] = true; });
    const s1 = {};
    cand.h.forEach((x) => { s1[x[0]] = true; });
    const k0 = Object.keys(s0);
    const k1 = Object.keys(s1);
    const inter = k0.filter((x) => s1[x]).length;
    const jac = Number((inter / (k0.length + k1.length - inter)).toFixed(3));
    if (jac > maxSim) maxSim = jac;
    distractors.push({
      name: cand.n,
      sim: jac,
      more: k1.filter((x) => !s0[x]).slice(0, 5),
      less: k0.filter((x) => !s1[x]).slice(0, 5),
    });
  }

  const options = shuffle(
    [{ label: f.n, isCorrect: true, sim: 1, more: [], less: [] }].concat(
      distractors.map((d) => ({ label: d.name, isCorrect: false, sim: d.sim, more: d.more, less: d.less }))
    )
  );

  const compText = f.h.map((x) => (x[1] ? `${x[2] || x[0]} ${x[1]}g` : (x[2] || x[0]))).join('、');
  return {
    q_type: 'similar_discriminate',
    q_type_label: expGroup === 'B_jaccard' ? '相似方辨析' : '方剂辨识',
    formula: f.n,
    category: f.cat,
    dynasty: f.dyn,
    source: f.src,
    indication: f.ind,
    prompt: '以下药物组成对应哪首经典名方？',
    stem: compText,
    hint: `类别提示：${f.cat} · ${f.dyn}《${f.src}》`,
    options,
    answer: f.n,
    distractor_max_sim: maxSim,
    is_review: isReview,
  };
}

// 题型 2：缺药填空（挖去方剂中 1 味关键药材，4 选 1）
function buildMissingHerbQuestion(f, isReview) {
  const targetIdx = Math.floor(Math.random() * Math.min(4, f.h.length));
  const missingHerb = f.h[targetIdx][0];
  const fHerbs = {};
  f.h.forEach((x) => { fHerbs[x[0]] = true; });

  const info = HERB_MAP[missingHerb];
  const sameCatHerbs = Object.keys(HERB_MAP).filter(
    (h) => !fHerbs[h] && info && HERB_MAP[h].c === info.c
  );
  const commonHerbs = ['人参', '黄芪', '白术', '茯苓', '当归', '川芎', '白芍', '柴胡', '黄芩', '黄连', '半夏', '陈皮', '桂枝', '麻黄', '大黄', '附子', '干姜', '知母', '麦冬', '生地黄'];
  const pool = shuffle(sameCatHerbs).concat(shuffle(commonHerbs.filter((h) => !fHerbs[h])));
  const distractors = [];
  const used = { [missingHerb]: true };
  for (let i = 0; i < pool.length && distractors.length < 3; i++) {
    if (!used[pool[i]]) {
      used[pool[i]] = true;
      distractors.push(pool[i]);
    }
  }

  const stemList = f.h.map((x, idx) => (idx === targetIdx ? '【 ？ 】' : x[0]));
  const options = shuffle(
    [{ label: missingHerb, isCorrect: true }].concat(distractors.map((h) => ({ label: h, isCorrect: false })))
  );

  return {
    q_type: 'missing_herb',
    q_type_label: '缺药填空',
    formula: f.n,
    category: f.cat,
    dynasty: f.dyn,
    source: f.src,
    indication: f.ind,
    prompt: `《${f.n}》组成中缺失了哪一味关键药材？`,
    stem: stemList.join('、'),
    hint: `主治参考：${f.ind || f.cat}`,
    options,
    answer: missingHerb,
    distractor_max_sim: f.sim && f.sim.length ? f.sim[0][1] : 0,
    is_review: isReview,
  };
}

// 题型 3：配伍禁忌排雷（十八反 / 十九畏）
function buildIncompatQuestion() {
  const pair = RULES.incompat[Math.floor(Math.random() * RULES.incompat.length)];
  const [rtype, a, b] = pair;
  const safePool = shuffle(['茯苓', '白术', '陈皮', '黄芪', '山药', '麦冬', '桔梗', '防风', '柴胡', '当归', '川芎', '葛根', '大枣', '生姜']);
  const incompatMap = {};
  RULES.incompat.forEach(([, x, y]) => {
    incompatMap[`${x}|${y}`] = true;
    incompatMap[`${y}|${x}`] = true;
  });

  const safeOpts = [];
  for (let i = 0; i < safePool.length && safeOpts.length < 3; i++) {
    const h = safePool[i];
    if (h !== a && h !== b && !incompatMap[`${a}|${h}`]) {
      safeOpts.push(`${a} + ${h}`);
    }
  }

  const ansLabel = `${a} + ${b}`;
  const options = shuffle(
    [{ label: ansLabel, isCorrect: true }].concat(safeOpts.map((s) => ({ label: s, isCorrect: false })))
  );

  return {
    q_type: 'incompat_rule',
    q_type_label: '配伍禁忌排雷',
    formula: `${rtype}:${a}-${b}`,
    category: '配伍安全',
    dynasty: '药典规则',
    source: '中药学教材',
    indication: `${a} 与 ${b} 属于传统「${rtype}」配伍禁忌组合`,
    prompt: `下列哪组药对属于传统「${rtype}」配伍禁忌？`,
    stem: `围绕主药「${a}」辨别配伍禁忌`,
    hint: '复习口诀：半蒌贝蔹芨攻乌，藻戟遂芫俱战草，诸参辛芍叛藜芦',
    options,
    answer: ansLabel,
    distractor_max_sim: 0,
    is_review: false,
  };
}

function generateQuestion(expGroup, stepIndex, recentNames = [], focusCategory = '') {
  // 每 5 题穿插 1 道配伍禁忌排雷，每 3 题穿插 1 道缺药填空，其余主打核心相似方辨析
  if (!focusCategory && stepIndex > 0 && stepIndex % 5 === 4) {
    return buildIncompatQuestion();
  }
  const { formula, isReview } = pickNextFormula(expGroup, recentNames, focusCategory);
  if (stepIndex % 3 === 2) {
    return buildMissingHerbQuestion(formula, isReview);
  }
  return buildSimilarFormulaQuestion(formula, expGroup, isReview);
}

// 聚合个人错题与易混淆方对（供「错题图谱」页展示）
function computeMistakeSummary() {
  const logs = telemetry.getQuizLogs();
  const byCat = {};
  const confusePairs = {};
  const wrongByFormula = {};

  logs.forEach((l) => {
    const cat = l.category || '其他';
    if (!byCat[cat]) byCat[cat] = { cat, total: 0, right: 0 };
    byCat[cat].total += 1;
    if (l.is_correct) byCat[cat].right += 1;
    else {
      if (l.q_type !== 'incompat_rule') {
        wrongByFormula[l.formula] = (wrongByFormula[l.formula] || 0) + 1;
      }
      if (l.q_type === 'similar_discriminate' && l.chosen && l.chosen !== l.formula) {
        const key = `${l.formula} → 误选 ${l.chosen}`;
        if (!confusePairs[key]) {
          confusePairs[key] = { key, target: l.formula, chosen: l.chosen, count: 0, sim: l.distractor_max_sim || 0 };
        }
        confusePairs[key].count += 1;
      }
    }
  });

  const catStats = Object.values(byCat)
    .map((x) => ({
      cat: x.cat,
      total: x.total,
      right: x.right,
      acc: Math.round((x.right / x.total) * 100),
    }))
    .sort((a, b) => a.acc - b.acc);

  const topConfused = Object.values(confusePairs).sort((a, b) => b.count - a.count).slice(0, 8);
  const topWrong = Object.keys(wrongByFormula)
    .map((name) => ({ name, wrong: wrongByFormula[name] }))
    .sort((a, b) => b.wrong - a.wrong)
    .slice(0, 10);

  return {
    totalLogs: logs.length,
    totalRight: logs.filter((x) => x.is_correct).length,
    overallAcc: logs.length ? Math.round((logs.filter((x) => x.is_correct).length / logs.length) * 100) : 0,
    catStats,
    topConfused,
    topWrong,
  };
}

module.exports = {
  updateSM2,
  generateQuestion,
  computeMistakeSummary,
};
