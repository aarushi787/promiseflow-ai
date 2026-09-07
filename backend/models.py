"""Universal, validated manufacturing input contract. All time durations are minutes."""

from datetime import datetime, date
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def valid_id(self):
        value = getattr(self, "id", None)
        if value is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value
        ):
            raise ValueError(
                "IDs must contain 1–80 letters, digits, periods, underscores or hyphens"
            )
        return self


class Customer(Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    category: str = "Regular"
    priority_weight: int = Field(default=1, ge=1, le=10)


class Window(Model):
    start: datetime
    end: datetime
    reason: str = "Unavailable"

    @model_validator(mode="after")
    def check(self):
        if self.start.tzinfo or self.end.tzinfo:
            raise ValueError("Use plant-local time without a UTC offset")
        if self.end <= self.start:
            raise ValueError("Window end must follow start")
        return self


class Calendar(Model):
    id: str
    name: str
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    shifts: list[list[int]] = Field(default_factory=lambda: [[480, 960]], min_length=1)
    holidays: list[str] = []

    @model_validator(mode="after")
    def check(self):
        if any(d not in range(7) for d in self.weekdays):
            raise ValueError("Weekdays must be 0 through 6")
        for holiday in self.holidays:
            if date.fromisoformat(holiday).isoformat() != holiday:
                raise ValueError("Holidays require YYYY-MM-DD dates")
        for i, shift in enumerate(sorted(self.shifts)):
            if len(shift) != 2 or not 0 <= shift[0] < shift[1] <= 1440:
                raise ValueError(
                    "Shifts need start/end minutes within one day; split overnight shifts"
                )
            if i and sorted(self.shifts)[i - 1][1] > shift[0]:
                raise ValueError("Shifts cannot overlap")
        return self


class Resource(Model):
    id: str
    name: str
    type: str = "Machine"
    department: str = "Production"
    work_centre: str = ""
    capacity: int = Field(default=1, ge=1, le=100)
    calendar_id: str = "DAY"
    status: Literal[
        "AVAILABLE", "RUNNING", "SETUP", "MAINTENANCE", "BREAKDOWN", "UNAVAILABLE"
    ] = "AVAILABLE"
    efficiency: float = Field(default=1, gt=0, le=2)
    cost_per_hour: float = Field(default=450, ge=0)
    location: str = "Pune · Plant 01"
    unavailable: list[Window] = []
    supplier_id: str | None = None


class Material(Model):
    id: str
    description: str
    stock: float = Field(default=0, ge=0)
    reserved: float = Field(default=0, ge=0)
    incoming: float = Field(default=0, ge=0)
    arrival: datetime | None = None
    supplier_id: str | None = None
    lead_time_days: int = Field(default=0, ge=0)
    safety_stock: float = Field(default=0, ge=0)
    unit: str = "pieces"
    quality_hold: bool = False
    hold_reason: str = ""


class Auxiliary(Model):
    id: str
    name: str
    kind: Literal["Tool", "Operator"]
    capacity: int = Field(default=1, ge=1, le=100)
    skill: str = ""
    calendar_id: str = "DAY"
    eligible_resources: list[str] = []
    unavailable: list[Window] = []


class Supplier(Model):
    id: str
    name: str
    lead_time_days: int = Field(default=1, ge=0)
    reliability: float = Field(default=0.95, ge=0, le=1)


class Alternative(Model):
    resource_id: str
    cycle_minutes: float = Field(gt=0, le=10000)
    setup_minutes: int = Field(default=30, ge=0, le=10000)
    external_lead_minutes: int = Field(default=0, ge=0, le=50000)
    transit_minutes: int = Field(default=0, ge=0, le=10000)
    unit_cost: float = Field(default=0, ge=0)


class Operation(Model):
    id: str
    name: str
    sequence: int = Field(ge=1)
    alternatives: list[Alternative] = Field(min_length=1)
    transfer_minutes: int = Field(default=0, ge=0)
    queue_minutes: int = Field(default=0, ge=0)
    required_skill: str = ""
    tool_id: str | None = None
    batch_size: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def unique_alternatives(self):
        if len({a.resource_id for a in self.alternatives}) != len(self.alternatives):
            raise ValueError("Each resource may appear only once per operation")
        return self


class Routing(Model):
    id: str
    name: str
    operations: list[Operation] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self):
        if len({o.id for o in self.operations}) != len(self.operations) or len(
            {o.sequence for o in self.operations}
        ) != len(self.operations):
            raise ValueError(
                "Operation IDs and sequences must be unique within a routing"
            )
        return self


class MaterialRequirement(Model):
    material_id: str
    per_unit: float = Field(gt=0)


class Product(Model):
    id: str
    name: str
    description: str = ""
    batch_size: int = Field(default=100, ge=1, le=10000)
    routing_id: str
    materials: list[MaterialRequirement] = []
    lead_time_days: int = Field(default=3, ge=0)
    customer_variant: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def unique_materials(self):
        if len({m.material_id for m in self.materials}) != len(self.materials):
            raise ValueError(
                "Combine duplicate material requirements into one per-unit demand"
            )
        return self


