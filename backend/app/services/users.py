"""User persistence and credential checks."""

from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError

from app.core.security import hash_password, verify_password
from app.db.mongo import get_db, to_object_id
from app.schemas.auth import UserOut

# A real hash of a random string: verifying against it costs the same as a real
# check, so "unknown email" and "wrong password" take equal time (no user enumeration).
_DUMMY_HASH = hash_password("timing-attack-padding")


class EmailAlreadyRegistered(Exception):
    pass


def to_user_out(doc: dict) -> UserOut:
    return UserOut(id=str(doc["_id"]), name=doc["name"], email=doc["email"], created_at=doc["created_at"])


async def create_user(name: str, email: str, password: str) -> dict:
    doc = {
        "name": name.strip(),
        "email": email.lower(),
        "password_hash": hash_password(password),
        "created_at": datetime.now(UTC),
    }
    try:
        result = await get_db().users.insert_one(doc)
    except DuplicateKeyError as exc:
        raise EmailAlreadyRegistered from exc
    doc["_id"] = result.inserted_id
    return doc


async def authenticate(email: str, password: str) -> dict | None:
    user = await get_db().users.find_one({"email": email.lower()})
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user["password_hash"]) else None


async def get_user(user_id: str) -> dict | None:
    oid = to_object_id(user_id)
    return await get_db().users.find_one({"_id": oid}) if oid else None
