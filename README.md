# TPCH-Benchmark-for-DuckDB

For this benchmarking, I have used DuckDB and used the filter complexity dimension. For the configuration, I choose In-memory vs on-disk database as a discrete option and vary the size
of the dataset(scale factors-0.1,1,3) as the continuous option. Using these two configurations helps to understand how the volume of data and complexity of the queries influence the performance of the in-memory and on-disk databases.

# Queries used

Query 1: Simple query - Uses only two equality predicates and has no subqueries, no
expressions, no aggregates

SELECT * from lineitem where l_returnflag='N' AND l_shipmode='MAIL';

Query 2: Moderate - Uses Range , AND and LIKE filters. This query requires more CPU
work due to different comparison types.

SELECT l_orderkey,l_shipdate,l_extendedprice,l_shipmode,l_linestatus
FROM lineitem
WHERE
l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-12-31'
AND l_extendedprice >= 10000
AND l_shipmode LIKE 'AIR%' ;

Query 3: Multi clause - Uses BETWEEN, EXISTS, correlated subquery, grouping, HAVING and requires Requires multiple stages: scan → filter → subquery check → group → aggregate → filter again. The correlated subquery introduces nested-loop evaluation.

SELECT
l1.l_linestatus,
COUNT(*) AS line_count,
SUM(l1.l_extendedprice * (1 - l1.l_discount)) AS total_revenue
FROM lineitem l1
WHERE l1.l_extendedprice BETWEEN 100 AND 50000
AND EXISTS (
SELECT 1
FROM lineitem l2
WHERE l2.l_orderkey = l1.l_orderkey
AND l2.l_shipdate < l1.l_shipdate
AND l2.l_quantity > 10
)
GROUP BY l1.l_linestatus
HAVING SUM(l1.l_extendedprice) > 10000
ORDER BY total_revenue DESC, line_count DESC;

Query 4: Multi operator – Uses multiple scalar subqueries, CASE expressions and conditional string operators. Also contains Computation-heavy expressions like arithmetic
and date transformation. This makes the query more complex.

SELECT
l1.l_orderkey,
l1.l_linenumber,
(l1.l_extendedprice * (1 - l1.l_discount)) +
CASE
WHEN l1.l_tax > 0.05 THEN l1.l_tax * 100
ELSE l1.l_tax * 10
END AS base_revenue_score,
COALESCE((
SELECT AVG(l2.l_quantity)
FROM lineitem l2
WHERE l2.l_orderkey = l1.l_orderkey
AND l2.l_linenumber < l1.l_linenumber
), 0) AS avg_prev_line_quantity,
(SELECT SUM(l3.l_extendedprice)
FROM lineitem l3
WHERE l3.l_orderkey = l1.l_orderkey
) AS total_order_price,
EXTRACT(DAY FROM (l1.l_shipdate + INTERVAL 30 DAY))
AS target_delivery_day_of_month,
CASE
WHEN l1.l_comment LIKE '%URGENT%'
AND INSTR(l1.l_comment, 'PRIORITY') > 0
THEN SUBSTRING(l1.l_comment, 1, 10)
ELSE 'STANDARD'
END AS priority_status_code
FROM lineitem l1;
