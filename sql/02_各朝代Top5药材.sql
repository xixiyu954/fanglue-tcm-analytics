-- 02 经典名方：各朝代高频药材 Top5
-- 技能点：ROW_NUMBER() 分组取 TopN、限定经典名方口径避免现代中成药稀释历史分布
WITH usage AS (
    SELECT f.dynasty,
           f.dynasty_order,
           fh.herb,
           COUNT(DISTINCT fh.formula) AS n_formula
    FROM formula_herb fh
    JOIN formula f ON f.formula = fh.formula
    WHERE f.formula_type = '经典名方'
    GROUP BY f.dynasty, f.dynasty_order, fh.herb
)
SELECT dynasty, herb, n_formula
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY dynasty ORDER BY n_formula DESC, herb) AS rn
    FROM usage
)
WHERE rn <= 5
ORDER BY dynasty_order, rn;
