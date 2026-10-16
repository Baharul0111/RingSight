MATCH (s:Account {id:$src}),(d:Account {id:$dst})
CALL algo.SPpaths({sourceNode:s,targetNode:d,relTypes:$rel_types,relDirection:'outgoing',weightProp:$wprop,maxLen:$max_hops,pathCount:$k})
YIELD path,pathWeight
RETURN [n IN nodes(path) | n.id] AS node_ids,
 [r IN relationships(path) | {id:r.id,type:type(r),amount:r.amount,ts:r.ts,rail:r.rail}] AS edges,
 length(path) AS hops,pathWeight
