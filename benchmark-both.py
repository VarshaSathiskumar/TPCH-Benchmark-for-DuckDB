# NOTE: To actually clear the OS page cache, you must run with sudo privileges.
# On Linux this uses:  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
# On macOS this uses:  sudo purge

import os
os.environ.setdefault("MPLBACKEND", "Agg")
from matplotlib.lines import Line2D

import time
from pathlib import Path
import platform
import duckdb
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.ticker as ticker

WARMUPS = 3
RUNS = 10
SCALE_FACTORS = [0.1, 1, 3]  # edit as needed
CLEAR_OS_CACHE = False       # set to False if you don't want to drop caches

# ---------------------------------
# Four queries
# ---------------------------------

QUERIES = {

    "Q1 Simple":
    """
    SELECT * from lineitem where l_returnflag='N' and l_shipmode='MAIL';
    """,

    "Q2 Moderate":
    """
    SELECT
        l_orderkey,
        l_shipdate,
        l_extendedprice,
        l_shipmode,
        l_linestatus
    FROM lineitem
    WHERE l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-12-31'
      AND l_extendedprice >= 10000
      AND l_shipmode LIKE 'AIR%';
    """,

    "Q3 Multi-clause":
    """
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
    """,

    "Q4 Multi-operator ":
    """
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
    """
}

# ----------------------------
# OS cache clearing
# ----------------------------

def clear_os_cache():
    """
    Try to drop the OS page cache so 'On-Disk' timing is less affected
    by filesystem cache. Requires sudo privileges.
    """
    if not CLEAR_OS_CACHE:
        return

    system = platform.system().lower()

    try:
        if "linux" in system:
            cmd = "sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null"
        elif "darwin" in system:  # macOS
            cmd = "sudo purge"
        else:
            print(f"[WARN] OS cache clearing not supported on {system}")
            return

        print(f"[INFO] Clearing OS cache using: {cmd}")
        ret = os.system(cmd)
        if ret != 0:
            print(f"[WARN] OS cache clearing command returned code {ret}")
    except Exception as e:
        print(f"[WARN] Failed to clear OS cache: {e}")

# ----------------------------
# Data preparation utilities
# ----------------------------

def ensure_tpch_on_disk(con, sf: float):
    """Ensure TPC-H tables exist in this on-disk DB at the given scale factor."""
    has_orders = con.execute("""
        SELECT COUNT(*) > 0
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'orders';
    """).fetchone()[0]
    if not has_orders:
        print(f"[INFO] Populating TPC-H SF={sf} on disk...")
        con.execute("INSTALL tpch;")
        con.execute("LOAD tpch;")
        con.execute(f"CALL dbgen(sf={sf});")
        con.execute("ANALYZE;")
        con.execute("CHECKPOINT;")

def prepare_tpch_in_memory(con, sf: float):
    """Generate TPC-H tables at the given scale factor in this in-memory DB."""
    con.execute("INSTALL tpch;")
    con.execute("LOAD tpch;")
    con.execute(f"CALL dbgen(sf={sf});")
    con.execute("ANALYZE;")

def run_benchmark(con, query: str, warmups: int, runs: int):
    """Return (first_column_value, timings_ms_list)."""
    # Warmups (not timed)
    for _ in range(warmups):
        con.execute(query).fetchone()

    timings_ms = []
    result = None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = con.execute(query).fetchone()
        t1 = time.perf_counter()
        timings_ms.append((t1 - t0) * 1000.0)
    return result[0], timings_ms

# ----------------------------
# Statistics helpers
# ----------------------------

def mean_std(values):
    m = float(np.mean(values)) if len(values) else 0.0
    s = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return m, s

def biggest_jump(vals):
    """
    Find the largest relative jump between consecutive values.
    Returns (i0, i1, pct_change) where pct_change is (v1 - v0) / v0.
    """
    if len(vals) < 2:
        return (0, 0, 0.0)
    best = (0, 1, 0.0)
    for i in range(len(vals) - 1):
        base = vals[i] if vals[i] != 0 else 1e-9
        pct = (vals[i+1] - vals[i]) / base
        if abs(pct) > abs(best[2]):
            best = (i, i+1, pct)
    return best

# ----------------------------
# Plot 1: runtimes vs scale factor (mean ± stddev, with annotations)
# ----------------------------

