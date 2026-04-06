import bcrypt

from app.config import settings


def hash_password(password: str) -> str:
    """Return a bcrypt hash of password using the configured cost factor."""
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Return True if password matches hashed. Always runs in constant time."""
    return bcrypt.checkpw(password.encode(), hashed.encode())
