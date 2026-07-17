"""Authentication routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..auth import authenticate_user, create_access_token, get_current_user
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, Token, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _issue(user: User) -> Token:
    token, expires_in = create_access_token(user.username, extra={"role": user.role})
    return Token(access_token=token, expires_in=expires_in)


@router.post("/login", response_model=Token)
def login_json(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    """Login with a JSON body (used by the web app)."""
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    return _issue(user)


@router.post("/token", response_model=Token)
def login_form(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    """OAuth2 password-flow token endpoint (Swagger 'Authorize' button)."""
    user = authenticate_user(db, form.username, form.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    return _issue(user)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current
