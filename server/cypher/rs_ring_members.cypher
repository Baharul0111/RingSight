// Count before any collection, to refuse a giant component cheaply.
MATCH (seed:Account {id:$id})
WITH seed.{prop} AS cid,seed.algo_run_at AS computed_at
MATCH (m:Account {{prop}:cid})
WITH cid,computed_at,count(m) AS n
RETURN cid,computed_at,n,(n >= $min AND n <= $max) AS in_bounds
