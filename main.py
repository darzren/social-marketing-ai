"""
Social Marketing AI — Main Entry Point

Usage:
    python main.py --industry real_estate
    python main.py --industry swimwear
    python main.py --industry generic   (default)
    python main.py --dry-run            (generate only, no posting)

Scheduled daily at 9am via Claude Code /schedule.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "social_marketing.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def load_industry_config(industry: str) -> dict:
    config_path = Path(f"config/industries/{industry}.json")
    if not config_path.exists():
        available = [p.stem for p in Path("config/industries").glob("*.json")]
        raise FileNotFoundError(
            f"Industry config '{industry}' not found.\n"
            f"Available: {', '.join(available)}"
        )
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def get_env() -> dict:
    return {
        "ANTHROPIC_API_KEY":          os.getenv("ANTHROPIC_API_KEY", ""),
        "FACEBOOK_PAGE_ID":           os.getenv("FACEBOOK_PAGE_ID", ""),
        "FACEBOOK_ACCESS_TOKEN":      os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
        "INSTAGRAM_USER_ID":          os.getenv("INSTAGRAM_USER_ID", ""),
        "INSTAGRAM_ACCESS_TOKEN":     os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        "INSTAGRAM_DEFAULT_IMAGE_URL":os.getenv("INSTAGRAM_DEFAULT_IMAGE_URL", ""),
        "TIKTOK_ACCESS_TOKEN":        os.getenv("TIKTOK_ACCESS_TOKEN", ""),
        "TIKTOK_VIDEO_URL":           os.getenv("TIKTOK_VIDEO_URL", ""),
    }


def validate_env(env: dict, dry_run: bool) -> list[str]:
    warnings = []
    if not env["ANTHROPIC_API_KEY"]:
        warnings.append("ANTHROPIC_API_KEY is missing — content generation will fail.")
    if not dry_run:
        if not env["FACEBOOK_PAGE_ID"] or not env["FACEBOOK_ACCESS_TOKEN"]:
            warnings.append("Facebook credentials missing — Facebook posting will fail.")
        if not env["INSTAGRAM_USER_ID"] or not env["INSTAGRAM_ACCESS_TOKEN"]:
            warnings.append("Instagram credentials missing — Instagram posting will fail.")
        if not env["INSTAGRAM_DEFAULT_IMAGE_URL"]:
            warnings.append("INSTAGRAM_DEFAULT_IMAGE_URL not set — Instagram posts will be skipped.")
        if not env["TIKTOK_ACCESS_TOKEN"]:
            warnings.append("TIKTOK_ACCESS_TOKEN missing — TikTok posting will fail.")
        if not env["TIKTOK_VIDEO_URL"]:
            warnings.append("TIKTOK_VIDEO_URL not set — TikTok posts will be skipped.")
    return warnings


def main():
    parser = argparse.ArgumentParser(description="Social Marketing AI — daily post generator")
    parser.add_argument(
        "--industry", default="generic",
        help="Industry config to use (e.g. real_estate, swimwear, generic)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate posts and print them without publishing"
    )
    args = parser.parse_args()

    logger.info(f"=== Social Marketing AI | Industry: {args.industry} | Dry-run: {args.dry_run} ===")

    # Load config and environment
    try:
        industry_config = load_industry_config(args.industry)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    env = get_env()
    warnings = validate_env(env, args.dry_run)
    for w in warnings:
        logger.warning(w)

    # Generate posts
    from src.content_generator import generate_posts
    logger.info("Generating posts with Claude...")
    try:
        posts = generate_posts(industry_config, api_key=env["ANTHROPIC_API_KEY"])
    except Exception as e:
        logger.error(f"Content generation failed: {e}")
        sys.exit(1)

    # Print generated posts
    logger.info("\n--- GENERATED POSTS ---")
    for platform, content in posts.items():
        logger.info(f"\n[{platform.upper()}]\n{content}\n")

    if args.dry_run:
        logger.info("Dry-run mode: skipping publishing.")
        return

    # Publish
    from src.poster import run
    results = run(posts=posts, industry=args.industry, env=env)

    # Summary
    logger.info("\n--- POSTING RESULTS ---")
    for platform, result in results["platforms"].items():
        if result.get("success"):
            logger.info(f"  {platform}: Posted successfully (ID: {result.get('post_id') or result.get('publish_id')})")
        elif result.get("skipped"):
            logger.warning(f"  {platform}: Skipped — {result.get('error')}")
        else:
            logger.error(f"  {platform}: Failed — {result.get('error')}")

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
