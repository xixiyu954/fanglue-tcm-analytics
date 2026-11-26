// 前端轻量方剂分析引擎（与 Python core/analysis.py 保持完全一致的业务口径）
const HERBS = require('../data/herbs');
const FORMULAS = require('../data/formulas');
const RULES = require('../data/rules');

const HERB_MAP = {};
HERBS.forEach((h) => { HERB_MAP[h.n] = h; });

const FORMULA_MAP = {};
FORMULAS.forEach((f) => { FORMULA_MAP[f.n] = f; });

const ARISTOLOCHIC_SET = {};
RULES.aristolochic.forEach((h) => { ARISTOLOCHIC_SET[h] = true; });

const PROC_PREFIXES = [
  ['姜汁炒', '姜制'], ['盐水炒', '盐制'], ['酒蒸', '酒蒸'], ['酥炙', '酥炙'], ['微炒', '微炒'],
  ['蜜炙', '蜜炙'], ['酒炒', '酒炒'], ['酒炙', '酒炙'], ['酒制', '酒制'], ['醋炙', '醋炙'],
  ['醋炒', '醋炒'], ['醋制', '醋制'], ['盐炙', '盐炙'], ['盐炒', '盐炒'], ['麸炒', '麸炒'],
  ['土炒', '土炒'], ['清炒', '炒'], ['炒焦', '炒焦'], ['姜炙', '姜制'], ['姜制', '姜制'],
  ['炙', '炙'], ['生', '生用'], ['炒', '炒'], ['焦', '炒焦'], ['酒', '酒制'],
  ['醋', '醋制'], ['盐', '盐制'], ['煅', '煅'], ['制', '炮制'], ['炮', '炮制'], ['煨', '煨'],
];

const FLAVOR_ORDER = ['辛', '甘', '酸', '苦', '咸', '淡', '涩'];
const MERIDIAN_ORDER = ['肺', '大肠', '胃', '脾', '心', '小肠', '膀胱', '肾', '心包', '三焦', '胆', '肝'];

function normalizeHerb(raw) {
  const s = String(raw || '').trim();
  const aliasVal = RULES.aliases[s];
  if (aliasVal) {
    if (Array.isArray(aliasVal)) return { herb: aliasVal[0], processing: aliasVal[1] || '' };
    return { herb: aliasVal, processing: '' };
  }
  if (HERB_MAP[s]) return { herb: s, processing: '' };
  for (let i = 0; i < PROC_PREFIXES.length; i++) {
    const [pref, proc] = PROC_PREFIXES[i];
    if (s.indexOf(pref) === 0 && s.length > pref.length + 1) {
      const base = s.slice(pref.length);
      if (HERB_MAP[base]) return { herb: base, processing: proc };
      const bv = RULES.aliases[base];
      if (bv) return { herb: Array.isArray(bv) ? bv[0] : bv, processing: proc };
    }
  }
  return { herb: s, processing: '' };
}

function parseFormulaText(text) {
  const re = /([\u4e00-\u9fa5]+)\s*(\d+(?:\.\d+)?)?\s*(?:g|G|克)?/g;
  const items = [];
  const unmatched = [];
  const seen = {};
  let m;
  while ((m = re.exec(text)) !== null) {
    const raw = m[1];
    const dose = m[2] ? parseFloat(m[2]) : null;
    const norm = normalizeHerb(raw);
    if (HERB_MAP[norm.herb]) {
      if (!seen[norm.herb]) {
        seen[norm.herb] = true;
        items.push({ herb_raw: raw, herb: norm.herb, processing: norm.processing, dose_g: dose });
      }
    } else {
      unmatched.push(raw);
    }
  }
  return { items, unmatched };
}

function heatLabel(score) {
  if (score <= -1.5) return '偏寒凉（明显）';
  if (score <= -0.5) return '偏寒凉';
  if (score < 0.5) return '寒热平和';
  if (score < 1.5) return '偏温热';
  return '偏温热（明显）';
}

