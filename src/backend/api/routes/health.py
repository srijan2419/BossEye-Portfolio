"""
Health check endpoints for load balancers and monitoring.
"""
import logging
import os
from datetime import datetime, UTC

from fastapi import APIRouter
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Basic liveness check — returns 200 if the service is running."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "hawkeye-main-api",
    }


@router.get("/ready")
async def readiness_check():
    """Readiness check — verifies database and Redis connectivity."""
    checks = {}

    # Check PostgreSQL
    try:
        from database import get_main_session
        session = get_main_session()
        session.execute(text("SELECT 1"))
        session.close()
        checks["database"] = "ok"
    except Exception as e:
        logger.error(f"Readiness: database check failed: {e}")
        checks["database"] = "failed"

    # Check Redis
    try:
        import redis
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            socket_timeout=2,
        )
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.warning(f"Readiness: redis check failed: {e}")
        checks["redis"] = "failed"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
    }
