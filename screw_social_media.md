# ScrewSocialMedia plan

API/access last checked on May 14, 2026.

This should post the thing without making anyone open the apps.

The tool should have one script per platform and one parent script that calls the selected platform scripts. Each platform script should still work by itself. It should validate the obvious stuff before posting, print the created post/video link or id, and exit non-zero when something fails.

It should not read feeds, notifications, analytics, replies, comments, timelines, follower counts, or anything else that turns "post this" into "check social media." That is the whole point.

Allowed reads are only the ones needed to finish the post:

- OAuth token refresh or session creation
- account/capability checks required before posting, like TikTok creator info or Meta Page setup
- upload, processing, or publish status for media the script just created
- permalink/id lookup for the object the script just created

No-post testing can also read the configured account/profile identity so credentials can be checked without publishing anything. Those reads must use explicit ids from credentials, setup output, or the just-created post. They must not enumerate timelines, inboxes, comments, replies, analytics, followers, or feeds.

The examples assume you are running commands from the `ScrewSocialMedia/` directory:

```bash
python ...
```

If this folder is copied into another repo, use that repo's Python environment.

Keep credentials and machine-specific paths in env. Keep stable captions, API paths, app names, and other normal constants in code.

## Build Scope

Build every platform script:

- Twitter
- Reddit
- YouTube
- Bluesky
- Facebook
- Instagram
- Snapchat
- TikTok

Some platforms can be tested with normal OAuth credentials. Bluesky, Facebook, Instagram, Snapchat, and TikTok may need extra account status, app approval, or allowlisting. They should validate inputs and credentials, build the real request bodies, make the documented API calls, and return clear success/failure output. Treat any script as unproven until it is tested with a real account that has the needed access.

## Files

Script set:

```text
ScrewSocialMedia/
  post.py
  twitter_post.py
  reddit_post.py
  youtube_post.py
  bluesky_post.py
  facebook_post.py
  instagram_post.py
  snapchat_post.py
  tiktok_post.py
  text_templates.py
  common.py
  requirements.txt
```

Do not add a shared framework just because it feels tidy. If the platform files start repeating real token or request handling, then add a small helper.

Use the standard library plus `requests`, which is already in the repo requirements. Do not add a CLI framework. Snapchat media encryption needs AES-256-CBC, so `cryptography` belongs in `ScrewSocialMedia/requirements.txt` and is only imported by the Snapchat script.

Each platform script should start with a short comment header. It should say:

- what the script can post
- what credentials/env vars it needs
- where to get those credentials
- any platform gotchas that matter before running it

Keep it useful, not fancy. The point is that opening `twitter_post.py` or `reddit_post.py` should immediately show what is needed before the script can work.

Example shape:

```python
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
```

## Commands

Standalone scripts:

```bash
python twitter_post.py \
  --text "New video is live." \
  --url "https://example.com/video"

python reddit_post.py \
  --title "New video is live" \
  --subreddit "test" \
  --url "https://example.com/video"

python youtube_post.py \
  --title "New clip is up" \
  --description "New upload from an independent creator." \
  --media "./clip.mp4"
```

Parent script:

```bash
python post.py \
  --x \
  --reddit \
  --youtube \
  --text-key new-video \
  --url "https://example.com/video" \
  --reddit-title "New video is live" \
  --subreddit "test" \
  --media "./clip.mp4"
```

Other platform scripts:

```bash
python bluesky_post.py \
  --text-key new-video \
  --url "https://example.com/video"

python facebook_post.py \
  --text "New video is live." \
  --url "https://example.com/video"

python instagram_post.py \
  --text "New clip is up." \
  --image-url "https://example.com/clip-cover.jpg"

python instagram_post.py \
  --text "New reel is up." \
  --reel-url "https://example.com/clip.mp4"

python snapchat_post.py \
  --spotlight \
  --description "New clip is up #creator" \
  --locale "en_US" \
  --media "./clip.mp4"

python tiktok_post.py \
  --title "New clip is up #creator #video" \
  --media "./clip.mp4"
```

