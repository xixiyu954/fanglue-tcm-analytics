-- 11 小程序 A/B 实验分组核心指标对比（答题正确率、复测正确率、平均耗时与活跃天数）
-- 技能点：实验分流口径对齐、条件聚合、用户粒度先聚合再均值（避免重度用户刷量偏差）
WITH user_quiz AS (
    SELECT u.user_hash,
           u.exp_group,
           COUNT(q.log_id)                                                       AS n_quiz,
           AVG(q.is_correct)                                                     AS user_acc,
           AVG(CASE WHEN q.is_review = 1 THEN q.is_correct END)                  AS review_acc,
           AVG(q.duration_ms) / 1000.0                                           AS avg_sec,
           COUNT(DISTINCT DATE(q.ts))                                            AS active_days
    FROM mp_user u
    LEFT JOIN mp_quiz_log q ON q.user_hash = u.user_hash
    GROUP BY u.user_hash, u.exp_group
)
SELECT exp_group,
       COUNT(*)                                       AS users,
       ROUND(AVG(n_quiz), 1)                          AS avg_quiz_per_user,
       ROUND(AVG(user_acc), 3)                        AS avg_user_acc,
       ROUND(AVG(review_acc), 3)                      AS avg_review_acc,
       ROUND(AVG(avg_sec), 2)                         AS avg_sec_per_q,
       ROUND(AVG(active_days), 2)                     AS avg_active_days
FROM user_quiz
GROUP BY exp_group
ORDER BY exp_group;
