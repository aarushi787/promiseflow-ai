# IoT & Mini CRM Integration Blueprint · PromiseFlow AI (ProductionSaathi)

## Executive Summary

This document details the architectural plan and technical roadmap to integrate **IoT Live Telemetry** and **Mini CRM** into **PromiseFlow AI (ProductionSaathi)**.

By combining real-time machine telematics with customer lifecycle management, PromiseFlow AI evolves from a static planning solver into a **connected, self-correcting smart factory ecosystem**:

1. **IoT Integration**: Automates shop-floor progress tracking, machine working hours, cycle counts, OEE calculation, and predictive condition alerts directly from physical PLC/sensor hardware.
2. **Mini CRM Integration**: Connects sales inquiries, quotations, delivery SLAs, and customer interaction logs directly to the **CP-SAT Promise Checker**, enabling instant, feasible commitment dates during sales negotiations.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Physical Plant & IoT Edge
        PLC["PLC / Machine Relays (Modbus/OPC-UA)"]
        SENSORS["Vibration / Temp / Stroke Sensors"]
        EDGE["IoT Edge Gateway (Mosquitto MQTT / Node-RED)"]
        PLC --> EDGE
        SENSORS --> EDGE
    end

    subgraph Backend Core (FastAPI & Python)
        MQTT_SUB["MQTT / WebSocket Listener (`iot_bridge.py`)"]
        CRM_API["Mini CRM Service (`crm.py`)"]
        STORE["Store & DB Boundary (SQLite / PostgreSQL)"]
        SOLVER["Google OR-Tools CP-SAT Engine"]
        ANOMALY["Anomaly & Maintenance Engine"]

        EDGE -- "MQTT / TLS (Port 8883)" --> MQTT_SUB
        MQTT_SUB --> ANOMALY
        MQTT_SUB --> STORE
        CRM_API --> STORE
        CRM_API -- "Check Feasibility" --> SOLVER
    end

    subgraph Frontend Application (React + Vite)
        DASH["Dashboard & Shop Floor"]
        MAINT["Maintenance & Reminders"]
        CRM_UI["Mini CRM Workbench (Leads, Quotes, SLA)"]

        MQTT_SUB -- "WebSockets / SSE" --> DASH
        MQTT_SUB -- "Live Status" --> MAINT
        CRM_API <--> CRM_UI
    end
```

---

## Module 1: IoT Integration Blueprint

### 1.1 Core Objectives
* **Automated Telemetry Logging**: Eliminate manual counter logging by streaming machine run hours, stroke counts, and power consumption directly from edge devices.
* **Live Machine Status & OEE**: Automatically determine whether a machine is `RUNNING`, `IDLE`, `SETUP`, `MAINTENANCE`, or `BREAKDOWN`.
* **Predictive Maintenance (PdM)**: Generate automated warnings when sensor thresholds (vibration RMS > 4.5 mm/s, temperature > 75°C) are breached before mechanical failure occurs.
* **1-Click Disruption Recovery**: Link machine breakdown signals directly to the CP-SAT engine to trigger instant What-If re-optimization.

### 1.2 Data Schemas & Models

```python
# backend/models.py extensions

class IoTTelemetryMessage(Model):
    resource_id: str = Field(min_length=1, max_length=80)
    timestamp: datetime
    status: Literal["RUNNING", "IDLE", "SETUP", "MAINTENANCE", "BREAKDOWN"] = "RUNNING"
    working_hours_delta: float = Field(default=0.0, ge=0)
    production_count_delta: int = Field(default=0, ge=0)
    spindle_speed_rpm: float | None = None
    temperature_celsius: float | None = None
    vibration_rms_mms: float | None = None
    power_draw_kw: float | None = None

class MachineAlert(Model):
    id: str
    resource_id: str
    timestamp: datetime
    alert_type: Literal["THRESHOLD_EXCEEDED", "UNPLANNED_STOPPAGE", "PREDICTIVE_SERVICE_DUE"]
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    acknowledged: bool = False
```

### 1.3 Backend Architecture (`backend/iot.py`)
1. **MQTT Subscriber Service**: Background thread using `paho-mqtt` listening to `factory/machines/+/telemetry`.
2. **Telemetry Ingestion Engine**:
   - Updates `working_hours_since_service` and `production_count_since_service` on `Resource`.
   - Compares metrics against configured limits (`max_working_hours`, `max_production_count`).
   - Broadcasts real-time events over Server-Sent Events (SSE) `/api/iot/stream`.

### 1.4 Phase-by-Phase Rollout
* **Phase 1 (Week 1-2)**: MQTT Broker setup, Pydantic schemas, and FastAPI `/api/iot/telemetry` endpoint.
* **Phase 2 (Week 3-4)**: Live machine telemetry widgets on Shop Floor and Maintenance screens.
* **Phase 3 (Week 5-6)**: OEE calculation (Availability %, Performance %, Quality %) and automated breakdown alerts.
* **Phase 4 (Week 7-8)**: Edge device hardware testing with ESP32 & Modbus RS485 transmitters.

---

## Module 2: Mini CRM Integration Blueprint

### 2.1 Core Objectives
* **Lead & Sales Opportunity Management**: Capture customer inquiries, target quantities, and requested delivery timelines.
* **Constraint-Aware Quoting**: Integrate the **CP-SAT Promise Checker** directly into sales quotes, guaranteeing realistic delivery dates based on current finite factory capacity.
* **Customer 360° Profile**: Single dashboard showing customer order history, revenue, active commitments, SLA compliance, and communication notes.
* **SLA & Reliability Scorecard**: Track on-time delivery performance (OTIF %) per customer to prioritize key accounts.

### 2.2 Data Schemas & Models

```python
# backend/models.py extensions

