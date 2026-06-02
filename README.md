# ScrewSocialMedia

`ScrewSocialMedia` is for creators who know social media matters, but also know it's toxic, addictive, and generally terrible for the brain.

I'm not pretending social media is useless. If you make videos, music, art, games, streams, writing, or basically anything online, you probably need to post somewhere. People still need to find your work.

The point is to keep "post this update" from turning into opening five apps, checking notifications, obsessing over metrics, doom scrolling getting annoyed by ragebait, and somehow losing an hour to websites you did not even want to visit.

This repo is meant to upload to most of the major social medias. Some platforms can be tested with normal OAuth credentials. Others need app review, allowlisting, business setup, or custom OAuth URLs. I'll write down the process, but I won't be doing it myself. Only the guide.

## The Idea

A creator can post videos, clips, announcements, links, or updates to Twitter, Bluesky, Reddit, Facebook, Instagram, Snapchat, TikTok, YouTube, or whatever.

Each social media platform has its own script. It takes the info it needs, fails if something important is missing, and print the post/video link when it works.

## Why?

Because I care about my mental health.

## Cost Notes

- Twitter: paid per request. URL posts currently cost more than plain text posts.
- Bluesky: no per-post fee found. Rate limits are the thing to watch.
- Reddit: free for eligible low-volume OAuth use, with rate limits.
- Facebook/Instagram: no per-post fee found. App review, tokens, and rate limits are the annoying part.
- Snapchat: no per-post fee found. Direct posting needs allowlisted Public Profile API access and has rate limits.
- YouTube: quota units, not dollars. Uploads are cheap at low volume.
- TikTok: login/posting looks free as far as public docs show, but it is rate limited and public posting needs approval.

## Current Status

Right now this is a standalone tool in this folder. Twitter/X has been auth-checked without posting. Reddit, Twitter/X, and YouTube are the only platforms I can realistically prove with accounts I have once the needed tokens exist. The rest have scripts built but they are my best attempt.

## Structure

The shape is simple:

- one Python script per platform
- one parent script for posting to a few places at once
- env vars only for credentials, tokens, usernames, and local credential file paths

Each platform script has a comment header explaining what it can post, what credentials it needs, and where to get those credentials.

Each platform script owns its own auth, request body, response parsing, and anything platform specific.

The platform scripts work independently. Sometimes you only want to post to X, or only want to submit one Reddit link, and that should not require going through the parent script.

```bash
python twitter_post.py \
  --text "New clip is up."

python reddit_post.py \
  --title "New video is live" \
  --subreddit "test" \
  --url "https://example.com/video"

python youtube_post.py \
  --title "New clip is up" \
  --description "New upload from an independent creator." \
  --media "./clip.mp4"
```

The parent script takes flags for where the post should go:

```bash
python post.py \
  --x \
  --reddit \
  --youtube \
  --text "New video is live. Go watch it before the algorithm hides it in a ditch." \
  --url "https://example.com/video" \
  --reddit-title "New video is live" \
  --subreddit "test" \
  --media "./clip.mp4"
```

For repeated posts, it also supports text keys:

```bash
python post.py \
  --x \
  --reddit \
  --text-key new-video \
  --url "https://example.com/video" \
  --reddit-title "New video is live" \
  --subreddit "test"
```

That way common captions and announcements can live in code instead of getting typed out manually every time.

API keys and access tokens still need to exist somewhere because social platforms make sure nothing is ever painless, but the goal is not to add random configuration for things that can be hard-coded or derived.

The current script set covers:

- Twitter
- Bluesky
- Reddit
- Facebook
- Instagram
- Snapchat
- YouTube
- TikTok
