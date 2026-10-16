MATCH (a:Account{scope})
WHERE $inc OR NOT a.type IN ['merchant','payroll','exchange']
RETURN a.id AS id,a.type AS type,a.pagerank AS pagerank,a.betweenness AS betweenness,a.in_deg AS in_deg,a.out_deg AS out_deg,
 a.type IN ['merchant','payroll','exchange'] AS legit_hub,a.algo_run_at AS computed_at,$exact AS exact
ORDER BY a.{metric} DESC,a.id LIMIT $limit