def plot_lines_all_queries(scale_factors, summary):
    """
    summary[query_label][mode][sf] = { 'mean': m, 'std': s, 'result': r }
    mode in {'disk','mem'}

    Figure 1: line plot of mean runtime vs scale factor for each query,
    where the mean is computed by combining On-Disk and In-Memory
    runtimes:

        combined_mean(sf) ≈ (mean_disk(sf) + mean_mem(sf)) / 2

    Error bars show the (simple) average of stddevs from disk and mem.

    Below the plot, a table lists, for each query, the largest relative
    runtime jump and the scale-factor range where it occurs, based on
    these combined means.
    """
    fig, ax = plt.subplots(figsize=(9.5, 6))

    query_labels = list(summary.keys())
    cmap = plt.get_cmap("tab10")
    all_means = []

    # Precompute combined mean/std per query and sf
    combined = {
        qlabel: {
            sf: {
                "mean": (
                    summary[qlabel]["disk"][sf]["mean"]
                    + summary[qlabel]["mem"][sf]["mean"]
                ) / 2.0,
                # simple average of stddevs for visualization
                "std": (
                    summary[qlabel]["disk"][sf]["std"]
                    + summary[qlabel]["mem"][sf]["std"]
                ) / 2.0,
            }
            for sf in scale_factors
        }
        for qlabel in query_labels
    }

    # ==== draw lines + error bars: ONE line per query (disk+mem combined) ====
    for qi, qlabel in enumerate(query_labels):
        color = cmap(qi % 10)

        means = [combined[qlabel][sf]["mean"] for sf in scale_factors]
        stds  = [combined[qlabel][sf]["std"]  for sf in scale_factors]

        means = np.array(means)
        stds  = np.array(stds)
        all_means.extend(list(means))

        ax.errorbar(
            scale_factors,
            means,
            yerr=stds,
            fmt='-o',
            capsize=4,
            label=f"{qlabel} (avg Disk+Mem)",
            color=color,
        )

    ax.set_title(
        "Figure 1. Mean Query runtime vs Scale factor (Disk+Memory average) for DuckDB\n"
        "Error bars show mean ± 1 standard deviation (avg of disk & mem)",
        fontsize=10,
    )
    ax.set_xlabel("Scale Factor (SF)")
    ax.set_ylabel("Mean Query runtime (ms)")
    ax.grid(True, which='both', linestyle=':', linewidth=0.7)

    # log scale if needed
    use_log = False
    if all_means:
        minv = max(min(all_means), 1e-9)
        maxv = max(all_means)
        if maxv / minv >= 2.0:
            use_log = True
            ax.set_yscale("log")
        top = maxv
        lower = minv / 1.5 if use_log else 0.0
        ax.set_ylim(lower, top * 1.45)

    # leave space at bottom for the table (and keep x-axis visible)
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.30)

    # ==== build table with biggest jumps (4 rows: 1 per query) ====
    table_rows = []
    for qlabel in query_labels:
        means = [combined[qlabel][sf]["mean"] for sf in scale_factors]
        i0, i1, pct = biggest_jump(means)
        if len(scale_factors) >= 2:
            sf_from = scale_factors[i0]
            sf_to = scale_factors[i1]
            sf_range_str = f"{sf_from} → {sf_to}"
        else:
            sf_range_str = "N/A"

        table_rows.append([
            qlabel,
            "Disk+Mem avg",
            f"{pct * 100:.1f}%",
            sf_range_str,
        ])

    header = ["Query", "Mode", "Largest Δruntime", "SF range"]
    table_data = [header] + table_rows

    # place table slightly below the main axes so it doesn't hide x-axis
    ax_table = fig.add_axes([0.10, 0.02, 0.80, 0.23])
    ax_table.axis("off")
    table = ax_table.table(
        cellText=table_data,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6)
    table.scale(1.0, 1.0)

    ax.legend(
        ncols=2,
        fontsize=7.2,
        frameon=True,
        framealpha=0.9,
        borderpad=0.4,
        handlelength=2.5,
    )

    plt.savefig("figure_1_lines_4queries_disk_mem_combined_cacheclear.png", dpi=150)
    plt.close(fig)

# ----------------------------
# Plot 2: runtime by query, scale factor, and mode (mean ± stddev)
# ----------------------------

