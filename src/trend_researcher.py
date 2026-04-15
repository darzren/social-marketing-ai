"""
Trend Researcher — searches the web for trending topics, hashtags, and news
relevant to a brand's niche, then uses Claude to synthesise into a structured
research brief saved to data/research/.

Runs 3x per week via GitHub Actions, before the daily posting window.
The content scheduler reads these files (max_age_days=3) when building prompts.

Usage:
    python src/trend_researcher.py --industry velocx_nz
"""

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_RESEARCH = Path("data/research")
CONFIG_DIR    = Path("config/industries")
STRATEGY_DIR  = Path("config/strategy")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_brand_config(industry: str) -> dict:
    return json.loads((CONFIG_DIR / f"{industry}.json").read_text(encoding="utf-8"))


def load_strategy(industry: str) -> dict:
    path = STRATEGY_DIR / f"{industry}_strategy.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def build_queries(brand_config: dict) -> list[str]:
    """Build targeted search queries from brand config."""
    month_year   = date.today().strftime("%B %Y")
    display_name = brand_config.get("display_name", "")
    audience     = brand_config.get("target_audience", {}).get("primary", "")
    pillars      = brand_config.get("content_pillars", [])
    core_tags    = brand_config.get("hashtags", {}).get("core", [])

    # Extract first 3 pillar names for targeted queries
    pillar_names = []
    for p in pillars[:3]:
        name = p.get("pillar", p) if isinstance(p, dict) else str(p)
        pillar_names.append(name)

    # Build niche descriptor from audience description
    niche = audience.split(" in ")[0] if " in " in audience else audience

    queries = []
    # Pillar-based queries
    for pillar in pillar_names:
        queries.append(f"{pillar} social media content ideas {month_year}")
    # Audience + location trends
    queries.append(f"{niche} trends tips {month_year}")
    # Hashtag research
    tag_seed = core_tags[1] if len(core_tags) > 1 else niche
    queries.append(f"{tag_seed} trending hashtags Instagram Facebook {month_year}")
    # Local/news angle
    queries.append(f"{display_name} industry news New Zealand {month_year}")

    return queries[:6]  # cap at 6 to avoid rate limits


