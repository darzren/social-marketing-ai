# Daily Social Media Agent Instructions

## Brand
Velocx NZ — premium Italian competitive swimwear, based in New Zealand.
Full brand config: `config/industries/velocx_nz.json`

## Your job every run

### Step 1 — Install dependencies
```
pip install requests python-dotenv -q
```

### Step 2 — Get the current timestamp
Run this and note the output (you will use it in the filename):
```
python -c "import datetime; ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S'); print(ts)"
```

### Step 3 — Generate the Facebook post
Read `config/industries/velocx_nz.json` for brand details.

Write a single Facebook post following these guidelines:
- 150–250 words
- Tone: premium, performance-driven, passionate about swimming, aspirational
- Audience: competitive swimmers, triathletes, swim clubs in New Zealand
- Choose ONE content type based on today's date, rotating through:
  `performance_tip`, `product_highlight`, `training_insight`,
  `race_motivation`, `technique_tip`, `community_spotlight`
- End with relevant hashtags from the config
- No markdown formatting in the post text

### Step 4 — Write the post to a timestamped file
Use the Write tool to save to:
```
data/content_ready/velocx_nz_TIMESTAMP_pending.json
```
Replace `TIMESTAMP` with the value from Step 2 (e.g. `velocx_nz_20260406_090300_pending.json`).

File contents must be a JSON object with a single key `facebook`:
```json
{"facebook": "your post text here"}
```

### Step 5 — Commit and push to GitHub
Run these commands one at a time:
```
git config user.email agent@claude.ai
git config user.name Claude-Agent
git remote set-url origin https://GITHUB_TOKEN@github.com/darzren/social-marketing-ai.git
git add data/content_ready/
git commit -m "content: velocx_nz daily post"
git push
```

### Step 6 — Report
Confirm:
- The exact filename written
- Whether the push succeeded
- GitHub Actions will automatically pick up the file and post to Facebook
