from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config.config import config
from ..crypto.password import hash_password
from ..database.db import get_db
from ..database.models import User
from ..rate_limit import RateLimiter, client_ip
from ..schemas.http import RegisterRequest, RegisterResponse

router = APIRouter(tags=["auth"])


def _check_register_rate_limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    ip = client_ip(request.headers, request.client)
    rl = config.rate_limiting
    retry_after = limiter.hit(ip, rl.register_limit, rl.register_window_seconds)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(
    req: RegisterRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_check_register_rate_limit),
) -> RegisterResponse:
    hashed = hash_password(
        req.password
    )  # runs before the DB write — constant-time regardless of username collision
    user = User(username=req.username, password_hash=hashed)
    try:
        db.add(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "username already taken") from exc

    return RegisterResponse(username=req.username)
