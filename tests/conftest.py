from datetime import datetime
import pytest
from backend.models import Factory


@pytest.fixture
def base():
    return datetime(2026, 9, 7)


@pytest.fixture
def factory():
    return Factory.model_validate(
        dict(
            customers=[dict(id="C", name="Test customer")],
            calendars=[
                dict(
                    id="DAY",
                    name="Day shift",
                    weekdays=[0, 1, 2, 3, 4],
                    shifts=[[480, 960]],
                )
            ],
            resources=[
                dict(id="M1", name="Machine one"),
                dict(id="M2", name="Machine two"),
            ],
            materials=[dict(id="MAT", description="Blank", stock=1000)],
            auxiliaries=[
                dict(id="TOOL", name="Fixture", kind="Tool"),
                dict(id="OP", name="Operator", kind="Operator", skill="Machining"),
            ],
            routings=[
                dict(
                    id="R",
                    name="Two operations",
                    operations=[
                        dict(
                            id="10",
                            name="Machine",
                            sequence=10,
                            alternatives=[
                                dict(
                                    resource_id="M1", cycle_minutes=1, setup_minutes=10
                                ),
                                dict(
                                    resource_id="M2", cycle_minutes=1.2, setup_minutes=5
                                ),
                            ],
                            required_skill="Machining",
                            tool_id="TOOL",
                        ),
                        dict(
                            id="20",
                            name="Inspect",
                            sequence=20,
                            alternatives=[
                                dict(
                                    resource_id="M2", cycle_minutes=0.5, setup_minutes=5
                                )
                            ],
                            transfer_minutes=10,
                        ),
                    ],
                )
            ],
            products=[
                dict(
                    id="P",
                    name="Product",
                    routing_id="R",
                    batch_size=100,
                    materials=[dict(material_id="MAT", per_unit=1)],
                )
            ],
            orders=[
                dict(
                    id="A",
                    customer_id="C",
                    product_id="P",
                    quantity=100,
                    order_date="2026-09-07T00:00",
                    requested_date="2026-09-09T16:00",
                    priority="High",
                ),
                dict(
                    id="B",
                    customer_id="C",
                    product_id="P",
                    quantity=100,
                    order_date="2026-09-07T00:00",
                    requested_date="2026-09-09T16:00",
                ),
            ],
        )
    )
