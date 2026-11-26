-- 06 用户行为漏斗：访问 → 进入核心分析工具 → 完成分析 → 导出报告
-- 技能点：会话级去重、条件聚合、转化漏斗
WITH s AS (
    SELECT session_id,
           MAX(CASE WHEN event = 'page_view' THEN 1 ELSE 0 END) AS step1_visit,
           MAX(CASE WHEN event = 'page_view' AND page IN ('方剂体检', '网络药理学') THEN 1 ELSE 0 END) AS step2_open_tool,
           MAX(CASE WHEN event IN ('formula_analyzed', 'netpharm_run') THEN 1 ELSE 0 END) AS step3_analyze,
           MAX(CASE WHEN event = 'report_exported' THEN 1 ELSE 0 END) AS step4_export
    FROM events
    GROUP BY session_id
)
SELECT '1 访问平台'       AS step, COALESCE(SUM(step1_visit), 0) AS sessions FROM s
UNION ALL
SELECT '2 进入核心分析页', COALESCE(SUM(step1_visit * step2_open_tool), 0) FROM s
UNION ALL
SELECT '3 完成一次分析',   COALESCE(SUM(step1_visit * step2_open_tool * step3_analyze), 0) FROM s
UNION ALL
SELECT '4 导出报告/数据',  COALESCE(SUM(step1_visit * step2_open_tool * step3_analyze * step4_export), 0) FROM s;
