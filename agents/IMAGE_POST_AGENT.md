# Image Post Agent Instructions

This agent runs on **image days** (alternating with text days).
It researches, crafts a DALL-E 3 image prompt, and writes the image pending file.

---

## When to run this agent

The daily post agent determines post type by checking the last posted file.
If the last post was a **text** post (or has no `type` field) → today is an **image** day.
If the last post was an **image** post → today is a **text** day.

---

## Step 1 — Research the image concept

Run 3–4 WebSearches focused on:
- Visually compelling swimming / triathlon / swimwear social media imagery
- High-engagement image formats in the athletic/sports niche right now
- Seasonal or event-driven visual themes relevant to NZ swimmers
- Color and composition trends in sports photography on Instagram/Facebook

Use WebFetch on any useful articles found.

Cross-reference against recent post history to ensure:
- The visual theme (e.g. underwater shot, race start, training session) has not been used recently
- The content angle is fresh and not repetitive

**Save the research brief** to:
```
data/research/<industry>_TIMESTAMP_image_research.json
```

Format:
```json
{
  "industry": "velocx_nz",
  "post_type": "image",
  "researched_at": "20260406_090000",
  "trending_visual_themes": [
    "underwater dolphin kick POV",
    "dramatic race start silhouette",
    "flat lay of elite race gear"
  ],
  "recommended_visual_style": "cinematic underwater action shot with dramatic orange lighting",
  "content_angle": "The 15-metre underwater phase — where races are won and lost",
  "trending_hashtags": ["#SwimPhotography", "#PoolLife"],
  "key_insight": "High-contrast underwater action shots are outperforming poolside content 3:1 in the swim niche this week.",
  "previously_used_visual_themes": [
    "race start off the blocks",
    "flat lay gear photo"
  ]
}
```

---

## Step 2 — Craft the DALL-E 3 image prompt

The image must:
- Be **1024×1024** square format (safe for Facebook, Instagram, TikTok)
- Reflect brand aesthetic: **dark, premium, cinematic, athletic**
- Brand colors: black `#000000`, white `#FFFFFF`, orange `#F8A30E` accent, light blue `#A3CEF1`
- Leave the **bottom-right corner relatively uncluttered** (logo will be overlaid there)
- Leave the **upper portion clean or with minimal text** if overlay_text will be used
- Contain **no competing brand logos** on swimwear or gear
- Feature **no specific real athletes** — use anonymous or silhouette-style subjects
- Style: professional sports photography, cinematic, dramatic lighting, 8K quality

**Good prompt structure:**
```
[Subject + action] in a [setting], [lighting style], [colour palette matching brand],
[camera angle/perspective], [mood/feel], no brand logos on swimwear, photorealistic, cinematic quality
```

**IMPORTANT: Keep the prompt under 400 characters.** Longer prompts cause URL errors.
Be specific but concise — pick the 3–4 most important visual details, not every element.

**Example subjects by content pillar:**
- Performance/Training: swimmer mid-stroke underwater, race dive off blocks, dolphin kick sequence
- Mindset/Motivation: athlete on pool deck pre-race, triumphant finish, podium moment
- Lifestyle: early morning training, swim bag flat lay, goggle reflection of pool
- Community/NZ: coastal open water swim, club team warm-up, harbour swim scenery
- Gear: close-up of sleek racing swimsuit in water, goggle reflection, streamlined silhouette

---

## Step 3 — Write the overlay text (optional)

`overlay_text` is a short headline burned onto the image.
- Maximum 5 words
- Use if the image needs context — skip if the image speaks for itself
- Font will be brand orange `#F8A30E` on a semi-transparent black background
- Placed in the upper-left safe zone of the image

If the image is self-explanatory (e.g. dramatic action shot), set `overlay_text` to `null`.

---

## Step 4 — Write the Facebook caption

The caption accompanies the photo post. Follow the same structure as the POST_TEMPLATE.md
but adapted for an image post:
- The image carries the visual hook — the caption amplifies it
- Still use the 8-section structure: hook → problem → story → emotional trigger → value → soft CTA
- Keep caption under 150 words (shorter than text posts — the image does the heavy lifting)
- Include `engagement_bait` and `hashtags` as per standard template rules

---

## Output format

Return STRICT JSON ONLY — no explanation, no markdown wrapper:

```json
{
  "type": "image",
  "content_angle": "one-line description of the visual theme and angle",
  "image_prompt": "Full DALL-E 3 prompt — detailed, specific, brand-aligned",
  "overlay_text": "Short headline or null",
  "caption": "Full photo caption: hook + problem + story + emotional trigger + value + soft CTA — NO hashtags, NO engagement bait",
  "engagement_bait": "Drop a 🔥 if you agree! 👇",
  "hashtags": ["#VelocxNZ", "#Jaked", "#SwimFast"],
  "call_to_action": "the soft CTA question line"
}
```

**Field rules:**
- `type` — always `"image"` for image posts
- `image_prompt` — the exact prompt sent to DALL-E 3; make it detailed and specific
- `overlay_text` — max 5 words, or `null` if not needed
- `caption` — the post text accompanying the photo (no hashtags, no engagement bait)
- `engagement_bait` — reaction prompt only, no delivery promise
- `hashtags` — brand config tags plus any trending visual/photography tags found in research

---

## Pending file format

The CCR agent writes the image pending file as:
```
data/content_ready/<industry>_TIMESTAMP_image_pending.json
```

The file wraps the above JSON under a `facebook` key, with the `type` field at the top level:

```json
{
  "type": "image",
  "facebook": {
    "content_angle": "...",
    "image_prompt": "...",
    "overlay_text": "...",
    "caption": "...",
    "engagement_bait": "...",
    "hashtags": ["#VelocxNZ"],
    "call_to_action": "..."
  }
}
```