Basic rules:

- `--text` and `--text-key` are mutually exclusive.
- `--dry-run` validates local inputs and env vars without network calls.
- `--check-auth` only does safe account/capability checks and must not call publish/upload/submit/post endpoints.
- Unknown text keys fail before anything posts.
- The parent script resolves `--text-key` once before calling any platform.
- The parent script fails if no platform is selected.
- The parent script should try every requested platform after shared input validation passes, then exit non-zero if any requested platform fails.
- Twitter needs text. `--url` gets appended when present.
- Reddit needs a title and at least one subreddit. `--subreddit` may be repeated.
- Reddit uses a link post when `--url` exists, otherwise a self post.
- YouTube needs a title and media file.
- Bluesky needs text. `--url` gets appended when present.
- Facebook needs text, a URL, or an image URL.
- Instagram is not text-only. It needs exactly one media input at first: `--image-url` or `--reel-url`.
- Snapchat is not a normal personal account poster. It needs API-approved Public Profile access and local media. Exactly one of `--story` or `--spotlight` is required, and Spotlight needs a locale.
- TikTok should query creator info before post init and use `PUBLIC_TO_EVERYONE` only when the API says that privacy level is available. If public posting is not available, fail before uploading.
- Missing credentials should only fail the platform that needs them.
- Print one success or failure line per platform. Do not print tokens, app passwords, client secrets, or raw credential files.
- Upon verification of information, display everything (Video, text, platform, etc.) to the user and ask if they are sure they want to post.

## Text Keys

Put repeated captions in `text_templates.py`. Start with:

```text
new-video
```

The captions should be normal creator copy. If a template needs a URL, append the URL in the script instead of baking a deployment-specific link into the template.

## Twitter

First version: create a text/link post with `POST /2/tweets`.

Env:

```text
X_USER_ACCESS_TOKEN
X_USER_ACCESS_TOKEN_SECRET
X_CONSUMER_KEY
X_CONSUMER_KEY_SECRET
```

Example:

```bash
Use OAuth 1.0a user-context signing with `X_CONSUMER_KEY`, `X_CONSUMER_KEY_SECRET`, `X_USER_ACCESS_TOKEN`, and `X_USER_ACCESS_TOKEN_SECRET`.
```

Return a post URL when the API gives back an id. Twitter posting is pay-per-use, and URL posts may be priced differently than plain text posts, so check the developer console before doing anything more expensive like media upload.

Do not implement Twitter media upload in the first pass.

Sources:

- https://docs.x.com/x-api/posts/manage-tweets/quickstart
- https://docs.x.com/x-api/getting-started/pricing

## Bluesky

First version: create a session, then create an `app.bsky.feed.post` record.

Env:

```text
BLUESKY_HANDLE
BLUESKY_APP_PASSWORD
```

Session example:

```bash
curl -X POST "https://bsky.social/xrpc/com.atproto.server.createSession" \
  -H "Content-Type: application/json" \
  -d '{
    "identifier": "{BLUESKY_HANDLE}",
    "password": "{BLUESKY_APP_PASSWORD}"
  }'
```

Post example:

```bash
curl -X POST "https://bsky.social/xrpc/com.atproto.repo.createRecord" \
  -H "Authorization: Bearer {BLUESKY_ACCESS_JWT}" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "{BLUESKY_DID}",
    "collection": "app.bsky.feed.post",
    "record": {
      "$type": "app.bsky.feed.post",
      "text": "New video is live.",
      "createdAt": "{CREATED_AT_ISO_UTC}"
    }
  }'
```

If the post includes a URL, add an `app.bsky.richtext.facet#link` facet for the URL span so Bluesky treats it like a link.

Facet indexes are UTF-8 byte offsets, not Python character indexes.

Sources:

- https://docs.bsky.app/blog/create-post
- https://docs.bsky.app/docs/api/com-atproto-repo-create-record

