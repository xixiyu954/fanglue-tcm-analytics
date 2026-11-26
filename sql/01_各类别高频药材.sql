-- 01 各功效类别的高频药材 Top3
-- 技能点：CTE、聚合、RANK() 窗口函数
WITH herb_usage AS (
    SELECT f.category,
           fh.herb,
           COUNT(DISTINCT fh.formula) AS n_formula
    FROM formula_herb fh
    JOIN formula f ON f.formula = fh.formula
    GROUP BY f.category, fh.herb
),
category_size AS (
    SELECT category, COUNT(*) AS n_total FROM formula GROUP BY category
),
ranked AS (
    SELECT u.category,
           u.herb,
           u.n_formula,
           ROUND(1.0 * u.n_formula / c.n_total, 2) AS usage_rate,
           RANK() OVER (PARTITION BY u.category ORDER BY u.n_formula DESC) AS rnk
    FROM herb_usage u
    JOIN category_size c ON c.category = u.category
)
SELECT category, rnk, herb, n_formula, usage_rate
FROM ranked
WHERE rnk <= 3
ORDER BY category, rnk, herb;
