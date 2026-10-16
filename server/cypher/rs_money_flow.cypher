// Aggregated seed-time FLOW projection avoids unsupported TX multi-edges.
// The server refuses as_of before the projection's latest transfer timestamp.
MATCH (s:Account) WHERE s.id IN $sources WITH collect(s) AS S
MATCH (t:Account) WHERE t.id IN $sinks WITH S,collect(t) AS T
CALL algo.maxFlow({sourceNodes:S,targetNodes:T,relationshipTypes:['FLOW'],capacityProperty:$cap})
YIELD nodes,edges,edgeFlows,maxFlow
RETURN maxFlow,[n IN nodes | n.id] AS node_ids,
 [i IN range(0,size(edges)-1) | {id:edges[i].id,flow:edgeFlows[i],amount:edges[i].amount,ts:edges[i].ts,first_ts:edges[i].first_ts,count:edges[i].w,source:startNode(edges[i]).id,target:endNode(edges[i]).id,type:'FLOW'}] AS flow_edges
