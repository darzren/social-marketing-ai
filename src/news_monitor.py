"""
News Monitor — checks NZ real estate news sources every 3 hours.

If new relevant news is found, generates a branded image post and posts to
Facebook (direct image upload). Instagram uses the committed GitHub raw URL
and is posted in a second phase after git push.

Usage:
    python src/news_monitor.py --industry JL_RealEstate --phase generate
    python src/news_monitor.py --industry JL_RealEstate --phase post

Phase 1 (generate): fetches news, selects best article, generates image,
                    saves to data/news_images/, writes data/news_pending/ file.
Phase 2 (post):     reads pending file, posts to Facebook + Instagram,
                    archives result, updates seen_urls.json.
"""

import argparse
import io
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_NEWS_IMAGES  = Path("data/news_images")
DATA_NEWS_PENDING = Path("data/news_pending")
DATA_NEWS_POSTED  = Path("data/news_posted")

NEWS_SOURCES = [
    {
        "name": "interest.co.nz",
        "rss":  "https://www.interest.co.nz/rss",
    },
    {
        "name": "REINZ",
        "rss":  "https://www.reinz.co.nz/reinz-news/category/media-releases/feed",
    },
    {
        "name": "RBNZ",
        "rss":  "https://www.rbnz.govt.nz/hub/news/feed",
    },
    {
        "name": "NZ Herald Property",
        "rss":  "https://www.nzherald.co.nz/arc/outboundfeeds/rss/property/",
    },
]

REAL_ESTATE_KEYWORDS = [
    "property", "house", "home", "mortgage", "interest rate", "rbnz", "ocr",
    "real estate", "housing", "market", "auction", "listing", "suburb",
    "auckland", "buyer", "seller", "rent", "landlord", "tenant", "lending",
    "reinz", "median price", "sales volume", "first home", "investment",
    "dwelling", "apartment", "corelogic", "qv ", "property values",
]


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _load_seen_urls() -> set:
    path = DATA_NEWS_POSTED / "seen_urls.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        return {url for url, ts in data.items() if ts >= cutoff}
    except Exception:
        return set()


def _save_seen_url(url: str):
    DATA_NEWS_POSTED.mkdir(parents=True, exist_ok=True)
    path = DATA_NEWS_POSTED / "seen_urls.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[url] = datetime.now().isoformat()
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    data = {u: ts for u, ts in data.items() if ts >= cutoff}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------

def _fetch_rss(source: dict) -> list[dict]:
    articles = []
    try:
        resp = requests.get(
            source["rss"],
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JinneyLee-NewsBot/1.0)"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        # Atom namespace
        ATOM_NS = "http://www.w3.org/2005/Atom"

        items = root.findall(".//item")
        if not items:
            items = root.findall(f".//{{{ATOM_NS}}}entry")

        for item in items[:10]:
            def _text(tag, atom_tag=None):
                el = item.find(tag)
                if el is None and atom_tag:
                    el = item.find(f"{{{ATOM_NS}}}{atom_tag}")
                return (el.text or "").strip() if el is not None else ""

            title   = _text("title",       "title")
            summary = _text("description", "summary")[:300]

            # URL — <link> or Atom <link href="...">
            url = _text("link", "link")
            if not url:
                link_el = item.find(f"{{{ATOM_NS}}}link")
                if link_el is not None:
                    url = link_el.get("href", "")

            if title and url:
                articles.append({
                    "source":  source["name"],
                    "title":   title,
                    "url":     url.strip(),
                    "summary": summary,
                })

        logger.info(f"  {source['name']}: {len(articles)} articles")
    except Exception as e:
        logger.warning(f"  {source['name']}: fetch failed — {e}")
    return articles


def _is_relevant(article: dict) -> bool:
    text = (article["title"] + " " + article["summary"]).lower()
    return any(kw in text for kw in REAL_ESTATE_KEYWORDS)


