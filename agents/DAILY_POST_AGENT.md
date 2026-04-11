# Daily Social Media Post Agent

> **This agent is brand-agnostic.** Your brand is set by the entry file that called you.
> Wherever you see `{INDUSTRY}`, substitute the value given in your session entry file.

---

## Step 1 — Install dependencies
```
pip install requests python-dotenv -q
```

## Step 2 — Get the current timestamp
Run this and note the output — used in all filenames:
```
python -c "import datetime; print(datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))"
```

## Step 3 — Load brand config
Read `config/industries/{INDUSTRY}.json`.

This file is your **complete brand brief**. Extract and hold in memory:
- `display_name` — brand name for commit messages and logging
- `website` — for CTAs
- `tone` — voice and style to write in
- `target_audience` — who you are speaking to
- `content_pillars` — topics to rotate through
- `hashtags` — core + platform-specific tags
- `brand_colors.accent` — overlay headline colour
- `platforms` — which platforms are active (only post to these)
- `posting_schedule` — frequency, alternating_types flag
- `voice_guide` — headline style, caption rules, overlay examples
- `image_style` — visual style guide for image days (if present)

**Never hardcode brand values** — always use what the config says.

---

## Step 4 — Review post history and determine today's post type

Use Glob to list all files: `data/content_posted/{INDUSTRY}_*_posted.json`
Read the most recent 7 files (or all if fewer exist).

From each file extract:
- `content.type` (`"image"` or `"text"` / absent)
- `content.facebook.content_angle` or `content.content_angle` — the angle used

**Determine today's post type** (if `posting_schedule.alternating_types` is true):
- Most recent posted file `content.type` is `"image"` → today is **TEXT**
- Most recent posted file `content.type` is `"text"` or absent → today is **IMAGE**
- No posted files yet → start with **TEXT**

Build a clear list of recently used angles — used in Step 5 to avoid repetition.

---

## Step 5A — TEXT POST day

**Research:** Read and follow `agents/RESEARCH_AGENT.md`.

In summary:
- Generate 4–5 search queries based on the brand config (industry, audience, content pillars)
- Run WebSearches for trending content formats, topics, hashtags in this niche right now
- Use WebFetch on high-value articles or resources
- Cross-reference against recent post angles — avoid repeating anything from the last 7 posts
- Synthesise into a research brief

Write the research brief to:
```
data/research/{INDUSTRY}_TIMESTAMP_research.json
```

**Generate:** Read `agents/POST_TEMPLATE.md` for formatting and output structure rules.

Using the brand config, post history, and research brief:
- Use `recommended_content_type` and `content_angle` from the research brief
- Write in the brand's `tone` and `voice_guide.caption_style`
- Speak to the `target_audience`
- Combine `hashtags.core` + platform hashtags + `trending_hashtags` from research
- Must NOT repeat any angle from the last 7 posts
- Output must be strict JSON per the template

Write the pending file to:
```
data/content_ready/{INDUSTRY}_TIMESTAMP_pending.json
```

File format (no `type` field needed — absence defaults to text):
```json
{
  "facebook": {
    "content_angle": "one-line description of the angle used",
    "post_text": "full formatted post body — no hashtags, no engagement bait",
    "engagement_bait": "simple reaction prompt or tag request",
    "hashtags": ["#Tag1", "#Tag2"],
    "call_to_action": "the soft CTA line"
  }
}
```

---

## Step 5B — IMAGE POST day

Read and follow `agents/IMAGE_POST_AGENT.md` exactly.

The image agent reads the full visual style guide from `config/industries/{INDUSTRY}.json`
under the `image_style` key — no separate style reference needed.

It will:
- Research trending visual formats across Facebook, Instagram, and TikTok
- Select an image type from `image_style.image_types` (avoiding recently used ones)
- Craft a Pollinations.ai prompt using `image_style.prompt_base` as the foundation
- Write overlay text using `voice_guide.overlay_examples` as style reference
- Write the caption and hashtag list
- Save research brief: `data/research/{INDUSTRY}_TIMESTAMP_image_research.json`
- Write image pending file: `data/content_ready/{INDUSTRY}_TIMESTAMP_image_pending.json`

File format (must include `"type": "image"`):
```json
{
  "type": "image",
  "facebook": {
    "content_angle": "one-line description of the visual theme and why chosen",
    "image_type": "race_action",
    "image_prompt": "Concise Pollinations.ai prompt under 400 chars",
    "overlay_text": "Short headline.\nSubtext line.\nOptional URL",
    "caption": "Photo caption — hook + value + soft CTA. No hashtags.",
    "engagement_bait": "reaction prompt",
    "hashtags": ["#Tag1", "#Tag2"],
    "call_to_action": "the soft CTA question"
  }
}
```

---

## Step 6 — Commit and push to GitHub

Run these commands one at a time:
```
git config user.email agent@claude.ai
git config user.name Claude-Agent
git remote set-url origin https://GITHUB_TOKEN@github.com/darzren/social-marketing-ai.git
git add data/content_ready/ data/research/
git commit -m "content: {INDUSTRY} daily post"
git push
```
Replace `GITHUB_TOKEN` with the token provided in your session context.

---

## Step 7 — Report

Confirm:
- Brand and today's post type (text or image), and why that type was chosen
- Angles or image types skipped due to post history
- Research brief filename and key insight found
- Pending file filename and one-line summary of today's angle
- Whether the push succeeded
