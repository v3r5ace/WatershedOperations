from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Iterable
from typing import Optional, Union

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole


def hash_password(password: str, *, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 390000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt_hex, digest_hex = password_hash.split(":", 1)
    candidate = hash_password(password, salt=bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, password_hash)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email.lower().strip(), User.is_active.is_(True)).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user


def require_roles(*roles: Union[UserRole, str]):
    role_values = {role.value if isinstance(role, UserRole) else role for role in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in role_values:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


def can_manage_tasks(role: UserRole) -> bool:
    return role in {UserRole.admin, UserRole.manager}


def role_label_options() -> Iterable[str]:
    return [role.value for role in UserRole]
