# This file defines an API route that shows the last login
# timestamp for each user. It queries the database, grabs the
# most recent login times, and returns them in JSON format.
#
# The result is a simple dictionary: { "username": "timestamp" }
# where the timestamp is ISO 8601 (so the frontend can parse it).

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api.dependencies import get_current_user
from app.crud.events import get_last_logins

# Prefix ensures everything here lives under /api/last-logins
router = APIRouter(prefix="/api/last-logins", tags=["stats"])


# GET /api/last-logins/
#
# Requires authentication. Pulls last login times from the DB
# using our CRUD helper and converts them into ISO8601 strings.
# This keeps the API consistent and makes parsing easier for 
# the React frontend and any external tools.
@router.get("/")
def read_last_logins(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    data = get_last_logins(db)
    # convert Python datetime objects into ISO strings for JSON
    return {u: ts.isoformat() for u, ts in data.items()}
