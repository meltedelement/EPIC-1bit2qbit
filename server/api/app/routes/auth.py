from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import RegisterRequest, RegisterResponse
from ..security.passwords import hash_password


router = APIRouter(tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    user = User(username=req.username, password=hash_password(req.password))
    try:
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "username already taken")

    return RegisterResponse(username=req.username)