function analyzeComposition(items, excludeName) {
  const valid = items.filter((it) => HERB_MAP[it.herb]);
  if (!valid.length) return null;

  const hasDose = valid.some((it) => it.dose_g !== null && it.dose_g > 0);
  const doses = valid.map((it) => (it.dose_g && it.dose_g > 0 ? it.dose_g : 1));
  const totalW = doses.reduce((a, b) => a + b, 0) || 1;
  const totalDose = hasDose ? valid.reduce((a, it) => a + (it.dose_g || 0), 0) : null;

  let heatSum = 0;
  const flavorSum = {};
  const meridianSum = {};
  const herbSet = {};
  const detail = [];

  valid.forEach((it, idx) => {
    const info = HERB_MAP[it.herb];
    const w = doses[idx];
    herbSet[it.herb] = true;
    heatSum += w * (info.s || 0);

    const seenF = {};
    (info.f || []).forEach((fl) => {
      const mainF = fl.replace(/^微/, '');
      if (!seenF[mainF]) {
        seenF[mainF] = true;
        flavorSum[mainF] = (flavorSum[mainF] || 0) + w;
      }
    });
    (info.m || []).forEach((me) => {
      meridianSum[me] = (meridianSum[me] || 0) + w;
    });

    detail.push({
      herb_raw: it.herb_raw || it.herb,
      herb: it.herb,
      processing: it.processing || '',
      dose_g: it.dose_g,
      nature: info.t,
      flavors: (info.f || []).join('、'),
      meridians: (info.m || []).join('、'),
      category: info.c,
      dose_range: info.d ? `${info.d[0]}~${info.d[1]}g` : '—',
    });
  });

  const heatIndex = Number((heatSum / totalW).toFixed(2));
  // 0~100 进度条位置：-3 -> 0%, 0 -> 50%, +3 -> 100%
  const heatPos = Math.max(4, Math.min(96, Math.round(((heatIndex + 3) / 6) * 100)));

  const flavors = FLAVOR_ORDER.map((fl) => ({
    name: fl,
    pct: Math.round(((flavorSum[fl] || 0) / totalW) * 100),
  })).filter((x) => x.pct > 0).sort((a, b) => b.pct - a.pct);

  const meridians = MERIDIAN_ORDER.map((me) => ({
    name: me,
    pct: Math.round(((meridianSum[me] || 0) / totalW) * 100),
  })).filter((x) => x.pct > 0).sort((a, b) => b.pct - a.pct);

  // ---------- 安全规则校验 ----------
  const alerts = [];
  RULES.incompat.forEach(([rtype, a, b]) => {
    if (herbSet[a] && herbSet[b]) {
      alerts.push({ level: '高', type: rtype, msg: `${a} 与 ${b} 属${rtype}配伍禁忌` });
    }
  });
  Object.keys(herbSet).forEach((h) => {
    if (ARISTOLOCHIC_SET[h]) {
      alerts.push({ level: '高', type: '肾毒警示', msg: `${h} 含马兜铃酸，存在明确肾毒风险，现代临床多禁用或替代` });
    }
  });
  valid.forEach((it) => {
    const info = HERB_MAP[it.herb];
    if (info.tx) {
      alerts.push({
        level: info.tx === '大毒' ? '高' : '中',
        type: '毒性',
        msg: `${it.herb} 标注「${info.tx}」，学习记忆须注意炮制与先煎控量`,
      });
    }
    if (info.p) {
      alerts.push({
        level: info.p === '禁用' ? '高' : '中',
        type: '妊娠',
        msg: `${it.herb}：孕妇${info.p}`,
      });
    }
    if (it.dose_g && info.d && it.dose_g > info.d[1]) {
      alerts.push({
        level: '中',
        type: '剂量',
        msg: `${it.herb} ${it.dose_g}g 高于药典常用量上限 ${info.d[1]}g`,
      });
    }
  });
  const rankMap = { 高: 0, 中: 1, 低: 2 };
  alerts.sort((a, b) => rankMap[a.level] - rankMap[b.level]);

  // ---------- 相似经典方 Top 4（Jaccard） ----------
  const similar = [];
  const herbsArr = Object.keys(herbSet);
  FORMULAS.forEach((f) => {
    if (f.n === excludeName) return;
    const fSet = {};
    f.h.forEach((x) => { fSet[x[0]] = true; });
    const fArr = Object.keys(fSet);
    const inter = herbsArr.filter((x) => fSet[x]);
    if (!inter.length) return;
    const unionCount = herbsArr.length + fArr.length - inter.length;
    const jac = inter.length / unionCount;
    similar.push({
      name: f.n,
      cat: f.cat,
      dyn: f.dyn,
      sim: Number(jac.toFixed(2)),
      simPct: Math.round(jac * 100),
      common: inter.join('、'),
      more: fArr.filter((x) => !herbSet[x]).join('、') || '无',
      less: herbsArr.filter((x) => !fSet[x]).join('、') || '无',
    });
  });
  similar.sort((a, b) => b.sim - a.sim);

  return {
    n_herbs: valid.length,
    total_dose: totalDose ? Number(totalDose.toFixed(1)) : null,
    heat_index: heatIndex,
    heat_label: heatLabel(heatIndex),
    heat_pos: heatPos,
    flavors,
    meridians,
    alerts,
    detail,
    similar: similar.slice(0, 4),
  };
}

function getFormulaByName(name) {
  return FORMULA_MAP[name] || null;
}

function getHerbByName(name) {
  return HERB_MAP[name] || null;
}

module.exports = {
  HERBS,
  FORMULAS,
  RULES,
  HERB_MAP,
  FORMULA_MAP,
  normalizeHerb,
  parseFormulaText,
  analyzeComposition,
  getFormulaByName,
  getHerbByName,
  heatLabel,
};
