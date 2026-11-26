-- 04 经典名方：每首方剂的剂量加权寒热指数
-- 技能点：加权平均、COALESCE 处理缺失剂量、多表关联、CASE 分档
SELECT f.formula,
       f.dynasty,
       f.dynasty_order,
       f.category,
       ROUND(SUM(COALESCE(fh.dose_g, 1.0) * h.nature_score) / SUM(COALESCE(fh.dose_g, 1.0)), 2) AS heat_index,
       CASE
           WHEN SUM(COALESCE(fh.dose_g, 1.0) * h.nature_score) / SUM(COALESCE(fh.dose_g, 1.0)) <= -0.5 THEN '偏寒凉'
           WHEN SUM(COALESCE(fh.dose_g, 1.0) * h.nature_score) / SUM(COALESCE(fh.dose_g, 1.0)) <   0.5 THEN '平和'
           ELSE '偏温热'
       END AS tendency,
       COUNT(*) AS n_herbs
FROM formula f
JOIN formula_herb fh ON fh.formula = f.formula
JOIN herb h          ON h.herb = fh.herb
WHERE f.formula_type = '经典名方'
GROUP BY f.formula, f.dynasty, f.dynasty_order, f.category
ORDER BY heat_index;