## Reddit

First version: refresh/obtain a user token and submit one post per subreddit.

Env:

```text
REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET
REDDIT_REFRESH_TOKEN
REDDIT_USERNAME
```

Stable user agent:

```text
linux:screw-social-media:v0.1.0 (by /u/<REDDIT_USERNAME>)
```

Token refresh example:

```bash
curl -X POST "https://www.reddit.com/api/v1/access_token" \
  -u "{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SECRET}" \
  -H "User-Agent: linux:screw-social-media:v0.1.0 (by /u/{REDDIT_USERNAME})" \
  --data-urlencode "grant_type=refresh_token" \
  --data-urlencode "refresh_token={REDDIT_REFRESH_TOKEN}"
```

Link post example:

```bash
curl -X POST "https://oauth.reddit.com/api/submit" \
  -H "Authorization: Bearer {REDDIT_USER_ACCESS_TOKEN}" \
  -H "User-Agent: linux:screw-social-media:v0.1.0 (by /u/{REDDIT_USERNAME})" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "api_type=json" \
  --data-urlencode "kind=link" \
  --data-urlencode "sr=test" \
  --data-urlencode "title=New video is live" \
  --data-urlencode "url=https://example.com/video"
```

Self post example:

```bash
curl -X POST "https://oauth.reddit.com/api/submit" \
  -H "Authorization: Bearer {REDDIT_USER_ACCESS_TOKEN}" \
  -H "User-Agent: linux:screw-social-media:v0.1.0 (by /u/{REDDIT_USERNAME})" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "api_type=json" \
  --data-urlencode "kind=self" \
  --data-urlencode "sr=test" \
  --data-urlencode "title=New video is live" \
  --data-urlencode "text=New upload is live: https://example.com/video"
```

If one subreddit fails, keep going through the explicitly requested subreddits and exit non-zero at the end. Reddit moderation is the real risk here. Many subreddits have karma, flair, account-age, or self-promo rules.

Reddit titles can be at most 300 characters, so fail before OAuth/posting if the title is longer than that.

Do not try to fetch subreddit rules or flair requirements in the first pass. If the API rejects a post because a subreddit needs something extra, print Reddit's error for that subreddit and keep going.

Sources:

- https://www.reddit.com/dev/api/
- https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki
- https://redditinc.com/policies/data-api-terms

## Facebook And Instagram

Facebook and Instagram both use Meta Graph API. Use one Graph API version as a code constant, not an env var. In these examples, replace `{GRAPH_API_VERSION}` with the supported version chosen during implementation.

Setup starts by using a User Access Token to find the managed Pages, Page token, and linked Instagram professional account id:

```bash
curl -G "https://graph.facebook.com/{GRAPH_API_VERSION}/me/accounts" \
  --data-urlencode "fields=name,access_token,tasks,instagram_business_account" \
  --data-urlencode "access_token={META_USER_ACCESS_TOKEN}"
```

Normal posting should use the Page access token, not require the setup User Access Token every time.

Env:

```text
META_PAGE_ACCESS_TOKEN
FACEBOOK_PAGE_ID
INSTAGRAM_USER_ID
```

The setup token needs permission to list managed Pages and linked Instagram accounts. The saved Page token needs permission to create Page content, and Instagram publishing also needs `instagram_content_publish` with the linked professional account. Do not save the setup User Access Token in env after copying the Page token and ids.

### Facebook

Useful first Facebook support: Page text/link posts and hosted photo posts.

Text/link post:

```bash
curl -X POST "https://graph.facebook.com/{GRAPH_API_VERSION}/{FACEBOOK_PAGE_ID}/feed" \
  --data-urlencode "message=New video is live." \
  --data-urlencode "link=https://example.com/video" \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

Hosted photo post:

```bash
curl -X POST "https://graph.facebook.com/{GRAPH_API_VERSION}/{FACEBOOK_PAGE_ID}/photos" \
  --data-urlencode "url=https://example.com/image.jpg" \
  --data-urlencode "caption=New clip is up." \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

