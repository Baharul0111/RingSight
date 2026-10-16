CALL db.idx.fulltext.createNodeIndex({label:'Person', language:'English'}, {field:'name_norm', phonetic:'dm:en'});
CALL db.idx.fulltext.createNodeIndex('Merchant', {field:'name', phonetic:'dm:en'});
CALL db.idx.fulltext.createNodeIndex('Finding', 'text');
