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
        "logo_bottom_margin": 30,
        "logo_width_ratio": 0.55,    # wide ratio so height clamp drives the size
        "text_safe_margin": 60,
    },
    "instagram": {
        "pollinations_w": 1080,
        "pollinations_h": 1350,
        "dalle_size": "1024x1792",
        "logo_bottom_margin": 110,
        "logo_width_ratio": 0.45,
        "text_safe_margin": 80,
    },
    "tiktok": {
        "pollinations_w": 1080,
        "pollinations_h": 1920,
        "dalle_size": "1024x1792",
        "logo_bottom_margin": 200,
        "logo_width_ratio": 0.45,
        "text_safe_margin": 100,
    },
}

PLATFORM_KEYS = {"facebook", "instagram", "tiktok"}

# Clean images directory
CLEAN_IMAGES_DIR = Path("assets/clean_images")

# Keyword hints used to loosely match filenames to image_type
IMAGE_TYPE_HINTS = {
    "race_action":  ["race", "action", "butterfly", "breaststroke", "freestyle", "DSC_70", "SaveClip", "SnapInsta"],
    "training":     ["train", "drill", "DSC_69", "DSC_70"],
    "gear_closeup": ["gear", "suit", "flat", "product", "jaked_ "],
    "lifestyle":    ["DSC_69", "poolside", "portrait"],
    "open_water":   ["open", "ocean", "sea", "harbour"],
    "team":         ["team", "group", "club"],
}

# Brand colors
BRAND_ORANGE = "#F8A30E"
# Bottom gradient (for overlay_text area)
BOTTOM_BAND_RATIO   = 0.45   # taller band to accommodate more text
BOTTOM_MAX_ALPHA    = 230
# Top gradient (behind logo in top corner)
TOP_BAND_RATIO      = 0.22
TOP_MAX_ALPHA       = 160
# Logo corner margin as fraction of image width
LOGO_CORNER_MARGIN_RATIO = 0.04
# Logo sized relative to image width — bigger for prominence
LOGO_WIDTH_TARGET_RATIO  = 0.28
# Text overlay — headline font size base (scales with image width)
FONT_SIZE_HEADLINE  = 88
FONT_SIZE_SUBTEXT   = 52
# Max text width as fraction of image width (for word wrap)
TEXT_MAX_WIDTH_RATIO = 0.88


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Clean image selection
# ---------------------------------------------------------------------------

def pick_clean_image(image_type: str, used_images: list[str] | None = None) -> Path | None:
    """
    Pick a clean image from assets/clean_images/ that matches the image_type.
    Avoids recently used images where possible.
    Returns None if no clean images are available.
    """
    if not CLEAN_IMAGES_DIR.exists():
        return None

    all_images = [
        p for p in CLEAN_IMAGES_DIR.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.name != ".gitkeep"
    ]
    if not all_images:
        return None

    used = set(used_images or [])

    # Try to match by image_type hints first
    hints = IMAGE_TYPE_HINTS.get(image_type, [])
    preferred = [p for p in all_images if any(h.lower() in p.name.lower() for h in hints)]
    unused_preferred = [p for p in preferred if p.name not in used]
    unused_any = [p for p in all_images if p.name not in used]

    pool = unused_preferred or unused_any or preferred or all_images
    chosen = random.choice(pool)
    logger.info(f"Clean image selected: {chosen.name} (type={image_type})")
    return chosen