def run_searches(queries: list[str], brave_api_key: str) -> list[dict]:
    """Search via Brave Search API. Returns list of {query, hits} dicts.
    Gracefully returns empty on any error."""
    if not brave_api_key:
        logger.warning("BRAVE_API_KEY not set — skipping web search.")
        return []

    import requests as req

    results = []
    headers = {
        "Accept":               "application/json",
        "Accept-Encoding":      "gzip",
        "X-Subscription-Token": brave_api_key,
    }

    for query in queries:
        try:
            resp = req.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params={"q": query, "count": 5, "country": "NZ", "search_lang": "en"},
                timeout=10,
            )
            resp.raise_for_status()
            raw = resp.json().get("web", {}).get("results", [])
            hits = [
                {
                    "title": r.get("title", "")[:120],
                    "body":  r.get("description", "")[:200]
                                .replace('"', "'")
                                .replace("\n", " ")
                                .replace("\\", ""),
                }
                for r in raw
            ]
            results.append({"query": query, "hits": hits})
            logger.info(f"  '{query[:60]}' → {len(hits)} results")
        except Exception as e:
            logger.warning(f"  Search failed: '{query[:60]}' — {e}")
            results.append({"query": query, "hits": [], "error": str(e)})

    return results


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def synthesise(brand_config: dict, strategy: dict,
               search_results: list[dict], api_key: str) -> dict:
    """Pass search results to Claude Haiku → structured research JSON."""
    import anthropic

    client     = anthropic.Anthropic(api_key=api_key)
    today      = date.today().strftime("%Y-%m-%d")
    month_year = date.today().strftime("%B %Y")

    strategy_context = ""
    if strategy:
        strategy_context = f"""
Current strategy guidance:
- Increase focus on: {strategy.get("content_pillars", {}).get("increase_focus", [])}
- Top performing content types: {strategy.get("image_strategy", {}).get("top_performing_types", [])}
- Main recommendation: {strategy.get("reasoning", {}).get("main_recommendation", "")}
- Best hook style: {strategy.get("post_template", {}).get("hook_style", "")}
"""

    search_block = (
        json.dumps(search_results, indent=2, ensure_ascii=False)
        if search_results
        else "No web search data — rely on your training knowledge for this niche."
    )

    prompt = f"""You are a social media trend analyst producing a weekly research brief for {brand_config['display_name']}.

Today: {today} ({month_year})
Brand: {brand_config.get('description', '')}
Target audience: {json.dumps(brand_config.get('target_audience', {}), ensure_ascii=False)}
Content pillars: {json.dumps([p.get('pillar', p) if isinstance(p, dict) else p for p in brand_config.get('content_pillars', [])], ensure_ascii=False)}
Core hashtags: {json.dumps(brand_config.get('hashtags', {}).get('core', []), ensure_ascii=False)}
{strategy_context}

=== WEB SEARCH RESULTS ===
{search_block}

=== YOUR TASK ===
Produce a structured research brief the content scheduler will use this week.
Be specific and actionable — every item must directly help write better posts for this brand.
For trending_hashtags, include both niche-specific and currently popular tags (12–18 total).

Output ONLY valid JSON. No markdown fences. No explanation.
Rules: keep ALL string values under 15 words. Do NOT copy or quote text from search results. Write your own words only. Escape any apostrophes as \\u0027.
{{
  "generated_at": "{today}",
  "month": "{month_year}",
  "trending_topics": [
    {{"topic": "topic name", "relevance": "high|medium|low", "content_angle": "one post angle"}}
  ],
  "trending_hashtags": ["#Tag1", "#Tag2"],
  "seasonal_context": "one sentence on what is happening this month",
  "content_opportunities": [
    {{"angle": "post idea", "why": "why timely", "format": "text|image"}}
  ],
  "avoid_this_week": ["stale topic 1", "stale topic 2"],
  "recommended_hook_styles": ["hook pattern 1", "hook pattern 2"],
  "news_summary": "one sentence on relevant recent news"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}\nRaw: {text[:300]}")
        # Return a minimal valid structure so the file still saves
        return {
            "generated_at": date.today().strftime("%Y-%m-%d"),
            "month": date.today().strftime("%B %Y"),
            "trending_topics": [],
            "trending_hashtags": brand_config.get("hashtags", {}).get("core", []),
            "seasonal_context": "Research synthesis failed — using brand defaults.",
            "content_opportunities": [],
            "avoid_this_week": [],
            "recommended_hook_styles": [],
            "news_summary": "",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Trend researcher")
    parser.add_argument("--industry", required=True)
    args = parser.parse_args()

    load_dotenv(f"config/credentials/{args.industry}.env", override=True)
    api_key      = os.getenv("ANTHROPIC_API_KEY", "")
    brave_key    = os.getenv("BRAVE_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    if not brave_key:
        logger.warning("BRAVE_API_KEY not set — web search will be skipped, Claude will use its own knowledge.")

    logger.info(f"=== Trend Researcher | {args.industry} ===")

    brand_config = load_brand_config(args.industry)
    strategy     = load_strategy(args.industry)

    # Web search
    queries        = build_queries(brand_config)
    logger.info(f"Running {len(queries)} searches...")
    search_results = run_searches(queries, brave_key)
    found          = sum(len(r.get("hits", [])) for r in search_results)
    logger.info(f"Total results fetched: {found}")

    # Synthesise with Claude
    logger.info("Synthesising with Claude Haiku...")
    research = synthesise(brand_config, strategy, search_results, api_key)

    # Save
    DATA_RESEARCH.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DATA_RESEARCH / f"{args.industry}_{ts}_research.json"
    out_path.write_text(json.dumps(research, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Research saved: {out_path.name}")

    topics = [t.get("topic", "") for t in research.get("trending_topics", [])]
    logger.info(f"Topics: {topics}")
    logger.info(f"Hashtags: {research.get('trending_hashtags', [])[:6]}...")
    logger.info(f"Opportunities: {len(research.get('content_opportunities', []))}")
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
