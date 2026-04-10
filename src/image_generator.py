"""
Image Post Generator

Handles the full image post flow for image days:
  1. Generate image via OpenAI DALL-E 3
  2. Overlay VelocX logo (bottom-right safe zone)
  3. Overlay text headline (upper-left safe zone, optional)
  4. Post to Facebook as a photo
  5. Archive result

Called by main.py when the pending file has type == "image".
"""

import io
import json
import logging
import os
import requests
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Image dimensions — 1024x1024 square, safe for Facebook, Instagram, TikTok
IMAGE_SIZE = "1024x1024"
# Logo position: bottom-center, safe for all platforms
# Bottom clearance: 130px clears Instagram like-bar (~100px) and TikTok buttons (~150px edge)
LOGO_BOTTOM_MARGIN = 130
# Logo width as fraction of image width — 25% is prominent without overwhelming
LOGO_WIDTH_RATIO = 0.25
# Semi-transparent backing pad around the logo (px)
LOGO_BACKING_PAD = 18
# Safe zone margin for text overlay (px)
SAFE_MARGIN = 82
# Text font size
FONT_SIZE = 52
# Brand colors
BRAND_ORANGE = "#F8A30E"
BRAND_BLACK = (0, 0, 0)
BRAND_WHITE = (255, 255, 255)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def generate_image(prompt: str, openai_api_key: str = "") -> bytes:
    """
    Generate image from prompt.
    Uses DALL-E 3 if OPENAI_API_KEY is provided, otherwise Pollinations.ai (free).
    """
    if openai_api_key:
        return _generate_dalle(prompt, openai_api_key)
    return _generate_pollinations(prompt)


def _generate_pollinations(prompt: str) -> bytes:
    """Pollinations.ai — free, no API key, FLUX model, 1024x1024."""
    import random
    import urllib.parse
    seed = random.randint(1, 999999)
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=1024&model=flux&nologo=true&seed={seed}"
    )
    logger.info("Generating image with Pollinations.ai (free / FLUX model)...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def _generate_dalle(prompt: str, api_key: str) -> bytes:
    """DALL-E 3 via OpenAI API — ~$0.04 per image."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    logger.info("Generating image with DALL-E 3...")
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=IMAGE_SIZE,
        quality="standard",
        n=1,
    )
    image_url = response.data[0].url
    logger.info("DALL-E 3 image URL received, downloading...")
    img_response = requests.get(image_url, timeout=60)
    img_response.raise_for_status()
    return img_response.content


def overlay_logo_and_text(
    image_bytes: bytes,
    logo_path: Path,
    overlay_text: str | None = None,
) -> bytes:
    """
    Overlay the brand logo and optional text onto the generated image.

    Logo: bottom-right corner, within safe zone.
    Text: upper-left corner, within safe zone, brand orange on semi-transparent black.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size  # 1024x1024

    # --- Logo overlay (bottom-center, safe zone for all platforms) ---
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_target_w = int(width * LOGO_WIDTH_RATIO)
            logo_target_h = int(logo.height * (logo_target_w / logo.width))
            logo = logo.resize((logo_target_w, logo_target_h), Image.LANCZOS)

            # Center horizontally, clear of platform UI at bottom
            logo_x = (width - logo_target_w) // 2
            logo_y = height - logo_target_h - LOGO_BOTTOM_MARGIN

            # Semi-transparent dark backing so logo reads on any background
            pad = LOGO_BACKING_PAD
            backing = Image.new("RGBA", (logo_target_w + pad * 2, logo_target_h + pad * 2), (0, 0, 0, 160))
            img.paste(backing, (logo_x - pad, logo_y - pad), backing)

            img.paste(logo, (logo_x, logo_y), logo)
            logger.info("Logo overlaid at bottom-center.")
        except Exception as e:
            logger.warning(f"Logo overlay failed: {e}")
    else:
        logger.warning(f"Logo not found at {logo_path} — skipping logo overlay.")

    # --- Text overlay ---
    if overlay_text:
        draw = ImageDraw.Draw(img)
        orange_rgb = _hex_to_rgb(BRAND_ORANGE)

        # Try bold fonts available on Ubuntu (GitHub Actions runner)
        font = None
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
        for fp in font_paths:
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(fp, FONT_SIZE)
                break
            except Exception:
                continue
        if font is None:
            from PIL import ImageFont
            font = ImageFont.load_default()

        text_x = SAFE_MARGIN
        text_y = SAFE_MARGIN
        padding = 14

        bbox = draw.textbbox((text_x, text_y), overlay_text, font=font)
        draw.rectangle(
            [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding],
            fill=(0, 0, 0, 200),
        )
        draw.text((text_x, text_y), overlay_text, fill=orange_rgb + (255,), font=font)
        logger.info(f"Text overlay added: '{overlay_text}'")

    # Convert RGBA → RGB for JPEG output
    final = img.convert("RGB")
    buf = io.BytesIO()
    final.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def post_photo_to_facebook(
    image_bytes: bytes,
    caption: str,
    page_id: str,
    access_token: str,
) -> dict:
    """Upload image bytes and post as a Facebook photo with caption."""
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
        else:
            error = data.get("error", {}).get("message", response.text)
            return {"success": False, "error": error}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_image_post(raw: dict, industry: str, env: dict, pending_path: Path) -> dict:
    """
    Full image post pipeline.

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

    fb_data = raw.get("facebook", {})
    image_prompt = fb_data.get("image_prompt", "")
    overlay_text = fb_data.get("overlay_text")  # may be null/None
    caption_text = fb_data.get("caption", "").strip()
    engagement_bait = fb_data.get("engagement_bait", "").strip()
    hashtags = fb_data.get("hashtags", [])
    hashtag_line = " ".join(hashtags)

    # Compose full Facebook photo caption
    caption_parts = [caption_text]
    if engagement_bait:
        caption_parts.append(engagement_bait)
    if hashtag_line:
        caption_parts.append(hashtag_line)
    full_caption = "\n\n".join(caption_parts).strip()

    openai_key = env.get("OPENAI_API_KEY", "")
    page_id = env.get("FACEBOOK_PAGE_ID", "")
    access_token = env.get("FACEBOOK_ACCESS_TOKEN", "")

    if not image_prompt:
        logger.error("image_prompt is empty — cannot generate image.")
        results["platforms"]["facebook"] = {"success": False, "error": "image_prompt missing"}
    else:
        try:
            # 1. Generate image (free via Pollinations.ai, or DALL-E 3 if OPENAI_API_KEY set)
            image_bytes = generate_image(image_prompt, openai_key)

            # 2. Overlay logo + text
            logo_path = Path(f"assets/logos/{industry}_logo.png")
            image_bytes = overlay_logo_and_text(image_bytes, logo_path, overlay_text)

            # 3. Post to Facebook
            logger.info("Posting image to Facebook...")
            result = post_photo_to_facebook(image_bytes, full_caption, page_id, access_token)
            results["platforms"]["facebook"] = result
            status = "OK" if result["success"] else f"FAILED: {result.get('error')}"
            logger.info(f"Facebook image post: {status}")

        except Exception as e:
            logger.error(f"Image post pipeline failed: {e}", exc_info=True)
            results["platforms"]["facebook"] = {"success": False, "error": str(e)}

    # Archive if successful
    any_success = any(r.get("success") for r in results["platforms"].values())
    if any_success:
        from src.content_generator import archive_as_posted
        posted_path = archive_as_posted(pending_path, industry, results, raw)
        logger.info(f"Archived to {posted_path}")
    else:
        logger.warning("Image post failed — pending file kept for retry.")

    return results
