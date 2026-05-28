from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from whereWeHashPasswords import hash_password

from ..database.db import get_db
from ..database.models import User
from ..database.schemas import RegisterRequest, RegisterResponse

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    hashed = hash_password(
        req.password
    )  # always runs — constant-time regardless of username collision
    user = User(username=req.username, password_hash=hashed)
    try:
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "username already taken")

    return RegisterResponse(username=req.username)
