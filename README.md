# 🦆 TPCH-Benchmark-for-DuckDB

## 📌 Overview

This project benchmarks DuckDB performance using different query complexities and storage configurations based on the TPC-H dataset.

The benchmark evaluates how:
- 📈 Increasing dataset size
- 🧠 Query complexity
- 💾 Storage mode (In-memory vs On-disk)

influence analytical query performance in DuckDB.

---

# ⚙️ Benchmark Configuration

## 🗄️ Database Modes

- 🧠 In-Memory Database
- 💽 On-Disk Database

---

## 📊 Dataset Scale Factors

The following TPC-H scale factors were used:

- 0.1
- 1
- 3

These configurations help analyze how data volume and query complexity impact execution performance under different storage strategies.

---

# 🧪 Query Complexity Categories

| Query | Complexity Level | Characteristics |
|---|---|---|
| Query 1 | 🟢 Simple | Equality filters only |
| Query 2 | 🟡 Moderate | Range filters, LIKE, AND conditions |
| Query 3 | 🟠 Multi-Clause | Correlated subqueries, grouping, aggregation |
| Query 4 | 🔴 Multi-Operator | Scalar subqueries, CASE expressions, string operations |

---

# 🟢 Query 1 — Simple Query

Uses:
- Equality predicates
- No aggregates
- No expressions
- No subqueries

```sql
SELECT * 
FROM lineitem 
WHERE l_returnflag='N' 
AND l_shipmode='MAIL';
```

### 🔍 Purpose
Evaluates baseline scan and filter performance with minimal computational overhead.

---

# 🟡 Query 2 — Moderate Complexity Query

Uses:
- BETWEEN range filter
- AND conditions
- LIKE pattern matching

```sql
SELECT 
    l_orderkey,
    l_shipdate,
    l_extendedprice,
    l_shipmode,
    l_linestatus
FROM lineitem
WHERE
    l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-12-31'
    AND l_extendedprice >= 10000
    AND l_shipmode LIKE 'AIR%';
```

### 🔍 Purpose
Measures CPU overhead caused by mixed comparison operators and filtering logic.

---

# 🟠 Query 3 — Multi-Clause Query

Uses:
- BETWEEN filters
- EXISTS correlated subquery
- GROUP BY
- HAVING
- ORDER BY
- Aggregations

```sql
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
```

### 🔍 Purpose
Evaluates performance under:
- Nested-loop evaluation
- Multi-stage execution pipelines
- Aggregation-heavy workloads

Execution stages:
```text
Scan → Filter → Correlated Subquery → Group → Aggregate → Filter → Sort
```

---

# 🔴 Query 4 — Multi-Operator Query

Uses:
- Scalar subqueries
- CASE expressions
- Arithmetic computations
- Date transformations
- String functions
- Conditional logic

```sql
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

    (
        SELECT SUM(l3.l_extendedprice)
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
```

### 🔍 Purpose
Benchmarks computation-heavy analytical workloads involving:
- Complex expressions
- Nested scalar subqueries
- String processing
- Date arithmetic
- Conditional transformations

---

# 🏗️ Benchmark Architecture

## 🔄 Workflow

```text
TPC-H Dataset
      ↓
DuckDB Database
      ↓
In-Memory / On-Disk Execution
      ↓
Query Execution
      ↓
Performance Measurement
      ↓
Result Analysis
```

---

# 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Database Engine | DuckDB | Analytical query execution |
| Benchmark Dataset | TPC-H | Standard analytical benchmarking dataset |
| Query Language | SQL | Query execution and analytics |
| Programming Language | Python | Benchmark orchestration and automation |
| Data Processing | Pandas | Result handling and analysis |
| Storage Modes | In-memory / On-disk | Performance comparison |

---

# 🚀 Key Features

- TPC-H benchmark execution
- Query complexity analysis
- In-memory vs on-disk comparison
- Multi-scale dataset evaluation
- CPU-intensive query benchmarking
- Correlated subquery performance testing
- Aggregation and filter analysis
- Analytical workload simulation

---

# 🎯Outcomes

- Compare DuckDB execution performance across storage modes
- Analyze how query complexity impacts execution time
- Measure scalability with increasing dataset sizes
- Understand performance trade-offs between memory and disk-based execution
- Benchmark analytical SQL workloads in DuckDB environments

---
