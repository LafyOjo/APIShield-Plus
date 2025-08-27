import os
import requests

API_BASE = os.environ.get("API_BASE", "http://localhost:8001")

# Register and login to obtain a valid token
r = requests.post(f"{API_BASE}/register", json={"username": "demo", "password": "demo"})
r.raise_for_status()
login = requests.post(f"{API_BASE}/login", json={"username": "demo", "password": "demo"})
login.raise_for_status()
valid_token = login.json()["access_token"]
print("Received valid token", valid_token)

# Call a protected endpoint with the valid token
resp = requests.get(f"{API_BASE}/api/alerts", headers={"Authorization": f"Bearer {valid_token}"})
print("Valid token status", resp.status_code)

# Now try with a random/invalid token
invalid_token = "invalid." * 3
resp = requests.get(f"{API_BASE}/api/alerts", headers={"Authorization": f"Bearer {invalid_token}"})
print("Invalid token status", resp.status_code)
