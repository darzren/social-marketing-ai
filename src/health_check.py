"""
Health Check — runs 20 minutes after the daily post agent via GitHub Actions.
Checks if today's post succeeded and auto-retries if possible.

Exit codes:
  0 — OK or successfully queued a retry
  1 — unrecoverable failure (token/permissions), manual action needed
"""

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_READY = Path("data/content_ready")
DATA_POSTED = Path("data/content_posted")


def _today() -> str:
    return date.today().strftime("%Y%m%d")


def _find_today_files(industry: str, today: str):
    pending = sorted(DATA_READY.glob(f"{industry}_{today}*_pending.json"))
    posted  = sorted(DATA_POSTED.glob(f"{industry}_{today}*_posted.json"))
    return pending, posted


def _shorten_prompt(prompt: str, limit: int = 350) -> str:
    if len(prompt) <= limit:
        return prompt
    cut = prompt[:limit]
    last_period = cut.rfind(".")
    return (cut[:last_period + 1] if last_period > limit * 0.6 else cut).strip()


def _write_retry_pending(content: dict, industry: str, post_type: str) -> Path:
    """Write a new pending file (triggers post_to_facebook.yml via path filter)."""
    DATA_READY.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "image_pending" if post_type == "image" else "pending"
    path = DATA_READY / f"{industry}_{ts}_{suffix}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
    logger.info(f"Retry pending file written: {path.name}")
    return path


def _load_brand_config(industry: str) -> dict:
    path = Path(f"config/industries/{industry}.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_posting_day(industry: str, brand_config: dict) -> tuple[bool, str]:
    """Return (is_posting_day, reason) based on post_interval_days config."""
    interval = brand_config.get("posting_schedule", {}).get("post_interval_days", 1)
    if interval <= 1:
        return True, "daily posting — every day is a posting day"

    cutoff = date.today() - timedelta(days=interval - 1)
    recent = []
    for f in list(DATA_POSTED.glob(f"{industry}_*_posted.json")) + \
             list(DATA_READY.glob(f"{industry}_*_pending.json")):
        m = re.search(r'_(\d{8})_', f.name)
        if m:
            file_date = datetime.strptime(m.group(1), "%Y%m%d").date()
            if file_date >= cutoff:
                recent.append(file_date)

    if recent:
        days_ago = (date.today() - max(recent)).days
        next_in  = interval - days_ago
        return False, f"not a posting day — last post {days_ago}d ago, next in {next_in}d (interval: every {interval}d)"

    return True, f"posting due — no post in the last {interval} days"


def main():
    parser = argparse.ArgumentParser(description="Post health check and auto-retry")
    parser.add_argument("--industry", default="velocx_nz")
    args = parser.parse_args()

    today = _today()
    logger.info(f"=== Health Check | {args.industry} | {today} ===")

    # Skip gracefully on non-posting days
    brand_config = _load_brand_config(args.industry)
    posting_day, reason = _is_posting_day(args.industry, brand_config)
    if not posting_day:
        logger.info(f"✅ {reason} — nothing to check.")
        return 0

    pending_files, posted_files = _find_today_files(args.industry, today)
    logger.info(f"Pending : {[f.name for f in pending_files] or 'none'}")
    logger.info(f"Posted  : {[f.name for f in posted_files] or 'none'}")

    # -------------------------------------------------------------------------
    # Case A — posted file exists, check platform results
    # -------------------------------------------------------------------------
    if posted_files:
        posted_data = json.loads(posted_files[-1].read_text(encoding="utf-8"))
        results = posted_data.get("results", {})
        failures = {
            p: r for p, r in results.items()
            if not r.get("success") and not r.get("skipped")
        }

        if not failures:
            logger.info("✅ All platforms posted successfully — no action needed.")
            return 0

        # Case B — posted with platform failures
        logger.warning(f"⚠️  Platform failures: {list(failures.keys())}")
        for platform, result in failures.items():
            error = result.get("error", "unknown")
            logger.error(f"  {platform}: {error}")

        # Check for unrecoverable auth errors
        all_errors = " ".join(r.get("error", "") for r in failures.values()).lower()
        if any(kw in all_errors for kw in ["token", "oauth", "session", "permission", "#200"]):
            logger.error("❌ Facebook auth/permission error — cannot fix automatically.")
            logger.error("   ACTION REQUIRED: refresh FACEBOOK_ACCESS_TOKEN in GitHub Secrets.")
            sys.exit(1)

        # Retry — rewrite pending file from the archived content
        content   = posted_data.get("content", {})
        post_type = content.get("type", "text")
        content["retry"] = True
        _write_retry_pending(content, args.industry, post_type)
        logger.info("↺  Retry pending file written — post_to_facebook.yml will re-trigger.")
        return 0

    # -------------------------------------------------------------------------
    # Case C — pending file exists but nothing posted yet
    # -------------------------------------------------------------------------
    if pending_files:
        logger.warning("⚠️  Pending file found but no posted file — GitHub Actions may have failed.")
        content   = json.loads(pending_files[-1].read_text(encoding="utf-8"))
        post_type = content.get("type", "text")

        # Fix long image prompts that caused Pollinations 500 errors
        if post_type == "image":
            for platform_key in ("facebook", "instagram", "tiktok"):
                pf = content.get(platform_key, {})
                prompt = pf.get("image_prompt", "")
                if len(prompt) > 400:
                    logger.info(f"  Shortening image_prompt: {len(prompt)} → 350 chars")
                    pf["image_prompt"] = _shorten_prompt(prompt, 350)
                    content[platform_key] = pf

        # Remove old pending file; write a new one to trigger GitHub Actions path filter
        for pf in pending_files:
            pf.unlink()
            logger.info(f"  Removed stale pending file: {pf.name}")

        content["retry"] = True
        _write_retry_pending(content, args.industry, post_type)
        logger.info("↺  Rewrote pending file — GitHub Actions will re-trigger.")
        return 0

    # -------------------------------------------------------------------------
    # Case D — posting was due today but nothing was generated
    # -------------------------------------------------------------------------
    logger.error("❌ No pending or posted files found — scheduler may have failed.")
    logger.error("   Trigger manually: GitHub Actions → Schedule → Run workflow → Force post.")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