If Facebook only gives back a post id, fetch the permalink:

```bash
curl -G "https://graph.facebook.com/{GRAPH_API_VERSION}/{FACEBOOK_POST_ID}" \
  --data-urlencode "fields=permalink_url" \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

Facebook Reels are not in the first version. If they get added, use the Page Reels upload session flow: start upload, upload to the returned URL, then finish/publish.

Sources:

- https://www.postman.com/meta
- https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api
- https://developers.facebook.com/docs/pages-api/posts/
- https://developers.facebook.com/docs/graph-api/reference/page/feed/#publish
- https://developers.facebook.com/docs/graph-api/reference/page/photos/#Creating

### Instagram

Instagram is media-first. There is no plain text/link post for this tool.

Useful first Instagram support: one hosted image post and one hosted Reel post. The account must be an Instagram professional account linked to a Facebook Page, and the token needs `instagram_content_publish`.

Only hosted media URLs are supported in the first pass. Local image or local Reel upload for Instagram is out of scope until the hosted URL path works.

Image container:

```bash
curl -X POST "https://graph.facebook.com/{GRAPH_API_VERSION}/{INSTAGRAM_USER_ID}/media" \
  --data-urlencode "image_url=https://example.com/image.jpg" \
  --data-urlencode "caption=New clip is up." \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

Publish the returned container:

```bash
curl -X POST "https://graph.facebook.com/{GRAPH_API_VERSION}/{INSTAGRAM_USER_ID}/media_publish" \
  --data-urlencode "creation_id={IG_CONTAINER_ID}" \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

Get the permalink when Meta only returns a media id:

```bash
curl -G "https://graph.facebook.com/{GRAPH_API_VERSION}/{IG_MEDIA_ID}" \
  --data-urlencode "fields=permalink" \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

Reel container:

```bash
curl -X POST "https://graph.facebook.com/{GRAPH_API_VERSION}/{INSTAGRAM_USER_ID}/media" \
  --data-urlencode "media_type=REELS" \
  --data-urlencode "video_url=https://example.com/reel.mp4" \
  --data-urlencode "caption=New reel is up." \
  --data-urlencode "share_to_feed=true" \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

Poll the container:

```bash
curl -G "https://graph.facebook.com/{GRAPH_API_VERSION}/{IG_CONTAINER_ID}" \
  --data-urlencode "fields=status_code,status" \
  --data-urlencode "access_token={META_PAGE_ACCESS_TOKEN}"
```

Publish with `media_publish` once `status_code` is `FINISHED`. If the container says `ERROR` or `EXPIRED`, do not publish it.

Use a small fixed poll count. If processing does not finish, print the container id and exit non-zero instead of waiting forever.

Sources:

- https://www.postman.com/meta
- https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
- https://developers.facebook.com/docs/instagram-platform/content-publishing/
- https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media

## Snapchat

Snapchat should be built as a best-effort script. It can post content through the Public Profile API, but that is not the same as posting from a normal personal account. It requires a Snapchat Public Profile, a Snap business setup, an OAuth app created through Ads Manager/Business Dashboard, and allowlist access from Snap.

Creative Kit does not fit this CLI. It can send images, videos, links, and captions into Snapchat's preview screen, but the user still finishes the post inside Snapchat.

Live posting needs:

- a Snapchat account with a Public Profile
- a Snap business account
- an OAuth app created through Ads Manager/Business Dashboard, not the normal Developer Portal
- a redirect URI for OAuth
- Public Profile API allowlisting for the OAuth client id
- a user access token with the `snapchat-profile-api` scope
- the public profile id
- media encryption, media creation, multipart upload, and finalize handling

Env:

```text
SNAPCHAT_CLIENT_ID
SNAPCHAT_CLIENT_SECRET
SNAPCHAT_REFRESH_TOKEN
SNAPCHAT_PUBLIC_PROFILE_ID
```

The script should refresh the access token from `SNAPCHAT_REFRESH_TOKEN` before posting.

The upload flow is heavier than the other platforms. Snapchat wants the media encrypted first, then a media container created, then the encrypted file uploaded with multipart upload, then finalized. The returned `media_id` is what gets posted.

Encrypt with AES-256-CBC using a random 32-byte key and 16-byte IV, base64 encode the key and IV for the media container request, and upload the encrypted file in chunks up to 32 MB.

Create media container:

```bash
curl -X POST "https://businessapi.snapchat.com/v1/public_profiles/{SNAPCHAT_PUBLIC_PROFILE_ID}/media" \
  -H "Authorization: {SNAPCHAT_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "VIDEO",
    "name": "new-clip",
    "key": "{BASE64_ENCRYPTION_KEY}",
    "iv": "{BASE64_ENCRYPTION_IV}"
  }'
