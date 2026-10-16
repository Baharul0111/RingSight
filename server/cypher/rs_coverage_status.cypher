MATCH (r:Rail) WITH collect({name:r.name,first:r.first_loaded,last:r.last_loaded}) AS rails
OPTIONAL MATCH (d:IngestionDay)
WHERE ($rail IS NULL OR d.rail=$rail) AND ($f IS NULL OR d.date >= $f) AND ($t IS NULL OR d.date <= $t)
WITH rails,collect({rail:d.rail,date:d.date,source:d.source_count,graph:d.graph_count,delta:d.source_count-d.graph_count}) AS days
RETURN rails,days,[x IN days WHERE x.delta<>0 | x] AS delta_days,
 [x IN ['UPI','NEFT','RTGS','IMPS','CARD','WALLET','CASH','XB'] WHERE NOT x IN [r IN rails | r.name]] AS missing_rails
