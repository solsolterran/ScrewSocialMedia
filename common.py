import argparse
import json
import math
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
REQUEST_TIMEOUT = 30
SENSITIVE_KEY_PARTS = ("authorization", "password", "secret", "token")
SENSITIVE_QUERY_PARTS = SENSITIVE_KEY_PARTS + ("key", "code")
TEXT_TEMPLATES = {
    "new-video": "New video is live. Go watch it before the algorithm hides it in a ditch.",
}


class ScriptError(Exception):
    pass


class CanceledPost(Exception):
    pass


def load_environment() -> None:
    for env_path in (REPO_DIR / ".env", SCRIPT_DIR / ".env"):
        load_env_file(env_path)


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


def require_env(*names: str) -> dict[str, str]:
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise ScriptError(f"Missing env var(s): {', '.join(missing)}")
    return {name: os.environ[name] for name in names}


def add_text_arguments(
    parser: argparse.ArgumentParser, *, required: bool = False
) -> Any:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--text", help="Text to post.")
    group.add_argument("--text-key", help="Named text template from text_templates.py.")
    return group


def add_confirm_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--confirmed", action="store_true", help=argparse.SUPPRESS)


def add_no_post_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate local inputs and print the request plan without network calls.",
    )
    group.add_argument(
        "--check-auth",
        action="store_true",
        help="Check credentials with safe account/capability calls and do not post.",
    )


def resolve_text(text: str | None, text_key: str | None, *, required: bool) -> str:
    if text_key:
        try:
            text = get_template(text_key)
        except ValueError as exc:
            raise ScriptError(str(exc)) from exc
    if text is None:
        if required:
            raise ScriptError("Text is required. Pass --text or --text-key.")
        return ""
    text = text.strip()
    if required and not text:
        raise ScriptError("Text cannot be empty.")
    return text


def append_url(text: str, url: str | None) -> str:
    url = (url or "").strip()
    if not url:
        return text
    if not text:
        return url
    return f"{text.rstrip()} {url}"


def require_file(path_value: str, label: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_file():
        raise ScriptError(f"{label} does not exist or is not a file: {path}")
    return path


def confirm_post(
    platform: str, details: list[tuple[str, Any]], *, confirmed: bool = False
) -> None:
    if confirmed:
        return
    print("About to post:")
    print(f"- Platform: {platform}")
    for label, value in details:
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value)
        print(f"- {label}: {value}")
    try:
        answer = input("Post this? Type yes to continue: ").strip().lower()
    except EOFError as exc:
        raise ScriptError("Confirmation is required before posting.") from exc
    if answer != "yes":
        raise CanceledPost()


def print_dry_run(platform: str, details: list[tuple[str, Any]]) -> None:
    print(
        f"{platform}: dry run only. "
        "No network request was made and nothing was posted."
    )
    for label, value in details:
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value)
        print(f"- {label}: {value}")


def run_platform(platform: str, action) -> int:
    try:
        action()
        return 0
    except CanceledPost:
        print(f"{platform}: canceled.")
        return 0
    except ScriptError as exc:
        print(f"{platform}: failed: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(
            f"{platform}: failed: network request failed: {redact_text(str(exc))}",
            file=sys.stderr,
        )
        return 1


def response_json(response: requests.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ScriptError(
            f"{operation} returned non-JSON HTTP {response.status_code}: "
            f"{shorten(redact_text(response.text))}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScriptError(
            f"{operation} returned unexpected JSON: {describe_payload(payload)}"
        )
    return payload


def expect_json_response(response: requests.Response, operation: str) -> dict[str, Any]:
    payload = response_json(response, operation)
    if not 200 <= response.status_code < 300:
        raise ScriptError(
            f"{operation} failed with HTTP {response.status_code}: "
            f"{describe_payload(payload)}"
        )
    return payload


def describe_payload(payload: Any) -> str:
    redacted = redact_sensitive(payload)
    try:
        return shorten(json.dumps(redacted, sort_keys=True))
    except TypeError:
        return shorten(str(redacted))


def redact_text(text: str) -> str:
    redacted = text
    for part in SENSITIVE_QUERY_PARTS:
        redacted = re.sub(
            rf"(?i)([?&][^=\s&]*{re.escape(part)}[^=\s&]*=)[^&\s)]+",
            lambda match: f"{match.group(1)}<redacted>",
            redacted,
        )
    return redacted


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "<redacted>"
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def shorten(text: str, limit: int = 800) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def media_type_for_path(path: Path, fallback: str = "application/octet-stream") -> str:
    media_type, unused_encoding = mimetypes.guess_type(path.name)
    return media_type or fallback


def chunk_plan(file_size: int, max_chunk_size: int) -> tuple[int, int]:
    if file_size <= 0:
        raise ScriptError("Media file is empty.")
    if file_size <= max_chunk_size:
        return file_size, 1
    chunk_count = math.ceil(file_size / max_chunk_size)
    if chunk_count > 1000:
        raise ScriptError("Media file is too large for a 1000-part upload.")
    chunk_size = file_size // chunk_count
    return chunk_size, chunk_count


def get_template(key: str) -> str:
    try:
        return TEXT_TEMPLATES[key]
    except KeyError as exc:
        known = ", ".join(sorted(TEXT_TEMPLATES)) or "none"
        raise ValueError(f"Unknown text key '{key}'. Known keys: {known}") from exc
