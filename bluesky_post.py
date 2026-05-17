import argparse
from datetime import datetime, timezone

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


# Bluesky posting script.
#
# Can do:
# - creates text/link posts through com.atproto.repo.createRecord
#
# Needs:
# - BLUESKY_HANDLE
# - BLUESKY_APP_PASSWORD from Bluesky app passwords
#
# Notes:
# - Link facets use UTF-8 byte offsets.

PLATFORM = "Bluesky"
SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
CREATE_RECORD_URL = "https://bsky.social/xrpc/com.atproto.repo.createRecord"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post text or a link to Bluesky.")
    add_text_arguments(parser, required=False)
    parser.add_argument("--url", help="Optional URL to append to the post text.")
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def make_link_facet(text: str, url: str | None) -> list[dict]:
    if not url:
        return []
    start_character = text.rfind(url)
    if start_character < 0:
        return []
    byte_start = len(text[:start_character].encode("utf-8"))
    byte_end = byte_start + len(url.encode("utf-8"))
    return [
        {
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [
                {"$type": "app.bsky.richtext.facet#link", "uri": url},
            ],
        }
    ]


def create_session(env: dict[str, str]) -> dict:
    session_response = requests.post(
        SESSION_URL,
        json={
            "identifier": env["BLUESKY_HANDLE"],
            "password": env["BLUESKY_APP_PASSWORD"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    session_payload = expect_json_response(session_response, "Create Bluesky session")
    access_jwt = session_payload.get("accessJwt")
    did = session_payload.get("did")
    if not access_jwt or not did:
        raise ScriptError("Bluesky session response did not include accessJwt and did.")
    return session_payload


def check_auth(env: dict[str, str]) -> None:
    session_payload = create_session(env)
    handle = session_payload.get("handle") or env["BLUESKY_HANDLE"]
    did = session_payload.get("did") or "unknown did"
    print(f"{PLATFORM}: auth check passed for {handle} ({did}). No post was created.")


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD")
    if args.check_auth:
        check_auth(env)
        return

    text = append_url(resolve_text(args.text, args.text_key, required=True), args.url)
    facets = make_link_facet(text, args.url)

    if args.dry_run:
        print_dry_run(
            PLATFORM,
            [
                ("Session request", f"POST {SESSION_URL}"),
                ("Post request", f"POST {CREATE_RECORD_URL}"),
                ("Handle", env["BLUESKY_HANDLE"]),
                ("Text", text),
                ("URL", args.url),
                ("Link facets", len(facets)),
            ],
        )
        return

    confirm_post(
        PLATFORM,
        [
            ("Handle", env["BLUESKY_HANDLE"]),
            ("Text", text),
            ("URL", args.url),
        ],
        confirmed=args.confirmed,
    )

    session_payload = create_session(env)
    access_jwt = session_payload.get("accessJwt")
    did = session_payload.get("did")

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    if facets:
        record["facets"] = facets

    create_response = requests.post(
        CREATE_RECORD_URL,
        headers={
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": "application/json",
        },
        json={
            "repo": did,
            "collection": "app.bsky.feed.post",
            "record": record,
        },
        timeout=REQUEST_TIMEOUT,
    )
    create_payload = expect_json_response(create_response, "Create Bluesky post")
    uri = str(create_payload.get("uri") or "")
    post_key = uri.rsplit("/", 1)[-1] if "/" in uri else ""
    if not post_key:
        raise ScriptError(f"Bluesky did not return a usable post uri: {uri or 'missing'}")
    print(f"{PLATFORM}: posted https://bsky.app/profile/{env['BLUESKY_HANDLE']}/post/{post_key}")


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
