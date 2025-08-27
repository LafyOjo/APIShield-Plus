# This module contains a couple of straightforward functions
# for working with the users table: looking them up by username
# and creating new ones with a role and optional policy link.

from sqlalchemy.orm import Session
from app.models.users import User


# Look up a single User object by their username. Returns the
# User row if found, otherwise returns None. This is used a lot
# in authentication and authorization flows.
def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


# Insert a new user row into the database. You must supply the
# username and a pre-hashed password. You can also set their
# role (default is "user") and optionally attach a policy_id.
# The function commits immediately and returns the new row.
def create_user(
    db: Session,
    username: str,
    password_hash: str,
    role: str = "user",
    policy_id: int | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=password_hash,
        role=role,
        policy_id=policy_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
