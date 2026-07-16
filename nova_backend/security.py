from fastapi import Header, HTTPException, status

from config import config


def require_admin(x_nova_admin_key: str | None = Header(default=None)) -> None:
    if not config.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured.",
        )

    if x_nova_admin_key != config.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access denied.",
        )