def fetch_all_news() -> list[dict]:
    all_articles = []
    for source in NEWS_SOURCES:
        all_articles.extend(_fetch_rss(source))
    return all_articles


# ---------------------------------------------------------------------------
# Claude — select and summarise
# ---------------------------------------------------------------------------

def select_and_summarise(articles: list[dict], api_key: str) -> dict | None:
    """Ask Claude to pick the best article and produce a ≤10-word headline."""
    import anthropic

    numbered = "\n".join(
        f"{i+1}. [{a['source']}] {a['title']}\n"
        f"   URL: {a['url']}\n"
        f"   {a['summary'][:200]}"
        for i, a in enumerate(articles[:15])
    )

    prompt = f"""You are a social media manager for Jinny Lee Real Estate, an East Auckland real estate agent.

Review these NZ real estate news articles and select the ONE most relevant and interesting for our Facebook audience (East Auckland homeowners, buyers, and sellers).

{numbered}

If NONE are relevant to NZ real estate (property prices, interest rates, market trends, OCR decisions, buying/selling tips, Auckland property news), respond with exactly: NONE

If one is relevant, respond with valid JSON only — no markdown fences, no explanation:
{{
  "index": <article number 1-based>,
  "headline_10w": "<key fact in 10 words max — factual and specific, e.g. 'OCR holds at 3.25% — mortgage rates stay steady'>",
  "caption": "<1-2 sentence Facebook caption in Jinny's warm, knowledgeable voice explaining why this matters to East Auckland property owners>"
}}

Rules for headline_10w:
- Maximum 10 words
- Factual and specific — include numbers if relevant
- No quotation marks inside the text
- Sentence case"""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    if text.upper().startswith("NONE"):
        logger.info("Claude: no relevant article found.")
        return None

    # Strip any accidental markdown
    text = text.strip("`\n ").removeprefix("json").strip()
    try:
        result = json.loads(text)
        idx = result.get("index", 1) - 1
        if 0 <= idx < len(articles):
            result["url"]            = articles[idx]["url"]
            result["source"]         = articles[idx]["source"]
            result["original_title"] = articles[idx]["title"]
        return result
    except Exception as e:
        logger.error(f"Claude parse error: {e} — raw: {text}")
        return None


# ---------------------------------------------------------------------------
# Image generation (Pillow template overlay)
# ---------------------------------------------------------------------------