```

After uploading and finalizing the encrypted media through the returned upload paths, post it as a Story:

```bash
curl -X POST "https://businessapi.snapchat.com/v1/public_profiles/{SNAPCHAT_PUBLIC_PROFILE_ID}/stories" \
  -H "Authorization: {SNAPCHAT_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"media_id": "{SNAPCHAT_MEDIA_ID}"}'
```

Or post it as a Spotlight:

```bash
curl -X POST "https://businessapi.snapchat.com/v1/public_profiles/{SNAPCHAT_PUBLIC_PROFILE_ID}/spotlights" \
  -H "Authorization: {SNAPCHAT_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "media_id": "{SNAPCHAT_MEDIA_ID}",
    "skip_save_to_profile": false,
    "description": "New clip is up #creator",
    "locale": "en_US"
  }'
```

Story and Spotlight videos must be MP4, 5-300 seconds long, and at least 540x960. Spotlight descriptions can be up to 160 characters.

Media uploads can be at most 1 GB, and the encrypted multipart upload should not exceed 35 parts.

Snapchat Marketing API rate limits are 20 requests per second at the app level and 10 requests per second per access token. That is enough for low-volume posting, but the script should still treat HTTP 429 as a failed post and print a clear message.

Sources:

- https://developers.snap.com/api/marketing-api/Public-Profile-API/Introduction
- https://developers.snap.com/api/marketing-api/Public-Profile-API/GetStarted
- https://developers.snap.com/api/marketing-api/Public-Profile-API/ProfileAssetManagement
- https://developers.snap.com/snap-kit/creative-kit/overview
- https://developers.snap.com/api/marketing-api/Ads-API/rate-limits

## YouTube

YouTube upload support belongs in the script set. Before trusting it, confirm the API project can publish the way the tool needs. Unverified projects can get stuck with private uploads.

Env:

```text
YOUTUBE_CLIENT_SECRETS_FILE
YOUTUBE_TOKEN_FILE
```

Upload starts with a resumable upload session:

```http
POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status
Authorization: Bearer {YOUTUBE_USER_ACCESS_TOKEN}
Content-Type: application/json

