# BossEye — Engineering Notes

This is a portfolio selection of real code from a commercially delivered monitoring product. The entire customer installation is intentionally not published.

## Code tour

| Area | Code | Engineering topic |
| --- | --- | --- |
| Object tracking | [tracker.py](src/backend/tracker.py) | Multi-object tracking, Kalman prediction, and assignment logic |
| Motion tracking | [motion_tracker.py](src/backend/motion_tracker.py) | Spatial proximity and tracking trajectories |
| Activity rules | [activity_threshold_alert.py](src/backend/activity_threshold_alert.py) | Activity duration thresholds and alert handling |
| Camera discovery | [orchestrator.go](src/bridge/internal/discovery/orchestrator.go) | Coordinating edge camera discovery |
| Edge communication | [heartbeat.go](src/bridge/internal/control/heartbeat.go) | Backend heartbeat and configuration reconciliation |
| Bridge test cases | [heartbeat_test.go](src/bridge/internal/control/heartbeat_test.go) | Local tests for coordination and cancellation |
| Camera capture | [snapshot.go](src/bridge/internal/snapshot/snapshot.go) | Snapshot interfaces |
| Backend tenancy | [auth.py](src/backend/middleware/auth.py) | Tenant context and authentication middleware |
| Operational UI | [EventDistributionChart.tsx](src/frontend/EventDistributionChart.tsx), [EventLogTable.tsx](src/frontend/EventLogTable.tsx) | Tracking and reviewing events through a React dashboard |

## Architecture decisions

**Vision beyond object detection.** Matching detections over time and managing track identity are separate concerns from alert generation. The Python tracker demonstrates the time-dependent part; activity threshold logic shows how observations inform operations.

**Edge integration.** Real camera installations vary in protocol support and network accessibility. The Go bridge separates local camera discovery and capture from higher-level backend operations.

**Customer delivery.** The product was built to support paying clients, so deployment constraints, operations, and iterative requirements mattered alongside modeling.

## Technical interview guide

I can explain the track association algorithm, edge-to-server coordination, event threshold design, tenant boundaries, and engineering trade-offs encountered during customer deployment.

## Scope

This is a **curated edition**, not a full runnable build. It uses fresh source history and contains neither confidential customer data nor production credentials. Some dependencies and platform services were deliberately omitted.

The author reports paid customer work; source code is technical evidence, while customer payments and business outcomes require separate documentation. There is no claim that every included development feature was active in every paying deployment.

This code is rights-reserved and shared for portfolio review. Publication requires the author's approval and final privacy review.
