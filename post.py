import argparse
import subprocess
import sys

from common import (
    SCRIPT_DIR,
    ScriptError,
    add_no_post_arguments,
    add_text_arguments,
    append_url,
    confirm_post,
    load_environment,
    resolve_text,
    run_platform,
)

# Parent posting script.
#
# Can do:
# - asks for one confirmation, then calls the selected platform scripts
#
# Needs:
# - whichever credentials are required by the requested platform scripts
#
# Notes:
# - Missing platform credentials fail only that platform.
# - The parent does not read feeds, notifications, analytics, replies, or timelines.

PLATFORM = "ScrewSocialMedia"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post to selected social platforms.")
    platform_group = parser.add_argument_group("platforms")
    platform_group.add_argument("--x", action="store_true", help="Post to Twitter.")
    platform_group.add_argument("--reddit", action="store_true", help="Post to Reddit.")
    platform_group.add_argument(
        "--youtube", action="store_true", help="Upload to YouTube."
    )
    platform_group.add_argument(
        "--bluesky", action="store_true", help="Post to Bluesky."
    )
    platform_group.add_argument(
        "--facebook", action="store_true", help="Post to Facebook."
    )
    platform_group.add_argument(
        "--instagram", action="store_true", help="Post to Instagram."
    )
    platform_group.add_argument(
        "--snapchat", action="store_true", help="Post to Snapchat."
    )
    platform_group.add_argument("--tiktok", action="store_true", help="Post to TikTok.")

    add_text_arguments(parser, required=False)
    parser.add_argument("--url", help="Shared URL for platforms that accept links.")
    parser.add_argument("--media", help="Shared local media path for video platforms.")

    reddit_group = parser.add_argument_group("reddit")
    reddit_group.add_argument("--reddit-title", help="Reddit post title.")
    reddit_group.add_argument(
        "--subreddit", action="append", help="Subreddit name. May be repeated."
    )

    youtube_group = parser.add_argument_group("youtube")
    youtube_group.add_argument("--youtube-title", help="YouTube title.")
    youtube_group.add_argument("--youtube-description", help="YouTube description.")

    facebook_group = parser.add_argument_group("facebook")
    facebook_group.add_argument(
        "--facebook-image-url", help="Hosted Facebook image URL."
    )

    instagram_group = parser.add_argument_group("instagram")
    instagram_media_group = instagram_group.add_mutually_exclusive_group()
    instagram_media_group.add_argument(
        "--instagram-image-url", help="Hosted Instagram image URL."
    )
    instagram_media_group.add_argument(
        "--instagram-reel-url", help="Hosted Instagram Reel URL."
    )

    snapchat_group = parser.add_argument_group("snapchat")
    snapchat_destination = snapchat_group.add_mutually_exclusive_group()
    snapchat_destination.add_argument("--snapchat-story", action="store_true")
    snapchat_destination.add_argument("--snapchat-spotlight", action="store_true")
    snapchat_group.add_argument(
        "--snapchat-description", help="Snapchat Spotlight description."
    )
    snapchat_group.add_argument("--snapchat-locale", help="Snapchat Spotlight locale.")

    tiktok_group = parser.add_argument_group("tiktok")
    tiktok_group.add_argument("--tiktok-title", help="TikTok title/caption.")
    add_no_post_arguments(parser)
    return parser.parse_args()


def selected_platforms(args: argparse.Namespace) -> list[str]:
    selected: list[str] = []
    for flag, label in [
        ("x", "Twitter"),
        ("reddit", "Reddit"),
        ("youtube", "YouTube"),
        ("bluesky", "Bluesky"),
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("snapchat", "Snapchat"),
        ("tiktok", "TikTok"),
    ]:
        if getattr(args, flag):
            selected.append(label)
    if not selected:
        raise ScriptError("Select at least one platform.")
    return selected


