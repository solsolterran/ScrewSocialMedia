import argparse
import time

import requests

from common import (
    REQUEST_TIMEOUT,
    ScriptError,
    add_confirm_argument,
    add_no_post_arguments,
    add_text_arguments,
    confirm_post,
    expect_json_response,
    load_environment,
    print_dry_run,
    require_env,
    resolve_text,
    run_platform,
)


# Instagram publishing script.
#
# Can do:
# - publishes one hosted image post
# - publishes one hosted Reel post
#
# Needs:
# - META_PAGE_ACCESS_TOKEN
# - INSTAGRAM_USER_ID for the linked Instagram professional account
#
# Notes:
# - Instagram Graph publishing does not support plain text-only posts.
# - Local media upload is intentionally not implemented in this first pass.

PLATFORM = "Instagram"
GRAPH_API_VERSION = "v25.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
POLL_ATTEMPTS = 10
POLL_SECONDS = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish hosted media to Instagram.")
    add_text_arguments(parser, required=False)
    media_group = parser.add_mutually_exclusive_group()
    media_group.add_argument("--image-url", help="Hosted image URL to publish.")
    media_group.add_argument("--reel-url", help="Hosted video URL to publish as a Reel.")
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def wait_for_reel_container(container_id: str, access_token: str) -> None:
    for attempt in range(POLL_ATTEMPTS):
        if attempt:
            time.sleep(POLL_SECONDS)
        response = requests.get(
            f"{GRAPH_BASE_URL}/{container_id}",
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=REQUEST_TIMEOUT,
        )
        payload = expect_json_response(response, "Check Instagram Reel container")
        status_code = str(payload.get("status_code") or "")
        if status_code == "FINISHED":
            return
        if status_code in {"ERROR", "EXPIRED"}:
            raise ScriptError(f"Instagram Reel container {container_id} is {status_code}.")
    raise ScriptError(
        f"Instagram Reel container {container_id} did not finish processing in time."
    )


def fetch_permalink(media_id: str, access_token: str) -> str:
    response = requests.get(
        f"{GRAPH_BASE_URL}/{media_id}",
        params={"fields": "permalink", "access_token": access_token},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Fetch Instagram permalink")
    return str(payload.get("permalink") or media_id)


def check_auth(instagram_user_id: str, access_token: str) -> None:
    response = requests.get(
        f"{GRAPH_BASE_URL}/{instagram_user_id}",
        params={"fields": "id,username", "access_token": access_token},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Check Instagram auth")
    username = payload.get("username") or "unknown username"
    returned_user_id = payload.get("id") or instagram_user_id
    print(
        f"{PLATFORM}: auth check passed for {username} ({returned_user_id}). "
        "No media container or post was created."
    )


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env("META_PAGE_ACCESS_TOKEN", "INSTAGRAM_USER_ID")
    if args.check_auth:
        check_auth(env["INSTAGRAM_USER_ID"], env["META_PAGE_ACCESS_TOKEN"])
        return

    caption = resolve_text(args.text, args.text_key, required=False)
    if not args.image_url and not args.reel_url:
        raise ScriptError("Instagram needs --image-url or --reel-url.")
    media_url = args.image_url or args.reel_url
    media_kind = "Reel" if args.reel_url else "Image"

    if args.dry_run:
        print_dry_run(
            PLATFORM,
            [
                (
                    "Container request",
                    f"POST {GRAPH_BASE_URL}/{env['INSTAGRAM_USER_ID']}/media",
                ),
                (
                    "Publish request",
                    f"POST {GRAPH_BASE_URL}/{env['INSTAGRAM_USER_ID']}/media_publish",
                ),
                ("Instagram user ID", env["INSTAGRAM_USER_ID"]),
                ("Media kind", media_kind),
                ("Caption", caption),
                ("Media URL", media_url),
            ],
        )
        return

    confirm_post(
        PLATFORM,
        [
            ("Instagram user ID", env["INSTAGRAM_USER_ID"]),
            ("Media kind", media_kind),
            ("Caption", caption),
            ("Media URL", media_url),
        ],
        confirmed=args.confirmed,
    )

    data = {"caption": caption, "access_token": env["META_PAGE_ACCESS_TOKEN"]}
    if args.reel_url:
        data.update(
            {
                "media_type": "REELS",
                "video_url": args.reel_url,
                "share_to_feed": "true",
            }
        )
    else:
        data["image_url"] = args.image_url

    container_response = requests.post(
        f"{GRAPH_BASE_URL}/{env['INSTAGRAM_USER_ID']}/media",
        data=data,
        timeout=REQUEST_TIMEOUT,
    )
    container_payload = expect_json_response(
        container_response, "Create Instagram media container"
    )
    container_id = str(container_payload.get("id") or "")
    if not container_id:
        raise ScriptError("Instagram did not return a media container id.")
    if args.reel_url:
        wait_for_reel_container(container_id, env["META_PAGE_ACCESS_TOKEN"])

    publish_response = requests.post(
        f"{GRAPH_BASE_URL}/{env['INSTAGRAM_USER_ID']}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": env["META_PAGE_ACCESS_TOKEN"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    publish_payload = expect_json_response(publish_response, "Publish Instagram media")
    media_id = str(publish_payload.get("id") or "")
    if not media_id:
        raise ScriptError("Instagram did not return a published media id.")
    permalink = fetch_permalink(media_id, env["META_PAGE_ACCESS_TOKEN"])
    print(f"{PLATFORM}: posted {permalink}")


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
