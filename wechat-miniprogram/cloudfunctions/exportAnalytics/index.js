// 分页拉取云开发四张分析表（dim_user / fact_quiz_log / fact_event / fact_share）
const cloud = require('wx-server-sdk');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

async function fetchAll(name, maxRows = 5000) {
  const batch = 100;
  const rows = [];
  for (let skip = 0; skip < maxRows; skip += batch) {
    const res = await db.collection(name).skip(skip).limit(batch).get();
    rows.push(...res.data);
    if (res.data.length < batch) break;
  }
  return rows;
}

exports.main = async () => {
  const [dim_user, fact_quiz_log, fact_event, fact_share] = await Promise.all([
    fetchAll('dim_user'),
    fetchAll('fact_quiz_log'),
    fetchAll('fact_event'),
    fetchAll('fact_share'),
  ]);
  return {
    exported_at: new Date().toISOString(),
    source: 'fanglue_cloudbase',
    dim_user,
    fact_quiz_log,
    fact_event,
    fact_share,
  };
};
