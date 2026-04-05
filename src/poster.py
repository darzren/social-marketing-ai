"""
Orchestrator: loads config, generates posts, publishes, and archives results.
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path

from src.platforms import facebook, instagram, tiktok

logger = logging.getLogger(__name__)

DATA_READY = Path("data/content_ready")
DATA_POSTED = Path("data/content_posted")


def _archive(filename: str, content: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    filepath = folder / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)


def run(posts: dict, industry: str, env: dict) -> dict:
    """
    Publish generated posts to each platform.

    posts   — { 'facebook': '...', 'instagram': '...', 'tiktok': '...' }
    industry — industry slug (e.g. 'real_estate')
    env     — dict of environment variables

    Returns summary dict.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {"timestamp": timestamp, "industry": industry, "platforms": {}}

    # Save generated content before posting
    _archive(f"{industry}_{timestamp}_generated.json", posts, DATA_READY)

    # --- Facebook ---
    if "facebook" in posts:
        logger.info("Posting to Facebook...")
        result = facebook.post(
            message=posts["facebook"],
            page_id=env.get("FACEBOOK_PAGE_ID", ""),
            access_token=env.get("FACEBOOK_ACCESS_TOKEN", ""),
        )
        results["platforms"]["facebook"] = result
        status = "OK" if result["success"] else f"FAILED: {result.get('error')}"
        logger.info(f"Facebook: {status}")

    # --- Instagram ---
    if "instagram" in posts:
        logger.info("Posting to Instagram...")
        result = instagram.post(
            caption=posts["instagram"],
            ig_user_id=env.get("INSTAGRAM_USER_ID", ""),
            access_token=env.get("INSTAGRAM_ACCESS_TOKEN", ""),
            image_url=env.get("INSTAGRAM_DEFAULT_IMAGE_URL"),
        )
        results["platforms"]["instagram"] = result
        status = "OK" if result["success"] else f"FAILED: {result.get('error')}"
        logger.info(f"Instagram: {status}")

    # --- TikTok ---
    if "tiktok" in posts:
        logger.info("Posting to TikTok...")
        result = tiktok.post(
            description=posts["tiktok"],
            access_token=env.get("TIKTOK_ACCESS_TOKEN", ""),
            video_url=env.get("TIKTOK_VIDEO_URL"),
        )
        results["platforms"]["tiktok"] = result
        status = "OK" if result["success"] else f"FAILED: {result.get('error')}"
        logger.info(f"TikTok: {status}")

    # Archive full results (posts + outcomes)
    archive_data = {"generated": posts, "results": results}
    _archive(f"{industry}_{timestamp}_results.json", archive_data, DATA_POSTED)

    return results
