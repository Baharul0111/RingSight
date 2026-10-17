// v6.0.2's createNodeIndex(map) procedure is a no-op; DDL creates real indexes.
// Phonetic configuration is preserved, as exercised by the upstream6 tests.
CREATE FULLTEXT INDEX FOR (p:Person) ON (p.name_norm) OPTIONS {language:'English',phonetic:'dm:en'};
CREATE FULLTEXT INDEX FOR (m:Merchant) ON (m.name) OPTIONS {phonetic:'dm:en'};
CREATE FULLTEXT INDEX FOR (f:Finding) ON (f.text);