class CustomerLead(Model):
    id: str = Field(min_length=1, max_length=80)
    company_name: str
    contact_person: str
    email: str
    phone: str
    stage: Literal["NEW_INQUIRY", "FEASIBILITY_CHECK", "QUOTED", "WON", "LOST"] = "NEW_INQUIRY"
    estimated_value: float = Field(default=0, ge=0)
    assigned_salesperson: str = ""
    notes: str = ""

class Quotation(Model):
    id: str = Field(min_length=1, max_length=80)
    lead_id: str
    customer_id: str
    product_id: str
    quantity: int = Field(ge=1)
    target_date: datetime
    feasible_date: datetime | None = None
    unit_price: float = Field(ge=0)
    total_price: float = Field(ge=0)
    status: Literal["DRAFT", "SENT", "ACCEPTED", "REJECTED", "CONVERTED_TO_ORDER"] = "DRAFT"
    promise_check_id: str | None = None
    created_at: datetime

class CustomerInteraction(Model):
    id: str
    customer_id: str
    actor: str
    interaction_type: Literal["CALL", "EMAIL", "MEETING", "PROMISE_CHECK", "SLA_REVIEW"]
    summary: str
    timestamp: datetime
```

### 2.3 Key Features & Workflows

#### A. Inquiry-to-Order Conversion Pipeline
```
[New Lead Inquiry] ──► [Select Product & Quantity] ──► [Run CP-SAT Promise Checker]
                                                                  │
[Create Production Order] ◄── [Customer Accepts Quote] ◄── [Send Feasible Quote & Date]
```

#### B. Customer SLA Scorecard
* **OTIF % (On-Time In-Full)**: Calculated automatically as completed orders delivered on or before committed date.
* **Revenue at Risk**: Total value of orders currently flagged as `AT RISK` or `LATE` for a specific customer.
* **Priority Weight Sync**: High-value/VIP customer leads automatically inherit higher priority weights (`priority_weight` 1-10) during CP-SAT solving.

---

## Data Database Schema Modifications

```sql
-- New tables for SQLite and PostgreSQL

CREATE TABLE IF NOT EXISTS customer_leads (
    id TEXT PRIMARY KEY,
    body JSON NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotations (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    body JSON NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_interactions (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    body JSON NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS iot_telemetry_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    metrics JSON NOT NULL
);
```

---

## Frontend UI Components Blueprint

### 1. Mini CRM Workbench (`frontend/src/crm.tsx`)
* **Tabs**: `Inquiries & Leads`, `Quotations`, `Customer 360`, `SLA Analytics`.
* **Feasibility Action**: Button inside Quote builder **"Check Solver Feasibility"** calling `/api/promise` without modifying active schedule.
* **1-Click Convert**: Convert approved quote into a binding Production Order (`Order`).

### 2. Live Telemetry Panel (`frontend/src/maintenance.tsx` & `planning.tsx`)
* **Live Machine Status Cards**: Displays real-time RPM, temperature gauges, vibration meters, and current active order on the machine.

---

## Security, Access Control & Deployment

1. **IoT Edge Security**:
   - Device Authentication via X.509 client certificates or unique API tokens.
   - Dedicated restricted role `iot_gateway` with write access limited to telemetry tables.
2. **CRM Role-Based Access Control**:
   - `sales` role: Full write access to Leads, Quotes, and Customer Interactions; read access to Promise Checker.
   - `planner` / `manager` role: Full access to convert Quotes to Production Orders and adjust Priority Weights.

---

## Timeline & Resource Estimates

| Phase | Milestone | Deliverables | Est. Effort |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Mini CRM Core | Lead & Quote management, Customer 360 view, Feasible quote generator | 2 Weeks |
| **Phase 2** | Customer SLA & Integration | OTIF analytics, Quote-to-Order conversion, Priority weight solver integration | 1.5 Weeks |
| **Phase 3** | IoT Telemetry Ingestion | MQTT subscriber, FastAPI telemetry endpoints, DB schema migration | 2 Weeks |
| **Phase 4** | Live Shop Floor Telematics | Real-time WebSockets, Machine gauges, Automated breakdown trigger | 1.5 Weeks |
| **Total** | **Full Connected Smart Factory** | **Complete IoT + Mini CRM solution for MSME manufacturers** | **7 Weeks** |
