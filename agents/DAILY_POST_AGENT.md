# Daily Social Media Agent Instructions

## Brand
Velocx NZ — premium Italian competitive swimwear, based in New Zealand.
Full brand config: `config/industries/velocx_nz.json`

---

## Your job every run

### Step 1 — Install dependencies
```
pip install requests python-dotenv -q
```

### Step 2 — Get the current timestamp
Run this and note the output — you will use it in all filenames:
```
python -c "import datetime; print(datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))"
```

### Step 3 — Read the brand config
Read `config/industries/velocx_nz.json` for brand details, call_to_action, website, tone, audience,
content pillars, and hashtags.

### Step 4 — Review post history and determine today's post type
Use Glob to list all files matching `data/content_posted/velocx_nz_*_posted.json`.
Read the most recent 7 files (or all if fewer exist).

From each file extract:
- The `content.type` field (`"image"` or `"text"` / absent)
- The `content.facebook` text, angle, drills, products, or hooks used

**Determine today's post type by alternating:**
- Check the most recent posted file's `content.type` field
- If it is `"image"` → today is a **TEXT** post
- If it is `"text"` or the field is absent → today is an **IMAGE** post
- If there are no posted files yet → start with a **TEXT** post

Note today's type — it determines which branch (Step 5A or 5B) you follow.

Build a clear list of what topics/angles have already been covered recently.
This list is used in Steps 5–7 to guarantee today's post is fresh and non-repetitive.

---

### Step 5A — TEXT POST (if today is a text day)

**Research:** Read `agents/RESEARCH_AGENT.md` for full research instructions.

In summary:
- Run 4–5 WebSearches for trending social media content in the competitive
  swimwear, swimming, and triathlon niche
- Look for: high-engagement formats, trending topics, popular hashtags,
  seasonal hooks relevant to NZ swimmers
- Use WebFetch on any useful articles or resources found
- Cross-reference findings against the post history from Step 4 — avoid
  recommending angles already used recently
- Synthesise into a research brief

Write the research brief to:
`data/research/velocx_nz_TIMESTAMP_research.json`

**Generate:** Read `agents/POST_TEMPLATE.md` for formatting rules and output structure.

Using the brand config, post history, and research brief, generate the post:
- Use `recommended_content_type` and `content_angle` from the research brief
- Tone: premium, performance-driven, passionate about swimming, aspirational
- Audience: competitive swimmers, triathletes, swim clubs in New Zealand
- Combine brand config hashtags with `trending_hashtags` from the research brief
- MUST NOT repeat any topic, angle, drill, product, or hook from the last 7 posts
- Output must be strict JSON as defined in the template — no other text

**Write the text pending file:**
```
data/content_ready/velocx_nz_TIMESTAMP_pending.json
```

File format (no `type` field needed for text posts — absence defaults to text):
```json
{
  "facebook": {
    "content_angle": "one-line description of the angle used",
    "post_text": "full formatted post body — no hashtags",
    "engagement_bait": "simple reaction prompt or tag request — no delivery promise",
    "hashtags": ["#Tag1", "#Tag2", "#Tag3"],
    "call_to_action": "the CTA line"
  }
}
```

---

### Step 5B — IMAGE POST (if today is an image day)

**Research:** Read `agents/IMAGE_POST_AGENT.md` for full image research and generation instructions.

In summary:
- Run 3–4 WebSearches for compelling visual content in the swimming/swimwear niche
- Look for: high-performing image styles, visual themes, seasonal hooks, NZ-relevant angles
- Use WebFetch on any useful resources found
- Cross-reference against post history — avoid visual themes already used recently
- Craft a detailed DALL-E 3 prompt in brand style (dark, cinematic, athletic)
- Brand colors: black `#000000`, white `#FFFFFF`, orange `#F8A30E`, light blue `#A3CEF1`
- Leave bottom-right corner uncluttered (VelocX logo will be overlaid there)
- Leave upper area clear if overlay_text will be used

**Write the image pending file:**
```
data/content_ready/velocx_nz_TIMESTAMP_image_pending.json
```

File format (must include `"type": "image"` at top level):
```json
{
  "type": "image",
  "facebook": {
    "content_angle": "one-line description of the visual theme",
    "image_prompt": "Full detailed DALL-E 3 prompt",
    "overlay_text": "Short headline (max 5 words) or null",
    "caption": "Full photo caption — no hashtags, no engagement bait",
    "engagement_bait": "Drop a 🔥 if you agree! 👇",
    "hashtags": ["#VelocxNZ", "#Jaked", "#SwimFast"],
    "call_to_action": "the CTA question line"
  }
}
```

---

### Step 6 — Commit and push to GitHub
Run these commands one at a time:
```
git config user.email agent@claude.ai
git config user.name Claude-Agent
git remote set-url origin https://GITHUB_TOKEN@github.com/darzren/social-marketing-ai.git
git add data/content_ready/ data/research/
git commit -m "content: velocx_nz daily post"
git push
```
Replace GITHUB_TOKEN with the token provided in your session prompt.

### Step 7 — Report
Confirm:
- Today's post type (text or image) and why
- Topics/angles skipped due to post history
- The research brief filename and key insight
- The post filename and a one-line summary of today's angle
- Whether the push succeeded