def load_clean_image(image_path: Path, target_w: int, target_h: int) -> bytes:
    """Load and centre-crop a clean image to the target platform dimensions."""
    from PIL import Image as PILImage

    img = PILImage.open(image_path).convert("RGB")
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Wider than target — crop sides, keep centre
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        # Taller than target — crop bottom, keep top (subject usually at top)
        new_h = int(src_w / target_ratio)
        img = img.crop((0, 0, src_w, new_h))

    img = img.resize((target_w, target_h), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


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


def _generate_pollinations(prompt: str, target_w: int, target_h: int) -> bytes:
    """
    Pollinations.ai — free, no API key, FLUX model.

    Always generates at 1024×1024 (most reliable size) then smart-crops to
    the target platform dimensions. Retries with progressively shorter prompts.
    """
    import time
    from PIL import Image as PILImage

    MAX_PROMPT_CHARS = 400
    GEN_SIZE = 1024          # generate square, crop to target after
    base_url = "https://image.pollinations.ai/prompt/"

    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        cut = text[:limit]
        last_period = cut.rfind(".")
        return (cut[:last_period + 1] if last_period > limit * 0.6 else cut).strip()

    attempts = [
        _truncate(prompt, MAX_PROMPT_CHARS),
        _truncate(prompt, 200),
        "competitive swimmer in action, dark cinematic pool, orange accent lighting, photorealistic",
    ]

    raw_bytes = None
    for i, p in enumerate(attempts):
        seed = random.randint(1, 999999)
        encoded = urllib.parse.quote(p)
        url = f"{base_url}{encoded}?width={GEN_SIZE}&height={GEN_SIZE}&model=flux&nologo=true&seed={seed}"
        logger.info(f"Pollinations.ai attempt {i + 1}/3 (prompt {len(p)} chars, {GEN_SIZE}×{GEN_SIZE})...")
        try:
            response = requests.get(url, timeout=180)
            if response.status_code == 200:
                raw_bytes = response.content
                break
            logger.warning(f"Attempt {i + 1} failed: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {i + 1} request error: {e}")
        wait = 30 if response.status_code == 429 else 8
        if i < len(attempts) - 1:
            logger.info(f"Waiting {wait}s before retry...")
            time.sleep(wait)

    if raw_bytes is None:
        raise RuntimeError("Pollinations.ai failed after 3 attempts.")

    # Smart-crop square image to target platform dimensions
    img = PILImage.open(io.BytesIO(raw_bytes)).convert("RGB")
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        img = img.crop((0, 0, src_w, new_h))

    img = img.resize((target_w, target_h), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    logger.info(f"Image resized to {target_w}×{target_h} for platform.")
    return buf.getvalue()


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

def _apply_gradient(img: "Image.Image", width: int, y_start: int, band_height: int,
                    max_alpha: int, direction: str = "bottom_up") -> None:
    """
    Paint a full-width gradient band onto img.
    direction='bottom_up': transparent at top, max_alpha at bottom (bottom band).
    direction='top_down':  max_alpha at top, transparent at bottom (top band).
    """
    from PIL import Image

    strip = Image.new("L", (1, band_height))
    for y in range(band_height):
        t = y / max(band_height - 1, 1)
        if direction == "bottom_up":
            alpha = int(t ** 1.6 * max_alpha)
        else:
            alpha = int((1 - t) ** 1.6 * max_alpha)
        strip.putpixel((0, y), alpha)

    alpha_mask = strip.resize((width, band_height), Image.BILINEAR)
    black_band = Image.new("RGBA", (width, band_height), (0, 0, 0, 255))
    img.paste(black_band, (0, y_start), alpha_mask)


def _load_font(size: int):
    from PIL import ImageFont
    for fp in [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def overlay_logo_and_text(
    image_bytes: bytes,
    logo_path: Path,
    platform: str,
    overlay_text: str | None = None,
) -> bytes:
    """
    Overlay matching reference promo style:
      - Logo icon: top-right corner on a subtle dark gradient
      - overlay_text: bottom-center on a dark gradient, brand orange
    """
    from PIL import Image, ImageDraw

    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["facebook"])
    text_safe_margin = spec["text_safe_margin"]

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    corner_margin = int(width * LOGO_CORNER_MARGIN_RATIO)

    # --- Top gradient (behind logo) ---
    top_band_h = int(height * TOP_BAND_RATIO)
    _apply_gradient(img, width, 0, top_band_h, TOP_MAX_ALPHA, direction="top_down")

    # --- Logo — top-right corner ---
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_target_w = int(width * LOGO_WIDTH_TARGET_RATIO)
            logo_target_h = int(logo.height * (logo_target_w / logo.width))
            # Clamp so it stays within the top gradient band
            if logo_target_h > int(top_band_h * 0.80):
                logo_target_h = int(top_band_h * 0.80)
                logo_target_w = int(logo.width * (logo_target_h / logo.height))
            logo = logo.resize((logo_target_w, logo_target_h), Image.LANCZOS)

            logo_x = width - logo_target_w - corner_margin
            logo_y = corner_margin
            img.paste(logo, (logo_x, logo_y), logo)
            logger.info(f"Logo ({logo_target_w}×{logo_target_h}) at top-right for {platform}.")
        except Exception as e:
            logger.warning(f"Logo overlay failed: {e}")
    else:
        logger.warning(f"Logo not found at {logo_path} — skipping.")

    # --- overlay_text — bottom-center on dark gradient ---
    # overlay_text supports multi-line via "\n":
    #   Line 1 (before first \n) → large headline in brand orange
    #   Line 2+ (after first \n) → smaller subtext in white
    if overlay_text:
        bottom_band_h = int(height * BOTTOM_BAND_RATIO)
        _apply_gradient(img, width, height - bottom_band_h, bottom_band_h,
                        BOTTOM_MAX_ALPHA, direction="bottom_up")

        draw = ImageDraw.Draw(img)
        orange_rgb = _hex_to_rgb(BRAND_ORANGE) + (255,)
        white_rgb  = (255, 255, 255, 255)

        scale = width / 1080
        headline_size = max(52, int(FONT_SIZE_HEADLINE * scale))
        subtext_size  = max(32, int(FONT_SIZE_SUBTEXT  * scale))
        max_text_w    = int(width * TEXT_MAX_WIDTH_RATIO)

        headline_font = _load_font(headline_size)
        subtext_font  = _load_font(subtext_size)

        # Split into headline and subtext lines
        lines = overlay_text.split("\n")
        headline = lines[0].strip()
        sublines = [l.strip() for l in lines[1:] if l.strip()]

        def wrap_line(text: str, font, max_w: int) -> list[str]:
            """Wrap a single line to fit within max_w pixels."""
            import textwrap
            words = text.split()
            wrapped = []
            current = ""
            for word in words:
                test = f"{current} {word}".strip()
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] <= max_w:
                    current = test
                else:
                    if current:
                        wrapped.append(current)
                    current = word
            if current:
                wrapped.append(current)
            return wrapped or [text]

        headline_lines = wrap_line(headline, headline_font, max_text_w)
        sub_wrapped = []
        for sl in sublines:
            sub_wrapped.extend(wrap_line(sl, subtext_font, max_text_w))

        # Calculate total text block height
        line_gap = int(headline_size * 0.15)
        sub_gap  = int(headline_size * 0.25)

        h_line_h  = headline_size + line_gap
        total_h   = len(headline_lines) * h_line_h
        if sub_wrapped:
            total_h += sub_gap + len(sub_wrapped) * (subtext_size + line_gap)

        # Position: vertically centred in the bottom band, with bottom padding
        band_top = height - bottom_band_h
        bottom_pad = int(bottom_band_h * 0.12)
        ty = height - total_h - bottom_pad

        # Draw headline lines (brand orange)
        for hline in headline_lines:
            bbox = draw.textbbox((0, 0), hline, font=headline_font)
            tx = (width - (bbox[2] - bbox[0])) // 2
            draw.text((tx, ty), hline, fill=orange_rgb, font=headline_font)
            ty += h_line_h

        # Draw subtext lines (white)
        if sub_wrapped:
            ty += sub_gap - line_gap
            for sline in sub_wrapped:
                bbox = draw.textbbox((0, 0), sline, font=subtext_font)
                tx = (width - (bbox[2] - bbox[0])) // 2
                draw.text((tx, ty), sline, fill=white_rgb, font=subtext_font)
                ty += subtext_size + line_gap

        logger.info(f"Text overlay ({len(headline_lines)} headline + {len(sub_wrapped)} sublines) for {platform}.")

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

    # Build list of recently used clean images to avoid repeats
    used_images: list[str] = []
    data_posted = Path("data/content_posted")
    if data_posted.exists():
        recent = sorted(data_posted.glob(f"{industry}*_posted.json"))[-7:]
        for pf in recent:
            try:
                d = json.loads(pf.read_text(encoding="utf-8"))
                used_images.append(d.get("content", {}).get("clean_image", ""))
            except Exception:
                pass

    # Generate and post per active platform
    for platform, platform_data in raw.items():
        if platform not in PLATFORM_KEYS or not isinstance(platform_data, dict):
            continue

        spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["facebook"])
        w, h = spec["pollinations_w"], spec["pollinations_h"]
        image_type = platform_data.get("image_type", "race_action")
        logger.info(f"Processing {platform} image ({w}×{h}, type={image_type})...")

        try:
            from src.image_reviewer import review_image

            spec   = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["facebook"])
            tw, th = spec["pollinations_w"], spec["pollinations_h"]
            anthropic_key = env.get("ANTHROPIC_API_KEY", "")

            image_bytes = None
            MAX_RETRIES = 3
            for attempt in range(1, MAX_RETRIES + 1):
                logger.info(f"Generating image — attempt {attempt}/{MAX_RETRIES}...")
                candidate = generate_image(image_prompt, platform, openai_key)
                candidate = overlay_logo_and_text(candidate, logo_path, platform, overlay_text)

                review = review_image(candidate, tw, th, anthropic_key)
                if review.approved:
                    logger.info(f"Image approved (score={review.score}). {review.recommendation}")
                    image_bytes = candidate
                    break
                else:
                    logger.warning(
                        f"Image rejected on attempt {attempt} "
                        f"(score={review.score}): {review.issues}"
                    )
                    if attempt < MAX_RETRIES:
                        logger.info("Regenerating with a new seed...")

            if image_bytes is None:
                logger.error("Image failed review after all attempts — skipping this platform.")
                results["platforms"][platform] = {
                    "success": False,
                    "error": f"Image quality review failed after {MAX_RETRIES} attempts.",
                }
                continue

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
