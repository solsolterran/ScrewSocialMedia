import argparse

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


# Facebook Page posting script.
#
# Can do:
# - creates Page text/link posts through /{page_id}/feed
# - creates hosted photo posts through /{page_id}/photos
#
# Needs:
# - META_PAGE_ACCESS_TOKEN
# - FACEBOOK_PAGE_ID
#
# Notes:
# - Uses a Page access token, not the one-time setup User Access Token.
# - Facebook Reels are intentionally not implemented in this first pass.

PLATFORM = "Facebook"
GRAPH_API_VERSION = "v25.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post to a Facebook Page.")
    add_text_arguments(parser, required=False)
    parser.add_argument("--url", help="Optional link URL for a Page feed post.")
    parser.add_argument("--image-url", help="Hosted image URL for a Page photo post.")
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def fetch_permalink(object_id: str, access_token: str) -> str:
    response = requests.get(
        f"{GRAPH_BASE_URL}/{object_id}",
        params={"fields": "permalink_url", "access_token": access_token},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Fetch Facebook permalink")
    return str(payload.get("permalink_url") or object_id)


def check_auth(page_id: str, access_token: str) -> None:
    response = requests.get(
        f"{GRAPH_BASE_URL}/{page_id}",
        params={"fields": "id,name,link", "access_token": access_token},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Check Facebook Page auth")
    name = payload.get("name") or "unknown page"
    returned_page_id = payload.get("id") or page_id
    print(
        f"{PLATFORM}: auth check passed for {name} ({returned_page_id}). "
        "No post was created."
    )


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env("META_PAGE_ACCESS_TOKEN", "FACEBOOK_PAGE_ID")
    if args.check_auth:
        check_auth(env["FACEBOOK_PAGE_ID"], env["META_PAGE_ACCESS_TOKEN"])
        return

    text = resolve_text(args.text, args.text_key, required=False)
    if not text and not args.url and not args.image_url:
        raise ScriptError("Facebook needs --text, --text-key, --url, or --image-url.")
    caption = append_url(text, args.url) if args.image_url else text

    if args.dry_run:
        endpoint = "photos" if args.image_url else "feed"
        print_dry_run(
            PLATFORM,
            [
                (
                    "Request",
                    f"POST {GRAPH_BASE_URL}/{env['FACEBOOK_PAGE_ID']}/{endpoint}",
                ),
                ("Page ID", env["FACEBOOK_PAGE_ID"]),
                ("Text", caption if args.image_url else text),
                ("URL", None if args.image_url else args.url),
                ("Image URL", args.image_url),
            ],
        )
        return

    confirm_post(
        PLATFORM,
        [
            ("Page ID", env["FACEBOOK_PAGE_ID"]),
            ("Text", caption if args.image_url else text),
            ("URL", None if args.image_url else args.url),
            ("Image URL", args.image_url),
        ],
        confirmed=args.confirmed,
    )

    if args.image_url:
        response = requests.post(
            f"{GRAPH_BASE_URL}/{env['FACEBOOK_PAGE_ID']}/photos",
            data={
                "url": args.image_url,
                "caption": caption,
                "access_token": env["META_PAGE_ACCESS_TOKEN"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        payload = expect_json_response(response, "Create Facebook photo post")
        object_id = str(payload.get("post_id") or payload.get("id") or "")
    else:
        data = {"access_token": env["META_PAGE_ACCESS_TOKEN"]}
        if text:
            data["message"] = text
        if args.url:
            data["link"] = args.url
        response = requests.post(
            f"{GRAPH_BASE_URL}/{env['FACEBOOK_PAGE_ID']}/feed",
            data=data,
            timeout=REQUEST_TIMEOUT,
        )
        payload = expect_json_response(response, "Create Facebook feed post")
        object_id = str(payload.get("id") or "")

    if not object_id:
        raise ScriptError("Facebook did not return a post id.")
    permalink = fetch_permalink(object_id, env["META_PAGE_ACCESS_TOKEN"])
    print(f"{PLATFORM}: posted {permalink}")


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
