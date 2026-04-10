"""
Image Post Generator

Handles the full image post flow for image days:
  1. Generate platform-specific sized images via Pollinations.ai (free) or DALL-E 3
  2. Overlay VelocX logo at bottom-center (platform safe zone)
  3. Overlay text headline in upper-left safe zone (optional)
  4. Post to each active platform
  5. Archive result

Platform image specs:
  Facebook  — 1200×630  (landscape 1.91:1)
  Instagram — 1080×1350 (portrait 4:5, best feed reach)
  TikTok    — 1080×1920 (vertical 9:16)

Called by main.py when the pending file has type == "image".
"""

import io
import json
import logging
import os
import random
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Per-platform image specs
# pollinations_w/h  — exact size requested from Pollinations.ai
# dalle_size        — closest size DALL-E 3 supports (1024x1024 | 1792x1024 | 1024x1792)
# logo_bottom_margin— px clearance from bottom edge (clears platform UI elements)
# logo_width_ratio  — logo width as fraction of image width
# text_safe_margin  — px from edge for text overlay

PLATFORM_SPECS = {
    "facebook": {
        "pollinations_w": 1200,
        "pollinations_h": 630,
        "dalle_size": "1792x1024",
        "logo_bottom_margin": 60,
        "logo_width_ratio": 0.22,
        "text_safe_margin": 60,
    },
    "instagram": {
        "pollinations_w": 1080,
        "pollinations_h": 1350,
        "dalle_size": "1024x1792",
        "logo_bottom_margin": 140,
        "logo_width_ratio": 0.25,
        "text_safe_margin": 80,
    },
    "tiktok": {
        "pollinations_w": 1080,
        "pollinations_h": 1920,
        "dalle_size": "1024x1792",
        "logo_bottom_margin": 240,   # TikTok has tall interaction UI at bottom
        "logo_width_ratio": 0.25,
        "text_safe_margin": 100,
    },
}

PLATFORM_KEYS = {"facebook", "instagram", "tiktok"}

# Brand colors
BRAND_ORANGE = "#F8A30E"
LOGO_BACKING_ALPHA = 160   # 0–255, semi-transparent black backing behind logo
FONT_SIZE_BASE = 52        # scales with image width
TEXT_BACKING_ALPHA = 200


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

def generate_image(prompt: str, platform: str, openai_api_key: str = "") -> bytes:
    """
    Generate an image sized for the given platform.
    Uses DALL-E 3 if openai_api_key is provided, otherwise Pollinations.ai (free).
    """
    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["facebook"])
    if openai_api_key:
        return _generate_dalle(prompt, openai_api_key, spec["dalle_size"],
                               spec["pollinations_w"], spec["pollinations_h"])
    return _generate_pollinations(prompt, spec["pollinations_w"], spec["pollinations_h"])


def _generate_pollinations(prompt: str, width: int, height: int) -> bytes:
    """Pollinations.ai — free, no API key, FLUX model."""
    seed = random.randint(1, 999999)
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&model=flux&nologo=true&seed={seed}"
    )
    logger.info(f"Generating {width}×{height} image with Pollinations.ai (FLUX)...")
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    return response.content


