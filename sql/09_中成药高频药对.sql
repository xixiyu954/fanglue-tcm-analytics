-- 09 药典中成药（剂型去重后）：高频药对共现与提升度 Top30
-- 技能点：利用 idx_fh_formula 索引执行大规模自连接、过滤队列口径、支持度/置信度/提升度计算
WITH n AS (
    SELECT COUNT(*) AS total FROM formula WHERE formula_type = '现代中成药'
),
single AS (
    SELECT fh.herb, COUNT(DISTINCT fh.formula) AS cnt
    FROM formula_herb fh
    JOIN formula f ON f.formula = fh.formula
    WHERE f.formula_type = '现代中成药'
    GROUP BY fh.herb
),
pair AS (
    SELECT a.herb AS herb_a, b.herb AS herb_b, COUNT(*) AS cnt
    FROM formula f
    JOIN formula_herb a ON a.formula = f.formula
    JOIN formula_herb b ON b.formula = f.formula AND a.herb < b.herb
    WHERE f.formula_type = '现代中成药'
    GROUP BY a.herb, b.herb
    HAVING COUNT(*) >= 80
)
SELECT p.herb_a,
       p.herb_b,
       p.cnt                                                AS co_count,
       ROUND(1.0 * p.cnt / n.total, 3)                      AS support,
       ROUND(1.0 * p.cnt / sa.cnt, 3)                       AS conf_a_to_b,
       ROUND(1.0 * p.cnt * n.total / (sa.cnt * sb.cnt), 2)  AS lift
FROM pair p
JOIN single sa ON sa.herb = p.herb_a
JOIN single sb ON sb.herb = p.herb_b
CROSS JOIN n
ORDER BY lift DESC, co_count DESC
LIMIT 30;
