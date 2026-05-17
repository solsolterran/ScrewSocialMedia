import argparse
import json
from pathlib import Path

import requests

from common import (
    REQUEST_TIMEOUT,
    ScriptError,
    add_confirm_argument,
    add_no_post_arguments,
    confirm_post,
    expect_json_response,
    load_environment,
    media_type_for_path,
    print_dry_run,
    require_env,
    require_file,
    run_platform,
)


# YouTube upload script.
#
# Can do:
# - uploads one video through a resumable videos.insert session
#
# Needs:
# - YOUTUBE_CLIENT_SECRETS_FILE pointing to a Google OAuth client JSON file
# - YOUTUBE_TOKEN_FILE pointing to a JSON file with refresh_token and access_token
#
# Notes:
# - Uploads are public by default.
# - The API project must be verified before trusting public posting.

PLATFORM = "YouTube"
UPLOAD_INIT_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
DEFAULT_CATEGORY_ID = "20"
DEFAULT_PRIVACY_STATUS = "public"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a video to YouTube.")
    parser.add_argument("--title", help="YouTube video title.")
    parser.add_argument("--description", default="", help="YouTube video description.")
    parser.add_argument("--media", help="Local video file to upload.")
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def load_json_file(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScriptError(f"Could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ScriptError(f"{label} must contain a JSON object: {path}")
    return payload


def oauth_client_info(client_secrets_path: Path) -> tuple[str, str, str]:
    payload = load_json_file(client_secrets_path, "YouTube client secrets file")
    client_config = payload.get("installed") or payload.get("web") or payload
    client_id = client_config.get("client_id")
    client_secret = client_config.get("client_secret")
    token_uri = client_config.get("token_uri") or "https://oauth2.googleapis.com/token"
    if not client_id or not client_secret:
        raise ScriptError(
            "YouTube client secrets file must include client_id and client_secret."
        )
    return str(client_id), str(client_secret), str(token_uri)


def load_token_file(token_path: Path) -> dict:
    if not token_path.exists():
        raise ScriptError(
            f"YouTube token file does not exist: {token_path}. Create it with OAuth first."
        )
    return load_json_file(token_path, "YouTube token file")


def refresh_access_token(
    token_path: Path,
    client_id: str,
    client_secret: str,
    token_uri: str,
    *,
    write_token: bool = True,
) -> str:
    token_payload = load_token_file(token_path)
    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        access_token = token_payload.get("access_token")
        if access_token:
            return str(access_token)
        raise ScriptError("YouTube token file must include refresh_token or access_token.")

    response = requests.post(
        token_uri,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Refresh YouTube access token")
    access_token = payload.get("access_token")
    if not access_token:
        raise ScriptError("YouTube token refresh did not return an access token.")
    refreshed_refresh_token = payload.get("refresh_token") or refresh_token
    token_payload.update(payload)
    token_payload["refresh_token"] = refreshed_refresh_token
    if write_token:
        token_path.write_text(
            json.dumps(token_payload, indent=2) + "\n", encoding="utf-8"
        )
    return str(access_token)


def require_post_args(args: argparse.Namespace) -> None:
    if not args.title:
        raise ScriptError("YouTube needs --title.")
    if not args.media:
        raise ScriptError("YouTube needs --media.")


def check_auth(access_token: str) -> None:
    response = requests.get(
        CHANNELS_URL,
        params={"part": "id,snippet,status", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Check YouTube auth")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ScriptError("YouTube auth check returned no channels for this account.")
    channel = items[0]
    if not isinstance(channel, dict):
        raise ScriptError("YouTube auth check returned an unexpected channel payload.")
    snippet = channel.get("snippet") or {}
    status = channel.get("status") or {}
    title = snippet.get("title") or "unknown channel"
    channel_id = channel.get("id") or "unknown id"
    long_uploads = status.get("longUploadsStatus") or "unknown"
    print(
        f"{PLATFORM}: auth check passed for {title} ({channel_id}); "
        f"long uploads: {long_uploads}. No video was uploaded."
    )


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env("YOUTUBE_CLIENT_SECRETS_FILE", "YOUTUBE_TOKEN_FILE")
    client_secrets_path = require_file(
        env["YOUTUBE_CLIENT_SECRETS_FILE"], "YouTube client secrets file"
    )
    token_path = Path(env["YOUTUBE_TOKEN_FILE"]).expanduser()
    client_id, client_secret, token_uri = oauth_client_info(client_secrets_path)
    if args.check_auth:
        access_token = refresh_access_token(
            token_path, client_id, client_secret, token_uri, write_token=False
        )
        check_auth(access_token)
        return

    require_post_args(args)
    media_path = require_file(args.media, "YouTube media")
    media_size = media_path.stat().st_size
    media_type = media_type_for_path(media_path, "video/mp4")
    if args.dry_run:
        token_payload = load_token_file(token_path)
        if not token_payload.get("refresh_token") and not token_payload.get(
            "access_token"
        ):
            raise ScriptError(
                "YouTube token file must include refresh_token or access_token."
            )
        print_dry_run(
            PLATFORM,
            [
                ("Request", f"POST {UPLOAD_INIT_URL} then PUT upload URL"),
                ("Title", args.title),
                ("Description", args.description),
                ("Media", media_path),
                ("Media size", media_size),
                ("Media type", media_type),
                ("Privacy", DEFAULT_PRIVACY_STATUS),
                ("Synthetic media", "true"),
            ],
        )
        return

    confirm_post(
        PLATFORM,
        [
            ("Title", args.title),
            ("Description", args.description),
            ("Media", media_path),
            ("Privacy", DEFAULT_PRIVACY_STATUS),
            ("Synthetic media", "true"),
        ],
        confirmed=args.confirmed,
    )

    access_token = refresh_access_token(token_path, client_id, client_secret, token_uri)
    init_response = requests.post(
        UPLOAD_INIT_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(media_size),
            "X-Upload-Content-Type": media_type,
        },
        json={
            "snippet": {
                "title": args.title,
                "description": args.description,
                "categoryId": DEFAULT_CATEGORY_ID,
            },
            "status": {
                "privacyStatus": DEFAULT_PRIVACY_STATUS,
                "containsSyntheticMedia": True,
            },
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not 200 <= init_response.status_code < 300:
        expect_json_response(init_response, "Start YouTube upload")
    upload_url = init_response.headers.get("Location")
    if not upload_url:
        raise ScriptError("YouTube did not return a resumable upload URL.")

    with media_path.open("rb") as media_file:
        upload_response = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": media_type,
                "Content-Length": str(media_size),
            },
            data=media_file,
            timeout=None,
        )
    upload_payload = expect_json_response(upload_response, "Upload YouTube video")
    video_id = upload_payload.get("id")
    if not video_id:
        raise ScriptError("YouTube did not return a video id.")
    print(f"{PLATFORM}: posted https://youtu.be/{video_id}")


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
