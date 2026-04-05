"""
Content Generator — uses Claude API to create platform-tailored social media posts.
"""

import json
import random
import anthropic
from datetime import datetime


def _build_prompt(industry_config: dict, platform: str, content_type: str) -> str:
    cfg = industry_config
    day_of_week = datetime.now().strftime("%A")
    hashtags = " ".join(
        cfg["hashtags"]["core"][:3] + cfg["hashtags"].get(platform, [])[:3]
    )

    platform_guidelines = {
        "facebook": (
            "Facebook post: conversational, 150-250 words, can include a question to drive comments, "
            "suited for link sharing and community engagement. No markdown formatting."
        ),
        "instagram": (
            "Instagram caption: visually descriptive, 100-150 words, use line breaks for readability, "
            "emoji-friendly but not excessive, end with a call-to-action. No markdown formatting."
        ),
        "tiktok": (
            "TikTok video description: punchy, 50-80 words, hook in the first line, "
            "high energy, trendy language appropriate for short-form video content. No markdown formatting."
        ),
    }

    return f"""You are a social media content creator for a {cfg['display_name']} business.

Business description: {cfg['description']}
Tone: {cfg['tone']}
Target audience: {cfg['target_audience']}
Today is {day_of_week}.
Content type for this post: {content_type}
Content pillars to draw from: {', '.join(cfg['content_pillars'])}

Write a single {platform_guidelines[platform]}

The post should feel fresh, relevant to today being {day_of_week}, and naturally include these hashtags at the end:
{hashtags}

Return ONLY the post text with hashtags. No explanations, no labels, no quotes around the output."""


def generate_posts(industry_config: dict, api_key: str) -> dict:
    """
    Generate one post per platform for the given industry config.
    Returns dict: { 'facebook': '...', 'instagram': '...', 'tiktok': '...' }
    """
    client = anthropic.Anthropic(api_key=api_key)
    platforms = industry_config.get("platforms", ["facebook", "instagram", "tiktok"])
    content_types = industry_config.get("content_types", ["tip"])

    posts = {}
    for platform in platforms:
        content_type = random.choice(content_types)
        prompt = _build_prompt(industry_config, platform, content_type)

        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        posts[platform] = message.content[0].text.strip()

    return posts
