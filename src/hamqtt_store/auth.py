from pathlib import Path

from sqlalchemy import delete, select
from werkzeug.security import check_password_hash, generate_password_hash

from .config import settings
from .db import ApplicationUser, SessionLocal


def reset_marker_path() -> Path:
    return Path(settings.app_data_dir) / ".reset-auth"


def reset_authentication_if_requested() -> bool:
    marker = reset_marker_path()
    if not marker.exists():
        return False
    with SessionLocal() as session:
        session.execute(delete(ApplicationUser))
        session.commit()
    try:
        marker.unlink()
    except FileNotFoundError:
        pass
    return True


def get_user(session):
    return session.scalar(select(ApplicationUser).order_by(ApplicationUser.id))


def valid_credentials(username: str, password: str) -> bool:
    return bool(username.strip() and password and len(password) >= 6)


def password_matches(user: ApplicationUser, password: str) -> bool:
    return check_password_hash(user.password_hash, password)


def set_password(user: ApplicationUser, password: str) -> None:
    user.password_hash = generate_password_hash(password)
    user.session_version = (user.session_version or 0) + 1