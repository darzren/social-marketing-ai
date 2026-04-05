"""
TikTok posting via TikTok Content Posting API.
Docs: https://developers.tiktok.com/doc/content-posting-api-get-started

Note: TikTok's Content Posting API requires VIDEO content.
This module posts a video from a public URL using the "PULL_FROM_URL" method.
For text-only posts, TikTok does not currently offer a public API endpoint.

If you don't have a video URL, set TIKTOK_VIDEO_URL in your .env to a
short branded video/clip. The generated caption is used as the video description.
"""

import requests


def post(description: str, access_token: str, video_url: str = None) -> dict:
    """
    Post a video to TikTok with the generated description as caption.

    Returns:
        dict with 'success' bool and 'publish_id' or 'error'
    """
    if not video_url:
        return {
            "success": False,
            "error": "TikTok requires a video_url. Set TIKTOK_VIDEO_URL in .env.",
            "skipped": True,
        }

    # Truncate description to TikTok's 2200 char limit
    description = description[:2200]

    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    payload = {
        "post_info": {
            "title": description,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    data = response.json()

    if response.status_code == 200 and data.get("error", {}).get("code") == "ok":
        return {"success": True, "publish_id": data.get("data", {}).get("publish_id")}
    else:
        error = data.get("error", {}).get("message", response.text)
        return {"success": False, "error": error}
