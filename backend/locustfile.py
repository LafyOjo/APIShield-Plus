# This file defines simulated users for Locust, a load testing
# tool. It mimics real user behavior (like browsing docs and
# submitting scores) so you can stress test your API.

from locust import HttpUser, task, between, tag
import random

# A small set of fake passwords that users will try. This gives
# the simulation some variety and makes results more realistic.
PASSWORDS = ["hunter2", "password123", "letmein!", "CorrectHorseBatteryStaple", "P@ssw0rd"]


class BaseUser(HttpUser):
    # Controls how long users wait between actions (1–3 sec).
    wait_time = between(1, 3)


    @task(3)
    def home(self):
        # Simulates hitting the root page (/). Weighted to happen
        # more often since it’s a common user action.
        self.client.get("/", name="GET /")

    @task(1)
    def docs(self):
        # Occasionally users will check out the API docs. This
        # keeps the test mix realistic.
        self.client.get("/docs", name="GET /docs")

    def _post_score(self, who: str):
        # Build a fake payload with a random password each time
        payload = {
            "user": who,
            "password": random.choice(PASSWORDS),
        }
        # Name the request uniquely so Locust shows separate stats
        # for Alice vs Ben traffic.
        self.client.post("/score", json=payload, name=f"POST /score ({who})")


class BenUser(BaseUser):
    # Relative traffic weight: Ben users appear more frequently
    weight = 3

    @task(2)
    @tag("ben")
    def score_ben(self):
        # Simulates Ben submitting scores repeatedly
        self._post_score("ben")


class AliceUser(BaseUser):
    # Slightly lower weight than Ben, so fewer Alice users spawn
    weight = 2

    @task(2)
    @tag("alice")
    def score_alice(self):
        # Simulates Alice trying to log scores too
        self._post_score("alice")