def build_commands(args: argparse.Namespace, text: str) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []

    if args.x:
        if not text:
            raise ScriptError("Twitter needs --text or --text-key.")
        command = [
            sys.executable,
            str(SCRIPT_DIR / "twitter_post.py"),
            "--text",
            text,
        ]
        if args.url:
            command.extend(["--url", args.url])
        add_child_mode(command, args)
        commands.append(("Twitter", command))

    if args.reddit:
        if not args.reddit_title:
            raise ScriptError("Reddit needs --reddit-title.")
        if not args.subreddit:
            raise ScriptError("Reddit needs at least one --subreddit.")
        if not args.url and not text:
            raise ScriptError("Reddit self posts need --text or --text-key.")
        command = [
            sys.executable,
            str(SCRIPT_DIR / "reddit_post.py"),
            "--title",
            args.reddit_title,
        ]
        for subreddit in args.subreddit:
            command.extend(["--subreddit", subreddit])
        if args.url:
            command.extend(["--url", args.url])
        elif text:
            command.extend(["--text", text])
        add_child_mode(command, args)
        commands.append(("Reddit", command))

    if args.youtube:
        youtube_title = args.youtube_title or args.reddit_title or text
        if not youtube_title:
            raise ScriptError("YouTube needs --youtube-title, --reddit-title, or text.")
        if not args.media:
            raise ScriptError("YouTube needs --media.")
        youtube_description = args.youtube_description
        if youtube_description is None:
            youtube_description = append_url(text, args.url)
        command = [
            sys.executable,
            str(SCRIPT_DIR / "youtube_post.py"),
            "--title",
            youtube_title,
            "--description",
            youtube_description,
            "--media",
            args.media,
        ]
        add_child_mode(command, args)
        commands.append(("YouTube", command))

    if args.bluesky:
        if not text:
            raise ScriptError("Bluesky needs --text or --text-key.")
        command = [
            sys.executable,
            str(SCRIPT_DIR / "bluesky_post.py"),
            "--text",
            text,
        ]
        if args.url:
            command.extend(["--url", args.url])
        add_child_mode(command, args)
        commands.append(("Bluesky", command))

    if args.facebook:
        if not text and not args.url and not args.facebook_image_url:
            raise ScriptError("Facebook needs text, --url, or --facebook-image-url.")
        command = [sys.executable, str(SCRIPT_DIR / "facebook_post.py")]
        if text:
            command.extend(["--text", text])
        if args.url:
            command.extend(["--url", args.url])
        if args.facebook_image_url:
            command.extend(["--image-url", args.facebook_image_url])
        add_child_mode(command, args)
        commands.append(("Facebook", command))

    if args.instagram:
        if not args.instagram_image_url and not args.instagram_reel_url:
            raise ScriptError(
                "Instagram needs --instagram-image-url or --instagram-reel-url."
            )
        command = [sys.executable, str(SCRIPT_DIR / "instagram_post.py")]
        instagram_caption = append_url(text, args.url) if args.url else text
        if instagram_caption:
            command.extend(["--text", instagram_caption])
        if args.instagram_image_url:
            command.extend(["--image-url", args.instagram_image_url])
        if args.instagram_reel_url:
            command.extend(["--reel-url", args.instagram_reel_url])
        add_child_mode(command, args)
        commands.append(("Instagram", command))

    if args.snapchat:
        if not args.media:
            raise ScriptError("Snapchat needs --media.")
        if not args.snapchat_story and not args.snapchat_spotlight:
            raise ScriptError(
                "Snapchat needs --snapchat-story or --snapchat-spotlight."
            )
        description = args.snapchat_description or text
        if args.snapchat_spotlight and not args.snapchat_locale:
            raise ScriptError("Snapchat Spotlight needs --snapchat-locale.")
        command = [
            sys.executable,
            str(SCRIPT_DIR / "snapchat_post.py"),
            "--media",
            args.media,
        ]
        command.append("--story" if args.snapchat_story else "--spotlight")
        if description:
            command.extend(["--description", description])
        if args.snapchat_locale:
            command.extend(["--locale", args.snapchat_locale])
        add_child_mode(command, args)
        commands.append(("Snapchat", command))

    if args.tiktok:
        title = args.tiktok_title or text
        if not title:
            raise ScriptError("TikTok needs --tiktok-title or text.")
        if not args.media:
            raise ScriptError("TikTok needs --media.")
        command = [
            sys.executable,
            str(SCRIPT_DIR / "tiktok_post.py"),
            "--title",
            title,
            "--media",
            args.media,
        ]
        add_child_mode(command, args)
        commands.append(("TikTok", command))

    return commands


def add_child_mode(command: list[str], args: argparse.Namespace) -> None:
    command.append("--dry-run" if args.dry_run else "--confirmed")


def build_auth_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    for flag, label, script in [
        ("x", "Twitter", "twitter_post.py"),
        ("reddit", "Reddit", "reddit_post.py"),
        ("youtube", "YouTube", "youtube_post.py"),
        ("bluesky", "Bluesky", "bluesky_post.py"),
        ("facebook", "Facebook", "facebook_post.py"),
        ("instagram", "Instagram", "instagram_post.py"),
        ("snapchat", "Snapchat", "snapchat_post.py"),
        ("tiktok", "TikTok", "tiktok_post.py"),
    ]:
        if getattr(args, flag):
            commands.append(
                (
                    label,
                    [sys.executable, str(SCRIPT_DIR / script), "--check-auth"],
                )
            )
    return commands


def run_commands(commands: list[tuple[str, list[str]]]) -> None:
    failed = 0
    for platform, command in commands:
        result = subprocess.run(command, cwd=SCRIPT_DIR)
        if result.returncode != 0:
            failed += 1
            print(
                f"{platform}: command exited with {result.returncode}", file=sys.stderr
            )
    if failed:
        raise ScriptError(f"{failed} requested platform command(s) failed.")


def main() -> None:
    args = parse_args()
    load_environment()
    platforms = selected_platforms(args)
    if args.check_auth:
        run_commands(build_auth_commands(args))
        return

    text = resolve_text(args.text, args.text_key, required=False)
    commands = build_commands(args, text)

    if not args.dry_run:
        confirm_post(
            PLATFORM,
            [
                ("Platforms", platforms),
                ("Text", text),
                ("URL", args.url),
                ("Media", args.media),
                ("Reddit title", args.reddit_title),
                ("Subreddits", args.subreddit),
                ("YouTube title", args.youtube_title),
                ("Facebook image URL", args.facebook_image_url),
                ("Instagram image URL", args.instagram_image_url),
                ("Instagram Reel URL", args.instagram_reel_url),
                (
                    "Snapchat destination",
                    (
                        "Story"
                        if args.snapchat_story
                        else "Spotlight" if args.snapchat_spotlight else None
                    ),
                ),
                ("Snapchat locale", args.snapchat_locale),
                ("TikTok title", args.tiktok_title),
            ],
        )

    run_commands(commands)


if __name__ == "__main__":
    raise SystemExit(run_platform(PLATFORM, main))