{
  "snippet": {
    "title": "New video is live",
    "description": "New upload from an independent creator.",
    "categoryId": "20"
  },
  "status": {
    "privacyStatus": "public",
    "containsSyntheticMedia": true
  }
}
```

Then upload the file bytes to the resumable upload URL from the response. The init request should send `X-Upload-Content-Length` and `X-Upload-Content-Type` for the local media file before uploading the bytes to the returned URL.

YouTube uses quota units instead of direct per-call dollars; `videos.insert` is the important cost to check.

YouTube currently documents `videos.insert` as 100 quota units, and unverified API projects created after July 28, 2020 can be restricted to private uploads. Check the API project before trusting public posting.

Sources:

- https://developers.google.com/youtube/v3/getting-started
- https://developers.google.com/youtube/v3/docs/videos/insert
- https://developers.google.com/youtube/v3/guides/uploading_a_video

## TikTok

TikTok should be built as a best-effort script. Login and content posting look free as far as public docs show, but the API is rate limited and public posting needs app approval. Build the script from the docs, but treat live posting as unproven until the OAuth/review setup exists.

Live posting needs:

- a TikTok developer app
- a public redirect URL, privacy policy, and terms page for OAuth/review
- the app is approved for public direct posting
- the user granted `video.publish`
- OAuth access and refresh token handling
- `FILE_UPLOAD` support for MP4, MOV/QuickTime, or WebM media, unless hosting-domain support gets added for `PULL_FROM_URL`
- creator info lookup before upload so the script knows the account's allowed privacy options
- retry/rate-limit handling; TikTok says the direct post init endpoint is limited to 6 requests per minute per user access token

Env:

```text
TIKTOK_CLIENT_KEY
TIKTOK_CLIENT_SECRET
TIKTOK_REFRESH_TOKEN
```

The script should refresh the user access token from `TIKTOK_REFRESH_TOKEN` before posting.

Before calling direct post init, call TikTok creator info for the authenticated user. That gives the allowed `privacy_level_options`; use `PUBLIC_TO_EVERYONE` only if it is returned. If the app is unaudited or the account cannot post publicly, fail before uploading and say which privacy levels were returned.

TikTok captions can be at most 2200 UTF-16 units.

Sample direct post init call using `FILE_UPLOAD`:

```bash
curl --location "https://open.tiktokapis.com/v2/post/publish/video/init/" \
  --header "Authorization: Bearer {TIKTOK_USER_ACCESS_TOKEN}" \
  --header "Content-Type: application/json; charset=UTF-8" \
  --data-raw '{
    "post_info": {
      "title": "New clip is up #creator #video",
      "privacy_level": "PUBLIC_TO_EVERYONE",
      "disable_duet": false,
      "disable_comment": false,
      "disable_stitch": false,
      "video_cover_timestamp_ms": 1000,
      "is_aigc": true
    },
    "source_info": {
      "source": "FILE_UPLOAD",
      "video_size": 50000123,
      "chunk_size": 10000000,
      "total_chunk_count": 5
    }
  }'
```

That returns a `publish_id` and an `upload_url`. The video bytes get uploaded to that `upload_url`, then the post status can be checked with TikTok's status endpoint.

After upload, check the TikTok status endpoint for the returned `publish_id`. If it returns `FAILED`, fail the command. If it returns `PUBLISH_COMPLETE`, print the publish id and any post ids returned. If it is still processing after a small fixed wait, print the publish id and current status instead of pretending the post is already visible.

For `FILE_UPLOAD`, choose `chunk_size` so `total_chunk_count` matches TikTok's floor division rule. The last chunk can absorb the remainder, but the announced chunk count must match the API docs or init/upload may fail.

Source:

- https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
- https://developers.tiktok.com/doc/tiktok-api-v2-rate-limit/

## Before Calling It Done

For docs-only changes:

```bash
git diff -- ScrewSocialMedia/README.md ScrewSocialMedia/screw_social_media.md ScrewSocialMedia/.env.example
```

Once code exists:

```bash
python -m py_compile \
  post.py \
  twitter_post.py \
  reddit_post.py \
  youtube_post.py \
  bluesky_post.py \
  facebook_post.py \
  instagram_post.py \
  snapchat_post.py \
  tiktok_post.py \
  text_templates.py \
  common.py

python post.py --help
python twitter_post.py --help
python reddit_post.py --help
python youtube_post.py --help
python bluesky_post.py --help
python facebook_post.py --help
python instagram_post.py --help
python snapchat_post.py --help
python tiktok_post.py --help
```

Before trusting live posting, make one low-risk post per implemented platform and confirm the printed link/id points to the created post. Also confirm none of the commands read feeds, notifications, analytics, comments, replies, or timelines.

This tool is not wired into Discord, Twitch, OBS, Unity, TTS, Qdrant, or the Web UI, so those do not need live checks for this work.
