"""
TikTok posting via TikTok Content Posting API (FILE_UPLOAD method).
Docs: https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide

Uses FILE_UPLOAD to avoid domain ownership verification required by PULL_FROM_URL.
The video file is read from the local filesystem (checked out in the runner).
"""

import math
import time
from pathlib import Path

import requests

GRAPH = "https://open.tiktokapis.com/v2"


def post(description: str, access_token: str, video_path: str = None, title: str = None) -> dict:
    """
    Post a video to TikTok using FILE_UPLOAD method.

    video_path — local path to the .mp4 file (e.g. assets/videos/brand.mp4)
    title      — optional short title shown as the TikTok caption (max 150 chars).
                 If omitted, falls back to the first 150 chars of description.

    Returns:
        dict with 'success' bool and 'publish_id' or 'error'
    """
    if not video_path or not Path(video_path).exists():
        return {
            "success": False,
            "error": f"TikTok video file not found: {video_path}",
            "skipped": True,
        }

    if title:
        # Caller provided a clean title — enforce 150-char hard limit
        caption = title[:150].rsplit(" ", 1)[0] if len(title) > 150 else title
    else:
        # Fall back to truncating description
        caption = description[:150].rsplit(" ", 1)[0] if len(description) > 150 else description

    post_info = {
        "title":         caption,
        "privacy_level": "SELF_ONLY",  # sandbox only; use PUBLIC_TO_EVERYONE in production
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json; charset=UTF-8",
    }

    video_size   = Path(video_path).stat().st_size
    chunk_size   = min(video_size, 64 * 1024 * 1024)
    total_chunks = 1

    # Step 1: Initialise upload
    init_resp = requests.post(
        f"{GRAPH}/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": post_info,
            "source_info": {
                "source":            "FILE_UPLOAD",
                "video_size":        video_size,
                "chunk_size":        chunk_size,
                "total_chunk_count": total_chunks,
            },
        },
        timeout=30,
    )
    init_data = init_resp.json()
    if init_resp.status_code != 200 or init_data.get("error", {}).get("code") != "ok":
        error = init_data.get("error", {}).get("message", init_resp.text)
        return {"success": False, "error": f"Upload init failed: {error}"}

    upload_url = init_data["data"]["upload_url"]
    publish_id = init_data["data"]["publish_id"]

    # Step 2: Upload chunks
    with open(video_path, "rb") as f:
        for i in range(total_chunks):
            chunk = f.read(chunk_size)
            start  = i * chunk_size
            end    = start + len(chunk) - 1
            upload_resp = requests.put(
                upload_url,
                headers={
                    "Content-Type":   "video/mp4",
                    "Content-Range":  f"bytes {start}-{end}/{video_size}",
                    "Content-Length": str(len(chunk)),
                },
                data=chunk,
                timeout=120,
            )
            if upload_resp.status_code not in (200, 201, 206):
                return {"success": False, "error": f"Chunk {i} upload failed: {upload_resp.status_code} {upload_resp.text[:200]}"}

    # Step 3: Poll until published
    for _ in range(20):  # up to ~2 minutes
        time.sleep(6)
        status_resp = requests.post(
            f"{GRAPH}/post/publish/status/fetch/",
            headers=headers,
            json={"publish_id": publish_id},
            timeout=30,
        )
        status = status_resp.json().get("data", {}).get("status", "")
        if status == "PUBLISH_COMPLETE":
            return {"success": True, "publish_id": publish_id}
        if status in ("FAILED", "SPAM_RISK_TOO_MANY_POSTS", "SPAM_RISK_USER_BANNED_FROM_POSTING"):
            return {"success": False, "error": f"TikTok publish failed: {status}"}

    return {"success": False, "error": "TikTok publish timed out after 2 minutes"}
