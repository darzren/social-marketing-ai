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
    month_year = date.today().strftime("%B %Y")
    niche      = brand_config.get("description", "")[:120]
    audience   = brand_config.get("target_audience", {}).get("primary", "")
    pillars    = brand_config.get("content_pillars", [])

    # Extract pillar names
    pillar_names = []
    for p in pillars[:4]:
        name = p.get("pillar", p) if isinstance(p, dict) else str(p)
        pillar_names.append(name)

    queries = [
        f"competitive swimming training tips trends {month_year}",
        f"swimming technique drills social media content {month_year}",
        f"New Zealand swimming events news {month_year}",
        f"swimming hashtags trending Instagram Facebook {month_year}",
        f"triathlon NZ fitness performance trends {month_year}",
        f"performance swimwear athlete content ideas {month_year}",
    ]
    return queries


def run_searches(queries: list[str]) -> list[dict]:
    """Run DuckDuckGo searches. Returns list of {query, hits} dicts."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.warning("duckduckgo_search not installed — skipping web search.")
        return []

    results = []
    with DDGS() as ddgs:
        for query in queries:
            try:
                hits = list(ddgs.text(query, max_results=5))
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
{{
  "generated_at": "{today}",
  "month": "{month_year}",
  "trending_topics": [
    {{"topic": "specific topic name", "relevance": "high|medium|low", "content_angle": "how to make a post about this"}}
  ],
  "trending_hashtags": ["#Tag1", "#Tag2"],
  "seasonal_context": "what is happening in NZ swimming / triathlon / fitness this month that content should reflect",
  "content_opportunities": [
    {{"angle": "specific post idea", "why": "why this is timely right now", "format": "text|image"}}
  ],
  "avoid_this_week": ["topics or angles that feel overdone or irrelevant right now"],
  "recommended_hook_styles": ["specific hook pattern e.g. 'bold claim + contradiction'"],
  "news_summary": "1-2 sentences on any relevant recent news or events the brand should acknowledge or reference"
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Trend researcher")
    parser.add_argument("--industry", required=True)
    args = parser.parse_args()

    load_dotenv(f"config/credentials/{args.industry}.env", override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    logger.info(f"=== Trend Researcher | {args.industry} ===")

    brand_config = load_brand_config(args.industry)
    strategy     = load_strategy(args.industry)

    # Web search
    queries        = build_queries(brand_config)
    logger.info(f"Running {len(queries)} searches...")
    search_results = run_searches(queries)
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
