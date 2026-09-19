-- Deliberately breaking every convention in snake-case-team.sqlfluff.
-- Run:
--   sqlfluff lint examples/demo.sql --config examples/snake-case-team.sqlfluff

CREATE TABLE Orders (
    active BOOLEAN COMMENT 'TODO',
    created TIMESTAMP,
    CustomerId STRING
) USING parquet;

CREATE VIEW active_orders AS
SELECT CAST(x AS BOOLEAN) AS active, * FROM Orders;

DROP TABLE Orders;
