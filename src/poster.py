"""
Orchestrator: publishes posts to each platform and archives results.
"""

import logging
from datetime import datetime
from pathlib import Path

from src.platforms import facebook, instagram, tiktok

logger = logging.getLogger(__name__)


def run(posts: dict, industry: str, env: dict, pending_path: Path) -> dict:
    """
    Publish generated posts to each platform.

    posts        — { 'facebook': '...', 'instagram': '...', 'tiktok': '...' }
    industry     — industry slug (e.g. 'velocx_nz')
    env          — dict of environment variables
    pending_path — Path to the pending JSON file (will be moved to content_posted)

    Returns summary dict.
    """
    results = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "industry": industry,
        "generated": posts,
        "platforms": {},
    }

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

    # Move pending → posted only if at least one platform succeeded
    any_success = any(
        r.get("success") for r in results["platforms"].values()
    )
    if any_success:
        from src.content_generator import archive_as_posted
        posted_path = archive_as_posted(pending_path, industry, results)
        logger.info(f"Archived to {posted_path}")
    else:
        logger.warning("No platforms posted successfully — pending file kept for retry.")

    return results
