from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUser
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import users

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: dict) -> TokenResponse:
    token, expires_in = create_access_token(str(user["_id"]))
    return TokenResponse(access_token=token, expires_in=expires_in, user=users.to_user_out(user))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest) -> TokenResponse:
    try:
        user = await users.create_user(body.name, body.email, body.password)
    except users.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from None
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    user = await users.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return _token_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return users.to_user_out(user)
