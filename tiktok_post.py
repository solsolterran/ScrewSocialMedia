import argparse
import time
from pathlib import Path

import requests

from common import (
    REQUEST_TIMEOUT,
    ScriptError,
    add_confirm_argument,
    add_no_post_arguments,
    chunk_plan,
    confirm_post,
    expect_json_response,
    load_environment,
    media_type_for_path,
    print_dry_run,
    redact_text,
    require_env,
    require_file,
    run_platform,
)


# TikTok direct posting script.
#
# Can do:
# - posts one local video through Content Posting API direct post FILE_UPLOAD
#
# Needs:
# - TIKTOK_CLIENT_KEY
# - TIKTOK_CLIENT_SECRET
# - TIKTOK_REFRESH_TOKEN
#
# Notes:
# - Public posting requires app approval.
# - The script fails before upload if PUBLIC_TO_EVERYONE is not available.

PLATFORM = "TikTok"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
DIRECT_POST_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
PUBLIC_PRIVACY_LEVEL = "PUBLIC_TO_EVERYONE"
MAX_TIKTOK_CHUNK_SIZE = 64 * 1024 * 1024
MAX_TIKTOK_TITLE_UTF16_UNITS = 2200
STATUS_POLL_ATTEMPTS = 6
STATUS_POLL_SECONDS = 10
TIKTOK_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct-post a video to TikTok.")
    parser.add_argument("--title", help="TikTok caption/title.")
    parser.add_argument("--media", help="Local video file to upload.")
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def refresh_access_token(env: dict[str, str]) -> str:
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": env["TIKTOK_CLIENT_KEY"],
            "client_secret": env["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": env["TIKTOK_REFRESH_TOKEN"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Refresh TikTok access token")
    access_token = payload.get("access_token")
    if not access_token:
        raise ScriptError("TikTok token refresh did not return an access token.")
    refreshed_refresh_token = payload.get("refresh_token")
    if refreshed_refresh_token and refreshed_refresh_token != env["TIKTOK_REFRESH_TOKEN"]:
        print("TikTok returned a new refresh token. Update TIKTOK_REFRESH_TOKEN in env.")
    return str(access_token)


def expect_tiktok_ok(payload: dict, operation: str) -> None:
    error = payload.get("error") or {}
    if error.get("code") not in (None, "ok"):
        message = error.get("message") or error.get("code")
        raise ScriptError(f"{operation} failed: {message}")


def query_creator_info(access_token: str) -> dict:
    response = requests.post(
        CREATOR_INFO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Query TikTok creator info")
    expect_tiktok_ok(payload, "Query TikTok creator info")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ScriptError("TikTok creator info response missed data.")
    privacy_options = data.get("privacy_level_options") or []
    if PUBLIC_PRIVACY_LEVEL not in privacy_options:
        raise ScriptError(
            "TikTok public posting is not available. Returned privacy levels: "
            f"{', '.join(str(option) for option in privacy_options) or 'none'}"
        )
    return data


def media_type_for_upload(media_path: Path) -> str:
    media_type = media_type_for_path(media_path, "")
    if media_type not in TIKTOK_VIDEO_TYPES:
        raise ScriptError("TikTok video posting expects MP4, MOV, or WebM media.")
    return media_type


def initialize_post(
    access_token: str,
    title: str,
    media_path: Path,
    creator_info: dict,
    chunk_size: int,
    chunk_count: int,
) -> tuple[str, str]:
    response = requests.post(
        DIRECT_POST_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": title,
                "privacy_level": PUBLIC_PRIVACY_LEVEL,
                "disable_duet": bool(creator_info.get("duet_disabled")),
                "disable_comment": bool(creator_info.get("comment_disabled")),
                "disable_stitch": bool(creator_info.get("stitch_disabled")),
                "video_cover_timestamp_ms": 1000,
                "brand_content_toggle": False,
                "brand_organic_toggle": False,
                "is_aigc": True,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": media_path.stat().st_size,
                "chunk_size": chunk_size,
                "total_chunk_count": chunk_count,
            },
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Initialize TikTok direct post")
    expect_tiktok_ok(payload, "Initialize TikTok direct post")
    data = payload.get("data") or {}
    publish_id = str(data.get("publish_id") or "")
    upload_url = str(data.get("upload_url") or "")
    if not publish_id or not upload_url:
        raise ScriptError("TikTok did not return publish_id and upload_url.")
    return publish_id, upload_url


def upload_video(
    upload_url: str, media_path: Path, chunk_size: int, media_type: str
) -> None:
    file_size = media_path.stat().st_size
    with media_path.open("rb") as source:
        start_byte = 0
        while start_byte < file_size:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            end_byte = start_byte + len(chunk) - 1
            response = requests.put(
                upload_url,
                headers={
                    "Content-Type": media_type,
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
                },
                data=chunk,
                timeout=None,
            )
            if response.status_code not in (201, 206):
                raise ScriptError(
                    f"TikTok video upload failed with HTTP {response.status_code}: "
                    f"{redact_text(response.text)}"
                )
            start_byte = end_byte + 1


def fetch_post_status(access_token: str, publish_id: str) -> dict:
    response = requests.post(
        STATUS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Fetch TikTok post status")
    expect_tiktok_ok(payload, "Fetch TikTok post status")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ScriptError("TikTok post status response missed data.")
    return data


def wait_for_post_status(access_token: str, publish_id: str) -> dict:
    status_data: dict = {}
    for attempt in range(STATUS_POLL_ATTEMPTS):
        if attempt:
            time.sleep(STATUS_POLL_SECONDS)
        status_data = fetch_post_status(access_token, publish_id)
        status = str(status_data.get("status") or "")
        if status == "FAILED":
            reason = status_data.get("fail_reason") or "unknown reason"
            raise ScriptError(f"TikTok post {publish_id} failed: {reason}")
        if status == "PUBLISH_COMPLETE":
            return status_data
    return status_data


def require_post_args(args: argparse.Namespace) -> None:
    if not args.title:
        raise ScriptError("TikTok needs --title.")
    if not args.media:
        raise ScriptError("TikTok needs --media.")


def check_auth(access_token: str) -> None:
    creator_info = query_creator_info(access_token)
    username = creator_info.get("creator_username") or "unknown creator"
    privacy_options = creator_info.get("privacy_level_options") or []
    print(
        f"{PLATFORM}: auth check passed for {username}; "
        f"privacy levels: {', '.join(str(option) for option in privacy_options)}. "
        "No post was initialized or uploaded."
    )


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env(
        "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"
    )
    if args.check_auth:
        access_token = refresh_access_token(env)
        check_auth(access_token)
        return

    require_post_args(args)
    media_path = require_file(args.media, "TikTok media")
    media_type = media_type_for_upload(media_path)
    if len(args.title.encode("utf-16-le")) // 2 > MAX_TIKTOK_TITLE_UTF16_UNITS:
        raise ScriptError("TikTok titles can be at most 2200 UTF-16 units.")
    chunk_size, chunk_count = chunk_plan(
        media_path.stat().st_size, MAX_TIKTOK_CHUNK_SIZE
    )

    if args.dry_run:
        print_dry_run(
            PLATFORM,
            [
                ("Creator info request", f"POST {CREATOR_INFO_URL}"),
                ("Post init request", f"POST {DIRECT_POST_URL}"),
                ("Title", args.title),
                ("Media", media_path),
                ("Media size", media_path.stat().st_size),
                ("Media type", media_type),
                ("Privacy", PUBLIC_PRIVACY_LEVEL),
                ("Chunk count", chunk_count),
            ],
        )
        return

    access_token = refresh_access_token(env)
    creator_info = query_creator_info(access_token)

    confirm_post(
        PLATFORM,
        [
            ("Creator", creator_info.get("creator_username")),
            ("Title", args.title),
            ("Media", media_path),
            ("Privacy", PUBLIC_PRIVACY_LEVEL),
            ("Chunk count", chunk_count),
        ],
        confirmed=args.confirmed,
    )

    publish_id, upload_url = initialize_post(
        access_token, args.title, media_path, creator_info, chunk_size, chunk_count
    )
    upload_video(upload_url, media_path, chunk_size, media_type)
    status_data = wait_for_post_status(access_token, publish_id)
    status = str(status_data.get("status") or "unknown")
    post_ids = (
        status_data.get("publicaly_available_post_id")
        or status_data.get("publicly_available_post_id")
        or []
    )
    if isinstance(post_ids, str):
        post_ids = [post_ids]
    elif not isinstance(post_ids, list):
        post_ids = []
    post_ids = [str(post_id) for post_id in post_ids]
    if status == "PUBLISH_COMPLETE":
        suffix = f"; post id(s) {', '.join(post_ids)}" if post_ids else ""
        print(f"{PLATFORM}: posted publish_id {publish_id}{suffix}")
    else:
        print(
            f"{PLATFORM}: uploaded publish_id {publish_id}; current status {status}"
        )


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
