"""
Content Scheduler — generates and queues social media content autonomously.

Runs hourly via GitHub Actions. Checks if posting is needed based on the brand's
learned or configured schedule, then calls Claude API to generate content and
commits the pending JSON to trigger the post workflow.

Usage:
    python src/content_scheduler.py --industry velocx_nz
    python src/content_scheduler.py --industry velocx_nz --force
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_READY    = Path("data/content_ready")
DATA_POSTED   = Path("data/content_posted")
DATA_RESEARCH = Path("data/research")
STRATEGY_DIR  = Path("config/strategy")
CONFIG_DIR    = Path("config/industries")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_brand_config(industry: str) -> dict:
    path = CONFIG_DIR / f"{industry}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_strategy(industry: str) -> dict:
    path = STRATEGY_DIR / f"{industry}_strategy.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_post_history(industry: str, n: int = 10) -> list:
    files = sorted(DATA_POSTED.glob(f"{industry}_*_posted.json"))[-n:]
    history = []
    for f in files:
        try:
            history.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return history


def load_trend_data(industry: str, max_age_days: int = 3) -> dict:
    """Load the most recent research file if fresh enough."""
    all_files = sorted(
        list(DATA_RESEARCH.glob(f"{industry}_*_research.json")) +
        list(DATA_RESEARCH.glob(f"{industry}_*_image_research.json")),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    cutoff = datetime.now() - timedelta(days=max_age_days)
    for f in all_files:
        if datetime.fromtimestamp(f.stat().st_mtime) > cutoff:
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {"note": "No recent trend data — using brand config defaults."}


# ---------------------------------------------------------------------------
# Scheduling logic
# ---------------------------------------------------------------------------

def should_post_now(industry: str, brand_config: dict, strategy: dict) -> tuple:
    """Return (bool, reason) — whether now is a posting window."""
    try:
        import pytz
        tz = pytz.timezone(brand_config.get("posting_schedule", {}).get("timezone", "UTC"))
        now = datetime.now(tz)
    except ImportError:
        now = datetime.now()

    schedule_cfg   = brand_config.get("posting_schedule", {})
    post_interval  = schedule_cfg.get("post_interval_days", 1)

    # --- Interval check: has a post gone out within the last N days? ---
    cutoff_date = now.date() - timedelta(days=post_interval - 1)
    recent = []
    for f in list(DATA_POSTED.glob(f"{industry}_*_posted.json")) + \
             list(DATA_READY.glob(f"{industry}_*_pending.json")):
        m = re.search(r'_(\d{8})_', f.name)
        if m:
            file_date = datetime.strptime(m.group(1), "%Y%m%d").date()
            if file_date >= cutoff_date:
                recent.append(file_date)

    if recent:
        days_ago = (now.date() - max(recent)).days
        next_in  = post_interval - days_ago
        return False, f"Posted {days_ago}d ago — next post in {next_in}d (every {post_interval}d)"

    # --- Same-day check: skip if a news post already went out today ---
    today_str = now.strftime("%Y%m%d")
    news_posted_dir = Path("data/news_posted")
    if any(today_str in f.name for f in news_posted_dir.glob(f"{industry}_*_news_posted.json")):
        return False, f"News post already published today ({today_str}) — skipping text post"

    # --- Timing window check ---
    learned_times = strategy.get("posting_schedule", {}).get("optimal_times", [])
    default_time  = schedule_cfg.get("daily_time", "09:00")
    windows       = learned_times if learned_times else [default_time]

    now_min = now.hour * 60 + now.minute
    for t in windows:
        m = re.match(r"(\d{1,2}):(\d{2})", str(t))
        if not m:
            continue
        h, mn = int(m.group(1)), int(m.group(2))
        if abs(now_min - (h * 60 + mn)) <= 90:
            return True, f"Within 90-min window of {t[:5]}"

    return False, f"Not in any window — now {now.strftime('%H:%M')}"


def determine_post_type(history: list, strategy: dict) -> str:
    """Alternate text/image, biased by learned image:text ratio."""
    if history:
        last_type = history[-1].get("content", {}).get("type", "text")
        # Check if strategy wants to bias the ratio
        # Extract only the leading "N:N" part — strategy may append explanatory text
        ratio_raw = strategy.get("posting_schedule", {}).get("image_to_text_ratio", "1:1")
        ratio_match = re.match(r"(\d+)\s*:\s*(\d+)", str(ratio_raw))
        img_n, txt_n = (int(ratio_match.group(1)), int(ratio_match.group(2))) if ratio_match else (1, 1)

        # Count recent posts
        recent = history[-max(img_n + txt_n, 4):]
        recent_images = sum(1 for p in recent if p.get("content", {}).get("type") == "image")
        recent_texts  = len(recent) - recent_images

        target_ratio = img_n / (img_n + txt_n)
        actual_ratio = recent_images / len(recent) if recent else 0

        if actual_ratio < target_ratio:
            return "image"
        if actual_ratio > target_ratio:
            return "text"
        # Fall back to strict alternation
        return "text" if last_type == "image" else "image"

    return "text"  # no history — start with text


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------

def build_prompt(industry: str, brand_config: dict, strategy: dict,
                 post_history: list, trend_data: dict, post_type: str) -> str:
    today = date.today().strftime("%Y-%m-%d")

    recent_angles = [
        p.get("content", {}).get("facebook", {}).get("content_angle", "")
        for p in post_history[-7:]
        if p.get("content", {}).get("facebook", {})
    ]
    recent_image_types = [
        p.get("content", {}).get("facebook", {}).get("image_type", "")
        for p in post_history[-7:]
        if p.get("content", {}).get("type") == "image"
    ][-3:]

    strategy_block = (
        json.dumps(strategy, indent=2, ensure_ascii=False)
        if strategy else "No strategy data yet — use brand config defaults."
    )

    base = f"""You are a senior social media content strategist generating a post for {brand_config['display_name']}.