def _load_font(size: int):
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for fp in candidates:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_news_image(
    headline: str,
    source_url: str,
    template_path: Path,
    brand_config: dict,
) -> bytes:
    """
    Overlay headline text onto the branded news template image.

    Template config (all relative 0.0–1.0 of image dimensions):
      box_x_pct, box_y_pct  — top-left of the yellow headline box
      box_w_pct, box_h_pct  — width/height of the yellow headline box
      url_y_pct             — Y position of the source URL line
      headline_color        — [R, G, B] for headline text
      url_color             — [R, G, B] for URL text
    """
    from PIL import Image, ImageDraw

    tmpl = brand_config.get("news_template", {})

    if template_path.exists():
        img = Image.open(template_path).convert("RGBA")
        logger.info(f"Template: {template_path.name} ({img.width}×{img.height})")
    else:
        logger.warning(f"Template not found at {template_path} — using fallback canvas")
        img = Image.new("RGBA", (1080, 1080), (245, 245, 245, 255))

    width, height = img.size
    draw = ImageDraw.Draw(img)

    box_x = int(width  * tmpl.get("box_x_pct", 0.06))
    box_y = int(height * tmpl.get("box_y_pct", 0.30))
    box_w = int(width  * tmpl.get("box_w_pct", 0.88))
    box_h = int(height * tmpl.get("box_h_pct", 0.38))

    headline_color = tuple(tmpl.get("headline_color", [30, 30, 30]))
    url_color      = tuple(tmpl.get("url_color",      [90, 90, 90]))
    url_y_pct      = tmpl.get("url_y_pct", 0.91)

    def _wrap(text: str, font, max_w: int) -> list[str]:
        words = text.split()
        lines, line = [], ""
        for word in words:
            test = f"{line} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_w:
                line = test
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines or [text]

    # Scale font down until all lines fit inside the yellow box
    max_text_w = box_w - int(width * 0.06)
    font_size  = max(40, int(width * 0.075))
    lines      = []
    while font_size >= 32:
        font    = _load_font(font_size)
        lines   = _wrap(headline, font, max_text_w)
        line_h  = font_size + int(font_size * 0.22)
        total_h = len(lines) * line_h
        if total_h <= box_h * 0.85:
            break
        font_size -= 4

    font   = _load_font(font_size)
    line_h = font_size + int(font_size * 0.22)
    total_h = len(lines) * line_h

    # Center text block vertically inside box
    text_y = box_y + (box_h - total_h) // 2
    for line in lines:
        bbox  = draw.textbbox((0, 0), line, font=font)
        text_x = box_x + (box_w - (bbox[2] - bbox[0])) // 2
        draw.text((text_x, text_y), line, fill=headline_color, font=font)
        text_y += line_h

    # Source URL — small, centered near bottom
    url_font_size = max(16, int(width * 0.020))
    url_font = _load_font(url_font_size)
    display_url = source_url if len(source_url) <= 65 else source_url[:62] + "..."
    url_bbox = draw.textbbox((0, 0), display_url, font=url_font)
    url_x = (width - (url_bbox[2] - url_bbox[0])) // 2
    url_y = int(height * url_y_pct)
    draw.text((url_x, url_y), display_url, fill=url_color, font=url_font)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=93)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Platform posting
# ---------------------------------------------------------------------------

