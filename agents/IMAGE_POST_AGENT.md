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

## VelocX visual style reference

All generated images must match this established brand aesthetic. Use this as your
creative brief when crafting every Pollinations.ai prompt.

**Photography style:**
- Professional sports / editorial photography quality
- Dark, moody, cinematic — not bright or cheerful
- Rich deep blue/teal pool water as primary background colour
- Dramatic overhead or side lighting creating strong highlights and deep shadows
- High contrast — subjects pop against dark surroundings
- Motion blur or frozen-motion water droplets add energy
- Shallow depth of field — subject sharp, background softly blurred

**Subject types (by image_type):**
- `race_action` — athlete mid-stroke (butterfly, breaststroke, freestyle), race dive off blocks, underwater dolphin kick, finish wall touch. Water exploding around the body. Jaked swim cap visible.
- `training` — athlete drilling in lane, coach on deck, early morning empty pool with single swimmer, pull buoy, paddles
- `gear_closeup` — sleek racing swimsuit flat lay on pool tiles or submerged in water, goggles with pool reflection, Jaked cap detail. Deep blue/teal water as backdrop.
- `lifestyle` — athlete poolside post-session, towel around shoulders, focused expression, warm stadium lighting, wet hair
- `open_water` — New Zealand coastal swim, ocean or harbour, dramatic sky, wetsuit or racing kit
- `team` — swim club warm-up, lane full of swimmers, coach briefing athletes pre-race

**Colours:**
- Pool water: deep teal `#007B8A` to midnight blue `#001F3F`
- Accent lighting: warm orange-amber `#F8A30E` from stadium overhead spots
- Athlete skin: warm highlighted tones against dark water
- Suit: sleek dark racing suit, no visible competing brand logos

**What to avoid:**
- Bright sunny outdoor pools (too casual)
- White backgrounds or studio setups
- Smiling lifestyle shots (we want focused, competitive, intense)
- Generic stock photography feel
- Any competing brand logos on suits, caps, or equipment

**Composition:**
- Bottom-centre area should be darker/less detailed (VelocX logo overlaid there)
- Leave breathing room — don't crowd every corner
- Portrait images: subject in upper 60%, pool/water fills lower portion
- Landscape images: subject left or centre, water/pool atmosphere right

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
- `image_prompt` — under 400 chars. Reflect VelocX visual style: dark cinematic pool,
  brand orange accent lighting, no competing logos. Reference the style guide above.
- `overlay_text` — 2–5 words or `null`
- `caption` — under 150 words, no hashtags, no engagement bait
- `engagement_bait` — reaction prompt only, no delivery promise
