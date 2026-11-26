// 微信云函数：将真实微信 OPENID 单向 SHA-256 哈希为匿名 user_hash，并按 50/50 确定性分流至 A/B 组
const crypto = require('crypto');
const cloud = require('wx-server-sdk');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

function hashOpenId(openid) {
  return 'wx_' + crypto.createHash('sha256').update(String(openid || 'anon')).digest('hex').slice(0, 16);
}

function assignBucket(userHash) {
  const num = parseInt(userHash.slice(-6), 16) || 0;
  return num % 2 === 0 ? 'A_chapter' : 'B_jaccard';
}

exports.main = async (event) => {
  const wxCtx = cloud.getWXContext();
  const userHash = wxCtx.OPENID ? hashOpenId(wxCtx.OPENID) : (event.payload && event.payload.user_hash) || 'u_unknown';
  const expGroup = assignBucket(userHash);
  const { action, payload = {} } = event || {};
  const serverTime = new Date().toISOString();

  if (action === 'upsert_user') {
    const existing = await db.collection('dim_user').where({ user_hash: userHash }).limit(1).get();
    if (!existing.data.length) {
      await db.collection('dim_user').add({
        data: {
          user_hash: userHash,
          first_seen_at: payload.first_seen_at || serverTime,
          register_date: (payload.register_date || serverTime.slice(0, 10)),
          channel_scene: String(payload.channel_scene || '1001'),
          inviter_hash: payload.inviter_hash || '',
          exp_group: expGroup,
        },
      });
    }
    return { ok: true, user_hash: userHash, exp_group: expGroup };
  }

  const allowed = { fact_event: 'fact_event', fact_quiz_log: 'fact_quiz_log', fact_share: 'fact_share' };
  const col = allowed[action];
  if (!col) return { ok: false, error: 'unknown_action' };

  const doc = Object.assign({}, payload, {
    user_hash: action === 'fact_share' ? undefined : userHash,
    invitee_hash: action === 'fact_share' ? userHash : undefined,
    exp_group: action === 'fact_share' ? undefined : expGroup,
    server_ts: serverTime,
  });
  Object.keys(doc).forEach((k) => { if (doc[k] === undefined) delete doc[k]; });
  await db.collection(col).add({ data: doc });
  return { ok: true, collection: col };
};
