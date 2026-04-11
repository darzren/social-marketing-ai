# Image Post Agent Instructions

Runs on **image days** (alternating with text days).
Researches current trends across Facebook, Instagram and TikTok before deciding
on the image type, overlay text, caption, and hashtags.

> **This agent is brand-agnostic.** All visual style, image types, and brand voice
> are read from `config/industries/{INDUSTRY}.json`. Substitute `{INDUSTRY}` with
> the value set in your session entry file.

---

## Step 1 — Load brand image style

Read `config/industries/{INDUSTRY}.json` and extract the `image_style` section.
This is your complete visual creative brief. It contains:
- `description` — overall photographic feel
- `photography_style` — list of style rules to follow
- `avoid` — list of things to never include
- `composition_rules` — framing and layout guidance
- `color_palette` — exact colours to reference in prompts
- `prompt_base` — the base Pollinations.ai prompt string to build from
- `image_types` — available image categories with descriptions

Also extract from the root config:
- `brand_colors.accent` — headline overlay colour
- `voice_guide.overlay_examples` — examples of good overlay text for this brand
- `voice_guide.headline_style` — how overlay text should read
- `hashtags` — core + platform tags

---

## Step 2 — Platform trend research

Run **5–6 WebSearches** across all three platforms. Tailor queries to the brand's
industry and target audience (from `config.description` and `config.target_audience`).

Cover each angle:

### Facebook
- What image formats are getting shares/comments in this niche on Facebook right now?
- Are static photos, carousels, or Reels performing better?

### Instagram
- What visual styles are dominating (dark/dramatic, bright, lifestyle, product-focused)?
- What caption hooks and overlay text are stopping the scroll?

### TikTok
- What content angles are going viral in this niche?
- What text hooks appear on high-performing photo/video posts?

### Cross-platform
- `{brand niche} social media marketing trends 2026`
- Are there seasonal events, product launches, or cultural moments relevant to the audience right now?

Use **WebFetch** on any high-value articles, posts, or creator pages found.

---

## Step 3 — Synthesise research findings

From your research, determine:

**Image type** — which category from `image_style.image_types` will resonate most right now

**Visual style direction** — which sub-style within the brand aesthetic fits the trend

**Overlay text style** — short punchy, question hook, stat/fact, motivational — based on what's performing

**Caption tone** — storytelling, list format, short sharp, question-led

---

## Step 4 — Check post history for repetition

Read the most recent 7 files in `data/content_posted/` for `{INDUSTRY}`.
For image posts specifically, note which `image_type` was used.
**Do not repeat an image type used in the last 3 image posts.**

---

## Step 5 — Select image type and write overlay text

**Image type:** pick the trending type from `image_style.image_types` that hasn't been used recently.

**Image prompt:** Build from `image_style.prompt_base` + the specific `image_type` description.
Keep under 400 characters. Reference the `color_palette` values.
No competing brand logos. Mention the accent colour from `brand_colors.accent`.

**Overlay text:** Use `voice_guide.overlay_examples` as style reference. Structure:
- **Line 1** — large headline in brand accent colour (2–5 words, punchy hook matching `headline_style`)
- **Line 2** — smaller subtext in white (brand name, product line, or supporting line)
- **Line 3** — optional (website URL or second supporting line)

Format: `"Headline here.\nSubtext line.\nOptional third line."`

Or set `overlay_text` to `null` if research shows clean images without text are outperforming.

---

## Step 6 — Write the caption

The caption accompanies the photo. It should:
- Open with a hook matching the trending format found in research
- Be under `voice_guide.caption_max_words` words (or 150 if not set)
- Follow the brand's `tone` and `voice_guide.caption_style`
- Include a soft CTA — not a hard sell
- **No hashtags in the caption** — they go in the `hashtags` field
- **No engagement bait in the caption** — goes in `engagement_bait` field

---

## Step 7 — Build hashtag list

Combine:
- `hashtags.core` from brand config
- Platform-specific tags from `hashtags.facebook`, `hashtags.instagram`, `hashtags.tiktok`
- Trending hashtags discovered in research
- Season/event tags if relevant

Aim for **10–14 hashtags** total.

---

## Step 8 — Save the image research brief

Write to:
```
data/research/{INDUSTRY}_TIMESTAMP_image_research.json
```

Format:
```json
{
  "industry": "{INDUSTRY}",
  "post_type": "image",
  "researched_at": "TIMESTAMP",
  "platform_insights": {
    "facebook": "what's performing on Facebook right now",
    "instagram": "what's performing on Instagram right now",
    "tiktok": "what's performing on TikTok right now"
  },
  "recommended_image_type": "race_action",
  "recommended_visual_style": "dark, dramatic, high contrast",
  "recommended_overlay_style": "short punchy 2-3 words",
  "trending_hooks": ["hook 1 found in research", "hook 2"],
  "key_insight": "one-line summary of the most important finding",
  "previously_used_image_types": ["gear_closeup", "lifestyle"],
  "trending_hashtags": ["#Hashtag1", "#Hashtag2"]
}
```

---

## Step 9 — Write the image pending file

Filename:
```
data/content_ready/{INDUSTRY}_TIMESTAMP_image_pending.json
```

Content (must include `"type": "image"` at top level):
```json
{
  "type": "image",
  "facebook": {
    "content_angle": "one-line description of the angle and why it was chosen",
    "image_type": "race_action",
    "image_prompt": "Concise Pollinations.ai prompt under 400 chars — brand style + image type + color palette",
    "overlay_text": "Headline line.\nSubtext line.\nOptional URL",
    "caption": "Full photo caption — hook + story + value + soft CTA. No hashtags. No engagement bait.",
    "engagement_bait": "Drop a fire emoji if this is your pre-race mindset.",
    "hashtags": ["#Tag1", "#Tag2", "#Tag3"],
    "call_to_action": "the soft CTA line from inside the caption"
  }
}
```

**Field rules:**
- `image_type` — must be one of the keys in `config.image_style.image_types`
- `image_prompt` — under 400 chars. Build from `image_style.prompt_base` + type description. No competing logos.
- `overlay_text` — 2–5 words per line, or `null`
- `caption` — under caption word limit, no hashtags, no engagement bait
- `engagement_bait` — reaction prompt only, no delivery promise
