"""
Content Generator — reads pre-generated posts from a JSON file written by the
Claude Code remote agent. No Anthropic API key required.

The remote agent generates the posts as part of its own reasoning and writes
them to data/content_ready/<industry>_pending.json before calling post.py.
"""

import json
from pathlib import Path


def load_pending_posts(industry: str) -> dict:
    """
    Load posts written by the Claude agent from data/content_ready/.

    Expected file: data/content_ready/<industry>_pending.json
    Expected shape: { "facebook": "...", "instagram": "...", "tiktok": "..." }
    """
    pending_path = Path(f"data/content_ready/{industry}_pending.json")
    if not pending_path.exists():
        raise FileNotFoundError(
            f"No pending posts found at {pending_path}.\n"
            "The Claude agent must write posts there before calling this script."
        )
    with open(pending_path, encoding="utf-8") as f:
        posts = json.load(f)

    # Clean up after loading so stale posts are never reused
    pending_path.unlink()
    return posts


def save_pending_posts(industry: str, posts: dict) -> Path:
    """
    Save generated posts to the pending file (used in local/API mode).
    """
    out_dir = Path("data/content_ready")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{industry}_pending.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)
    return out_path
