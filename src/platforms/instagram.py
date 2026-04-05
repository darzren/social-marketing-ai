"""
Instagram posting via Meta Graph API (Instagram Graph API).
Requires an Instagram Business or Creator account linked to a Facebook Page.
Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing

Note: Instagram requires a media URL (image/video) for feed posts.
This module posts as a text-only "caption" using a placeholder image approach,
or you can provide image_url for a real image post.
"""

import requests


def post(caption: str, ig_user_id: str, access_token: str, image_url: str = None) -> dict:
    """
    Post to Instagram. Requires an image URL for feed posts.

    If no image_url is provided, the post will be skipped with an explanation.
    For production use, provide a relevant image URL per industry.

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
    container_url = f"https://graph.facebook.com/v21.0/{ig_user_id}/media"
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }
    container_resp = requests.post(container_url, data=container_payload, timeout=30)
    container_data = container_resp.json()

    if container_resp.status_code != 200 or "id" not in container_data:
        error = container_data.get("error", {}).get("message", container_resp.text)
        return {"success": False, "error": f"Container creation failed: {error}"}

    creation_id = container_data["id"]

    # Step 2: Publish the container
    publish_url = f"https://graph.facebook.com/v21.0/{ig_user_id}/media_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": access_token,
    }
    publish_resp = requests.post(publish_url, data=publish_payload, timeout=30)
    publish_data = publish_resp.json()

    if publish_resp.status_code == 200 and "id" in publish_data:
        return {"success": True, "post_id": publish_data["id"]}
    else:
        error = publish_data.get("error", {}).get("message", publish_resp.text)
        return {"success": False, "error": f"Publish failed: {error}"}
