"""
News Monitor — checks NZ real estate news sources every 3 hours.

Deduplication strategy:
  - URL-level: never repost an article URL seen in the last 14 days
  - Topic-level: pass recently posted headlines to Claude so it avoids
    the same story even when covered by multiple sources with different URLs
  - Age filter: only articles published in the last 24 hours are considered

Priority (highest → lowest):
  1. OCR decisions and interest rate changes
  2. New government housing policies or legislation
  3. National property market data (prices, volumes, CoreLogic, REINZ stats)
  4. Auckland/East Auckland market trends
  5. Real estate industry analysis or opinion

Usage:
    python src/news_monitor.py --industry JL_RealEstate --phase generate
    python src/news_monitor.py --industry JL_RealEstate --phase post
"""

import argparse
import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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

MAX_ARTICLE_AGE_HOURS = 24   # ignore articles older than this

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
    "official cash rate", "reserve bank", "government policy", "kiwibuild",
]


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

SEEN_STATE_PATH = DATA_NEWS_POSTED / "seen_state.json"


def _load_seen_state() -> dict:
    """
    Returns {
      "urls": {url: iso_timestamp, ...},        # URL-level dedup
      "topics": [{"headline": ..., "ts": ...}]  # Topic-level dedup (last 7 days)
    }
    """
    empty = {"urls": {}, "topics": []}
    if not SEEN_STATE_PATH.exists():
        return empty
    try:
        data = json.loads(SEEN_STATE_PATH.read_text(encoding="utf-8"))
        url_cutoff   = (datetime.now() - timedelta(days=14)).isoformat()
        topic_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        data["urls"]   = {u: ts for u, ts in data.get("urls", {}).items()   if ts >= url_cutoff}
        data["topics"] = [t       for t    in data.get("topics", [])        if t.get("ts", "") >= topic_cutoff]
        return data
    except Exception:
        return empty


def _get_last_news_post_date(industry: str) -> datetime | None:
    """Return the datetime of the most recent news post, or None."""
    posted_files = sorted(DATA_NEWS_POSTED.glob(f"{industry}_*_news_posted.json"))
    if not posted_files:
        return None
    m = re.search(r"_(\d{8})_(\d{6})_news_posted", posted_files[-1].name)
    if m:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    return None


def _save_seen(url: str, headline: str):
    """Mark a URL and its topic headline as seen."""
    DATA_NEWS_POSTED.mkdir(parents=True, exist_ok=True)
    state = _load_seen_state()
    state["urls"][url] = datetime.now().isoformat()

    # Keep last 30 topic entries max
    state["topics"].append({"headline": headline, "ts": datetime.now().isoformat()})
    state["topics"] = state["topics"][-30:]

    with open(SEEN_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# RSS fetching with date parsing
# ---------------------------------------------------------------------------

def _parse_pub_date(text: str) -> datetime | None:
    """Parse RSS pubDate (RFC 2822) or Atom updated/published (ISO 8601)."""
    if not text:
        return None
    text = text.strip()
    # RFC 2822 — "Mon, 21 Apr 2026 09:00:00 +1200"
    try:
        return parsedate_to_datetime(text)
    except Exception:
        pass
    # ISO 8601 — "2026-04-21T09:00:00+12:00"
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text[:19], fmt[:len(fmt)])
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            continue
    return None


