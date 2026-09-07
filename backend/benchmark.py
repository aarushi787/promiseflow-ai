"""Reproducible synthetic capacity benchmarks, never reads the live database."""

import json
import platform
import time
from datetime import datetime
from pathlib import Path
from .models import Factory
from .engine import CpSatProvider
from .validation import validate_plan


def dataset(orders, operations, resources):
    steps = operations // orders
    return Factory.model_validate(
        dict(
            customers=[dict(id="C", name="Synthetic benchmark customer")],
            calendars=[
                dict(
                    id="DAY",
                    name="Continuous test calendar",
                    weekdays=list(range(7)),
                    shifts=[[0, 1440]],
                )
            ],
            resources=[
                dict(id=f"R{i}", name=f"Synthetic resource {i}")
                for i in range(resources)
            ],
            materials=[],
            products=[
                dict(
                    id="P",
                    name="Synthetic benchmark product",
                    routing_id="ROUTE",
                    batch_size=100,
                )
            ],
            routings=[
                dict(
                    id="ROUTE",
                    name="Benchmark route",
                    operations=[
                        dict(
                            id=f"OP{i}",
                            name=f"Operation {i}",
                            sequence=i + 1,
                            alternatives=[
                                dict(
                                    resource_id=f"R{i%resources}",
                                    cycle_minutes=0.1,
                                    setup_minutes=5,
                                ),
                                dict(
                                    resource_id=f"R{(i+steps)%resources}",
                                    cycle_minutes=0.12,
                                    setup_minutes=3,
                                ),
                            ],
                        )
                        for i in range(steps)
                    ],
                )
            ],
            orders=[
                dict(
                    id=f"O{i}",
                    customer_id="C",
                    product_id="P",
                    quantity=100,
                    order_date="2026-09-07T00:00",
                    requested_date="2026-09-10T16:00",
                )
                for i in range(orders)
            ],
        )
    )


def main():
    rows = []
    for counts in [(50, 200, 10), (500, 2500, 50), (2000, 10000, 150)]:
        factory = dataset(*counts)
        start = time.perf_counter()
        try:
            result = CpSatProvider().solve(factory, datetime(2026, 9, 7))
            valid = (
                validate_plan(factory, result)
                if result["solver_status"] in ("FEASIBLE", "OPTIMAL")
                and not result["blocked"]
                else False
            )
            outcome = dict(
                status=result["solver_status"],
                validated=valid,
                scheduled=len(result["operations"]),
                solver_seconds=result["statistics"]["wall_seconds"],
            )
        except ValueError as exc:
            outcome = dict(status="REJECTED_SCOPE", reason=str(exc))
        rows.append(
            dict(
                orders=counts[0],
                operations=counts[1],
                resources=counts[2],
                elapsed_seconds=round(time.perf_counter() - start, 3),
                **outcome,
            )
        )
    report = dict(
        python=platform.python_version(),
        platform=platform.platform(),
        synthetic=True,
        runs=rows,
    )
    Path("docs/benchmark-results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
