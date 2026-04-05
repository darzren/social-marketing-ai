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

### Step 4 — Research trending content (see RESEARCH_AGENT.md for full instructions)
Read `RESEARCH_AGENT.md` for detailed research instructions.

In summary:
- Run 4-5 WebSearches targeting trending social media content in the competitive
  swimwear, swimming, and triathlon niche
- Look for: high-engagement content formats, trending topics, popular hashtags,
  seasonal hooks relevant to NZ swimmers
- Use WebFetch on any useful articles or resources found
- Synthesise findings into a research brief

Write the research brief to:
`data/research/velocx_nz_TIMESTAMP_research.json`
(replace TIMESTAMP with the value from Step 2)

### Step 5 — Generate the Facebook post
Using BOTH the brand config (Step 3) AND the research brief (Step 4), write
a single Facebook post:
- 150-250 words
- Tone: premium, performance-driven, passionate about swimming, aspirational
- Audience: competitive swimmers, triathletes, swim clubs in New Zealand
- Use the `recommended_content_type` and `content_angle` from the research brief
- Supplement config hashtags with any `trending_hashtags` from the research
- No markdown formatting in the post text

### Step 6 — Write the post to a timestamped file
Use the Write tool to save to:
```
data/content_ready/velocx_nz_TIMESTAMP_pending.json
```
(replace TIMESTAMP with the value from Step 2 — same timestamp as the research file)

File must contain a JSON object with a single key `facebook`:
```json
{"facebook": "your post text here"}
```

### Step 7 — Commit and push to GitHub
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

### Step 8 — Report
Confirm:
- The research brief filename written
- The key insight found
- The post filename written
- Whether the push succeeded
- GitHub Actions will automatically pick up the pending file and post to Facebook
