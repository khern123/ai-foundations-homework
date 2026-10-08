"""Registration and login endpoints.

Passwords are hashed with scrypt before storage and are never returned:
responses always use UserOut, which has no password fields.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator

from . import db
from .security import DUMMY_HASH, hash_password, verify_password
from .sessions import issue_token, verify_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Password = Annotated[str, Field(min_length=8, max_length=128)]

INVALID_LOGIN = "Invalid email or password."


class RegisterIn(BaseModel):
    first_name: Name
    last_name: Name
    email: EmailStr
    password: Password
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterIn":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str


class AuthOut(BaseModel):
    user: UserOut
    token: str = Field(description="Session token; send as 'Authorization: Bearer <token>'")


SESSION_EXPIRED = "Your session has expired. Please log in again."


def current_user(authorization: Annotated[str | None, Header()] = None) -> dict | None:
    """The signed-in user ({id, name, first_name, email}) from the Bearer token, or None for guests.
    A token that is present but invalid/expired is rejected (401) rather than silently treated as a guest."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    user_id = verify_token(token.strip()) if scheme.lower() == "bearer" else None
    user = db.get_user_public(user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SESSION_EXPIRED)
    return user


def require_user(user: Annotated[dict | None, Depends(current_user)]) -> dict:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in to see your chat history.")
    return user


def normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthOut)
def register(body: RegisterIn) -> AuthOut:
    email = normalize_email(body.email)
    try:
        user_id = db.create_user(body.first_name, body.last_name, email, hash_password(body.password))
    except db.DuplicateEmailError:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    return AuthOut(
        user=UserOut(id=user_id, first_name=body.first_name, last_name=body.last_name, email=email),
        token=issue_token(user_id),
    )


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn) -> AuthOut:
    row = db.get_user_by_email(normalize_email(body.email))
    # Always run a hash check so unknown emails and wrong passwords look identical (message and timing).
    ok = verify_password(body.password, row["password_hash"] if row else DUMMY_HASH)
    if not row or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    return AuthOut(
        user=UserOut(id=row["id"], first_name=row["first_name"], last_name=row["last_name"], email=row["email"]),
        token=issue_token(row["id"]),
    )