def plot_runtime_by_query(scale_factors, summary):
    """
    For each query and scale factor, show mean runtime (ms)
    for both On-Disk and In-Memory as grouped bars.

    Error bars represent mean ± 1 standard deviation across RUNS repetitions.

    summary[query_label][mode][sf] = { 'mean': m, 'std': s, 'result': r }
    """
    query_labels = list(summary.keys())
    n_queries = len(query_labels)
    n_sf = len(scale_factors)

    # Collect times and stddevs
    times_disk = {qlabel: [] for qlabel in query_labels}
    times_mem  = {qlabel: [] for qlabel in query_labels}
    std_disk   = {qlabel: [] for qlabel in query_labels}
    std_mem    = {qlabel: [] for qlabel in query_labels}
    all_means = []

    for qlabel in query_labels:
        for sf in scale_factors:
            md = summary[qlabel]["disk"][sf]["mean"]
            mm = summary[qlabel]["mem"][sf]["mean"]
            sd = summary[qlabel]["disk"][sf]["std"]
            sm = summary[qlabel]["mem"][sf]["std"]
            times_disk[qlabel].append(md)
            times_mem[qlabel].append(mm)
            std_disk[qlabel].append(sd)
            std_mem[qlabel].append(sm)
            all_means.extend([md, mm])

    fig, ax = plt.subplots(figsize=(9.5, 6), constrained_layout=True)

    x = np.arange(n_queries)
    slots = n_sf * 2                # each SF has 2 bars (disk + mem)
    group_width = 0.9
    width = group_width / slots
    cmap = plt.get_cmap("tab10")

    # Draw bars with error bars
    for qi, qlabel in enumerate(query_labels):
        for i, sf in enumerate(scale_factors):
            md = times_disk[qlabel][i]
            mm = times_mem[qlabel][i]
            sd = std_disk[qlabel][i]
            sm = std_mem[qlabel][i]

            # positions within the group
            slot_disk = i * 2
            slot_mem  = i * 2 + 1
            x_disk = x[qi] + (slot_disk - (slots - 1) / 2) * width
            x_mem  = x[qi] + (slot_mem  - (slots - 1) / 2) * width

            color = cmap(i)

            # On-Disk bar (more opaque)
            ax.bar(
                x_disk, md, width=width,
                yerr=sd, capsize=3,
                color=color, alpha=0.9,
                label=f"SF={sf} On-Disk" if qi == 0 else "_nolegend_"
            )

            # In-Memory bar (same color, lighter alpha)
            ax.bar(
                x_mem, mm, width=width,
                yerr=sm, capsize=3,
                color=color, alpha=0.4,
                label=f"SF={sf} In-Memory" if qi == 0 else "_nolegend_"
            )

    ax.set_xticks(x)
    ax.set_xticklabels(query_labels, rotation=0)
    ax.set_xlabel("Queries")
    ax.set_ylabel("Mean Query runtime (ms)")
    ax.set_title(
        "Figure 2. Mean Query runtime vs Complexity of Queries (Scale Factors,In-Memory and On-disk) for DuckDB\n"
        "Error bars show mean ± 1 standard deviation over runs"
    )
    ax.grid(axis="y", linestyle=":", linewidth=0.7)

    # Optional: log scale if ranges are large
    if all_means:
        minv = max(min(all_means), 1e-9)
        maxv = max(all_means)
        if maxv / minv >= 10.0:
            ax.set_yscale("log")

    ax.legend(ncols=2, fontsize=7.5, frameon=True, framealpha=0.9)

    plt.xticks(rotation=0, ha="center")
    plt.tight_layout(rect=[0, 0.10, 1, 1])


    plt.savefig("figure_2_runtime_by_query_sf_mode.png", dpi=150)
    plt.close(fig)

# ----------------------------
# Main
# ----------------------------

def main():
    # summary[query_label][mode][sf] = {...}
    summary = {
        qlabel: {"disk": {}, "mem": {}}
        for qlabel in QUERIES.keys()
    }

    # 1) Ensure on-disk DBs exist (only once per SF)
    for sf in SCALE_FACTORS:
        db_path = Path(f"tpch_sf{sf}.duckdb")
        con = duckdb.connect(str(db_path))
        ensure_tpch_on_disk(con, sf)
        con.close()

    # 2) On-Disk runs (clear OS cache before each (query, sf) measurement)
    for qlabel, query_sql in QUERIES.items():
        print(f"=== {qlabel} : On-Disk ===")
        for sf in SCALE_FACTORS:
            db_path = Path(f"tpch_sf{sf}.duckdb")

            clear_os_cache()  # <-- important step

            con = duckdb.connect(str(db_path))
            result, timings = run_benchmark(con, query_sql, WARMUPS, RUNS)
            con.close()

            print(f"SF={sf} timings (ms): {timings}")
            m, s = mean_std(timings)
            summary[qlabel]["disk"][sf] = {
                "result": result,
                "mean": m,
                "std": s
            }

    # 3) In-Memory runs (no OS cache clearing needed, data is generated fresh)
    for qlabel, query_sql in QUERIES.items():
        print(f"=== {qlabel} : In-Memory ===")
        for sf in SCALE_FACTORS:
            con = duckdb.connect(":memory:")
            prepare_tpch_in_memory(con, sf)
            result, timings = run_benchmark(con, query_sql, WARMUPS, RUNS)
            con.close()

            print(f"SF={sf} timings (ms): {timings}")
            m, s = mean_std(timings)
            summary[qlabel]["mem"][sf] = {
                "result": result,
                "mean": m,
                "std": s
            }

    # 4) Figures
    plot_lines_all_queries(SCALE_FACTORS, summary)
    plot_runtime_by_query(SCALE_FACTORS, summary)

    print("Saved figures:")
    print("  figure1.png")
    print("  figure2..png")
    print("Queries run:")
    for qlabel in QUERIES.keys():
        print(" ", qlabel)


if __name__ == "__main__":
    main()
