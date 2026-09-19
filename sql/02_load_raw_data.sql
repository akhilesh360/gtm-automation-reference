-- DuckDB-specific CSV loading. In Snowflake this file becomes COPY INTO from a stage.
DELETE FROM accounts;
INSERT INTO accounts SELECT * FROM read_csv_auto($raw_dir || '/accounts.csv', header=true);

DELETE FROM account_enrichment;
INSERT INTO account_enrichment SELECT * FROM read_csv_auto($raw_dir || '/clay_enrichment.csv', header=true);

DELETE FROM intent_signals;
INSERT INTO intent_signals SELECT * FROM read_csv_auto($raw_dir || '/intent_signals.csv', header=true);

DELETE FROM usage_signals;
INSERT INTO usage_signals SELECT * FROM read_csv_auto($raw_dir || '/usage_signals.csv', header=true);

DELETE FROM products;
INSERT INTO products SELECT * FROM read_csv_auto($raw_dir || '/products.csv', header=true);

DELETE FROM quote_requests;
INSERT INTO quote_requests SELECT * FROM read_csv_auto($raw_dir || '/quote_requests.csv', header=true);

DELETE FROM opportunities;
INSERT INTO opportunities SELECT * FROM read_csv_auto($raw_dir || '/opportunities.csv', header=true);

DELETE FROM opportunity_stage_history;
INSERT INTO opportunity_stage_history SELECT * FROM read_csv_auto($raw_dir || '/opportunity_stage_history.csv', header=true);
