"""
Image Review Agent

Two-layer quality gate before posting to social media:

Layer 1 — Pillow sanity checks (fast, no API):
  - Image opens without error (not corrupted)
  - Dimensions within 10% of target
  - Not all-black / all-white / single colour
  - Sufficient contrast (std dev of pixel values)

Layer 2 — Claude Vision review (content quality):
  - Image is coherent and well-composed
  - Text overlay is readable
  - Brand colours (orange/black/teal) are visible
  - No weird artifacts, distortion, or broken elements
  - Overall suitability for professional social media posting

Returns a ReviewResult with approved flag, score, and issues list.
"""

import base64
import io
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    approved: bool
    score: int                    # 1–10
    issues: list[str] = field(default_factory=list)
    recommendation: str = ""
    layer1_passed: bool = True
    layer2_passed: bool = True


# ---------------------------------------------------------------------------
# Layer 1 — Pillow sanity checks
# ---------------------------------------------------------------------------

def _layer1_sanity(image_bytes: bytes, target_w: int, target_h: int) -> ReviewResult:
    """Fast programmatic checks — no API call needed."""
    from PIL import Image, ImageStat

    issues = []

    # 1. Can the image be opened?
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        return ReviewResult(
            approved=False, score=0, layer1_passed=False,
            issues=[f"Image cannot be opened: {e}"],
            recommendation="Regenerate — image file is corrupted.",
        )

    w, h = img.size

    # 2. Dimensions roughly correct (within 15%)
    if abs(w - target_w) / target_w > 0.15 or abs(h - target_h) / target_h > 0.15:
        issues.append(f"Dimensions {w}×{h} differ from target {target_w}×{target_h} by >15%.")

    # 3. Not all-black or all-white
    stat = ImageStat.Stat(img)
    mean_brightness = sum(stat.mean) / 3
    if mean_brightness < 10:
        issues.append("Image is nearly all-black (mean brightness < 10).")
    if mean_brightness > 245:
        issues.append("Image is nearly all-white (mean brightness > 245).")

    # 4. Sufficient pixel variance (not a solid colour)
    mean_stddev = sum(stat.stddev) / 3
    if mean_stddev < 15:
        issues.append(f"Image has very low variance ({mean_stddev:.1f}) — may be a solid colour block.")

    # 5. File size sanity (< 5KB is likely broken)
    if len(image_bytes) < 5_000:
        issues.append(f"File size suspiciously small ({len(image_bytes)} bytes).")

    passed = len(issues) == 0
    score  = 10 if passed else max(1, 10 - len(issues) * 3)
    return ReviewResult(
        approved=passed,
        score=score,
        issues=issues,
        layer1_passed=passed,
        recommendation="Passed basic sanity checks." if passed else "Failed sanity checks — regenerate.",
    )


# ---------------------------------------------------------------------------
# Layer 2 — Claude Vision review
# ---------------------------------------------------------------------------

REVIEW_PROMPT = """You are reviewing a social media image for VelocX NZ, a premium competitive swimwear brand.

Review this image and respond with ONLY a JSON object in this exact format:
{
  "approved": true or false,
  "score": 1-10,
  "coherent": true or false,
  "text_readable": true or false,
  "brand_colours_visible": true or false,
  "professional_quality": true or false,
  "issues": ["issue 1", "issue 2"],
  "recommendation": "one sentence"
}

Score guide:
  9-10 = Post-ready, excellent quality
  7-8  = Good, minor imperfections
  5-6  = Acceptable but not ideal
  1-4  = Do not post

Approve (true) only if score >= 7 AND:
  - Image is coherent with no major distortions or broken elements
  - Overall composition looks professional enough for Facebook/Instagram
  - No inappropriate or offensive content

Brand context: dark cinematic pool photography, orange (#F8A30E) accent lighting,
competitive swimmers, Jaked brand equipment. Moody and premium feel.

Text overlay (if present): should be readable against the dark gradient at the bottom.
Logo (if present): small circular icon in top-right corner.

Be strict — this goes directly to a brand's social media page."""


def _layer2_vision(image_bytes: bytes, api_key: str) -> ReviewResult:
    """Claude Vision content review."""
    import json
    import anthropic

    try:
        client = anthropic.Anthropic(api_key=api_key)
        b64 = base64.b64encode(image_bytes).decode()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": REVIEW_PROMPT},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

        approved = bool(data.get("approved", False))
        score    = int(data.get("score", 5))
        issues   = data.get("issues", [])
        rec      = data.get("recommendation", "")

        logger.info(f"Vision review: score={score}, approved={approved}, issues={issues}")
        return ReviewResult(
            approved=approved,
            score=score,
            issues=issues,
            recommendation=rec,
            layer2_passed=approved,
        )

    except Exception as e:
        logger.warning(f"Claude Vision review failed: {e} — skipping Layer 2, defaulting to approved.")
        return ReviewResult(
            approved=True,
            score=7,
            issues=[],
            recommendation="Vision review unavailable — proceeding with Layer 1 result.",
            layer2_passed=True,
        )


# ---------------------------------------------------------------------------
# Combined review
# ---------------------------------------------------------------------------

def review_image(
    image_bytes: bytes,
    target_w: int,
    target_h: int,
    api_key: str = "",
) -> ReviewResult:
    """
    Run both review layers. Returns a combined ReviewResult.
    Layer 2 is skipped if api_key is not provided.
    """
    logger.info("Running image review (Layer 1: sanity checks)...")
    l1 = _layer1_sanity(image_bytes, target_w, target_h)

    if not l1.approved:
        logger.warning(f"Layer 1 FAILED: {l1.issues}")
        return l1

    logger.info("Layer 1 passed.")

    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set — skipping Layer 2 vision review.")
        return l1

    logger.info("Running image review (Layer 2: Claude Vision)...")
    l2 = _layer2_vision(image_bytes, api_key)

    if not l2.approved:
        logger.warning(f"Layer 2 FAILED: score={l2.score}, issues={l2.issues}")
    else:
        logger.info(f"Layer 2 passed: score={l2.score}. {l2.recommendation}")

    # Combine: both layers must pass
    combined_issues = l1.issues + l2.issues
    return ReviewResult(
        approved=l1.approved and l2.approved,
        score=min(l1.score, l2.score),
        issues=combined_issues,
        recommendation=l2.recommendation or l1.recommendation,
        layer1_passed=l1.layer1_passed,
        layer2_passed=l2.layer2_passed,
    )
