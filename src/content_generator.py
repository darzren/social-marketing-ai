"""
Content Generator — reads pre-generated posts from a timestamped JSON file
written by the Claude Code remote agent into data/content_ready/.

Filename format: <industry>_YYYYMMDD_HHMMSS_pending.json
e.g.  velocx_nz_20260405_090300_pending.json
"""

import json
from datetime import datetime
from pathlib import Path

DATA_READY = Path("data/content_ready")
DATA_POSTED = Path("data/content_posted")


def load_pending_posts(industry: str) -> tuple[dict, Path]:
    """
    Find and load the latest pending post for the given industry.

    Returns (posts dict, source path) so the caller can archive it.
    Raises FileNotFoundError if nothing is pending.
    """
    DATA_READY.mkdir(parents=True, exist_ok=True)
    # Match both formats:
    #   velocx_nz_pending.json          (legacy, no timestamp)
    #   velocx_nz_20260405_090300_pending.json  (timestamped)
    matches = sorted(DATA_READY.glob(f"{industry}*_pending.json"))
    if not matches:
        raise FileNotFoundError(
            f"No pending posts found in {DATA_READY} for industry '{industry}'.\n"
            "The Claude agent must write a pending file before calling this script."
        )
    # Use the most recent one (sorted alphabetically = chronologically by timestamp)
    pending_path = matches[-1]
    with open(pending_path, encoding="utf-8") as f:
        posts = json.load(f)
    return posts, pending_path


def archive_as_posted(pending_path: Path, industry: str, results: dict) -> Path:
    """
    Move the pending file to content_posted with full results embedded.
    Filename: <industry>_YYYYMMDD_HHMMSS_posted.json
    """
    DATA_POSTED.mkdir(parents=True, exist_ok=True)

    # Derive timestamp from original pending filename, or use now
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
        "content": results.get("generated", {}),
        "results": results.get("platforms", {}),
    }
    with open(posted_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    # Remove the pending file
    pending_path.unlink()

    return posted_path
