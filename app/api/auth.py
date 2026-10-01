from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import SignupIn, TokenOut, UserOut
from app.services import users

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(data: SignupIn, db: Session = Depends(get_db)):
    return users.create_user(db, data)


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # form field is called "username" (OAuth2 spec), we treat it as the email
    user = users.authenticate(db, form.username, form.password)
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
