from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get("/me", response_model=UserOut)
def read_me(current_user: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(current_user)
