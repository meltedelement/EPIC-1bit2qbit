from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database.db import get_db
from ..database.models import User
from ..database.schemas import RegisterRequest, RegisterResponse
from ..security.passwords import hash_password


router = APIRouter(tags=["auth"])

#Any internal unhandled exceptions get obfuscated by fastAPI and if our registering system is failing we want to fail fast so thats fine
@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    user = User(username=req.username, auth_key=hash_password(req.auth_key))
    try:
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "username already taken")

    #return created resource by convention
    return RegisterResponse(username=req.username)
