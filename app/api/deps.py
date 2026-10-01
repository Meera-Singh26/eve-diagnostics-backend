from fastapi import Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_access_token, verify_webhook_signature
from app.db.session import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user = db.get(User, decode_access_token(token))
    if user is None:
        raise AuthError("Invalid or expired token")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise ForbiddenError("Admin access required")
    return user


async def verified_webhook_body(
    request: Request, x_webhook_signature: str | None = Header(default=None)
) -> bytes:
    # the signature is over the raw bytes, so check it before anything parses the body
    body = await request.body()
    if not verify_webhook_signature(body, x_webhook_signature):
        raise AuthError("Invalid webhook signature")
    return body
