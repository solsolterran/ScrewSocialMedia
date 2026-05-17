import argparse
import base64
import hashlib
import hmac
import time
import uuid
from urllib.parse import quote

import requests

from common import (
    REQUEST_TIMEOUT,
    ScriptError,
    add_confirm_argument,
    add_no_post_arguments,
    add_text_arguments,
    append_url,
    confirm_post,
    expect_json_response,
    load_environment,
    print_dry_run,
    require_env,
    resolve_text,
    run_platform,
)

# Twitter posting script.
#
# Can do:
# - creates text/link posts through POST /2/tweets
#
# Needs:
# - X_CONSUMER_KEY from the X Developer Portal
# - X_CONSUMER_KEY_SECRET from the X Developer Portal
# - X_USER_ACCESS_TOKEN from the X Developer Portal
# - X_USER_ACCESS_TOKEN_SECRET from the X Developer Portal
#
# Notes:
# - Twitter posting is paid per request.
# - URL posts may cost more than plain text posts.
# - Media upload is intentionally not implemented in this first pass.

PLATFORM = "Twitter"
POST_URL = "https://api.x.com/2/tweets"
VERIFY_CREDENTIALS_URL = "https://api.x.com/1.1/account/verify_credentials.json"


def percent_encode(value: str) -> str:
    return quote(value, safe="")


def oauth1_authorization_header(
    method: str,
    url: str,
    *,
    consumer_key: str,
    consumer_key_secret: str,
    access_token: str,
    access_token_secret: str,
    signature_params: dict[str, str] | None = None,
) -> str:
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    all_signature_params = dict(oauth_params)
    if signature_params:
        all_signature_params.update(signature_params)
    encoded_params = "&".join(
        f"{percent_encode(key)}={percent_encode(value)}"
        for key, value in sorted(all_signature_params.items())
    )
    signature_base = "&".join(
        percent_encode(part) for part in (method.upper(), url, encoded_params)
    )
    signing_key = "&".join(
        percent_encode(part) for part in (consumer_key_secret, access_token_secret)
    )
    oauth_params["oauth_signature"] = base64.b64encode(
        hmac.new(
            signing_key.encode("utf-8"),
            signature_base.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("ascii")
    return "OAuth " + ", ".join(
        f'{percent_encode(key)}="{percent_encode(value)}"'
        for key, value in sorted(oauth_params.items())
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post text or a link to Twitter.")
    add_text_arguments(parser, required=False)
    parser.add_argument("--url", help="Optional URL to append to the post text.")
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def check_auth(env: dict[str, str]) -> None:
    params = {"include_entities": "false", "skip_status": "true"}
    response = requests.get(
        VERIFY_CREDENTIALS_URL,
        params=params,
        headers={
            "Authorization": oauth1_authorization_header(
                "GET",
                VERIFY_CREDENTIALS_URL,
                consumer_key=env["X_CONSUMER_KEY"],
                consumer_key_secret=env["X_CONSUMER_KEY_SECRET"],
                access_token=env["X_USER_ACCESS_TOKEN"],
                access_token_secret=env["X_USER_ACCESS_TOKEN_SECRET"],
                signature_params=params,
            )
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Check Twitter auth")
    username = payload.get("screen_name") or "unknown"
    user_id = payload.get("id_str") or payload.get("id") or "unknown id"
    print(
        f"{PLATFORM}: auth check passed for @{username} ({user_id}). "
        "No post was created."
    )


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env(
        "X_CONSUMER_KEY",
        "X_CONSUMER_KEY_SECRET",
        "X_USER_ACCESS_TOKEN",
        "X_USER_ACCESS_TOKEN_SECRET",
    )
    if args.check_auth:
        check_auth(env)
        return

    text = append_url(resolve_text(args.text, args.text_key, required=True), args.url)

    if args.dry_run:
        print_dry_run(
            PLATFORM,
            [
                ("Request", f"POST {POST_URL}"),
                ("Text", text),
                ("URL", args.url),
            ],
        )
        return

    confirm_post(
        PLATFORM,
        [
            ("Text", text),
            ("URL", args.url),
        ],
        confirmed=args.confirmed,
    )

    response = requests.post(
        POST_URL,
        headers={
            "Authorization": oauth1_authorization_header(
                "POST",
                POST_URL,
                consumer_key=env["X_CONSUMER_KEY"],
                consumer_key_secret=env["X_CONSUMER_KEY_SECRET"],
                access_token=env["X_USER_ACCESS_TOKEN"],
                access_token_secret=env["X_USER_ACCESS_TOKEN_SECRET"],
            ),
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Create Twitter post")
    post_id = payload.get("data", {}).get("id")
    if not post_id:
        raise ScriptError(f"Twitter did not return a post id: {payload}")
    print(f"{PLATFORM}: posted https://x.com/i/web/status/{post_id}")


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
