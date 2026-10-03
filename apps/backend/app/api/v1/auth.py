from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.user import Token, UserCreate, UserLogin, UserOut
from app.services import user as user_service

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_db)]


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: SessionDep) -> UserOut:
    user = user_service.register_user(db, email=payload.email, password=payload.password)
    return UserOut.model_validate(user)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: SessionDep) -> Token:
    access_token = user_service.login_user(db, email=payload.email, password=payload.password)
    return Token(access_token=access_token)
