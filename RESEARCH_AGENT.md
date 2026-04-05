# Research Agent Instructions

This agent is **industry and brand agnostic**. It is driven entirely by the
brand config file (`config/industries/<industry>.json`).

It runs BEFORE post generation and outputs a research brief that informs
the quality and relevance of the social media post.

---

## Input

The brand config JSON contains:
- `display_name` — the brand/business name
- `industry` — industry slug
- `description` — what the business does
- `target_audience` — who we are speaking to
- `content_pillars` — topics to post about
- `hashtags` — platform-specific hashtag sets

---

## Research Steps

### 1. Identify search queries
Based on the brand config, generate 4-5 targeted search queries covering:
- Trending content in the industry on social media right now
- Popular hashtags and engagement patterns for the niche
- Competitor or similar brand content strategies
- Seasonal or current events relevant to the audience

Example for a competitive swimwear brand:
- "trending competitive swimming Instagram reels 2025"
- "swimwear brand Facebook post ideas high engagement"
- "swim training TikTok viral content"
- "triathlon gear social media trends"

### 2. Execute searches
Use WebSearch for each query. Scan results for:
- Content formats performing well (video, carousel, text, question posts)
- Recurring themes or topics getting high engagement
- Hashtags appearing frequently in top-performing posts
- Tone and language resonating with the audience
- Any seasonal hooks (upcoming events, seasons, competitions)

### 3. Fetch supporting detail (optional)
If a search result links to a relevant article, blog, or social media
marketing resource, use WebFetch to read it for deeper insight.

### 4. Synthesise findings
Produce a concise research brief with:
- `trending_topics` — 3-5 topics/themes getting traction right now
- `recommended_content_type` — best format for today based on research
- `content_angle` — a specific angle or hook to use in today's post
- `trending_hashtags` — any additional hashtags found beyond the config
- `key_insight` — one sentence summary of the most useful finding

---

## Output

Write the research brief to:
```
data/research/<industry>_TIMESTAMP_research.json
```

Format:
```json
{
  "industry": "velocx_nz",
  "researched_at": "20260406_090000",
  "trending_topics": [
    "underwater dolphin kick technique videos",
    "triathlon race prep content",
    "open water swimming safety tips"
  ],
  "recommended_content_type": "technique_tip",
  "content_angle": "Focus on the mental side of race preparation — anxiety management before a big swim event is trending this week",
  "trending_hashtags": ["#OpenWaterSwimming", "#TriathlonTraining"],
  "key_insight": "Short motivational reels with a single actionable tip are outperforming longer educational posts in the swimming niche this week."
}
```

---

## How the research feeds into post generation

The post generator reads the research brief and uses:
- `recommended_content_type` — overrides the random daily rotation
- `content_angle` — provides a specific hook rather than a generic topic
- `trending_hashtags` — supplements the config hashtags
- `key_insight` — informs tone and format decisions

This ensures every post is grounded in what is actually resonating
with the audience right now, not just evergreen content.
