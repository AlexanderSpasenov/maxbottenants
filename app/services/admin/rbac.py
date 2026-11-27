"""Minimal RBAC scaffold for admin endpoints.

Feature-flagged: when ADMIN_RBAC_ENABLED is false (default), behavior is unchanged:
shared-secret + optional IP allowlist only. When enabled, requests must provide
X-Admin-Role with an allowed role for the endpoint action. This is a scaffold
until an auth provider / SSO decision is made; do not treat it as production RBAC.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.core.config import Settings


@dataclass(frozen=True)
class AdminPrincipal:
    subject: str
    role: str
    auth_mode: str  # shared_secret | rbac_scaffold


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "ops_viewer": {
        "admin.stats.read",
        "admin.readiness.read",
        "admin.audit.read",
        "admin.sync.logs.read",
        "admin.outbox.read",
    },
    "ops_operator": {
        "admin.stats.read",
        "admin.readiness.read",
        "admin.audit.read",
        "admin.sync.logs.read",
        "admin.outbox.read",
        "admin.cleanup.run",
        "admin.outbox.requeue",
    },
    "tenant_admin": {
        "admin.stats.read",
        "admin.readiness.read",
        "admin.audit.read",
        "admin.sync.logs.read",
        "admin.outbox.read",
        "admin.sync.run",
    },
    "platform_admin": {"*"},
}


def role_allows(role: str, action: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or action in perms


def resolve_admin_principal(
    *,
    settings: Settings,
    request: Request,
    x_admin_sync_secret: str | None,
    x_admin_role: str | None,
    action: str,
) -> AdminPrincipal:
    expected = settings.admin_sync_secret
    if not expected:
        # dev mode allowed, warned by config validation
        pass
    elif not x_admin_sync_secret or x_admin_sync_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid admin sync secret")

    allowed_raw = (settings.admin_allowed_ips or "").strip()
    if allowed_raw:
        allowed = {ip.strip() for ip in allowed_raw.split(",") if ip.strip()}
        client_ip = (request.client.host if request.client else "") or ""
        if client_ip not in allowed:
            raise HTTPException(status_code=403, detail="Admin IP not allowed")

    if not settings.admin_rbac_enabled:
        return AdminPrincipal(subject="shared-secret", role="platform_admin", auth_mode="shared_secret")

    role = (x_admin_role or settings.admin_rbac_default_role or "").strip()
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=403, detail="Invalid admin role")
    if not role_allows(role, action):
        raise HTTPException(status_code=403, detail="Admin role not allowed for action")
    return AdminPrincipal(subject="shared-secret", role=role, auth_mode="rbac_scaffold")

