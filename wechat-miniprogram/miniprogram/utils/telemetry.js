// 统一匿名埋点层：支持微信云开发（CloudBase）实时上报 + 本地缓存离线导出双模式
const STORAGE_KEYS = {
  USER: 'fl_dim_user',
  EVENTS: 'fl_fact_event',
  QUIZ: 'fl_fact_quiz_log',
  SHARES: 'fl_fact_share',
  SM2: 'fl_sm2_state',
};

function nowIso() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())
  );
}

function todayStr() {
  return nowIso().slice(0, 10);
}

// FNV-1a 确定性哈希，用于本地离线模式 50/50 A/B 均匀分桶
function hashStr(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function randomHex(len) {
  let out = '';
  for (let i = 0; i < len; i++) {
    out += Math.floor(Math.random() * 16).toString(16);
  }
  return out;
}

function newSessionId() {
  return 's_' + Date.now().toString(36) + '_' + randomHex(6);
}

function callCloud(action, payload) {
  try {
    const app = getApp();
    if (!app || !app.globalData || !app.globalData.cloudEnabled || !wx.cloud) return;
    wx.cloud.callFunction({
      name: 'logEvent',
      data: { action, payload },
    });
  } catch (e) {
    // 埋点异常绝不阻塞学习主流程
  }
}

function appendLocal(key, row, cap) {
  try {
    const arr = wx.getStorageSync(key) || [];
    arr.push(row);
    const trimmed = arr.length > cap ? arr.slice(arr.length - cap) : arr;
    wx.setStorageSync(key, trimmed);
  } catch (e) {}
}

function initUser({ scene = '1001', inviter = '' } = {}) {
  let user = wx.getStorageSync(STORAGE_KEYS.USER);
  if (user && user.user_hash) {
    // 更新活跃天数与连续打卡
    const today = todayStr();
    if (user.last_active_day !== today) {
      const prev = new Date(user.last_active_day + 'T00:00:00');
      const cur = new Date(today + 'T00:00:00');
      const diffDays = Math.round((cur - prev) / 86400000);
      user.streak_days = diffDays === 1 ? (user.streak_days || 1) + 1 : 1;
      user.last_active_day = today;
      user.active_days = (user.active_days || 1) + 1;
      wx.setStorageSync(STORAGE_KEYS.USER, user);
    }
    return Object.assign({}, user, { is_new: false });
  }

  const uid = 'u_' + randomHex(12);
  const expGroup = hashStr(uid) % 2 === 0 ? 'A_chapter' : 'B_jaccard';
  const today = todayStr();
  user = {
    user_hash: uid,
    first_seen_at: nowIso(),
    register_date: today,
    last_active_day: today,
    active_days: 1,
    streak_days: 1,
    channel_scene: String(scene),
    inviter_hash: inviter || '',
    exp_group: expGroup,
  };
  wx.setStorageSync(STORAGE_KEYS.USER, user);
  callCloud('upsert_user', user);
  return Object.assign({}, user, { is_new: true });
}

function getUser() {
  return wx.getStorageSync(STORAGE_KEYS.USER) || initUser();
}

function trackEvent(page, event, params = {}) {
  const user = getUser();
  const app = getApp();
  const row = {
    user_hash: user.user_hash,
    session_id: (app && app.globalData && app.globalData.sessionId) || 's_local',
    ts: nowIso(),
    page,
    event,
    exp_group: user.exp_group,
    params_json: JSON.stringify(params || {}),
  };
  appendLocal(STORAGE_KEYS.EVENTS, row, 1500);
  callCloud('fact_event', row);
}

function trackQuiz(record) {
  const user = getUser();
  const row = {
    user_hash: user.user_hash,
    ts: nowIso(),
    exp_group: user.exp_group,
    formula: record.formula,
    category: record.category || '',
    q_type: record.q_type,
    chosen: record.chosen || '',
    distractor_max_sim: Number(record.distractor_max_sim || 0),
    is_correct: record.is_correct ? 1 : 0,
    duration_ms: Math.max(0, Math.round(record.duration_ms || 0)),
    is_review: record.is_review ? 1 : 0,
  };
  appendLocal(STORAGE_KEYS.QUIZ, row, 3000);
  callCloud('fact_quiz_log', row);
  return row;
}

function trackShareConversion({ inviter_hash, invitee_hash, card_type }) {
  const row = {
    inviter_hash,
    invitee_hash,
    card_type: card_type || 'formula_card',
    ts: nowIso(),
  };
  appendLocal(STORAGE_KEYS.SHARES, row, 500);
  callCloud('fact_share', row);
}

function getQuizLogs() {
  return wx.getStorageSync(STORAGE_KEYS.QUIZ) || [];
}

function getEvents() {
  return wx.getStorageSync(STORAGE_KEYS.EVENTS) || [];
}

function getSM2State() {
  return wx.getStorageSync(STORAGE_KEYS.SM2) || {};
}

function saveSM2State(state) {
  wx.setStorageSync(STORAGE_KEYS.SM2, state);
}

function exportBundleJson() {
  const user = getUser();
  const bundle = {
    exported_at: nowIso(),
    source: 'fanglue_miniprogram_local',
    dim_user: [user],
    fact_quiz_log: getQuizLogs(),
    fact_event: getEvents(),
    fact_share: wx.getStorageSync(STORAGE_KEYS.SHARES) || [],
  };
  return JSON.stringify(bundle, null, 2);
}

module.exports = {
  nowIso,
  todayStr,
  newSessionId,
  initUser,
  getUser,
  trackEvent,
  trackQuiz,
  trackShareConversion,
  getQuizLogs,
  getEvents,
  getSM2State,
  saveSM2State,
  exportBundleJson,
};