Today: {today}

=== BRAND CONFIG ===
{json.dumps(brand_config, indent=2, ensure_ascii=False)}

=== CURRENT STRATEGY (learned from performance data) ===
{strategy_block}

=== RECENT TREND DATA ===
{json.dumps(trend_data, indent=2, ensure_ascii=False)}

=== RECENT POST ANGLES — DO NOT REPEAT ANY OF THESE ===
{json.dumps(recent_angles, indent=2, ensure_ascii=False)}"""

    if post_type == "image":
        caption_limit = brand_config.get("voice_guide", {}).get("caption_max_words", 150)
        return base + f"""

=== RECENTLY USED IMAGE TYPES — AVOID LAST 3 ===
{json.dumps(recent_image_types, indent=2)}

=== TASK: Generate a social media IMAGE post ===

Rules:
- image_type must be one of the keys in brand_config.image_style.image_types
- image_prompt: start from image_style.prompt_base, add the image_type description. MAX 400 chars.
- overlay_text: use voice_guide.overlay_examples as style reference. 2–5 words per line. Use \\n between lines.
  Line 1 = orange headline. Line 2 = white subtext. Line 3 = optional URL.
- caption: under {caption_limit} words. Hook first. Soft CTA at end. NO hashtags. NO engagement bait.
- hashtags: combine hashtags.core + platform tags + trending from trend data. 10–14 total.
- content_angle must NOT appear in the recent angles list above.
- Do NOT use these image types: {recent_image_types}
- Apply strategy recommendations where available (top_performing_types, overlay_style, etc.)

Output ONLY a valid JSON object. No markdown fences. No explanation.
{{
  "type": "image",
  "facebook": {{
    "content_angle": "one-line description of visual theme and why chosen",
    "image_type": "race_action",
    "image_prompt": "under 400 chars — prompt_base + type description",
    "overlay_text": "Headline.\\nSubtext.\\nOptional URL",
    "caption": "full caption under word limit — no hashtags",
    "engagement_bait": "reaction prompt only",
    "hashtags": ["#Tag1", "#Tag2"],
    "call_to_action": "soft CTA question"
  }}
}}"""

    else:
        return base + f"""

=== TASK: Generate a social media TEXT post ===

Use this structure:
[HOOK — bold claim or question, 1 line + emoji]

[RELATABLE PROBLEM — 1–2 lines]

[STORY/VALUE — 2–3 lines, use 👉 bullets]

[EMOTIONAL TRIGGER — 1 line + emoji]

[VALUE TAKEAWAY — 2–3 lines, use ✔️ bullets]

[SOFT CTA — question format]

