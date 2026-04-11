"""
Performance Tracker — reads Facebook Page Insights and analyses the local post
archive to produce a structured insights file used by the strategy updater.

Runs weekly via GitHub Actions.

Usage:
    python src/performance_tracker.py --industry velocx_nz
    python src/performance_tracker.py --industry velocx_nz --days 60
"""

import argparse
import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_POSTED   = Path("data/content_posted")
DATA_INSIGHTS = Path("data/insights")
CONFIG_DIR    = Path("config/industries")

GRAPH_API     = "https://graph.facebook.com/v21.0"


# ---------------------------------------------------------------------------
# Facebook Insights API
# ---------------------------------------------------------------------------

def fetch_page_posts(page_id: str, access_token: str, days: int) -> list:
    """Fetch posts published in the last N days from the Facebook Page."""
    since = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    resp  = requests.get(
        f"{GRAPH_API}/{page_id}/posts",
        params={
            "fields":       "id,message,created_time,full_picture",
            "since":        since,
            "limit":        50,
            "access_token": access_token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        logger.warning(f"Could not fetch page posts: {resp.status_code} {resp.text[:200]}")
        return []
    return resp.json().get("data", [])


def fetch_post_insights(post_id: str, access_token: str) -> dict:
    """Fetch per-post engagement metrics."""
    resp = requests.get(
        f"{GRAPH_API}/{post_id}/insights",
        params={
            "metric":       "post_impressions,post_impressions_unique,"
                            "post_engaged_users,post_clicks,"
                            "post_reactions_by_type_total",
            "access_token": access_token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return {}
    result = {}
    for item in resp.json().get("data", []):
        val = item.get("values", [{}])
        result[item["name"]] = val[-1].get("value", 0) if val else 0
    return result


def fetch_facebook_insights(page_id: str, access_token: str, days: int) -> dict:
    """Pull page-level and per-post insights from Facebook."""
    posts = fetch_page_posts(page_id, access_token, days)
    logger.info(f"Fetched {len(posts)} posts from Facebook Page")

    post_data = []
    for post in posts[:25]:  # cap API calls
        metrics = fetch_post_insights(post["id"], access_token)
        created = post.get("created_time", "")
        hour    = int(created[11:13]) if len(created) >= 13 else None

        post_data.append({
            "id":         post["id"],
            "created":    created,
            "hour":       hour,
            "has_image":  bool(post.get("full_picture")),
            "impressions": metrics.get("post_impressions", 0),
            "reach":       metrics.get("post_impressions_unique", 0),
            "engagement":  metrics.get("post_engaged_users", 0),
            "clicks":      metrics.get("post_clicks", 0),
            "reactions":   metrics.get("post_reactions_by_type_total", 0),
        })

    if not post_data:
        return {"posts_analysed": 0, "note": "No posts found in period."}

    # Aggregate metrics
    avg_reach      = sum(p["reach"] for p in post_data) / len(post_data)
    avg_engagement = sum(p["engagement"] for p in post_data) / len(post_data)

    # Best hours by average engagement
    by_hour = defaultdict(list)
    for p in post_data:
        if p["hour"] is not None:
            by_hour[p["hour"]].append(p["engagement"])
    best_hours = sorted(
        by_hour.keys(),
        key=lambda h: sum(by_hour[h]) / len(by_hour[h]),
        reverse=True,
    )[:3]

    # Image vs text posts
    image_posts = [p for p in post_data if p["has_image"]]
    text_posts  = [p for p in post_data if not p["has_image"]]
    avg_img_eng = (sum(p["engagement"] for p in image_posts) / len(image_posts)
                   if image_posts else 0)
    avg_txt_eng = (sum(p["engagement"] for p in text_posts) / len(text_posts)
                   if text_posts else 0)

    return {
        "posts_analysed":       len(post_data),
        "avg_reach":            round(avg_reach),
        "avg_engagement":       round(avg_engagement),
        "best_posting_hours":   [f"{h:02d}:00" for h in best_hours],
        "image_avg_engagement": round(avg_img_eng),
        "text_avg_engagement":  round(avg_txt_eng),
        "image_outperforms_text": avg_img_eng > avg_txt_eng,
        "top_posts": sorted(post_data, key=lambda p: p["engagement"], reverse=True)[:5],
    }


# ---------------------------------------------------------------------------
# Local archive analysis
# ---------------------------------------------------------------------------

def analyse_local_archive(industry: str, days: int) -> dict:
    """Analyse content_posted/ files for content patterns and performance proxies."""
    cutoff = datetime.now() - timedelta(days=days)
    files  = sorted(DATA_POSTED.glob(f"{industry}_*_posted.json"))

    by_type        = defaultdict(list)
    by_image_type  = defaultdict(list)
    by_pillar      = defaultdict(int)
    angles_used    = []
    post_hours     = []
    hashtag_counts = defaultdict(int)

    for f in files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                continue

            data    = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", {})
            fb      = content.get("facebook", {})
            ptype   = content.get("type", "text")
            angle   = fb.get("content_angle", "")

            if angle:
                angles_used.append(angle)

            by_type[ptype].append(angle)

            if ptype == "image":
                img_type = fb.get("image_type", "unknown")
                by_image_type[img_type].append(angle)

            # Hashtag frequency
            for tag in fb.get("hashtags", []):
                hashtag_counts[tag] += 1

            # Extract hour from filename
            parts = f.stem.split("_")
            if len(parts) >= 3 and len(parts[2]) >= 2:
                try:
                    post_hours.append(int(parts[2][:2]))
                except ValueError:
                    pass

        except Exception as e:
            logger.warning(f"Could not parse {f.name}: {e}")

    most_used_hashtags = sorted(hashtag_counts.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        "total_posts":          sum(len(v) for v in by_type.values()),
        "by_type":              {k: len(v) for k, v in by_type.items()},
        "by_image_type":        {k: len(v) for k, v in by_image_type.items()},
        "most_used_hashtags":   most_used_hashtags,
        "recent_angles":        angles_used[-10:],
        "posting_hours":        post_hours,
        "most_common_hour":     (max(set(post_hours), key=post_hours.count)
                                 if post_hours else None),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Performance tracker")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    load_dotenv(f"config/credentials/{args.industry}.env", override=True)
    page_id      = os.getenv("FACEBOOK_PAGE_ID", "")
    access_token = os.getenv("FACEBOOK_ACCESS_TOKEN", "")

    logger.info(f"=== Performance Tracker | {args.industry} | {args.days} days ===")

    # Facebook API insights
    fb_insights: dict = {}
    if page_id and access_token:
        fb_insights = fetch_facebook_insights(page_id, access_token, args.days)
    else:
        logger.warning("Facebook credentials not set — skipping API insights.")
        fb_insights = {"note": "No credentials — API insights skipped."}

    # Local archive analysis
    local = analyse_local_archive(args.industry, args.days)
    logger.info(f"Local archive: {local['total_posts']} posts analysed")

    # Write insights file
    DATA_INSIGHTS.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DATA_INSIGHTS / f"{args.industry}_{ts}_insights.json"

    insights = {
        "industry":          args.industry,
        "generated_at":      datetime.now().isoformat(),
        "period_days":       args.days,
        "facebook_insights": fb_insights,
        "local_archive":     local,
    }

    out_path.write_text(json.dumps(insights, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Insights written: {out_path.name}")
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