def _generate_dalle(prompt: str, api_key: str, dalle_size: str,
                    target_w: int, target_h: int) -> bytes:
    """DALL-E 3 via OpenAI API, resized to exact platform dimensions."""
    from openai import OpenAI
    from PIL import Image

    client = OpenAI(api_key=api_key)
    logger.info(f"Generating image with DALL-E 3 (size={dalle_size})...")
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=dalle_size,
        quality="standard",
        n=1,
    )
    image_url = response.data[0].url
    img_response = requests.get(image_url, timeout=60)
    img_response.raise_for_status()

    # Resize to exact platform dimensions
    img = Image.open(io.BytesIO(img_response.content)).convert("RGB")
    img = img.resize((target_w, target_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Logo and text overlay
# ---------------------------------------------------------------------------

def overlay_logo_and_text(
    image_bytes: bytes,
    logo_path: Path,
    platform: str,
    overlay_text: str | None = None,
) -> bytes:
    """
    Overlay the brand logo (bottom-center) and optional text (upper-left).
    Positioning and sizing are platform-specific.
    """
    from PIL import Image, ImageDraw, ImageFont

    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["facebook"])
    logo_bottom_margin = spec["logo_bottom_margin"]
    logo_width_ratio = spec["logo_width_ratio"]
    text_safe_margin = spec["text_safe_margin"]

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    # --- Logo overlay (bottom-center, within platform safe zone) ---
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_w = int(width * logo_width_ratio)
            logo_h = int(logo.height * (logo_w / logo.width))
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)

            logo_x = (width - logo_w) // 2
            logo_y = height - logo_h - logo_bottom_margin

            # Semi-transparent dark backing for readability on any background
            pad = int(logo_w * 0.08)
            backing = Image.new(
                "RGBA",
                (logo_w + pad * 2, logo_h + pad * 2),
                (0, 0, 0, LOGO_BACKING_ALPHA),
            )
            img.paste(backing, (logo_x - pad, logo_y - pad), backing)
            img.paste(logo, (logo_x, logo_y), logo)
            logger.info(f"Logo overlaid at bottom-center for {platform} ({width}×{height}).")
        except Exception as e:
            logger.warning(f"Logo overlay failed: {e}")
    else:
        logger.warning(f"Logo not found at {logo_path} — skipping logo overlay.")

    # --- Text overlay (upper-left, within safe zone) ---
    if overlay_text:
        draw = ImageDraw.Draw(img)
        orange_rgb = _hex_to_rgb(BRAND_ORANGE) + (255,)

        # Scale font size proportionally to image width
        font_size = max(36, int(FONT_SIZE_BASE * (width / 1080)))
        font = None
        for fp in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]:
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        tx, ty = text_safe_margin, text_safe_margin
        pad = 14
        bbox = draw.textbbox((tx, ty), overlay_text, font=font)
        draw.rectangle(
            [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
            fill=(0, 0, 0, TEXT_BACKING_ALPHA),
        )
        draw.text((tx, ty), overlay_text, fill=orange_rgb, font=font)
        logger.info(f"Text overlay added for {platform}: '{overlay_text}'")

    final = img.convert("RGB")
    buf = io.BytesIO()
    final.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Platform posting
# ---------------------------------------------------------------------------

def _post_facebook_photo(image_bytes: bytes, caption: str, env: dict) -> dict:
    page_id = env.get("FACEBOOK_PAGE_ID", "")
    access_token = env.get("FACEBOOK_ACCESS_TOKEN", "")
    url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
    try:
        response = requests.post(
            url,
            files={"source": ("post.jpg", image_bytes, "image/jpeg")},
            data={"caption": caption, "access_token": access_token},
            timeout=60,
        )
        data = response.json()
        if response.status_code == 200 and "id" in data:
            return {"success": True, "post_id": data["id"]}
        error = data.get("error", {}).get("message", response.text)
        return {"success": False, "error": error}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _post_instagram_photo(image_bytes: bytes, caption: str, env: dict) -> dict:
    # Instagram requires a publicly accessible image URL, not a direct upload.
    # Upload the image to a temporary host or use the Instagram container API.
    # Not yet implemented — Instagram credentials not configured.
    return {"success": False, "skipped": True, "error": "Instagram image posting not yet configured."}


def _post_tiktok_photo(image_bytes: bytes, caption: str, env: dict) -> dict:
    # TikTok photo posts require the Content Posting API.
    # Not yet implemented — TikTok credentials not configured.
    return {"success": False, "skipped": True, "error": "TikTok image posting not yet configured."}


PLATFORM_POSTERS = {
    "facebook": _post_facebook_photo,
    "instagram": _post_instagram_photo,
    "tiktok": _post_tiktok_photo,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _compose_caption(platform_data: dict) -> str:
    """Compose full photo caption: caption + engagement_bait + hashtags."""
    parts = [platform_data.get("caption", "").strip()]
    bait = platform_data.get("engagement_bait", "").strip()
    if bait:
        parts.append(bait)
    hashtags = " ".join(platform_data.get("hashtags", []))
    if hashtags:
        parts.append(hashtags)
    return "\n\n".join(p for p in parts if p)


def run_image_post(raw: dict, industry: str, env: dict, pending_path: Path) -> dict:
    """
    Full image post pipeline — generates platform-specific images and posts each.

    raw          — parsed pending JSON (type=image)
    industry     — industry slug (e.g. 'velocx_nz')
    env          — environment variables dict
    pending_path — Path to the *_image_pending.json file
    """
    results = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "industry": industry,
        "platforms": {},
    }

    openai_key = env.get("OPENAI_API_KEY", "")
    logo_path = Path(f"assets/logos/{industry}_logo.png")

    # Extract image_prompt and overlay_text — shared across platforms
    # Look in any platform key for these fields (they're the same for all)
    image_prompt = ""
    overlay_text = None
    for key, val in raw.items():
        if key in PLATFORM_KEYS and isinstance(val, dict):
            image_prompt = image_prompt or val.get("image_prompt", "")
            overlay_text = overlay_text or val.get("overlay_text")

    if not image_prompt:
        logger.error("image_prompt is empty — cannot generate image.")
        for platform in (k for k in raw if k in PLATFORM_KEYS):
            results["platforms"][platform] = {"success": False, "error": "image_prompt missing"}
        return results

    # Generate and post per active platform
    for platform, platform_data in raw.items():
        if platform not in PLATFORM_KEYS or not isinstance(platform_data, dict):
            continue

        spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["facebook"])
        w, h = spec["pollinations_w"], spec["pollinations_h"]
        logger.info(f"Processing {platform} image ({w}×{h})...")

        try:
            image_bytes = generate_image(image_prompt, platform, openai_key)
            image_bytes = overlay_logo_and_text(image_bytes, logo_path, platform, overlay_text)

            caption = _compose_caption(platform_data)
            poster_fn = PLATFORM_POSTERS.get(platform)
            result = poster_fn(image_bytes, caption, env) if poster_fn else {
                "success": False, "error": f"No poster configured for {platform}"
            }
        except Exception as e:
            logger.error(f"{platform} image post failed: {e}", exc_info=True)
            result = {"success": False, "error": str(e)}

        results["platforms"][platform] = result
        status = "OK" if result.get("success") else (
            f"Skipped — {result.get('error')}" if result.get("skipped") else f"FAILED — {result.get('error')}"
        )
        logger.info(f"{platform}: {status}")

    # Archive if at least one platform succeeded
    any_success = any(r.get("success") for r in results["platforms"].values())
    if any_success:
        from src.content_generator import archive_as_posted
        posted_path = archive_as_posted(pending_path, industry, results, raw)
        logger.info(f"Archived to {posted_path}")
    else:
        logger.warning("No platforms posted successfully — pending file kept for retry.")

    return results
