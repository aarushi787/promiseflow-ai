from datetime import datetime, timedelta
from .models import Factory


def demo_factory(today=None):
    base = (today or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    while base.weekday() == 6:
        base += timedelta(days=1)

    def date(days, hour=16):
        return (base + timedelta(days=days, hours=hour)).isoformat()

    resources = [
        ("SAW-01", "Band saw 01", "Cutting", 350),
        ("CNC-01", "CNC turning 01", "Turning", 650),
        ("CNC-02", "CNC turning 02", "Turning", 720),
        ("VMC-01", "Vertical mill 01", "Milling", 850),
        ("VMC-02", "Vertical mill 02", "Milling", 900),
        ("GRD-01", "Cylindrical grinder", "Grinding", 550),
        ("CMM-01", "CMM inspection", "Quality", 450),
        ("HT-EXT", "Deccan Heat Treatment", "External vendor", 120),
    ]

    def alt(r, c, s=20, **kw):
        return dict(resource_id=r, cycle_minutes=c, setup_minutes=s, **kw)

    routings = [
        dict(
            id="RT-SHAFT",
            name="Shaft · 6-stage process",
            operations=[
                dict(
                    id="OP10",
                    name="Blank cutting",
                    sequence=10,
                    alternatives=[alt("SAW-01", 0.28)],
                ),
                dict(
                    id="OP20",
                    name="CNC turning",
                    sequence=20,
                    alternatives=[alt("CNC-01", 1.7, 40), alt("CNC-02", 1.45, 45)],
                    required_skill="Turning",
                    tool_id="FX-12",
                ),
                dict(
                    id="OP30",
                    name="Keyway milling",
                    sequence=30,
                    alternatives=[alt("VMC-01", 1.1, 30), alt("VMC-02", 0.95, 35)],
                ),
                dict(
                    id="OP40",
                    name="Heat treatment",
                    sequence=40,
                    alternatives=[
                        alt(
                            "HT-EXT",
                            0.01,
                            0,
                            external_lead_minutes=1440,
                            transit_minutes=240,
                            unit_cost=18,
                        )
                    ],
                ),
                dict(
                    id="OP50",
                    name="Finish grinding",
                    sequence=50,
                    alternatives=[alt("GRD-01", 0.6)],
                ),
                dict(
                    id="OP60",
                    name="Final inspection",
                    sequence=60,
                    alternatives=[alt("CMM-01", 0.35)],
                    transfer_minutes=60,
                ),
            ],
        ),
        dict(
            id="RT-HOUSING",
            name="Housing · machining & inspection",
            operations=[
                dict(
                    id="OP10",
                    name="Face milling",
                    sequence=10,
                    alternatives=[alt("VMC-01", 1.4, 35), alt("VMC-02", 1.2, 35)],
                ),
                dict(
                    id="OP20",
                    name="Bore turning",
                    sequence=20,
                    alternatives=[alt("CNC-01", 1.15, 25), alt("CNC-02", 1, 25)],
                    required_skill="Turning",
                ),
                dict(
                    id="OP30",
                    name="Dimensional inspection",
                    sequence=30,
                    alternatives=[alt("CMM-01", 0.4)],
                ),
            ],
        ),
        dict(
            id="RT-FLANGE",
            name="Flange · turning & drilling",
            operations=[
                dict(
                    id="OP10",
                    name="CNC profile turning",
                    sequence=10,
                    alternatives=[alt("CNC-01", 0.9, 25), alt("CNC-02", 0.8, 25)],
                    required_skill="Turning",
                ),
                dict(
                    id="OP20",
                    name="PCD drilling",
                    sequence=20,
                    alternatives=[alt("VMC-01", 0.6), alt("VMC-02", 0.5)],
                ),
                dict(
                    id="OP30",
                    name="Final inspection",
                    sequence=30,
                    alternatives=[alt("CMM-01", 0.25)],
                ),
            ],
        ),
    ]
    customers = [
        dict(id=x, name=n, category=c, priority_weight=w)
        for x, n, c, w in [
            ("C-01", "Bharat Motion Systems", "Strategic", 3),
            ("C-02", "Kinetic Auto Components", "Regular", 1),
            ("C-03", "Sahyadri Engineering", "Export", 2),
            ("C-04", "Atlas Industrial Drives", "Penalty-linked", 2),
            ("C-05", "Precision Mobility India", "Regular", 1),
        ]
    ]
    return Factory.model_validate(
        dict(
            customers=customers,
            routings=routings,
            calendars=[
                dict(id="DAY", name="General · Mon–Sat, 08:00–16:00"),
                dict(
                    id="ALL",
                    name="External · continuous",
                    weekdays=list(range(7)),
                    shifts=[[0, 1440]],
                ),
            ],
            suppliers=[
                dict(id="SUP-01", name="Pune Alloy Steels", lead_time_days=3),
                dict(
                    id="SUP-02",
                    name="Deccan Heat Treatment",
                    lead_time_days=1,
                    reliability=0.92,
                ),
            ],
            resources=[
                dict(
                    id=r,
                    name=n,
                    type="External vendor" if r == "HT-EXT" else "Machine",
                    department=d,
                    cost_per_hour=c,
                    calendar_id="ALL" if r == "HT-EXT" else "DAY",
                    capacity=5 if r == "HT-EXT" else 1,
                    supplier_id="SUP-02" if r == "HT-EXT" else None,
                    unavailable=(
                        [
                            dict(
                                start=date(1, 10),
                                end=date(1, 14),
                                reason="Preventive spindle maintenance",
                            )
                        ]
                        if r == "VMC-01"
                        else []
                    ),
                )
                for r, n, d, c in resources
            ],
            auxiliaries=[
                dict(
                    id="FX-12",
                    name="Shaft locating fixture F12",
                    kind="Tool",
                    calendar_id="ALL",
                ),
                dict(
                    id="OP-A",
                    name="Turning crew A",
                    kind="Operator",
                    skill="Turning",
                    capacity=2,
                ),
            ],
            materials=[
                dict(
                    id="EN8",
                    description="EN8 alloy steel blanks",
                    stock=1300,
                    reserved=100,
                    incoming=1500,
                    arrival=date(3, 8),
                    supplier_id="SUP-01",
                    safety_stock=100,
                ),
                dict(
                    id="CI-204",
                    description="Cast iron housing blanks",
                    stock=2400,
                    safety_stock=100,
                ),
                dict(
                    id="MS-40",
                    description="Mild steel flange blanks",
                    stock=2000,
                    safety_stock=100,
                ),
            ],
            products=[
                dict(
                    id="GS-204",
                    name="Transmission gear shaft",
                    routing_id="RT-SHAFT",
                    batch_size=100,
                    materials=[dict(material_id="EN8", per_unit=1)],
                    description="EN8 precision shaft · automotive drive train",
                ),
                dict(
                    id="BH-118",
                    name="Bearing housing",
                    routing_id="RT-HOUSING",
                    batch_size=100,
                    materials=[dict(material_id="CI-204", per_unit=1)],
                ),
                dict(
                    id="FL-062",
                    name="Drive coupling flange",
                    routing_id="RT-FLANGE",
                    batch_size=100,
                    materials=[dict(material_id="MS-40", per_unit=1)],
                ),
            ],
            orders=[
                dict(
                    id=f"PO-{4401+i}",
                    customer_id=customers[i % 5]["id"],
                    product_id=["GS-204", "BH-118", "FL-062"][i % 3],
                    quantity=[
                        200,
                        300,
                        200,
                        300,
                        200,
                        400,
                        200,
                        300,
                        200,
                        400,
                        200,
                        200,
                    ][i],
                    order_date=date(-2, 9),
                    requested_date=date([2, 1, 2, 3, 2, 3, 4, 4, 3, 5, 5, 6][i]),
                    committed_date=date([2, 1, 2, 3, 2, 3, 4, 4, 3, 5, 5, 6][i]),
                    priority=["High", "Critical", "Normal", "High", "Normal", "Low"][
                        i % 6
                    ],
                    value=[184000, 126000, 72000][i % 3],
                    status="PLANNED",
                )
                for i in range(12)
            ],
        )
    )
