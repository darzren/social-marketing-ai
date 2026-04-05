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
Read `config/industries/velocx_nz.json` for brand details, tone, audience,
content pillars, and hashtags.

### Step 4 — Review post history to avoid repetition
Use Glob to list all files matching `data/content_posted/velocx_nz_*_posted.json`.
Read the most recent 7 files (or all if fewer exist).

From each file extract:
- The `content.facebook` text
- The content type, topic, angle, drills, products, or hooks used

Build a clear list of what has already been covered recently. This list is used
in Steps 5 and 6 to guarantee today's post is fresh and non-repetitive.

### Step 5 — Research trending content
Read `RESEARCH_AGENT.md` for full research instructions.

In summary:
- Run 4-5 WebSearches for trending social media content in the competitive
  swimwear, swimming, and triathlon niche
- Look for: high-engagement formats, trending topics, popular hashtags,
  seasonal hooks relevant to NZ swimmers
- Use WebFetch on any useful articles or resources found
- Cross-reference findings against the post history from Step 4 — avoid
  recommending angles already used recently
- Synthesise into a research brief

Write the research brief to:
`data/research/velocx_nz_TIMESTAMP_research.json`
(replace TIMESTAMP with the value from Step 2)

### Step 6 — Generate the Facebook post
Using the brand config (Step 3), post history (Step 4), and research brief (Step 5),
write a single Facebook post:
- 150-250 words
- Tone: premium, performance-driven, passionate about swimming, aspirational
- Audience: competitive swimmers, triathletes, swim clubs in New Zealand
- Use the `recommended_content_type` and `content_angle` from the research brief
- Supplement config hashtags with any `trending_hashtags` from the research
- No markdown formatting in the post text
- MUST NOT repeat any topic, angle, drill, product, or hook from the last 7 posts
- If the research angle overlaps with recent posts, pick the next best angle

### Step 7 — Write the post to a timestamped file
Use the Write tool to save to:
```
data/content_ready/velocx_nz_TIMESTAMP_pending.json
```
(replace TIMESTAMP with the value from Step 2 — same timestamp as the research file)

File must contain a JSON object with a single key `facebook`:
```json
{"facebook": "your post text here"}
```

### Step 8 — Commit and push to GitHub
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

### Step 9 — Report
Confirm:
- Topics/angles skipped due to post history
- The research brief filename and key insight
- The post filename and a one-line summary of today's angle
- Whether the push succeeded
