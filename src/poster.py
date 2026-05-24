"""
Orchestrator: publishes posts to each platform and archives results.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from src.platforms import facebook, instagram, tiktok

logger = logging.getLogger(__name__)


def _load_text_disclaimer(industry: str) -> str:
    """Return the text_post_disclaimer from brand config, or empty string."""
    try:
        cfg = json.loads(
            Path(f"config/industries/{industry}.json").read_text(encoding="utf-8")
        )
        return cfg.get("text_post_disclaimer", "")
    except Exception:
        return ""


def _append_disclaimer(text: str, disclaimer: str) -> str:
    if not disclaimer:
        return text
    return f"{text}\n\n{disclaimer}"


def run(posts: dict, raw: dict, industry: str, env: dict, pending_path: Path) -> dict:
    """
    Publish generated posts to each platform.

    posts        — { 'facebook': 'composed string', ... } ready for platform APIs
    raw          — original structured pending JSON (archived as-is for history)
    industry     — industry slug (e.g. 'velocx_nz')
    env          — dict of environment variables
    pending_path — Path to the pending JSON file (will be moved to content_posted)

    Returns summary dict.
    """
    disclaimer = _load_text_disclaimer(industry)
    if disclaimer:
        logger.info("Text post disclaimer will be appended to all captions.")

    results = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "industry": industry,
        "platforms": {},
    }

    # --- Facebook ---
    if "facebook" in posts:
        logger.info("Posting to Facebook...")
        result = facebook.post(
            message=_append_disclaimer(posts["facebook"], disclaimer),
            page_id=env.get("FACEBOOK_PAGE_ID", ""),
            access_token=env.get("FACEBOOK_ACCESS_TOKEN", ""),
        )
        results["platforms"]["facebook"] = result
        status = "OK" if result["success"] else f"FAILED: {result.get('error')}"
        logger.info(f"Facebook: {status}")

    # --- Instagram ---
    if "instagram" in posts:
        logger.info("Posting to Instagram...")
        image_url = env.get("INSTAGRAM_DEFAULT_IMAGE_URL", "")
        # If this text post has a quote card, build its GitHub raw URL
        instagram_image = raw.get("instagram_image", "")
        if instagram_image:
            repo   = os.getenv("GITHUB_REPOSITORY", "")
            branch = os.getenv("GITHUB_REF_NAME", "main")
            if repo:
                image_url = (
                    f"https://raw.githubusercontent.com/{repo}/{branch}"
                    f"/data/content_ready/{instagram_image}"
                )
                logger.info(f"Using quote image for Instagram: {image_url}")
        # Instagram requires an image URL — skip gracefully rather than letting the API error
        if not image_url:
            logger.warning(
                "Instagram skipped — no image URL available. "
                "Quote image generation may have failed. "
                "Set INSTAGRAM_DEFAULT_IMAGE_URL as a fallback to avoid this."
            )
            results["platforms"]["instagram"] = {
                "success": False,
                "skipped": True,
                "error": "No image URL available (quote image missing, INSTAGRAM_DEFAULT_IMAGE_URL not set)",
            }
        else:
            result = instagram.post(
                caption=_append_disclaimer(posts["instagram"], disclaimer),
                ig_user_id=env.get("INSTAGRAM_USER_ID", ""),
                access_token=env.get("INSTAGRAM_ACCESS_TOKEN", ""),
                image_url=image_url,
            )
            results["platforms"]["instagram"] = result
            status = "OK" if result["success"] else f"FAILED: {result.get('error')}"
            logger.info(f"Instagram: {status}")

    # --- TikTok ---
    if "tiktok" in posts:
        logger.info("Posting to TikTok...")
        video_path = None
        try:
            cfg = json.loads(
                Path(f"config/industries/{industry}.json").read_text(encoding="utf-8")
            )
            video_path = cfg.get("tiktok_video_path", "")
        except Exception:
            pass
        result = tiktok.post(
            description=_append_disclaimer(posts["tiktok"], disclaimer),
            access_token=env.get("TIKTOK_ACCESS_TOKEN", ""),
            video_path=video_path or None,
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
        posted_path = archive_as_posted(pending_path, industry, results, raw)
        logger.info(f"Archived to {posted_path}")
    else:
        logger.warning("No platforms posted successfully — pending file kept for retry.")

    return results
