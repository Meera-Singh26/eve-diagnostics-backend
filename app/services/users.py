from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, ConflictError
from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.auth import SignupIn

# used to keep login timing similar when the email does not exist
_DUMMY_HASH = hash_password("not-a-real-password-1")


def create_user(db: Session, data: SignupIn) -> User:
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("An account with this email already exists")

    user = User(email=email, full_name=data.full_name, hashed_password=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # two signups with the same email raced each other
        db.rollback()
        raise ConflictError("An account with this email already exists")
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise AuthError("Incorrect email or password")
    if not verify_password(password, user.hashed_password):
        raise AuthError("Incorrect email or password")
    return user