def _fetch_rss(source: dict) -> list[dict]:
    articles = []
    now_utc  = datetime.now(timezone.utc)
    cutoff   = now_utc - timedelta(hours=MAX_ARTICLE_AGE_HOURS)

    try:
        resp = requests.get(
            source["rss"],
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JinneyLee-NewsBot/1.0)"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        ATOM_NS = "http://www.w3.org/2005/Atom"
        items = root.findall(".//item")
        if not items:
            items = root.findall(f".//{{{ATOM_NS}}}entry")

        skipped_old = 0
        for item in items[:20]:
            def _text(*tags) -> str:
                for tag in tags:
                    el = item.find(tag)
                    if el is not None and el.text:
                        return el.text.strip()
                    # Try Atom namespace
                    el = item.find(f"{{{ATOM_NS}}}{tag.split('}')[-1]}")
                    if el is not None and el.text:
                        return el.text.strip()
                return ""

            title   = _text("title")
            summary = _text("description", "summary", "content")[:350]

            # URL
            url = _text("link")
            if not url:
                link_el = item.find(f"{{{ATOM_NS}}}link")
                if link_el is not None:
                    url = link_el.get("href", "")
            url = url.strip()

            # Publication date
            pub_date_str = _text("pubDate", "published", "updated", "dc:date")
            pub_dt = _parse_pub_date(pub_date_str)

            # Age filter — skip articles with no date OR older than cutoff
            if pub_dt is None:
                # Accept undated articles (some feeds omit dates) but flag them
                age_label = "undated"
            else:
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    skipped_old += 1
                    continue
                age_hours = (now_utc - pub_dt).total_seconds() / 3600
                age_label = f"{age_hours:.1f}h ago"

            if title and url:
                articles.append({
                    "source":    source["name"],
                    "title":     title,
                    "url":       url,
                    "summary":   summary,
                    "age_label": age_label,
                })

        logger.info(
            f"  {source['name']}: {len(articles)} recent articles "
            f"({skipped_old} skipped — older than {MAX_ARTICLE_AGE_HOURS}h)"
        )
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
# Claude — select and summarise with priority + topic dedup
# ---------------------------------------------------------------------------

