"""
Facebook posting via Meta Graph API.
Docs: https://developers.facebook.com/docs/pages/publishing
"""

import requests


def post(message: str, page_id: str, access_token: str) -> dict:
    """
    Post a text message to a Facebook Page.

    Returns:
        dict with 'success' bool and 'post_id' or 'error'
    """
    url = f"https://graph.facebook.com/v21.0/{page_id}/feed"
    payload = {
        "message": message,
        "access_token": access_token,
    }

    response = requests.post(url, data=payload, timeout=30)
    data = response.json()

    if response.status_code == 200 and "id" in data:
        return {"success": True, "post_id": data["id"]}
    else:
        error = data.get("error", {}).get("message", response.text)
        return {"success": False, "error": error}
