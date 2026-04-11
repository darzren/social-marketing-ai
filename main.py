"""
Social Marketing AI — Post Publisher

This script ONLY handles publishing. Content must already exist in
data/content_ready/<industry>_pending.json (written by the Claude agent).

Usage:
    python main.py --industry generic
    python main.py --industry real_estate
    python main.py --dry-run
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # fallback global .env if present

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
import io
_stdout_handler = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        _stdout_handler,
        logging.FileHandler(log_dir / "social_marketing.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def get_env() -> dict:
    return {
        "FACEBOOK_PAGE_ID":            os.getenv("FACEBOOK_PAGE_ID", ""),
        "FACEBOOK_ACCESS_TOKEN":       os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
        "INSTAGRAM_USER_ID":           os.getenv("INSTAGRAM_USER_ID", ""),
        "INSTAGRAM_ACCESS_TOKEN":      os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        "INSTAGRAM_DEFAULT_IMAGE_URL": os.getenv("INSTAGRAM_DEFAULT_IMAGE_URL", ""),
        "TIKTOK_ACCESS_TOKEN":         os.getenv("TIKTOK_ACCESS_TOKEN", ""),
        "TIKTOK_VIDEO_URL":            os.getenv("TIKTOK_VIDEO_URL", ""),
    }


def validate_env(env: dict) -> list[str]:
    warnings = []
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
    parser = argparse.ArgumentParser(description="Social Marketing AI — post publisher")
    parser.add_argument("--industry", default="generic")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print posts without publishing")
    args = parser.parse_args()

    logger.info(f"=== Social Marketing AI | Industry: {args.industry} | Dry-run: {args.dry_run} ===")

    # Load industry-specific credentials (overrides any global .env values)
    creds_path = Path(f"config/credentials/{args.industry}.env")
    if creds_path.exists():
        load_dotenv(creds_path, override=True)
        logger.info(f"Loaded credentials from {creds_path}")
    else:
        logger.warning(f"No credentials file at {creds_path} — using global .env values")

    # Load posts written by the Claude agent
    from src.content_generator import load_pending_posts
    try:
        posts, pending_path, raw = load_pending_posts(args.industry)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"Loaded pending post: {pending_path.name}")
    logger.info("\n--- POSTS TO PUBLISH ---")
    for platform, content in posts.items():
        logger.info(f"\n[{platform.upper()}]\n{content}\n")

    if args.dry_run:
        logger.info("Dry-run mode: skipping publishing.")
        return

    env = get_env()
    env["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
    env["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "")
    for w in validate_env(env):
        logger.warning(w)

    post_type = raw.get("type", "text")
    if post_type == "image":
        logger.info("Post type: IMAGE — running image generation pipeline.")
        from src.image_generator import run_image_post
        results = run_image_post(raw=raw, industry=args.industry, env=env, pending_path=pending_path)
    else:
        logger.info("Post type: TEXT — running standard post pipeline.")
        from src.poster import run
        results = run(posts=posts, raw=raw, industry=args.industry, env=env, pending_path=pending_path)

    logger.info("\n--- POSTING RESULTS ---")
    for platform, result in results["platforms"].items():
        if result.get("success"):
            logger.info(f"  {platform}: OK (ID: {result.get('post_id') or result.get('publish_id')})")
        elif result.get("skipped"):
            logger.warning(f"  {platform}: Skipped — {result.get('error')}")
        else:
            logger.error(f"  {platform}: Failed — {result.get('error')}")

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
