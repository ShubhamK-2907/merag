"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.services import users

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    if creds is None:
        raise _UNAUTHORIZED
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise _UNAUTHORIZED
    user = await users.get_user(user_id)
    if user is None:
        raise _UNAUTHORIZED
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def uid(user: dict) -> str:
    return str(user["_id"])
