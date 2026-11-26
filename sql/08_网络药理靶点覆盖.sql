-- 08 网络药理学：各药材活性成分与实验靶点覆盖排名 Top25
-- 技能点：三表关联、条件聚合、去重计数、均值统计
SELECT hc.herb,
       h.category,
       COUNT(DISTINCT c.cid)                                             AS n_compounds,
       COUNT(DISTINCT CASE WHEN c.lipinski_pass = 1 AND c.QED >= 0.45 THEN c.cid END) AS n_druglike,
       COUNT(DISTINCT ct.gene)                                           AS n_targets,
       ROUND(AVG(c.QED), 3)                                              AS avg_qed,
       ROUND(AVG(c.OB_score), 1)                                         AS avg_ob
FROM np_herb_compound hc
JOIN np_compound c        ON c.cid = hc.cid
JOIN np_compound_target ct ON ct.cid = c.cid
LEFT JOIN herb h          ON h.herb = hc.herb
GROUP BY hc.herb, h.category
ORDER BY n_targets DESC, n_compounds DESC
LIMIT 25;
