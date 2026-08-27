"""Benchmarks the deterministic batch engine against the real loaded
dataset and reports observed performance (not a hard-coded guarantee).

Usage: python -m scripts.benchmark
"""

from __future__ import annotations

import time

import validation.operators  # noqa: F401
from adapters import csv_adapter
from validation.dsl.loader import load_all_rules
from validation.engine import build_field_season_contexts, run_batch


def main() -> None:
    con = csv_adapter.get_connection()

    t0 = time.perf_counter()
    csv_adapter.load_all(con)
    t1 = time.perf_counter()

    rules = load_all_rules()
    t2 = time.perf_counter()

    contexts = build_field_season_contexts(con)
    t3 = time.perf_counter()

    results = run_batch(con, rules, validation_run_id="benchmark")
    t4 = time.perf_counter()

    field_seasons = len(contexts)
    print(f"CSV load + adapt:        {t1 - t0:.3f}s")
    print(f"Rule load + DSL validate:{t2 - t1:.3f}s ({len(rules)} rules)")
    print(f"Context build:           {t3 - t2:.3f}s ({field_seasons} field-seasons)")
    print(f"Rule evaluation:         {t4 - t3:.3f}s ({len(results)} results)")
    print(f"Total:                   {t4 - t0:.3f}s")
    print(
        f"Throughput: {field_seasons * len(rules) / (t4 - t3):,.0f} rule-evaluations/sec "
        f"({field_seasons / (t4 - t3):,.0f} field-seasons/sec across {len(rules)} rules)"
    )


if __name__ == "__main__":
    main()