class Order(Model):
    id: str = Field(min_length=1, max_length=80)
    customer_id: str
    product_id: str
    quantity: int = Field(ge=1, le=1000000)
    order_date: datetime
    requested_date: datetime
    committed_date: datetime | None = None
    hard_deadline: datetime | None = None
    priority: Literal["Critical", "High", "Normal", "Low"] = "Normal"
    value: float = Field(default=0, ge=0)
    penalty: float = Field(default=0, ge=0)
    status: Literal[
        "NEW",
        "PLANNED",
        "RELEASED",
        "IN PRODUCTION",
        "ON HOLD",
        "COMPLETED",
        "DISPATCHED",
        "CANCELLED",
    ] = "NEW"
    notes: str = ""

    @model_validator(mode="after")
    def check(self):
        for v in (
            self.order_date,
            self.requested_date,
            self.committed_date,
            self.hard_deadline,
        ):
            if v and v.tzinfo:
                raise ValueError("Dates must be plant-local time without a UTC offset")
        if self.requested_date < self.order_date:
            raise ValueError("Requested delivery precedes order date")
        return self


class Settings(Model):
    plant_name: str = "Pragati Precision Works"
    timezone: str = "Asia/Kolkata"
    planning_start: datetime | None = None
    planning_not_before: datetime | None = None
    industry_pack: str = "Automotive"
    horizon_days: int = Field(default=21, ge=2, le=60)
    late_order_weight: int = Field(default=100000, ge=1, le=1000000)
    tardiness_weight: int = Field(default=100, ge=1, le=10000)
    makespan_weight: int = Field(default=1, ge=0, le=1000)
    cost_weight: int = Field(default=1, ge=0, le=100)
    risk_buffer_hours: int = Field(default=8, ge=0, le=168)
    overtime_cost_per_hour: int = Field(default=250, ge=0)
    data_confirmed_at: datetime | None = None
    data_source: str = "Unverified master data"
    freshness_hours: int = Field(default=24, ge=1, le=720)

    @model_validator(mode="after")
    def local_epoch(self):
        if self.planning_not_before and self.planning_not_before.tzinfo:
            raise ValueError(
                "Planning boundary must use plant-local time without an offset"
            )
        if self.data_confirmed_at and self.data_confirmed_at.tzinfo:
            raise ValueError("Confirmation must use plant-local time without an offset")
        if self.planning_start and self.planning_start.tzinfo:
            raise ValueError("Planning start must be plant-local without an offset")
        return self


class Factory(Model):
    customers: list[Customer]
    products: list[Product]
    routings: list[Routing]
    resources: list[Resource]
    materials: list[Material]
    calendars: list[Calendar]
    auxiliaries: list[Auxiliary] = []
    suppliers: list[Supplier] = []
    orders: list[Order]
    settings: Settings = Field(default_factory=Settings)

    @model_validator(mode="after")
    def references(self):
        maps = {}
        for name in (
            "customers",
            "products",
            "routings",
            "resources",
            "materials",
            "calendars",
            "auxiliaries",
            "suppliers",
            "orders",
        ):
            rows = getattr(self, name)
            maps[name] = {r.id for r in rows}
            if len(maps[name]) != len(rows):
                raise ValueError(f"Duplicate IDs in {name}")

        def ref(value, table):
            if value is not None and value not in maps[table]:
                raise ValueError(f"Unknown {table} reference: {value}")

        for o in self.orders:
            ref(o.customer_id, "customers")
            ref(o.product_id, "products")
        for p in self.products:
            ref(p.routing_id, "routings")
            for m in p.materials:
                ref(m.material_id, "materials")
        for r in self.resources:
            ref(r.calendar_id, "calendars")
            ref(r.supplier_id, "suppliers")
        for m in self.materials:
            ref(m.supplier_id, "suppliers")
            if m.reserved > m.stock:
                raise ValueError(f"{m.id}: reserved stock exceeds stock")
            if m.incoming and not m.arrival:
                raise ValueError(f"{m.id}: incoming stock requires arrival")
            if m.arrival and m.arrival.tzinfo:
                raise ValueError("Use plant-local material arrival")
        for a in self.auxiliaries:
            ref(a.calendar_id, "calendars")
            for r in a.eligible_resources:
                ref(r, "resources")
        for routing in self.routings:
            for op in routing.operations:
                ref(op.tool_id, "auxiliaries")
                if (
                    op.tool_id
                    and next(a for a in self.auxiliaries if a.id == op.tool_id).kind
                    != "Tool"
                ):
                    raise ValueError("Tool reference must have kind Tool")
                for alt in op.alternatives:
                    ref(alt.resource_id, "resources")
        return self
