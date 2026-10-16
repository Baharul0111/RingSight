// Fixed unrolled lengths 3, 4, 5. No caller string enters the template.
MATCH p={pattern}
WHERE {predicates}
RETURN {length} AS len,[n IN nodes(p) | n.id] AS accounts,
 [i IN range(0,{last_index}) | {id:relationships(p)[i].id,amount:relationships(p)[i].amount,ts:relationships(p)[i].ts,rail:relationships(p)[i].rail,memo:relationships(p)[i].memo,source:nodes(p)[i].id,target:nodes(p)[i+1].id,type:'TX'}] AS edges,
 r{length}.ts-r1.ts AS span_s
LIMIT $limit
