# This file defines reusable FastAPI dependencies for authentication
# and authorization. Any route that wants to know "who is the current
# user" or "does this user have the right role" will import functions
# from here.
#
# It ties together JWT decoding, token revocation checks, and database
# lookups so endpoints don’t have to reimplement this logic.

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, is_token_revoked
from app.core.db import get_db
from app.crud.users import get_user_by_username

# OAuth2PasswordBearer is the standard FastAPI helper that looks for
# an Authorization: Bearer <token> header. We point it to /api/token
# since that’s the endpoint where tokens are issued.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")



# This is the core dependency for protecting endpoints. It:
#   1. Extracts the bearer token from the request.
#   2. Decodes the JWT and validates it.
#   3. Checks if the token has been revoked.
#   4. Loads the corresponding user from the DB.
#
# If any step fails, we throw a 401. We also log an Alert into
# the DB if the JWT was invalid, so the dashboard can show 
# "invalid token" events with the client IP.
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    request: Request = None,
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decode the JWT payload
        payload = decode_access_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        # If decoding fails, log an "Invalid token" alert tied to client IP
        if request is not None:
            from app.models.alerts import Alert
            alert = Alert(ip_address=request.client.host, total_fails=0, detail="Invalid token")
            db.add(alert)
            db.commit()
        raise credentials_exception

    # Check if the token was explicitly revoked (logout, admin action, etc.)
    if is_token_revoked(token):
        raise credentials_exception

    # Look up the user record in the DB. If not found → reject.
    user = get_user_by_username(db, username)
    if not user:
        raise credentials_exception
    return user


# This is a higher-order dependency that enforces role-based access.
# Example usage:
#   @router.get("/admin")
#   def admin_dashboard(user = Depends(require_role("admin"))): ...
#
# It runs get_current_user first, then checks that the user’s role
# matches what the endpoint requires. Otherwise → 403 forbidden.
def require_role(required: str):
    def checker(user=Depends(get_current_user)):
        if user.role != required:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return checker