def select_and_summarise(
    articles: list[dict],
    api_key: str,
    recent_headlines: list[str],
) -> dict | None:
    """
    Ask Claude to pick the best article, respecting priority and avoiding
    recently-posted topics even if the URL is different.
    """
    import anthropic

    numbered = "\n".join(
        f"{i+1}. [{a['source']} • {a['age_label']}] {a['title']}\n"
        f"   URL: {a['url']}\n"
        f"   {a['summary'][:200]}"
        for i, a in enumerate(articles[:15])
    )

    recent_block = ""
    if recent_headlines:
        recent_block = (
            "\n\nRECENTLY POSTED (do NOT pick a story on the same topic as any of these):\n"
            + "\n".join(f"- {h}" for h in recent_headlines[-10:])
        )

    prompt = f"""You are a social media manager for Jinny Lee Real Estate, an East Auckland real estate agent.

Review these NZ real estate news articles (all published in the last 24 hours) and select the ONE most relevant and newsworthy for our Facebook audience (East Auckland homeowners, buyers, and sellers).

PRIORITY ORDER (pick the highest priority you can find):
1. OCR (Official Cash Rate) decisions and interest rate changes — most impactful
2. New government housing policies, legislation, or regulatory changes
3. National property market data: REINZ stats, median prices, sales volumes, CoreLogic reports
4. Auckland or East Auckland market trends
5. Real estate industry analysis or opinion pieces
{recent_block}

Articles to review:
{numbered}

If NONE are relevant to NZ real estate, respond with exactly: NONE
If all relevant articles cover the same topic as a recently posted story, respond with exactly: DUPLICATE

Otherwise respond with valid JSON only — no markdown fences, no explanation:
{{
  "index": <article number 1-based>,
  "priority_tier": <1-5 matching the priority list above>,
  "headline_10w": "<key fact in 10 words max — specific and factual, include numbers if relevant>",
  "caption": "<1-2 sentence Facebook caption in Jinny's warm, knowledgeable voice — explain why this matters to East Auckland property owners>"
}}

Rules for headline_10w:
- Maximum 10 words
- Factual and specific (e.g. "OCR cut to 3.25% — mortgage rates to drop" or "Auckland house prices rise 3% in March")
- No quotation marks inside the headline text
- Sentence case only"""

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
    if text.upper().startswith("DUPLICATE"):
        logger.info("Claude: all relevant articles are duplicates of recent posts.")
        return None

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
    Falls back to a plain yellow-box canvas if the template file is missing.
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

    max_text_w = box_w - int(width * 0.06)
    font_size  = max(40, int(width * 0.075))
    lines      = []
    while font_size >= 32:
        font   = _load_font(font_size)
        lines  = _wrap(headline, font, max_text_w)
        line_h = font_size + int(font_size * 0.22)
        if len(lines) * line_h <= box_h * 0.85:
            break
        font_size -= 4

    font    = _load_font(font_size)
    line_h  = font_size + int(font_size * 0.22)
    total_h = len(lines) * line_h

    text_y = box_y + (box_h - total_h) // 2
    for line in lines:
        bbox   = draw.textbbox((0, 0), line, font=font)
        text_x = box_x + (box_w - (bbox[2] - bbox[0])) // 2
        draw.text((text_x, text_y), line, fill=headline_color, font=font)
        text_y += line_h

    # Source URL — small, centered, wraps to next line if too long
    url_font = _load_font(max(16, int(width * 0.020)))
    url_max_w = int(width * 0.90)

    def _wrap_url(url: str, font, max_w: int) -> list[str]:
        """Wrap a URL at character boundaries to fit within max_w pixels."""
        lines, current = [], ""
        for char in url:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
        return lines or [url]

    url_lines  = _wrap_url(source_url, url_font, url_max_w)
    url_line_h = int(url_font.size * 1.3) if hasattr(url_font, "size") else 20
    url_y      = int(height * url_y_pct)
    for url_line in url_lines:
        url_bbox = draw.textbbox((0, 0), url_line, font=url_font)
        url_x = (width - (url_bbox[2] - url_bbox[0])) // 2
        draw.text((url_x, url_y), url_line, fill=url_color, font=url_font)
        url_y += url_line_h

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
    """Fetch → filter → select → generate image → write pending file."""
    state = _load_seen_state()
    seen_urls        = set(state["urls"].keys())
    recent_headlines = [t["headline"] for t in state.get("topics", [])]

    logger.info(f"Seen URLs (14 days): {len(seen_urls)}  |  Recent topics (7 days): {len(recent_headlines)}")

    all_articles = fetch_all_news()
    logger.info(f"Total articles from last {MAX_ARTICLE_AGE_HOURS}h: {len(all_articles)}")

    new_relevant = [
        a for a in all_articles
        if a["url"] not in seen_urls and _is_relevant(a)
    ]
    logger.info(f"New relevant articles (URL not seen, keyword match): {len(new_relevant)}")

    if not new_relevant:
        logger.info("✅ No new relevant news — nothing to post.")
        return 0

    selected = select_and_summarise(new_relevant, api_key, recent_headlines)
    if not selected:
        logger.info("✅ No post-worthy unique news — skipping.")
        return 0

    headline   = selected["headline_10w"]
    source_url = selected["url"]
    priority   = selected.get("priority_tier", 5)
    logger.info(f"Selected (priority tier {priority}): {headline}")
    logger.info(f"Source: {source_url}")

    # Posting interval check — bypass for high-priority tiers (OCR, govt policy)
    interval_days      = brand_config.get("news_post_interval_days", 1)
    override_tiers     = brand_config.get("news_priority_override_tiers", [1, 2])
    if interval_days > 1 and priority not in override_tiers:
        last_post = _get_last_news_post_date(industry)
        if last_post:
            days_since = (datetime.now() - last_post).total_seconds() / 86400
            if days_since < interval_days:
                logger.info(
                    f"⏭️  Skipping — last news posted {days_since:.1f}d ago "
                    f"(interval: every {interval_days}d, priority tier {priority} does not override). "
                    f"Only tier {override_tiers} bypass the interval."
                )
                return 0
        logger.info(f"Interval OK — proceeding (priority tier {priority})")

    tmpl_path_str = brand_config.get("news_template", {}).get(
        "template_path", f"assets/templates/{industry}_news_template.png"
    )
    image_bytes = generate_news_image(
        headline, source_url, Path(tmpl_path_str), brand_config
    )

    DATA_NEWS_IMAGES.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_filename = f"{industry}_{ts}_news.jpg"
    image_path = DATA_NEWS_IMAGES / image_filename
    image_path.write_bytes(image_bytes)
    logger.info(f"Image saved: {image_path}")

    DATA_NEWS_PENDING.mkdir(parents=True, exist_ok=True)
    pending = {
        "timestamp":      ts,
        "industry":       industry,
        "headline":       headline,
        "caption":        selected.get("caption", ""),
        "source_url":     source_url,
        "original_title": selected.get("original_title", ""),
        "priority_tier":  priority,
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
    """Read pending → post to platforms → archive → update seen state."""
    DATA_NEWS_PENDING.mkdir(parents=True, exist_ok=True)
    pending_files = sorted(DATA_NEWS_PENDING.glob(f"{industry}_*_news_pending.json"))
    if not pending_files:
        logger.info("No news pending files — nothing to post.")
        return 0

    pending_path = pending_files[-1]
    pending = json.loads(pending_path.read_text(encoding="utf-8"))

    headline       = pending["headline"]
    caption_text   = pending.get("caption", "")
    source_url     = pending["source_url"]
    image_path     = Path(pending["image_path"])
    image_filename = pending["image_filename"]
    ts             = pending["timestamp"]

    if not image_path.exists():
        logger.error(f"Image file missing: {image_path}")
        return 1

    image_bytes = image_path.read_bytes()

    core_tags = " ".join(brand_config.get("hashtags", {}).get("core", [])[:5])
    fb_tags   = " ".join(brand_config.get("hashtags", {}).get("facebook", [])[:3])
    ig_tags   = " ".join(brand_config.get("hashtags", {}).get("instagram", [])[:4])

    disclaimer = brand_config.get(
        "news_disclaimer",
        "Disclaimer: This content is based on information from external sources believed to be reliable. "
        "It is not independently verified. Please refer to the original source for full details.",
    )

    full_caption = f"{caption_text}\n\nSource: {source_url}\n\n{core_tags} {fb_tags}\n\n{disclaimer}".strip()
    ig_caption   = f"{caption_text}\n\nSource: {source_url}\n\n{core_tags} {ig_tags}\n\n{disclaimer}".strip()

    results = {}

    logger.info("Posting to Facebook...")
    results["facebook"] = _post_facebook_photo(image_bytes, full_caption, env)
    fb = results["facebook"]
    logger.info(f"  Facebook: {'OK' if fb['success'] else ('Skipped' if fb.get('skipped') else 'FAILED')} — {fb.get('post_id') or fb.get('error', '')}")

    github_repo   = os.getenv("GITHUB_REPOSITORY", "")
    github_branch = os.getenv("GITHUB_REF_NAME", "main").removeprefix("refs/heads/")
    if github_repo and env.get("INSTAGRAM_USER_ID") and env.get("INSTAGRAM_ACCESS_TOKEN"):
        raw_url = (
            f"https://raw.githubusercontent.com/{github_repo}/{github_branch}"
            f"/{DATA_NEWS_IMAGES}/{image_filename}"
        )
        logger.info(f"Posting to Instagram (raw URL: {raw_url})...")
        results["instagram"] = _post_instagram_photo(raw_url, ig_caption, env)
        ig = results["instagram"]
        logger.info(f"  Instagram: {'OK' if ig['success'] else ('Skipped' if ig.get('skipped') else 'FAILED')} — {ig.get('post_id') or ig.get('error', '')}")
    else:
        logger.info("  Instagram: skipped (credentials not set or GITHUB_REPOSITORY missing)")

    # Always mark seen — prevents reposting even on posting failure
    _save_seen(source_url, headline)

    DATA_NEWS_POSTED.mkdir(parents=True, exist_ok=True)
    result_path = DATA_NEWS_POSTED / f"{industry}_{ts}_news_posted.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp":      ts,
            "posted_at":      datetime.now().isoformat(),
            "headline":       headline,
            "source_url":     source_url,
            "original_title": pending.get("original_title", ""),
            "priority_tier":  pending.get("priority_tier"),
            "image_path":     str(image_path),
            "platforms":      results,
        }, f, indent=2, ensure_ascii=False)

    pending_path.unlink()
    logger.info(f"Archived: {result_path.name}")

    any_success = any(r.get("success") for r in results.values())
    logger.info("✅ News post published." if any_success else "⚠️  No platforms succeeded — URL still marked seen.")
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
    )
    args = parser.parse_args()

    logger.info(f"=== News Monitor | {args.industry} | phase={args.phase} | {datetime.now().strftime('%Y%m%d_%H%M%S')} ===")

    creds_path = Path(f"config/credentials/{args.industry}.env")
    if creds_path.exists():
        load_dotenv(creds_path, override=True)

    brand_config_path = Path(f"config/industries/{args.industry}.json")
    brand_config = (
        json.loads(brand_config_path.read_text(encoding="utf-8"))
        if brand_config_path.exists() else {}
    )

    if args.phase == "generate":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set.")
            sys.exit(1)
        return phase_generate(args.industry, brand_config, api_key)

    else:  # post
        env = {
            "FACEBOOK_PAGE_ID":       os.getenv("FACEBOOK_PAGE_ID", ""),
            "FACEBOOK_ACCESS_TOKEN":  os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
            "INSTAGRAM_USER_ID":      os.getenv("INSTAGRAM_USER_ID", ""),
            "INSTAGRAM_ACCESS_TOKEN": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        }
        return phase_post(args.industry, brand_config, env)


if __name__ == "__main__":
    sys.exit(main())