Rules:
- Tone: {brand_config.get("tone", "professional")}
- Max 200 words in post_text
- post_text must NOT contain hashtags or engagement bait
- content_angle must NOT appear in the recent angles list above
- Apply strategy recommendations (hook_style, structure, emoji_density, etc.)
- Combine hashtags.core + platform tags + trending hashtags from trend data

Output ONLY a valid JSON object. No markdown fences. No explanation.
{{
  "facebook": {{
    "content_angle": "one-line description of angle used",
    "post_text": "full post body following the 6-section structure",
    "engagement_bait": "reaction prompt only",
    "hashtags": ["#Tag1", "#Tag2"],
    "call_to_action": "soft CTA question"
  }}
}}"""


def generate_content(prompt: str, api_key: str) -> dict:
    """Call Claude API to generate the pending JSON content."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_pending_file(content: dict, industry: str, post_type: str) -> Path:
    DATA_READY.mkdir(parents=True, exist_ok=True)
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "image_pending" if post_type == "image" else "pending"
    path   = DATA_READY / f"{industry}_{ts}_{suffix}.json"
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Pending file written: {path.name}")
    return path


def generate_quote_image(post_text: str, industry: str, brand_config: dict) -> Path | None:
    """Render the hook line of a text post onto the quote card template for Instagram."""
    qt = brand_config.get("quote_template")
    if not qt:
        return None
    template_path = Path(qt["template_path"])
    if not template_path.exists():
        logger.warning(f"Quote template not found: {template_path}")
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not available — skipping quote image generation")
        return None

    hook = post_text.split("\n\n")[0].strip() if post_text else ""
    if not hook:
        logger.warning("No hook line found in post text — skipping quote image")
        return None

    # Strip emoji — system fonts on Linux don't render them (show as [])
    hook = re.sub(r'[^\x00-\x7FÀ-ɏḀ-ỿ]', '', hook).strip()

    img  = Image.open(template_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    bx = int(qt.get("box_x_pct", 0.02) * w)
    by = int(qt.get("box_y_pct", 0.155) * h)
    bw = int(qt.get("box_w_pct", 0.96) * w)
    bh = int(qt.get("box_h_pct", 0.415) * h)
    text_color   = tuple(qt.get("text_color",   [20, 30, 60]))
    accent_color = tuple(qt.get("accent_color", [200, 16, 46]))

    accent_h = 0  # no accent line — template already provides visual framing

    # Font — try bold system fonts, fall back to default
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    font_size = int(h * 0.048)
    font = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    # Word-wrap hook into lines that fit the box width
    padding  = int(bw * 0.05)
    max_tw   = bw - padding * 2

    def wrap(text, fnt):
        words, lines, current = text.split(), [], ""
        for word in words:
            test = f"{current} {word}".strip()
            if draw.textbbox((0, 0), test, font=fnt)[2] <= max_tw:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    lines = wrap(hook, font)

    # Shrink font until lines fit vertically in box (max 5 lines)
    min_size = int(h * 0.028)
    while len(lines) > 5 and font_size > min_size:
        font_size = max(min_size, int(font_size * 0.88))
        for fp in font_paths:
            if Path(fp).exists():
                try:
                    font = ImageFont.truetype(fp, font_size)
                    break
                except Exception:
                    pass
        lines = wrap(hook, font)

    # Centre text block vertically within box (below accent line)
    line_h   = draw.textbbox((0, 0), "Ag", font=font)[3] + int(font_size * 0.35)
    total_h  = line_h * len(lines)
    usable_y = by + accent_h
    text_y   = usable_y + ((bh - accent_h) - total_h) // 2

    for line in lines:
        lw     = draw.textbbox((0, 0), line, font=font)[2]
        text_x = bx + (bw - lw) // 2
        draw.text((text_x, text_y), line, font=font, fill=text_color)
        text_y += line_h

    DATA_READY.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DATA_READY / f"{industry}_{ts}_quote.jpg"
    img.save(out_path, "JPEG", quality=92)
    logger.info(f"Quote image written: {out_path.name}")
    return out_path


GDRIVE_TO_POST_FOLDERS = {
    "JL_RealEstate": "1Q6slJrkqtQI5-EBrLSGz8WSJ24QJyzF4",
}


def upload_to_google_drive(file_path: Path, industry: str) -> None:
    """Upload a quote image to the industry's Google Drive 'To Post' folder (best-effort)."""
    folder_id = GDRIVE_TO_POST_FOLDERS.get(industry)
    if not folder_id:
        return

    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        logger.info("GOOGLE_SERVICE_ACCOUNT_JSON not set — skipping Google Drive upload")
        return

    try:
        import json as _json
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials.from_service_account_info(
            _json.loads(sa_json),
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        media = MediaFileUpload(str(file_path), mimetype="image/jpeg")
        service.files().create(
            body={"name": file_path.name, "parents": [folder_id]},
            media_body=media,
        ).execute()
        logger.info(f"Uploaded to Google Drive (To Post): {file_path.name}")
    except Exception as e:
        logger.warning(f"Google Drive upload failed (non-blocking): {e}")


def git_commit_and_push(industry: str, post_type: str) -> bool:
    try:
        subprocess.run(["git", "add", "data/content_ready/"], check=True)
        diff = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if diff.returncode == 0:
            logger.info("No staged changes — nothing to push.")
            return False
        subprocess.run([
            "git", "commit", "-m",
            f"content: {industry} {post_type} post — auto-scheduled",
        ], check=True)
        subprocess.run(["git", "push"], check=True)
        logger.info("Committed and pushed.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git failed: {e}")
        return False


def trigger_post_workflow(industry: str) -> bool:
    """Trigger the post workflow via gh CLI (GITHUB_TOKEN push won't fire path triggers)."""
    workflow_file = f"post_{industry}.yml"
    try:
        result = subprocess.run(
            ["gh", "workflow", "run", workflow_file],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info(f"Triggered {workflow_file} via gh CLI.")
            return True
        logger.warning(f"gh workflow run failed: {result.stderr.strip()}")
        return False
    except FileNotFoundError:
        logger.warning("gh CLI not available — post workflow not triggered directly.")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Autonomous content scheduler")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--force", action="store_true",
                        help="Skip timing check and generate immediately")
    args = parser.parse_args()

    load_dotenv(f"config/credentials/{args.industry}.env", override=True)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot generate content.")
        sys.exit(1)

    logger.info(f"=== Content Scheduler | {args.industry} ===")

    brand_config = load_brand_config(args.industry)
    strategy     = load_strategy(args.industry)
    post_history = load_post_history(args.industry)
    trend_data   = load_trend_data(args.industry)

    if strategy:
        logger.info(f"Strategy loaded (updated {strategy.get('last_updated', 'unknown')})")
    else:
        logger.info("No strategy file yet — using brand config defaults")

    # Timing check
    if not args.force:
        should, reason = should_post_now(args.industry, brand_config, strategy)
        logger.info(f"Post now: {should} — {reason}")
        if not should:
            logger.info("Nothing to do.")
            sys.exit(0)

    # Decide post type
    post_type = determine_post_type(post_history, strategy)
    if not brand_config.get("image_posts_enabled", True) and post_type == "image":
        post_type = "text"
        logger.info("Image posts disabled in brand config — falling back to text.")
    logger.info(f"Post type: {post_type}")

    # Generate content
    logger.info("Calling Claude API to generate content...")
    prompt  = build_prompt(args.industry, brand_config, strategy, post_history, trend_data, post_type)
    content = generate_content(prompt, api_key)
    angle   = content.get("facebook", {}).get("content_angle", "—")
    logger.info(f"Generated: {angle}")

    # For text posts on Instagram-enabled brands, generate a quote card image
    needs_cdn_wait = False
    if post_type == "text" and "instagram" in brand_config.get("platforms", []):
        post_text = content.get("facebook", {}).get("post_text", "")
        quote_path = generate_quote_image(post_text, args.industry, brand_config)
        if quote_path:
            content["instagram_image"] = quote_path.name
            needs_cdn_wait = True
            logger.info(f"Quote image queued for Instagram: {quote_path.name}")
            upload_to_google_drive(quote_path, args.industry)

    # Write, push, and trigger post workflow
    write_pending_file(content, args.industry, post_type)
    pushed = git_commit_and_push(args.industry, post_type)
    if pushed:
        if needs_cdn_wait:
            logger.info("Waiting 15s for GitHub CDN to propagate quote image...")
            time.sleep(15)
        trigger_post_workflow(args.industry)

    logger.info("=== Scheduler done ===")


if __name__ == "__main__":
    main()
