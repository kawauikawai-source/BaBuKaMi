from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import apply_admin_email_role, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import UserPublic, UserUpdateRequest


router = APIRouter(prefix="/users", tags=["users"])


def split_display_name(name: str) -> tuple[str, str]:
    parts = str(name or "").strip().split(maxsplit=1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


@router.get("/me", response_model=UserPublic)
def get_my_profile(current_user: User = Depends(get_current_user)) -> UserPublic:
    apply_admin_email_role(current_user)
    return UserPublic.model_validate(current_user)


@router.patch("/me", response_model=UserPublic)
def update_my_profile(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        current_user.name = data["name"].strip()
        if "first_name" not in data and "last_name" not in data:
            first_name, last_name = split_display_name(current_user.name)
            current_user.first_name = first_name
            current_user.last_name = last_name
    if "first_name" in data and data["first_name"] is not None:
        current_user.first_name = data["first_name"].strip()
    if "last_name" in data and data["last_name"] is not None:
        current_user.last_name = data["last_name"].strip()
    if "first_name" in data or "last_name" in data:
        current_user.name = " ".join(
            part for part in (current_user.first_name, current_user.last_name) if part
        ).strip()
    if "email" in data and data["email"] is not None:
        email = data["email"].strip().lower()
        existing = db.scalar(select(User).where(User.email == email, User.id != current_user.id))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        current_user.email = email
    if "phone" in data and data["phone"] is not None:
        current_user.phone = data["phone"].strip()
    if "dob" in data and data["dob"] is not None:
        current_user.dob = data["dob"].strip()
    if "country" in data and data["country"] is not None:
        current_user.country = data["country"].strip()
    if "currency" in data and data["currency"] is not None:
        current_user.currency = data["currency"].strip().upper()

    apply_admin_email_role(current_user)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserPublic.model_validate(current_user)
