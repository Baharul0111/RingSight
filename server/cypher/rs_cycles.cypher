// Fixed unrolled lengths 3, 4, 5. No caller string enters the template.
MATCH {pattern}
WHERE {predicates}
RETURN {length} AS len,[{accounts}] AS accounts,
 [{edges}] AS edges,
 r{length}.ts-r1.ts AS span_s
LIMIT $limit
