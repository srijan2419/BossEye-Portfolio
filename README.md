# BossEye — Computer Vision Monitoring & Camera Operations

**Commercially deployed computer-vision product • Independently engineered • Production software**

BossEye is a camera-based monitoring platform built to help organizations use existing surveillance infrastructure for operational awareness, event detection, and configurable alerts. I independently engineered and delivered this product through SrijanAI Innovations for paid client use.

> **Portfolio edition.** This is a curated, sanitized source-code showcase built from genuine product implementation. It is not the complete deployable customer system. The original production repository and its Git history are private and are not linked, forked, or imported here.

## What the product does

- Connects camera infrastructure to a monitoring platform, including an **edge bridge** for on-premise camera connectivity.
- Provides computer-vision and tracking components for observations, activity analysis, and rule-driven alerts.
- Manages cameras, zones, and monitoring events through API services.
- Gives operators a React-based interface for monitoring and reviewing activity.
- Includes architecture for tenant-aware access, auditing, health checks, and operational hardening.

## Architecture overview

```text
Existing cameras (customer site)
       |
       v
Go edge bridge / camera discovery / snapshots
       |
       v
Authenticated ingestion + Python/FastAPI services
       |
       +--> Tracking / activity analysis / zone rules
       |
       +--> PostgreSQL and tenant-scoped operational data
       |
       +--> Alerts, event history, reporting APIs
       |
       v
React / TypeScript monitoring dashboard
```

## Engineering evidence

The portfolio contains real, reviewed implementation excerpts covering:

1. **Computer vision:** tracking and activity normalization from the monitoring backend.
2. **Edge systems:** Go camera bridge components, camera discovery, local state, transport, and adapter logic.
3. **Backend security:** selected authentication/tenant-access or operational endpoints where safe to show.
4. **Frontend operations:** monitoring and analytics UI components.

See [ENGINEERING_NOTES.md](ENGINEERING_NOTES.md) for design decisions and the exact scope of published source.

## Technical stack

Python • FastAPI • PostgreSQL • React • TypeScript • Go edge agent • ONVIF / camera integrations • Docker and deployment tooling

## Commercial delivery and ownership

I designed and built BossEye independently and deployed it in paid client engagements. This is a commercial engineering case study, not coursework or a tutorial. Client names, deployment identities, access credentials, surveillance imagery, and private operations are withheld.

## Scope and safety

This **sanitized portfolio edition** is not a full production release. It excludes live cloud credentials, API keys, passwords, customer/camera identifiers, private configurations, recorded footage, and historical production Git commits. The included code represents real engineering work; some modules rely on private services or configuration intentionally absent from this edition.

**Author:** Srijan Choudhary — product founder and engineer.
