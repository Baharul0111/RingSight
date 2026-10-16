MATCH (a:Account {id:$id})
OPTIONAL MATCH (a)<-[i:TX]-(s:Account) WHERE i.ts > $from AND i.ts <= $as_of
WITH a, count(i) AS in_n, coalesce(sum(i.amount),0) AS in_sum, count(DISTINCT s) AS in_cp, max(i.amount) AS in_max
OPTIONAL MATCH (a)-[o:TX]->(r:Account) WHERE o.ts > $from AND o.ts <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, count(o) AS out_n, coalesce(sum(o.amount),0) AS out_sum, count(DISTINCT r) AS out_cp
OPTIONAL MATCH (p:Person)-[own:OWNS]->(a) WHERE coalesce(own.since,0) <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, collect(DISTINCT p.id) AS owners
OPTIONAL MATCH (a)-[u:USES_DEVICE]->(d:Device) WHERE u.first_seen <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, owners, collect(DISTINCT {id:d.id,degree:d.degree}) AS devices
OPTIONAL MATCH (al:Alert)-[:ON]->(a) WHERE al.raised_at <= $as_of
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, owners, devices, collect(DISTINCT {id:al.id,rule:al.rule,raised_at:al.raised_at}) AS alerts
OPTIONAL MATCH (rx:Restriction)-[:ON]->(a) WHERE rx.in_force_from <= $as_of AND (rx.in_force_to IS NULL OR rx.in_force_to >= $as_of)
WITH a, in_n, in_sum, in_cp, in_max, out_n, out_sum, out_cp, owners, devices, alerts, collect(DISTINCT {id:rx.id,kind:rx.kind}) AS restrictions
OPTIONAL MATCH (f:Finding)-[:ABOUT]->(a) WHERE f.created_at <= $as_of AND f.expired_at IS NULL
RETURN a.id AS id, a.type AS type, a.bank AS bank, a.opened_at AS opened_at, a.kyc_tier AS kyc_tier, a.status AS status,
 a.in_deg AS in_deg, a.out_deg AS out_deg, a.pagerank AS pagerank, a.betweenness AS betweenness,
 a.wcc_id AS wcc_id, a.lpa_id AS lpa_id, a.ring_id AS ring_id, a.algo_run_at AS computed_at,
 in_n,in_sum,in_cp,in_max,out_n,out_sum,out_cp,
 CASE WHEN in_sum=0 OR out_sum=0 THEN 0.0 ELSE toFloat(CASE WHEN in_sum<out_sum THEN in_sum ELSE out_sum END)/toFloat(CASE WHEN in_sum<out_sum THEN out_sum ELSE in_sum END) END AS passthrough_ratio,
 owners,devices,alerts,restrictions,count(DISTINCT f) AS prior_findings
