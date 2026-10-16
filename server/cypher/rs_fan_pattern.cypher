// incoming/outgoing anchors and drain are enum-selected fixed templates.
MATCH {main}
WHERE t.ts>$as_of-$win AND t.ts<=$as_of
WITH a,count(DISTINCT s) AS n_cp,count(t) AS n_tx,sum(t.amount) AS total,min(t.ts) AS first_ts,max(t.ts) AS last_ts,
 collect({tx:t.id,source:{leg_src},target:{leg_dst},amount:t.amount,ts:t.ts,rail:t.rail,memo:t.memo,type:'TX'}) AS legs
WHERE n_cp >= $min_cp
OPTIONAL MATCH {drain}
WHERE o.ts>first_ts AND o.ts<=last_ts+$drain AND o.ts<=$as_of
WITH a,n_cp,n_tx,total,first_ts,last_ts,legs,count(o) AS drain_n,coalesce(sum(o.amount),0) AS drain_sum,
 collect({tx:o.id,source:{drain_src},target:{drain_dst},amount:o.amount,ts:o.ts,rail:o.rail,memo:o.memo,type:'TX'}) AS drain_legs
RETURN a.id AS account,n_cp,n_tx,total,first_ts,last_ts,legs[0..$limit] AS legs,drain_n,drain_sum,
 CASE WHEN total=0 THEN 0.0 ELSE toFloat(drain_sum)/toFloat(total) END AS drain_ratio,drain_legs[0..20] AS drain_legs
