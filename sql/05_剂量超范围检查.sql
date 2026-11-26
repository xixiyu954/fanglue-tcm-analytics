-- 05 数据质量：经典方剂量超出药典常用量范围的记录
-- 技能点：区间校验、空值过滤、数据质量规则
SELECT fh.formula,
       fh.herb_raw,
       fh.herb,
       fh.dose_g,
       h.dose_min,
       h.dose_max,
       CASE WHEN fh.dose_g > h.dose_max THEN '高于上限' ELSE '低于下限' END AS issue,
       f.source,
       f.dynasty
FROM formula_herb fh
JOIN herb h    ON h.herb = fh.herb
JOIN formula f ON f.formula = fh.formula
WHERE fh.dose_g IS NOT NULL
  AND h.dose_max IS NOT NULL
  AND (fh.dose_g > h.dose_max OR fh.dose_g < h.dose_min)
ORDER BY issue, fh.dose_g / COALESCE(h.dose_max, 1) DESC;
