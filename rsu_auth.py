"""RunSignup OAuth2 helper: one-time login, token exchange, and refresh.

Usage:
    python rsu_auth.py login            # opens browser, catches the code, saves tokens
    python rsu_auth.py login --code XXX # you already copied the code from the address bar
    python rsu_auth.py refresh          # get a new access token from the saved refresh token
    python rsu_auth.py check            # show which fields are saved (never prints secrets)

Needs a .env file and:  pip install httpx python-dotenv
"""
import argparse
import json
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv

env_file = find_dotenv(".env")
load_dotenv()

AUTH_URL = "https://runsignup.com/Profile/OAuth2/RequestGrant"
REDEEM_URL = "https://runsignup.com/rest/v2/auth/auth-code-redemption.json"
REFRESH_URL = "https://runsignup.com/rest/v2/auth/refresh-token.json"
SCOPE = "rsu_api_write"  # the guide says all API functions currently require this scope
TOKEN_FILE = Path("tokens.json")  # keep out of git (see .gitignore)


def need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing {name}. Add it to your .env file.")
    return value


def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": need("RSU_CLIENT_ID"),
        "redirect_uri": need("RSU_REDIRECT_URI"),
        "scope": SCOPE,
        "state": state,
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def wait_for_code(state: str, timeout_seconds: int = 300) -> str:
    """Open the browser and wait for RunSignup to redirect back to localhost."""
    redirect = urllib.parse.urlparse(need("RSU_REDIRECT_URI"))
    if redirect.hostname not in ("localhost", "127.0.0.1"):
        sys.exit("Automatic capture only works with a localhost redirect URI. "
                 "Use:  python rsu_auth.py login --code <code from address bar>")

    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != redirect.path:
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authorized. You can close this tab and return to the terminal.")

        def log_message(self, *args):  # keep the code out of terminal logs
            pass

    server = HTTPServer((redirect.hostname, redirect.port or 80), Handler)
    server.timeout = timeout_seconds
    print("Opening your browser. Log in to RunSignup and approve access...")
    webbrowser.open(build_authorize_url(state))
    deadline = time.time() + timeout_seconds
    while "code" not in result and "error" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()

    if "error" in result:
        sys.exit(f"Authorization failed: {result.get('error')} - {result.get('error_description', '')}")
    if "code" not in result:
        sys.exit("Timed out waiting for the redirect.")
    if result.get("state") != state:
        sys.exit("State mismatch. Discarding the code. Run login again.")
    return result["code"]


def post_form(url: str, data: dict) -> dict:
    r = httpx.post(url, data=data, timeout=30)
    if r.status_code >= 400:
        sys.exit(f"Request failed: HTTP {r.status_code}\n{r.text[:500]}")
    return r.json()


def save_tokens(new: dict, previous: dict | None = None) -> None:
    tokens = dict(new)
    # Some servers omit the refresh token on refresh; keep the old one if so.
    if previous and "refresh_token" not in tokens and "refresh_token" in previous:
        tokens["refresh_token"] = previous["refresh_token"]
    tokens["saved_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    try:
        TOKEN_FILE.chmod(0o600)  # owner read/write only (no effect on Windows)
    except OSError:
        pass


def load_tokens() -> dict:
    if not TOKEN_FILE.exists():
        sys.exit("No tokens.json yet. Run:  python rsu_auth.py login")
    return json.loads(TOKEN_FILE.read_text())


def redeem_code(code: str) -> dict:
    """Step 2: swap the one-time authorization code for tokens."""
    return post_form(REDEEM_URL, {
        "grant_type": "authorization_code",
        "client_id": need("RSU_CLIENT_ID"),
        "client_secret": need("RSU_CLIENT_SECRET"),
        "redirect_uri": need("RSU_REDIRECT_URI"),
        "code": code,
    })


def refresh_tokens() -> dict:
    old = load_tokens()
    if "refresh_token" not in old:
        sys.exit("tokens.json has no refresh_token field. Run 'check' to see what was saved.")
    new = post_form(REFRESH_URL, {
        "grant_type": "refresh_token",
        "refresh_token": old["refresh_token"],
        "client_id": need("RSU_CLIENT_ID"),
        "client_secret": need("RSU_CLIENT_SECRET"),
    })
    save_tokens(new, previous=old)
    return new


def get_access_token() -> str:
    """Import this from your pipeline code: from rsu_auth import get_access_token"""
    tokens = load_tokens()
    if "access_token" not in tokens:
        sys.exit("tokens.json has no access_token field. Run 'check' to see what was saved.")
    return tokens["access_token"]


def auth_headers() -> dict:
    """Headers for every API call: Bearer token plus API caller registration secret."""
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "X-RSU-API-REG-SECRET": need("RSU_API_REG_SECRET"),
        "User-Agent": "PacePipe/0.1 (you@email.com)",
    }


def cmd_login(code: str | None) -> None:
    if code:
        # Manual route: code was copied from the address bar. Be quick, it lasts 5 minutes.
        code = code.strip()
    else:
        code = wait_for_code(secrets.token_urlsafe(16))
    tokens = redeem_code(code)
    save_tokens(tokens)
    print(f"Success. Tokens saved to {TOKEN_FILE}. Fields received: {sorted(tokens.keys())}")


def cmd_check() -> None:
    tokens = load_tokens()
    print("Fields saved:", sorted(tokens.keys()))
    print("Saved at:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(tokens.get("saved_at", 0))))
    if "expires_in" in tokens:
        print("expires_in (seconds):", tokens["expires_in"])


def main() -> None:
    parser = argparse.ArgumentParser(description="RunSignup OAuth2 helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    login = sub.add_parser("login", help="one-time browser login and token exchange")
    login.add_argument("--code", help="authorization code copied from the address bar")
    sub.add_parser("refresh", help="refresh the access token")
    sub.add_parser("check", help="show saved token fields without revealing values")
    args = parser.parse_args()

    if args.cmd == "login":
        cmd_login(args.code)
    elif args.cmd == "refresh":
        refresh_tokens()
        print("Refreshed. New tokens saved.")
    elif args.cmd == "check":
        cmd_check()


if __name__ == "__main__":
    main()
