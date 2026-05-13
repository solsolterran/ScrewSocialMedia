# ScrewSocialMedia

Run the script. Post the thing. Keep your soul.

`ScrewSocialMedia` is for creators who know social media matters, but also know it's toxic, addictive, and generally terrible for the brain.

I'm not pretending social media is useless. If you make videos, music, art, games, streams, writing, or basically anything online, you probably need to post somewhere. People need to find your work. Growth matters. Distribution matters.

I just don't want "I should post this update" to turn into opening five apps, checking notifications, obsessing over metrics of how well a video or post did, scrolling garbage, comparing myself to strangers, getting annoyed by ragebait, and somehow losing an hour to websites I didn't even want to visit.

This repo will provide the means for people to upload what they need for most of the major social medias. I only have Twitter, Reddit, and YouTube API keys so those are all I can test with. The rest are going to be my best efforts to at least provide a blueprint for people who may want to utilize it. Some like TikTok require an app registration with custom URL's and stuff. I'll note down the process but won't be doing it myself. Only providing the guide.

## The Idea

If a creator needs to post videos, clips, announcements, links, or updates to X/Twitter, Bluesky, Reddit, Facebook, Instagram, Snapchat, TikTok, YouTube, or whatever platform becomes mandatory next week, that shouldn't require manually opening every site.

Each social media platform should have its own script. Each should take in the necessary information, reject if it doesn't have everything, if successful then it reports what happened and link to the post/video for inspection if the user wants.

In other words:

```text
I made something.
Throw it into the social media cesspool.
Never think about it again.
```

## Why?

Because I care about my mental health.

## Cost Notes

- X/Twitter: paid per request. URL posts currently cost more than plain text posts.
- Bluesky: no per-post fee found. Rate limits are the thing to watch.
- Reddit: free for eligible low-volume OAuth use, with rate limits.
- Facebook/Instagram: no per-post fee found. App review, tokens, and rate limits are the annoying part.
- Snapchat: no per-post fee found. Direct posting needs allowlisted Public Profile API access and has rate limits.
- YouTube: quota units, not dollars. Uploads are cheap at low volume.
- TikTok: login/posting looks free as far as I can find through public docs, but it is rate limited and public posting needs approval.

## Current Status

Right now this is a planned standalone tool. Reddit, X/Twitter, and YouTube are the only platforms I can really test with accounts I have. The rest still get scripts, but they are best-effort until I have the accounts and approvals needed to prove them.

## Planned Structure

The shape is simple:

- one Python script per platform
- one parent script for posting to a few places at once
- hard-coded text templates for captions I reuse
- env vars only for credentials, tokens, usernames, and local credential file paths

Each platform script has a comment header explaining what it can post, what credentials it needs, and where to get those credentials.

Each platform script owns its own auth, request body, response parsing, and anything platform specific.

The platform scripts work independently. Sometimes I only want to post to X, or only want to submit one Reddit link, and that should not require going through the parent script.

```bash
python x_post.py \
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

API keys and access tokens still need to exist somewhere because social platforms make sure nothing is ever painless, but the plan is not to add random configuration for things that can be hard-coded or derived.

The working plan in this directory has the commands, API notes, and platform-specific nonsense for:

- X/Twitter
- Bluesky
- Reddit
- Facebook
- Instagram
- Snapchat
- YouTube
- TikTok
