import argparse
import base64
import os
import tempfile
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
    print_dry_run,
    require_env,
    require_file,
    run_platform,
)


# Snapchat Public Profile posting script.
#
# Can do:
# - uploads one local MP4 to Snapchat Public Profile media
# - posts the uploaded media as a Story or Spotlight
#
# Needs:
# - SNAPCHAT_CLIENT_ID
# - SNAPCHAT_CLIENT_SECRET
# - SNAPCHAT_REFRESH_TOKEN
# - SNAPCHAT_PUBLIC_PROFILE_ID
#
# Notes:
# - This is not normal personal-account posting.
# - The OAuth app must be created from Snap Ads Manager/Business Dashboard.
# - The app must be allowlisted for Public Profile API access.
# - Requires the cryptography package for Snapchat's AES-256-CBC media encryption.

PLATFORM = "Snapchat"
TOKEN_URL = "https://accounts.snapchat.com/login/oauth2/access_token"
BUSINESS_API_BASE = "https://businessapi.snapchat.com"
MAX_SNAPCHAT_CHUNK_SIZE = 32 * 1024 * 1024
MAX_SNAPCHAT_MEDIA_SIZE = 1024 * 1024 * 1024
MAX_SNAPCHAT_PARTS = 35


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post local media to Snapchat.")
    destination_group = parser.add_mutually_exclusive_group()
    destination_group.add_argument("--story", action="store_true", help="Post as a Story.")
    destination_group.add_argument(
        "--spotlight", action="store_true", help="Post as a Spotlight."
    )
    parser.add_argument("--description", default="", help="Spotlight description.")
    parser.add_argument("--locale", help="Spotlight locale, such as en_US.")
    parser.add_argument("--media", help="Local MP4 file to upload.")
    add_no_post_arguments(parser)
    add_confirm_argument(parser)
    return parser.parse_args()


