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


# Reddit posting script.
#
# Can do:
# - creates one link post per subreddit when --url is present
# - creates one self post per subreddit when --url is absent
#
# Needs:
# - REDDIT_CLIENT_ID
# - REDDIT_CLIENT_SECRET
# - REDDIT_REFRESH_TOKEN
# - REDDIT_USERNAME
#
# Notes:
# - Subreddit-specific moderation, flair, karma, and self-promo rules can reject posts.

PLATFORM = "Reddit"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SUBMIT_URL = "https://oauth.reddit.com/api/submit"
ME_URL = "https://oauth.reddit.com/api/v1/me"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit a Reddit link or self post.")
    parser.add_argument("--title", help="Reddit post title.")
    parser.add_argument(
        "--subreddit",
        action="append",
        help="Subreddit name. May be repeated.",
    )
    parser.add_argument("--url", help="URL for a link post.")
    add_text_arguments(parser, required=False)
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def reddit_user_agent(username: str) -> str:
    return f"linux:screw-social-media:v0.1.0 (by /u/{username})"


def refresh_access_token(env: dict[str, str], user_agent: str) -> str:
    response = requests.post(
        TOKEN_URL,
        auth=(env["REDDIT_CLIENT_ID"], env["REDDIT_CLIENT_SECRET"]),
        headers={"User-Agent": user_agent},
        data={
            "grant_type": "refresh_token",
            "refresh_token": env["REDDIT_REFRESH_TOKEN"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Refresh Reddit access token")
    access_token = payload.get("access_token")
    if not access_token:
        raise ScriptError("Reddit token refresh did not return an access token.")
    return str(access_token)


def reddit_post_url(data: dict) -> str:
    url = data.get("url") or data.get("permalink")
    if isinstance(url, str) and url.startswith("/"):
        return f"https://www.reddit.com{url}"
    if isinstance(url, str) and url:
        return url
    post_id = data.get("id")
    if post_id:
        return f"reddit id {post_id}"
    return "created post id unavailable"


def require_post_args(args: argparse.Namespace) -> None:
    if not args.title:
        raise ScriptError("Reddit needs --title.")
    if len(args.title) > 300:
        raise ScriptError("Reddit post titles can be at most 300 characters.")
    if not args.subreddit:
        raise ScriptError("Reddit needs at least one --subreddit.")


def check_auth(access_token: str, user_agent: str) -> None:
    response = requests.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Check Reddit auth")
    username = payload.get("name")
    if not username:
        raise ScriptError("Reddit auth check did not return a username.")
    print(f"{PLATFORM}: auth check passed for u/{username}. No post was created.")


def submit_to_subreddit(
    subreddit: str,
    title: str,
    text: str,
    url: str | None,
    access_token: str,
    user_agent: str,
) -> str:
    data = {
        "api_type": "json",
        "sr": subreddit,
        "title": title,
        "kind": "link" if url else "self",
    }
    if url:
        data["url"] = url
    else:
        data["text"] = text
    response = requests.post(
        SUBMIT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
        },
        data=data,
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, f"Submit Reddit post to r/{subreddit}")
    result = payload.get("json", {})
    errors = result.get("errors") or []
    if errors:
        raise ScriptError(f"r/{subreddit}: {errors}")
    return reddit_post_url(result.get("data", {}))


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env(
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_REFRESH_TOKEN",
        "REDDIT_USERNAME",
    )
    user_agent = reddit_user_agent(env["REDDIT_USERNAME"])
    if args.check_auth:
        access_token = refresh_access_token(env, user_agent)
        check_auth(access_token, user_agent)
        return

    require_post_args(args)
    text = resolve_text(args.text, args.text_key, required=not bool(args.url))
    body = append_url(text, args.url) if not args.url else text

    if args.dry_run:
        print_dry_run(
            PLATFORM,
            [
                ("Request", f"POST {SUBMIT_URL}"),
                ("Kind", "link" if args.url else "self"),
                ("Subreddits", args.subreddit),
                ("Title", args.title),
                ("Text", body),
                ("URL", args.url),
            ],
        )
        return

    confirm_post(
        PLATFORM,
        [
            ("Kind", "link" if args.url else "self"),
            ("Subreddits", args.subreddit),
            ("Title", args.title),
            ("Text", body),
            ("URL", args.url),
        ],
        confirmed=args.confirmed,
    )

    access_token = refresh_access_token(env, user_agent)
    posted: list[str] = []
    failures: list[str] = []
    for subreddit in args.subreddit:
        try:
            post_url = submit_to_subreddit(
                subreddit,
                args.title,
                body,
                args.url,
                access_token,
                user_agent,
            )
            posted.append(f"r/{subreddit}: {post_url}")
        except ScriptError as exc:
            failures.append(str(exc))

    if posted:
        print(f"{PLATFORM}: posted {'; '.join(posted)}")
    if failures:
        raise ScriptError("; ".join(failures))


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
