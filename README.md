# BossEye — Commercial Computer-Vision Monitoring Platform

**Production engineering • Independently built • Delivered for paying clients**

BossEye is an operations-monitoring product built around existing surveillance cameras. I designed and engineered it through SrijanAI Innovations to combine camera connectivity, object/activity tracking, configurable alerts, tenant-aware backend services, and an operator dashboard.

> **Real product, real source.** This repository is a reviewed portfolio selection from the actual application. It is not a toy implementation, a full customer deployment, or a copy of the original production Git history.

## 30-second overview

| | |
| --- | --- |
| **Problem** | Organizations already have cameras but need usable, automated operational visibility. |
| **What I built** | A camera-to-insights platform with computer-vision tracking, activity alerts, APIs, and operator-facing monitoring. |
| **My role** | Independent product design, Python monitoring/backend, Go camera-edge components, integrations, and customer delivery. |
| **Commercial context** | Built and deployed for **paying clients**, with private client and contract information withheld. |
| **Technologies** | **Python, OpenCV, NumPy, FastAPI, PostgreSQL, Go, ONVIF/camera integrations, React, TypeScript**. |

## Start with the actual engineering

These are **source files from the product**, presented for technical review.

| System | Open the code | What it demonstrates |
| --- | --- | --- |
| Computer vision / multi-object tracking | [Advanced tracker](src/backend/tracker.py) | Kalman-based prediction, matching observations across frames, tracking state |
| Motion analysis | [Motion tracker](src/backend/motion_tracker.py) | Frame-to-frame motion and proximity-based tracking |
| Operational alerts | [Activity threshold alerts](src/backend/activity_threshold_alert.py) | Translating activity durations and threshold rules into notifications |
| Multi-tenant API access | [Authentication middleware](src/backend/middleware/auth.py) | JWT handling and tenant context in the backend |
| Edge-to-server coordination | [Bridge heartbeat](src/bridge/internal/control/heartbeat.go) | On-premise camera agent communication with backend services |
| Camera integrations | [Device discovery](src/bridge/internal/discovery/orchestrator.go) · [Snapshot handling](src/bridge/internal/snapshot/snapshot.go) | Building around existing camera systems |
| Monitoring dashboard | [Event distribution](src/frontend/EventDistributionChart.tsx) · [Event log](src/frontend/EventLogTable.tsx) | Operational data and event visibility in React |

[**Explore the architecture and implementation details →**](ENGINEERING_NOTES.md)

## System architecture

~~~mermaid
flowchart TD
    C["Existing cameras at customer site"] --> E["Go edge bridge: discovery and snapshots"]
    E --> I["Authenticated camera ingestion / backend services"]
    I --> V["Python computer-vision and tracking components"]
    V --> R["Activity and alert rules"]
    I --> DB[("PostgreSQL / tenant-scoped data")]
    R --> DB
    DB --> UI["React / TypeScript operations dashboard"]
~~~

The engineering challenge is broader than detecting an object in a frame: **integrate real camera hardware**, handle edge connectivity, maintain observations over time, route them through backend services, and make the results actionable for operators.

## What I can explain in an interview

1. **Tracking across frames:** Prediction, association, and managing detection changes over time.
2. **Deploying alongside existing infrastructure:** Camera protocols and the Go bridge's local-to-backend communication.
3. **Operational usefulness:** Turning activity analysis into thresholds, events, and dashboards.
4. **Backend boundaries:** Tenant-aware authorization and production operations considerations.
5. **Commercial delivery:** Mapping a real client's monitoring needs into a deployed product, including trade-offs and iteration.

## Commercial proof and portfolio scope

BossEye was engineered for paid customer engagements. The code is technical evidence of the system; payment and customer identity would require separate records or authorized references and are not implied by GitHub source alone.

**Portfolio scope:** This is a curated selection of authentic modules with a new Git history. It **does not include** production credentials, environment files, customer/camera identifiers, footage, historical commits, or full deployment infrastructure. Some components rely on unpublished dependencies, so this is **not a standalone runnable distribution**.

**Built by:** Srijan Choudhary • SrijanAI Innovations  
**Source rights:** All rights reserved; shared for technical portfolio review, not as an open-source license.
