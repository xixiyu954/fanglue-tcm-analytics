-- 10 小程序留存 Cohort：按注册日期统计 D0 / D1 / D3 / D7 / D14 留存率
-- 技能点：多表去重活跃日、JULIANDAY 日期差、条件去重计数（Cohort 留存标准 SQL 写法）
WITH activity AS (
    SELECT DISTINCT user_hash, DATE(ts) AS active_date FROM mp_event
    UNION
    SELECT DISTINCT user_hash, DATE(ts) AS active_date FROM mp_quiz_log
),
joined AS (
    SELECT u.user_hash,
           u.register_date,
           u.exp_group,
           CAST(JULIANDAY(a.active_date) - JULIANDAY(u.register_date) AS INTEGER) AS day_diff
    FROM mp_user u
    LEFT JOIN activity a ON a.user_hash = u.user_hash
)
SELECT register_date,
       COUNT(DISTINCT user_hash)                                                       AS cohort_size,
       ROUND(1.0 * COUNT(DISTINCT CASE WHEN day_diff = 1  THEN user_hash END) / COUNT(DISTINCT user_hash), 3) AS d1_ret,
       ROUND(1.0 * COUNT(DISTINCT CASE WHEN day_diff = 3  THEN user_hash END) / COUNT(DISTINCT user_hash), 3) AS d3_ret,
       ROUND(1.0 * COUNT(DISTINCT CASE WHEN day_diff = 7  THEN user_hash END) / COUNT(DISTINCT user_hash), 3) AS d7_ret,
       ROUND(1.0 * COUNT(DISTINCT CASE WHEN day_diff >= 14 THEN user_hash END) / COUNT(DISTINCT user_hash), 3) AS d14_plus_ret
FROM joined
GROUP BY register_date
ORDER BY register_date;