def refresh_access_token(env: dict[str, str]) -> str:
    response = requests.post(
        TOKEN_URL,
        data={
            "refresh_token": env["SNAPCHAT_REFRESH_TOKEN"],
            "client_id": env["SNAPCHAT_CLIENT_ID"],
            "client_secret": env["SNAPCHAT_CLIENT_SECRET"],
            "grant_type": "refresh_token",
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Refresh Snapchat access token")
    access_token = payload.get("access_token")
    if not access_token:
        raise ScriptError("Snapchat token refresh did not return an access token.")
    if payload.get("refresh_token") and payload.get("refresh_token") != env["SNAPCHAT_REFRESH_TOKEN"]:
        print("Snapchat returned a new refresh token. Update SNAPCHAT_REFRESH_TOKEN in env.")
    return str(access_token)


def encrypt_media(media_path: Path) -> tuple[Path, bytes, bytes]:
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise ScriptError(
            "Snapchat posting needs cryptography. Install ScrewSocialMedia/requirements.txt."
        ) from exc

    key = os.urandom(32)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()

    file_handle, temp_name = tempfile.mkstemp(prefix="snapchat-", suffix=".enc")
    os.close(file_handle)
    encrypted_path = Path(temp_name)
    try:
        with media_path.open("rb") as source, encrypted_path.open("wb") as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                padded = padder.update(chunk)
                if padded:
                    target.write(encryptor.update(padded))
            final_padded = padder.finalize()
            target.write(encryptor.update(final_padded))
            target.write(encryptor.finalize())
    except Exception:
        encrypted_path.unlink(missing_ok=True)
        raise
    return encrypted_path, key, iv


def snap_success(payload: dict, operation: str) -> None:
    if payload.get("request_status") != "SUCCESS":
        raise ScriptError(f"{operation} failed: {payload}")


def check_auth(profile_id: str, access_token: str) -> None:
    response = requests.get(
        f"{BUSINESS_API_BASE}/v1/public_profiles/{profile_id}",
        headers={"Authorization": access_token},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Check Snapchat Public Profile auth")
    snap_success(payload, "Check Snapchat Public Profile auth")
    profile_payload = payload.get("public_profile") or payload.get("public_profile_v2")
    if not isinstance(profile_payload, dict):
        profiles = payload.get("public_profiles")
        if isinstance(profiles, list) and profiles:
            first_profile = profiles[0]
            if isinstance(first_profile, dict):
                profile_payload = first_profile.get("public_profile") or first_profile
    if not isinstance(profile_payload, dict):
        raise ScriptError("Snapchat auth check did not return a public profile.")
    display_name = (
        profile_payload.get("display_name")
        or profile_payload.get("title")
        or "unknown profile"
    )
    returned_profile_id = profile_payload.get("id") or profile_payload.get("profile_id")
    print(
        f"{PLATFORM}: auth check passed for {display_name} "
        f"({returned_profile_id or profile_id}). No media was uploaded."
    )


def create_media_container(
    profile_id: str, access_token: str, media_path: Path, key: bytes, iv: bytes
) -> tuple[str, str, str]:
    response = requests.post(
        f"{BUSINESS_API_BASE}/v1/public_profiles/{profile_id}/media",
        headers={"Authorization": access_token, "Content-Type": "application/json"},
        json={
            "type": "VIDEO",
            "name": media_path.stem[:80] or "media",
            "key": base64.b64encode(key).decode("ascii"),
            "iv": base64.b64encode(iv).decode("ascii"),
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Create Snapchat media container")
    snap_success(payload, "Create Snapchat media container")
    media_id = str(payload.get("media_id") or "")
    add_path = str(payload.get("add_path") or "")
    finalize_path = str(payload.get("finalize_path") or "")
    if not media_id or not add_path or not finalize_path:
        raise ScriptError("Snapchat media container response missed upload paths.")
    return media_id, add_path, finalize_path


def upload_encrypted_media(
    access_token: str, encrypted_path: Path, add_path: str, finalize_path: str
) -> None:
    part_count = (
        encrypted_path.stat().st_size + MAX_SNAPCHAT_CHUNK_SIZE - 1
    ) // MAX_SNAPCHAT_CHUNK_SIZE
    if part_count > MAX_SNAPCHAT_PARTS:
        raise ScriptError("Snapchat multipart uploads support at most 35 parts.")
    part_number = 1
    with encrypted_path.open("rb") as source:
        while True:
            chunk = source.read(MAX_SNAPCHAT_CHUNK_SIZE)
            if not chunk:
                break
            response = requests.post(
                f"{BUSINESS_API_BASE}{add_path}",
                headers={"Authorization": access_token},
                data={"action": "ADD", "part_number": str(part_number)},
                files={"file": (encrypted_path.name, chunk)},
                timeout=None,
            )
            payload = expect_json_response(response, f"Upload Snapchat media part {part_number}")
            snap_success(payload, f"Upload Snapchat media part {part_number}")
            part_number += 1
    response = requests.post(
        f"{BUSINESS_API_BASE}{finalize_path}",
        headers={"Authorization": access_token},
        data={"action": "FINALIZE"},
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, "Finalize Snapchat media upload")
    snap_success(payload, "Finalize Snapchat media upload")


def publish_media(
    profile_id: str,
    access_token: str,
    media_id: str,
    *,
    story: bool,
    description: str,
    locale: str | None,
) -> str:
    endpoint = "stories" if story else "spotlights"
    body = {"media_id": media_id}
    if not story:
        body.update(
            {
                "skip_save_to_profile": False,
                "description": description,
                "locale": locale,
            }
        )
    response = requests.post(
        f"{BUSINESS_API_BASE}/v1/public_profiles/{profile_id}/{endpoint}",
        headers={"Authorization": access_token, "Content-Type": "application/json"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    payload = expect_json_response(response, f"Post Snapchat {endpoint[:-1]}")
    snap_success(payload, f"Post Snapchat {endpoint[:-1]}")
    return str(payload.get("request_id") or media_id)


def main() -> None:
    args = parse_args()
    load_environment()
    env = require_env(
        "SNAPCHAT_CLIENT_ID",
        "SNAPCHAT_CLIENT_SECRET",
        "SNAPCHAT_REFRESH_TOKEN",
        "SNAPCHAT_PUBLIC_PROFILE_ID",
    )
    if args.check_auth:
        access_token = refresh_access_token(env)
        check_auth(env["SNAPCHAT_PUBLIC_PROFILE_ID"], access_token)
        return

    if not args.media:
        raise ScriptError("Snapchat needs --media.")
    if not args.story and not args.spotlight:
        raise ScriptError("Snapchat needs --story or --spotlight.")
    media_path = require_file(args.media, "Snapchat media")
    if media_path.suffix.lower() != ".mp4":
        raise ScriptError(
            "Snapchat Story and Spotlight posting currently require MP4 media."
        )
    if media_path.stat().st_size > MAX_SNAPCHAT_MEDIA_SIZE:
        raise ScriptError("Snapchat media uploads can be at most 1 GB.")
    if args.spotlight and not args.locale:
        raise ScriptError("Snapchat Spotlight posting requires --locale.")
    if args.description and len(args.description) > 160:
        raise ScriptError(
            "Snapchat Spotlight descriptions can be at most 160 characters."
        )
    part_count = (
        media_path.stat().st_size + MAX_SNAPCHAT_CHUNK_SIZE - 1
    ) // MAX_SNAPCHAT_CHUNK_SIZE
    if part_count > MAX_SNAPCHAT_PARTS:
        raise ScriptError("Snapchat multipart uploads support at most 35 parts.")
    if args.dry_run:
        print_dry_run(
            PLATFORM,
            [
                (
                    "Media request",
                    f"POST {BUSINESS_API_BASE}/v1/public_profiles/"
                    f"{env['SNAPCHAT_PUBLIC_PROFILE_ID']}/media",
                ),
                (
                    "Publish request",
                    f"POST {BUSINESS_API_BASE}/v1/public_profiles/"
                    f"{env['SNAPCHAT_PUBLIC_PROFILE_ID']}/"
                    f"{'stories' if args.story else 'spotlights'}",
                ),
                ("Public profile ID", env["SNAPCHAT_PUBLIC_PROFILE_ID"]),
                ("Destination", "Story" if args.story else "Spotlight"),
                ("Media", media_path),
                ("Media size", media_path.stat().st_size),
                ("Estimated upload parts", part_count),
                ("Description", args.description),
                ("Locale", args.locale),
            ],
        )
        return

    confirm_post(
        PLATFORM,
        [
            ("Public profile ID", env["SNAPCHAT_PUBLIC_PROFILE_ID"]),
            ("Destination", "Story" if args.story else "Spotlight"),
            ("Media", media_path),
            ("Description", args.description),
            ("Locale", args.locale),
        ],
        confirmed=args.confirmed,
    )

    access_token = refresh_access_token(env)
    encrypted_path, key, iv = encrypt_media(media_path)
    try:
        media_id, add_path, finalize_path = create_media_container(
            env["SNAPCHAT_PUBLIC_PROFILE_ID"], access_token, media_path, key, iv
        )
        upload_encrypted_media(access_token, encrypted_path, add_path, finalize_path)
        result_id = publish_media(
            env["SNAPCHAT_PUBLIC_PROFILE_ID"],
            access_token,
            media_id,
            story=args.story,
            description=args.description,
            locale=args.locale,
        )
    finally:
        encrypted_path.unlink(missing_ok=True)
    print(f"{PLATFORM}: posted {result_id}")


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
