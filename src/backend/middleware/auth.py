"""
JWT Authentication middleware for HawkEye main API.

Provides a FastAPI dependency that validates JWT tokens and extracts
tenant context. Applied to all protected endpoints.
"""
import os
import re
import logging
from datetime import datetime, UTC
from typing import Optional

from dotenv import load_dotenv
import pathlib as _pathlib
load_dotenv(_pathlib.Path(__file__).parent.parent / '.env')

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from hawkeye_clients_database import SessionLocal as _RegistrySession, Client as _RegistryClient

# UUID format validation — prevents path traversal and injection via client_uuid
_UUID_RE = re.compile(r'^[a-f0-9\-]{8,64}$')

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable must be set")
ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)


class TenantContext:
    """Holds validated tenant information extracted from JWT."""

    def __init__(self, client_uuid: str, database_name: str, username: Optional[str] = None):
        self.client_uuid = client_uuid
        self.database_name = database_name
        self.username = username


async def get_current_tenant(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TenantContext:
    """FastAPI dependency: validates JWT and returns tenant context.

    Extracts client_uuid from the token (Bearer header or httpOnly cookie).
    On JWT decode failure or missing token, raises 401 with a structured
    log line for forensics. The legacy header fallback was removed
    2026-04-30 — it was silently masking JWT mismatch incidents (every
    'successful' request was bypassing JWT verification).
    """
    # Try Bearer header first, then httpOnly cookie
    token = None
    if credentials:
        token = credentials.credentials
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")

    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            database_name = payload.get("database")
            client_uuid = payload.get("client_uuid")
            username = payload.get("sub")

            if not database_name:
                raise HTTPException(status_code=401, detail="Invalid token: missing database")

            # If client_uuid not in token (old tokens), extract from database name
            if not client_uuid and database_name:
                # database_name format: hawkeye_client_{uuid}
                prefix = "hawkeye_client_"
                if database_name.startswith(prefix):
                    client_uuid = database_name[len(prefix):]

            if not client_uuid:
                raise HTTPException(status_code=401, detail="Invalid token: missing client identity")

            # Validate UUID format to prevent path traversal
            if not _UUID_RE.match(client_uuid):
                raise HTTPException(status_code=401, detail="Invalid client identity format")

            # Service kill-switch check: query registry DB for is_active
            try:
                reg_session = _RegistrySession()
                client_row = reg_session.query(_RegistryClient).filter(
                    _RegistryClient.client_uuid == client_uuid
                ).first()
                if client_row and client_row.is_active is False:
                    logger.warning("auth.client_suspended client_uuid=%s", client_uuid[:8])
                    raise HTTPException(status_code=403, detail="Account suspended")
            except HTTPException:
                raise
            except Exception as e:
                # Log but don't block on registry query failure
                logger.error("auth.is_active_check_failed err=%s", e)
            finally:
                try:
                    reg_session.close()
                except Exception:
                    pass

            return TenantContext(
                client_uuid=client_uuid,
                database_name=database_name,
                username=username,
            )
        except JWTError as e:
            # Structured log so future JWT mismatches surface immediately.
            # The client_uuid header is a non-secret routing hint sent by the
            # FE on every request; logging just its prefix lets us correlate a
            # 401 with the misbehaving session without leaking secrets.
            header_uuid = (
                request.headers.get("hawkeye_client_uuid")
                or request.headers.get("client_uuid")
                or ""
            )
            logger.warning(
                "auth.jwt_decode_failed err_type=%s client_uuid_prefix=%s path=%s",
                type(e).__name__,
                header_uuid[:8] if header_uuid else "none",
                request.scope.get("path", "?"),
            )
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    # No bearer token, no cookie → not authenticated. The legacy header
    # fallback was removed 2026-04-30 (see project_jwt_alignment_incident).
    # Endpoints in api/main.py that still read `client_uuid` from headers
    # directly bypass this middleware and continue to work — the FE axios
    # client sends the header on every request.
    logger.info(
        "auth.no_credentials path=%s",
        request.scope.get("path", "?"),
    )
    raise HTTPException(status_code=401, detail="Authentication required")


def _check_subscription_status(client_uuid: str):
    """Check if the client's subscription is active or trial is still valid.

    Raises 402 if subscription is cancelled or trial has expired.
    """
    try:
        from hawkeye_clients_database import SessionLocal, Client
        session = SessionLocal()
        try:
            client = session.query(Client).filter(Client.client_uuid == client_uuid).first()
            if not client:
                return  # Client not found in main DB — allow (may be legacy)

            if client.subscription_status == "cancelled":
                raise HTTPException(
                    status_code=402,
                    detail="Subscription cancelled. Please renew your subscription to continue.",
                )

            if (
                client.subscription_status == "trial"
                and client.free_trial_ends is not None
                and client.free_trial_ends < datetime.now(UTC)
            ):
                raise HTTPException(
                    status_code=402,
                    detail="Free trial has expired. Please upgrade to a paid plan to continue.",
                )
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Subscription check failed (allowing access): {e}")


async def get_optional_tenant(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TenantContext]:
    """Like get_current_tenant but returns None instead of 401.

    Use for endpoints that work with or without auth (e.g., health checks).
    """
    try:
        return await get_current_tenant(request, credentials)
    except HTTPException:
        return None
