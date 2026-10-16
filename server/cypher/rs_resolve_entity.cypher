// $label is selected by the validated kind; labels are never caller text.
MATCH (e:{label} {id:$q})
RETURN '{label}' AS label, e.id AS id, 1.0 AS score, 'exact' AS how
