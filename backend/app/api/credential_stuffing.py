# This endpoint is dedicated to tracking credential stuffing stats
# for demo users (Alice and Ben). It queries the AuthEvent table
# and counts how many total login attempts were made vs. how many
# actually succeeded. 
#
# The goal is to easily demonstrate the impact of credential 
# stuffing and highlight how protections (rate limits, reauth, 
# anomaly detection) reduce successful compromises.
# 

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.auth_events import AuthEvent

# Router without a prefix — we explicitly mount the endpoint below
router = APIRouter()


# Returns stats for Alice and Ben, since they are our test/demo
# accounts that attackers typically target. For each user we count:
#   1. total_attempts → how many times login was attempted
#   2. successful_attempts → how many of those actually worked
# This lets the dashboard show effectiveness of defenses in real time.
@router.get("/api/credential-stuffing-stats")
def get_credential_stuffing_stats(db: Session = Depends(get_db)):
    """
    Returns the total and successful credential stuffing attempts for Alice and Ben.
    """
    users = ["alice", "ben"]
    stats = {}

    for user in users:
        # Count *all* login attempts for this user
        total_attempts = db.query(AuthEvent).filter(AuthEvent.user == user).count()

        # Count only successful ones (password guessed correctly)
        successful_attempts = (
            db.query(AuthEvent)
            .filter(AuthEvent.user == user, AuthEvent.success == True)
            .count()
        )

        # Store both numbers in the response dict
        stats[user] = {
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
        }

    return stats
