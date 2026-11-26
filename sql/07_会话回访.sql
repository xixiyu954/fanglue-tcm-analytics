-- 07 会话回访：每个会话的活跃日期及距上次访问的间隔
-- 技能点：LAG() 窗口函数、日期计算
WITH daily AS (
    SELECT DISTINCT session_id, DATE(ts) AS d FROM events
),
gaps AS (
    SELECT session_id,
           d,
           LAG(d) OVER (PARTITION BY session_id ORDER BY d) AS prev_d
    FROM daily
)
SELECT session_id,
       COUNT(*)                                                    AS active_days,
       MIN(d)                                                      AS first_day,
       MAX(d)                                                      AS last_day,
       ROUND(AVG(JULIANDAY(d) - JULIANDAY(prev_d)), 1)             AS avg_gap_days,
       MAX(CASE WHEN JULIANDAY(d) - JULIANDAY(prev_d) = 1 THEN 1 ELSE 0 END) AS has_next_day_return
FROM gaps
GROUP BY session_id
ORDER BY active_days DESC, last_day DESC;