def _post_facebook_photo(image_bytes: bytes, caption: str, env: dict) -> dict:
    page_id      = env.get("FACEBOOK_PAGE_ID", "")
    access_token = env.get("FACEBOOK_ACCESS_TOKEN", "")
    if not page_id or not access_token:
        return {"success": False, "skipped": True, "error": "Facebook credentials not set."}
    try:
        resp = requests.post(
            f"https://graph.facebook.com/v21.0/{page_id}/photos",
            files={"source": ("news.jpg", image_bytes, "image/jpeg")},
            data={"caption": caption, "access_token": access_token},
            timeout=60,
        )
        data = resp.json()
        if resp.status_code == 200 and "id" in data:
            return {"success": True, "post_id": data["id"]}
        error = data.get("error", {}).get("message", resp.text)
        return {"success": False, "error": error}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _post_instagram_photo(image_url: str, caption: str, env: dict) -> dict:
    ig_user_id   = env.get("INSTAGRAM_USER_ID", "")
    access_token = env.get("INSTAGRAM_ACCESS_TOKEN", "")
    if not ig_user_id or not access_token:
        return {"success": False, "skipped": True, "error": "Instagram credentials not set."}
    try:
        c_resp = requests.post(
            f"https://graph.facebook.com/v21.0/{ig_user_id}/media",
            data={"image_url": image_url, "caption": caption, "access_token": access_token},
            timeout=30,
        )
        c_data = c_resp.json()
        if "id" not in c_data:
            error = c_data.get("error", {}).get("message", c_resp.text)
            return {"success": False, "error": f"Container failed: {error}"}

        p_resp = requests.post(
            f"https://graph.facebook.com/v21.0/{ig_user_id}/media_publish",
            data={"creation_id": c_data["id"], "access_token": access_token},
            timeout=30,
        )
        p_data = p_resp.json()
        if "id" in p_data:
            return {"success": True, "post_id": p_data["id"]}
        error = p_data.get("error", {}).get("message", p_resp.text)
        return {"success": False, "error": f"Publish failed: {error}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Phase 1 — generate
# ---------------------------------------------------------------------------

def phase_generate(industry: str, brand_config: dict, api_key: str):
    """
    Fetch news → select → generate image → write pending file.
    Exits 0 with no output if no relevant news found.
    """
    seen_urls = _load_seen_urls()
    logger.info(f"Seen URLs (last 14 days): {len(seen_urls)}")

    all_articles = fetch_all_news()
    logger.info(f"Total articles fetched: {len(all_articles)}")

    new_relevant = [
        a for a in all_articles
        if a["url"] not in seen_urls and _is_relevant(a)
    ]
    logger.info(f"New relevant articles: {len(new_relevant)}")

    if not new_relevant:
        logger.info("✅ No new relevant news — nothing to post.")
        return 0

    selected = select_and_summarise(new_relevant, api_key)
    if not selected:
        logger.info("✅ Claude found nothing post-worthy — skipping.")
        return 0

    headline   = selected["headline_10w"]
    source_url = selected["url"]
    logger.info(f"Selected: {headline}")
    logger.info(f"Source:   {source_url}")

    tmpl_path_str = brand_config.get("news_template", {}).get(
        "template_path", f"assets/templates/{industry}_news_template.png"
    )
    image_bytes = generate_news_image(
        headline, source_url, Path(tmpl_path_str), brand_config
    )

    # Save image
    DATA_NEWS_IMAGES.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_filename = f"{industry}_{ts}_news.jpg"
    image_path = DATA_NEWS_IMAGES / image_filename
    image_path.write_bytes(image_bytes)
    logger.info(f"Image saved: {image_path}")

    # Write pending file
    DATA_NEWS_PENDING.mkdir(parents=True, exist_ok=True)
    pending = {
        "timestamp":      ts,
        "industry":       industry,
        "headline":       headline,
        "caption":        selected.get("caption", ""),
        "source_url":     source_url,
        "original_title": selected.get("original_title", ""),
        "image_path":     str(image_path),
        "image_filename": image_filename,
    }
    pending_path = DATA_NEWS_PENDING / f"{industry}_{ts}_news_pending.json"
    with open(pending_path, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)
    logger.info(f"Pending file written: {pending_path.name}")
    return 0


# ---------------------------------------------------------------------------
# Phase 2 — post
# ---------------------------------------------------------------------------

def phase_post(industry: str, brand_config: dict, env: dict):
    """
    Read the latest pending file → post to Facebook + Instagram → archive.
    Must run AFTER git push (so image is accessible via GitHub raw URL).
    """
    DATA_NEWS_PENDING.mkdir(parents=True, exist_ok=True)
    pending_files = sorted(DATA_NEWS_PENDING.glob(f"{industry}_*_news_pending.json"))
    if not pending_files:
        logger.info("No news pending files — nothing to post.")
        return 0

    pending_path = pending_files[-1]
    pending = json.loads(pending_path.read_text(encoding="utf-8"))

    headline     = pending["headline"]
    caption_text = pending.get("caption", "")
    source_url   = pending["source_url"]
    image_path   = Path(pending["image_path"])
    image_filename = pending["image_filename"]
    ts = pending["timestamp"]

    if not image_path.exists():
        logger.error(f"Image file missing: {image_path}")
        return 1

    image_bytes = image_path.read_bytes()

    # Build full caption
    core_tags = " ".join(brand_config.get("hashtags", {}).get("core", [])[:5])
    fb_tags   = " ".join(brand_config.get("hashtags", {}).get("facebook", [])[:3])
    full_caption = (
        f"{caption_text}\n\n"
        f"Source: {source_url}\n\n"
        f"{core_tags} {fb_tags}".strip()
    )

    # Instagram caption (shorter hashtag set)
    ig_tags = " ".join(brand_config.get("hashtags", {}).get("instagram", [])[:5])
    ig_caption = (
        f"{caption_text}\n\n"
        f"Source: {source_url}\n\n"
        f"{core_tags} {ig_tags}".strip()
    )

    results = {}

    # --- Facebook (direct image upload) ---
    logger.info("Posting to Facebook...")
    results["facebook"] = _post_facebook_photo(image_bytes, full_caption, env)
    fb_status = "OK" if results["facebook"]["success"] else (
        f"Skipped — {results['facebook'].get('error')}" if results["facebook"].get("skipped")
        else f"FAILED — {results['facebook'].get('error')}"
    )
    logger.info(f"  Facebook: {fb_status}")

    # --- Instagram (GitHub raw URL) ---
    github_repo   = os.getenv("GITHUB_REPOSITORY", "")
    github_branch = os.getenv("GITHUB_REF_NAME", "main").removeprefix("refs/heads/")
    if github_repo:
        raw_url = f"https://raw.githubusercontent.com/{github_repo}/{github_branch}/{DATA_NEWS_IMAGES}/{image_filename}"
        logger.info(f"Posting to Instagram (raw URL: {raw_url})...")
        results["instagram"] = _post_instagram_photo(raw_url, ig_caption, env)
        ig_status = "OK" if results["instagram"]["success"] else (
            f"Skipped — {results['instagram'].get('error')}" if results["instagram"].get("skipped")
            else f"FAILED — {results['instagram'].get('error')}"
        )
        logger.info(f"  Instagram: {ig_status}")
    else:
        logger.info("  Instagram: skipped (GITHUB_REPOSITORY not set)")

    # Mark article as seen (regardless of posting outcome)
    _save_seen_url(source_url)

    # Archive result
    DATA_NEWS_POSTED.mkdir(parents=True, exist_ok=True)
    result_record = {
        "timestamp":      ts,
        "posted_at":      datetime.now().isoformat(),
        "headline":       headline,
        "source_url":     source_url,
        "original_title": pending.get("original_title", ""),
        "image_path":     str(image_path),
        "platforms":      results,
    }
    result_path = DATA_NEWS_POSTED / f"{industry}_{ts}_news_posted.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_record, f, indent=2, ensure_ascii=False)

    # Remove pending file
    pending_path.unlink()
    logger.info(f"Pending removed, result archived: {result_path.name}")

    any_success = any(r.get("success") for r in results.values())
    if any_success:
        logger.info("✅ News post published.")
    else:
        logger.warning("⚠️  No platforms succeeded — article still marked seen to avoid re-posting.")

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="JL RealEstate news monitor")
    parser.add_argument("--industry", default="JL_RealEstate")
    parser.add_argument(
        "--phase",
        choices=["generate", "post"],
        default="generate",
        help="generate: fetch+image; post: publish to platforms",
    )
    args = parser.parse_args()

    logger.info(f"=== News Monitor | {args.industry} | phase={args.phase} | {datetime.now().strftime('%Y%m%d_%H%M%S')} ===")

    # Load credentials
    creds_path = Path(f"config/credentials/{args.industry}.env")
    if creds_path.exists():
        load_dotenv(creds_path, override=True)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    brand_config_path = Path(f"config/industries/{args.industry}.json")
    brand_config = (
        json.loads(brand_config_path.read_text(encoding="utf-8"))
        if brand_config_path.exists() else {}
    )

    if args.phase == "generate":
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set.")
            sys.exit(1)
        return phase_generate(args.industry, brand_config, api_key)

    else:  # post
        env = {
            "FACEBOOK_PAGE_ID":      os.getenv("FACEBOOK_PAGE_ID", ""),
            "FACEBOOK_ACCESS_TOKEN": os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
            "INSTAGRAM_USER_ID":     os.getenv("INSTAGRAM_USER_ID", ""),
            "INSTAGRAM_ACCESS_TOKEN": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        }
        return phase_post(args.industry, brand_config, env)


if __name__ == "__main__":
    sys.exit(main())
