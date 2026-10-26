# Engineering Notes — BossEye

This is a **curated selection of real commercial-product source code**. It intentionally excludes the original repository history, production configuration, customer deployments and footage. It is not a turnkey runnable installation.

## Source walkthrough

| Focus | Code | What it shows |
| --- | --- | --- |
| Monitoring logic | [activity_threshold_alert.py](src/backend/activity_threshold_alert.py) | Thresholds and configurable alerts |
| Auth and tenant boundaries | [auth.py](src/backend/middleware/auth.py) | JWT checks and tenant context |
| Operational APIs | [rate_limiter.py](src/backend/utils/rate_limiter.py), [health.py](src/backend/api/routes/health.py) | Access/rate limits and readiness signals |
| Edge control loop | [heartbeat.go](src/bridge/internal/control/heartbeat.go) | Heartbeats, on-premise agent and server coordination |
| Camera discovery | [orchestrator.go](src/bridge/internal/discovery/orchestrator.go) | Discovery workflow |
| Camera snapshot integration | [http_auth.go](src/bridge/internal/snapshot/http_auth.go), [snapshot.go](src/bridge/internal/snapshot/snapshot.go) | Camera compatibility and authenticated capture abstractions |
| Monitoring UI | [EventDistributionChart.tsx](src/frontend/EventDistributionChart.tsx), [EventLogTable.tsx](src/frontend/EventLogTable.tsx) | React operator analytics |

## Engineering narrative

BossEye brings existing camera infrastructure into a multi-component application: a Go edge bridge handles local camera communication; backend services process activity and events; a React dashboard helps operators review insights. Authentication, health endpoints, and operational controls matter alongside the computer-vision features.

**Commercial context:** The author reports deployment in paying client engagements. Code demonstrates engineering implementation; contracts, invoices and customer authorization are separate proof of commercial results.

## Publication scope

The portfolio intentionally omits Google Cloud service-account JSON, password files, historical environment files, tenant/camera identifiers, private tunnel configuration, actual surveillance content, customer data, and all production Git commit history. Some files reference excluded dependencies; **this is not a complete runnable app**.

Basic text screening for common key formats has been performed. Before publication, use an independent secret scanner, manually check every included file and any future screenshots, and seek owner approval.

All rights reserved unless the owner grants a license.
