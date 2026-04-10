# Image Post Agent Instructions

Runs on **image days** (alternating with text days).
Researches current trends across Facebook, Instagram and TikTok before deciding
on the image type, overlay text, caption, and hashtags.

---

## Step 1 — Platform trend research

Run **5–6 WebSearches** across all three platforms. Cover each angle below:

### Facebook
- `site:facebook.com OR "on Facebook" swimming swimwear 2026 trending engagement`
- What image formats are getting shares/comments in the swim/triathlon niche on Facebook?
- Are static photos, carousels, or Reels performing better right now?

### Instagram
- `instagram swimming swimwear trending posts engagement 2026`
- `instagram reels vs photo posts swim athletic niche 2026`
- What visual styles are dominating (dark/dramatic, bright/poolside, underwater, lifestyle)?
- What caption hooks and overlay text are stopping the scroll?

### TikTok
- `tiktok swimming swimwear viral 2026 trending`
- What content angles are going viral in the competitive swim / athletic gear niche?
- What text hooks appear on high-performing photo/video posts?

### Cross-platform
- `competitive swimwear social media marketing trends 2026`
- `Jaked OR competitive swimming instagram facebook trending content`
- Are there any seasonal events, swim meets, or cultural moments relevant to NZ swimmers right now?

Use **WebFetch** on any high-value articles, posts, or creator pages found.

---

## Step 2 — Synthesise research findings

From your research, determine:

**Image type** — which category will resonate most right now:
- `race_action` — swimmer mid-stroke, race dive, finish wall, underwater dolphin kick
- `training` — drills, early morning pool session, coach on deck
- `gear_closeup` — swimsuit flat lay, goggle reflection, race suit detail
- `lifestyle` — poolside, athlete portrait, post-race emotion
- `open_water` — ocean/harbour swim, NZ coastal scene
- `team` — club team, warm-up, group training

**Visual style** — dark/dramatic, bright/clean, high-contrast, moody, energetic

**Overlay text style** — short punchy (2–4 words), question hook, stat/fact, motivational

**Caption tone** — which format is gaining traction: storytelling, list format, short sharp, question-led

---

## Step 3 — Check post history for repetition

Read the most recent 7 files in `data/content_posted/` for `velocx_nz`.
For each, extract:
- `content.type` (text or image)
- `content.facebook.content_angle` or `content.content_angle`

For image posts specifically, note which `image_type` was used recently.
**Do not repeat an image type used in the last 3 image posts.**

---

## Step 4 — Select image type and write overlay text

Based on research (Step 2) and history (Step 3), decide:

**Image type**: pick the trending type that hasn't been used recently.

**Overlay text**: Use `\n` to separate lines. Structure:
- **Line 1** — large headline in brand orange (2–5 words, punchy hook)
- **Line 2** — smaller subtext in white (brand name, product line, or supporting line)
- **Line 3** — optional (website URL or second supporting line)

The renderer will auto-wrap long lines and scale font size per platform.

Format: `"Headline here.\nSubtext line.\nOptional third line."`

Good examples:
- `"Built to race.\nJaked competitive swimwear\nvelocx.co.nz"`
- `"0.01 seconds matters.\nPremium Italian race suits\nvelocx.co.nz"`
- `"Train like you mean it.\nJaked by VelocX NZ"`
- `"Race day ready.\nShop the full Jaked range\nvelocx.co.nz"`

Or set `overlay_text` to `null` if research shows clean images without text are outperforming.

---

## Step 5 — Write the caption

The caption accompanies the photo. It should:
- Open with a hook that matches the trending format you found (question, bold statement, stat)
- Be **under 150 words** — the image carries the weight, caption amplifies it
- Follow the brand voice: premium, performance-driven, passionate about swimming
- Include a soft CTA (not a hard sell)
- **No hashtags in the caption** — they go in the `hashtags` field separately
- **No engagement bait in the caption** — goes in `engagement_bait` field separately

---

## Step 6 — Build hashtag list

Combine:
- Brand core tags from `config/industries/velocx_nz.json`
- Trending hashtags discovered in research
- Platform-specific tags (e.g. `#InstagramSwimming`, `#TikTokSwim` where relevant)
- NZ-specific tags (`#SwimNZ`, `#NZSwimmers`, `#NewZealandSwimming`)
- Season/event tags if relevant

Aim for **10–14 hashtags** total.

---

## Step 7 — Save the image research brief

Write to:
```
data/research/velocx_nz_TIMESTAMP_image_research.json
```

Format:
```json
{
  "industry": "velocx_nz",
  "post_type": "image",
  "researched_at": "TIMESTAMP",
  "platform_insights": {
    "facebook": "what's performing on Facebook right now",
    "instagram": "what's performing on Instagram right now",
    "tiktok": "what's performing on TikTok right now"
  },
  "recommended_image_type": "race_action",
  "recommended_visual_style": "dark, dramatic, high contrast",
  "recommended_overlay_style": "short punchy 2-3 words, all caps",
  "trending_hooks": ["hook 1 found in research", "hook 2"],
  "key_insight": "one-line summary of the most important finding",
  "previously_used_image_types": ["gear_closeup", "lifestyle"],
  "trending_hashtags": ["#SwimFast", "#RaceReady"]
}
```

---

## Step 8 — Write the image pending file

Filename:
```
data/content_ready/velocx_nz_TIMESTAMP_image_pending.json
```

Content (must include `"type": "image"` at top level):
```json
{
  "type": "image",
  "facebook": {
    "content_angle": "one-line description of the angle and why it was chosen",
    "image_type": "race_action",
    "image_prompt": "Concise Pollinations.ai prompt under 400 chars — used only if no clean image is available",
    "overlay_text": "Built different.",
    "caption": "Full photo caption — hook + story + value + soft CTA. No hashtags. No engagement bait.",
    "engagement_bait": "Drop a fire emoji if this is your pre-race mindset.",
    "hashtags": ["#VelocxNZ", "#Jaked", "#SwimFast", "#RaceReady"],
    "call_to_action": "the soft CTA line from inside the caption"
  }
}
```

**Field rules:**
- `image_type` — one of: `race_action`, `training`, `gear_closeup`, `lifestyle`, `open_water`, `team`
- `image_prompt` — still required as fallback (under 400 chars, no elaborate descriptions)
- `overlay_text` — 2–5 words or `null`
- `caption` — under 150 words, no hashtags, no engagement bait
- `engagement_bait` — reaction prompt only, no delivery promise
