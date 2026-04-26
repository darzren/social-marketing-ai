"""
Instagram posting via Meta Graph API (Instagram Graph API).
Requires an Instagram Business or Creator account linked to a Facebook Page.
Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing

Note: Instagram requires a media URL (image/video) for feed posts.
This module posts as a text-only "caption" using a placeholder image approach,
or you can provide image_url for a real image post.
"""

import time
import requests

GRAPH = "https://graph.facebook.com/v21.0"


def post(caption: str, ig_user_id: str, access_token: str, image_url: str = None) -> dict:
    """
    Post to Instagram. Requires an image URL for feed posts.

    Returns:
        dict with 'success' bool and 'post_id' or 'error'
    """
    if not image_url:
        return {
            "success": False,
            "error": "Instagram requires an image_url. Set INSTAGRAM_DEFAULT_IMAGE_URL in .env or pass one per post.",
            "skipped": True,
        }

    # Step 1: Create media container
    container_resp = requests.post(
        f"{GRAPH}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": access_token},
        timeout=30,
    )
    container_data = container_resp.json()

    if container_resp.status_code != 200 or "id" not in container_data:
        error = container_data.get("error", {}).get("message", container_resp.text)
        return {"success": False, "error": f"Container creation failed: {error}"}

    creation_id = container_data["id"]

    # Step 2: Poll until container status is FINISHED (Instagram processes the image async)
    for attempt in range(12):  # up to ~60 seconds
        time.sleep(5)
        status_resp = requests.get(
            f"{GRAPH}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        status = status_resp.json().get("status_code", "")
        if status == "FINISHED":
            break
        if status == "ERROR":
            return {"success": False, "error": "Container processing failed (status ERROR)"}
    else:
        return {"success": False, "error": "Container not ready after 60s — timed out"}

    # Step 3: Publish the ready container
    publish_resp = requests.post(
        f"{GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    publish_data = publish_resp.json()

    if publish_resp.status_code == 200 and "id" in publish_data:
        return {"success": True, "post_id": publish_data["id"]}
    else:
        error = publish_data.get("error", {}).get("message", publish_resp.text)
        return {"success": False, "error": f"Publish failed: {error}"}
