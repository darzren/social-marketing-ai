"""
Strategy Updater — combines performance insights and trend research to generate
an updated content strategy for a brand. Updates the brand config with learned
posting schedule and writes config/strategy/{industry}_strategy.json.

Runs weekly via GitHub Actions, after performance_tracker.py.

Usage:
    python src/strategy_updater.py --industry velocx_nz
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_INSIGHTS = Path("data/insights")
DATA_RESEARCH = Path("data/research")
STRATEGY_DIR  = Path("config/strategy")
CONFIG_DIR    = Path("config/industries")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_latest_insights(industry: str) -> dict:
    files = sorted(DATA_INSIGHTS.glob(f"{industry}_*_insights.json"))
    if not files:
        logger.warning("No insights files found — strategy will rely on trends only.")
        return {}
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    logger.info(f"Loaded insights: {files[-1].name}")
    return data


def load_recent_research(industry: str, n: int = 5) -> list:
    files = sorted(
        list(DATA_RESEARCH.glob(f"{industry}_*_research.json")) +
        list(DATA_RESEARCH.glob(f"{industry}_*_image_research.json")),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:n]
    result = []
    for f in files:
        try:
            result.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    logger.info(f"Loaded {len(result)} research files")
    return result


def load_current_strategy(industry: str) -> dict:
    path = STRATEGY_DIR / f"{industry}_strategy.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# ---------------------------------------------------------------------------
# Strategy generation
# ---------------------------------------------------------------------------

def generate_strategy(brand_config: dict, insights: dict, research: list,
                      current_strategy: dict, api_key: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Only pass identity-safe fields — never let Claude mutate core brand values
    brand_identity = {
        k: brand_config[k]
        for k in ["display_name", "tone", "brand_colors", "hashtags",
                  "content_pillars", "image_style", "voice_guide", "target_audience"]
        if k in brand_config
    }

    prompt = f"""You are a senior social media strategist producing a weekly strategy update for {brand_config['display_name']}.

=== BRAND IDENTITY (these values are FIXED — do not change them) ===
{json.dumps(brand_identity, indent=2, ensure_ascii=False)}

=== PERFORMANCE INSIGHTS (last 30 days) ===
{json.dumps(insights, indent=2, ensure_ascii=False) if insights else "No performance data yet — first run."}

=== RECENT RESEARCH BRIEFS (trend data from web searches) ===
{json.dumps(research, indent=2, ensure_ascii=False) if research else "No trend research yet."}

=== PREVIOUS STRATEGY (for comparison) ===
{json.dumps(current_strategy, indent=2, ensure_ascii=False) if current_strategy else "No previous strategy — generating first version."}

=== YOUR TASK ===
Produce an updated content strategy based on the data above.

Rules:
1. NEVER change core brand colors, core brand hashtags, brand name, logo, or brand positioning.
2. Only update TACTICS — timing, format preferences, hashtag mix, caption style, image types.
3. Every recommendation must cite a reason from the data (performance insight or trend).
4. Where data is insufficient (< 10 posts), note "low confidence" and use trend research + best practices.
5. hashtags.active must always include all of brand_identity.hashtags.core.
6. hashtags.retired: remove tags that showed no pattern of high-reach posts.
7. hashtags.trending_this_period: new tags from research showing traction in this niche.
8. posting_schedule.optimal_times: use best_posting_hours from facebook_insights if available.
9. image_strategy.top_performing_types: based on by_image_type counts and facebook engagement data.
10. post_template changes must be backed by engagement or reach differences.

Output ONLY a valid JSON object. No markdown. No explanation. No code fences.
{{
  "last_updated": "{datetime.now().strftime('%Y-%m-%d')}",
  "data_period_days": 30,
  "confidence": "low|medium|high",
  "post_template": {{
    "preferred_length_words": "120-150",
    "hook_style": "specific description of best performing hook pattern",
    "structure": "hook → X → Y → CTA",
    "emoji_density": "N-M per post",
    "best_performing_format": "description of what works best",
    "retired_formats": []
  }},
  "image_strategy": {{
    "top_performing_types": [],
    "deprioritise_types": [],
    "overlay_style": "description",
    "prompt_patterns_that_work": []
  }},
  "hashtags": {{
    "active": [],
    "retired": [],
    "trending_this_period": []
  }},
  "content_pillars": {{
    "increase_focus": [],
    "decrease_focus": [],
    "weighting": {{}}
  }},
  "posting_schedule": {{
    "optimal_times": [],
    "best_days": [],
    "posts_per_day": 1,
    "image_to_text_ratio": "1:1"
  }},
  "key_insights": [],
  "reasoning": {{
    "what_worked": "specific finding from data",
    "what_didnt": "specific finding from data",
    "main_recommendation": "one clear action to take"
  }}
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ---------------------------------------------------------------------------
# Brand config update
# ---------------------------------------------------------------------------

def update_brand_config_learned(industry: str, strategy: dict):
    """Write learned schedule back into brand config posting_schedule.learned."""
    config_path = CONFIG_DIR / f"{industry}.json"
    config      = json.loads(config_path.read_text(encoding="utf-8"))

    config.setdefault("posting_schedule", {})["learned"] = {
        "optimal_times":      strategy.get("posting_schedule", {}).get("optimal_times", []),
        "best_days":          strategy.get("posting_schedule", {}).get("best_days", []),
        "posts_per_day":      strategy.get("posting_schedule", {}).get("posts_per_day", 1),
        "image_to_text_ratio": strategy.get("posting_schedule", {}).get("image_to_text_ratio", "1:1"),
        "top_content_types":  strategy.get("image_strategy", {}).get("top_performing_types", []),
        "top_pillars":        strategy.get("content_pillars", {}).get("increase_focus", []),
        "last_updated":       strategy.get("last_updated", ""),
    }

    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Brand config posting_schedule.learned updated.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Strategy updater")
    parser.add_argument("--industry", required=True)
    args = parser.parse_args()

    load_dotenv(f"config/credentials/{args.industry}.env", override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    logger.info(f"=== Strategy Updater | {args.industry} ===")

    config_path      = CONFIG_DIR / f"{args.industry}.json"
    brand_config     = json.loads(config_path.read_text(encoding="utf-8"))
    insights         = load_latest_insights(args.industry)
    research         = load_recent_research(args.industry)
    current_strategy = load_current_strategy(args.industry)

    logger.info("Generating strategy via Claude API...")
    strategy = generate_strategy(brand_config, insights, research, current_strategy, api_key)

    # Write strategy file
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STRATEGY_DIR / f"{args.industry}_strategy.json"
    out_path.write_text(json.dumps(strategy, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Strategy written: {out_path.name}")
    logger.info(f"Confidence: {strategy.get('confidence', '?')}")
    logger.info(f"Key insights: {strategy.get('key_insights', [])}")
    logger.info(f"Recommendation: {strategy.get('reasoning', {}).get('main_recommendation', '')}")

    # Push learned schedule back to brand config
    update_brand_config_learned(args.industry, strategy)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
