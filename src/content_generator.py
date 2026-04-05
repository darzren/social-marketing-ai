"""
Content Generator — reads pre-generated posts from a timestamped JSON file
written by the Claude Code remote agent into data/content_ready/.

Filename format: <industry>_YYYYMMDD_HHMMSS_pending.json
e.g.  velocx_nz_20260405_090300_pending.json

Pending file format (structured, current):
{
  "facebook": {
    "content_angle": "...",
    "post_text": "...",
    "hashtags": ["#Tag1", "#Tag2"],
    "call_to_action": "..."
  }
}

Legacy format (flat string, still supported):
{
  "facebook": "full post text with hashtags"
}
"""

import json
from datetime import datetime
from pathlib import Path

DATA_READY = Path("data/content_ready")
DATA_POSTED = Path("data/content_posted")


def _compose_post(platform_value: str | dict) -> str:
    """
    Compose a final post string from either:
    - A structured dict: { post_text, hashtags, ... }
    - A legacy flat string (passed through unchanged)
    """
    if isinstance(platform_value, str):
        return platform_value

    post_text = platform_value.get("post_text", "").strip()
    hashtags = platform_value.get("hashtags", [])
    hashtag_line = " ".join(hashtags)

    return f"{post_text}\n\n{hashtag_line}".strip()


def load_pending_posts(industry: str) -> tuple[dict, Path]:
    """
    Find and load the latest pending post for the given industry.
    Composes final post strings ready for platform APIs.

    Returns (posts dict, source path).
    posts dict shape: { 'facebook': 'composed string', ... }
    """
    DATA_READY.mkdir(parents=True, exist_ok=True)
    matches = sorted(DATA_READY.glob(f"{industry}*_pending.json"))
    if not matches:
        raise FileNotFoundError(
            f"No pending posts found in {DATA_READY} for industry '{industry}'.\n"
            "The Claude agent must write a pending file before calling this script."
        )

    pending_path = matches[-1]
    with open(pending_path, encoding="utf-8") as f:
        raw = json.load(f)

    # Compose final strings for each platform, preserving raw for archiving
    composed = {platform: _compose_post(value) for platform, value in raw.items()}
    return composed, pending_path, raw


def archive_as_posted(pending_path: Path, industry: str, results: dict, raw: dict) -> Path:
    """
    Archive the pending file to content_posted with full results embedded.
    Stores both the raw structured content and the composed post strings.
    Filename: <industry>_YYYYMMDD_HHMMSS_posted.json
    """
    DATA_POSTED.mkdir(parents=True, exist_ok=True)

    stem = pending_path.stem  # e.g. velocx_nz_20260405_090300_pending
    timestamp_part = stem.replace(f"{industry}_", "").replace("_pending", "").strip("_")
    if not timestamp_part:
        timestamp_part = datetime.now().strftime("%Y%m%d_%H%M%S")

    posted_filename = f"{industry}_{timestamp_part}_posted.json"
    posted_path = DATA_POSTED / posted_filename

    archive = {
        "industry": industry,
        "generated_at": timestamp_part,
        "posted_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "content": raw,
        "results": results.get("platforms", {}),
    }
    with open(posted_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    pending_path.unlink()
    return posted_path
