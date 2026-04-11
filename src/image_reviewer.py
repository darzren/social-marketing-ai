"""
Image Review Agent — two optional layers.

Layer 1 (always runs, no API):
  Pillow sanity + quality checks — catches corrupted, blank, wrong-size,
  missing overlay, unreadable text area, low-detail images.

Layer 2 (optional, needs ANTHROPIC_API_KEY):
  Claude Vision (Haiku) — checks content the Pillow layer can't see:
  correct subject matter, no weird AI artifacts, brand aesthetic match,
  professional composition. Costs ~$0.001 per image (~$0.27/year at 1/day).

If ANTHROPIC_API_KEY is not set, Layer 1 alone is used and the image is
posted as long as it passes all technical checks.
"""

import io
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Minimum acceptable scores per check
THRESHOLDS = {
    "min_brightness":      15,    # avoid near-black images
    "max_brightness":      240,   # avoid near-white/overexposed
    "min_stddev":          20,    # avoid solid-colour blocks
    "min_edge_density":    0.02,  # fraction of edge pixels (sharpness)
    "min_entropy":         5.5,   # bits of information per pixel
    "brand_orange_pct":    0.003, # at least 0.3% pixels near brand orange
    "text_area_max_mean":  100,   # bottom gradient must be dark (mean < 100)
    "min_file_kb":         20,    # suspiciously small files
}

BRAND_ORANGE = (248, 163, 14)    # #F8A30E
ORANGE_TOLERANCE = 40            # per-channel tolerance for colour matching


@dataclass
class ReviewResult:
    approved: bool
    score: int                      # 1–10
    issues: list[str] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    recommendation: str = ""


def _colour_distance(px: tuple, target: tuple) -> int:
    return max(abs(px[i] - target[i]) for i in range(3))


# ---------------------------------------------------------------------------
# Layer 2 — Claude Vision (optional)
# ---------------------------------------------------------------------------

VISION_PROMPT = """You are reviewing an AI-generated social media image for VelocX NZ,
a premium competitive swimwear brand (Jaked brand, New Zealand).

Respond with ONLY a JSON object — no other text:
{
  "approved": true or false,
  "score": 1-10,
  "subject_correct": true or false,
  "no_artifacts": true or false,
  "brand_aesthetic": true or false,
  "issues": ["issue 1", "issue 2"],
  "recommendation": "one sentence"
}

Score guide: 9-10 excellent, 7-8 good, 5-6 marginal, 1-4 reject.
Approve (true) only if score >= 7 AND no major issues.

What to check:
- Subject is swimming / swimwear / pool / athlete related (not random scene)
- No severe AI artifacts (melted body parts, extra limbs, broken text on objects)
- Dark cinematic pool aesthetic — moody, premium, athletic feel
- Looks like professional sports photography, not generic stock photo
- Brand orange (#F8A30E) accent lighting visible somewhere
- Bottom area is darker (for text overlay readability)

Be strict — this goes directly to a brand's social media page."""


def _layer2_vision(image_bytes: bytes, api_key: str) -> ReviewResult:
    """Claude Vision content review — ~$0.001 per image."""
    import base64
    import json

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        b64 = base64.b64encode(image_bytes).decode()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
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
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data  = json.loads(raw.strip())

        approved = bool(data.get("approved", False))
        score    = int(data.get("score", 5))
        issues   = data.get("issues", [])
        rec      = data.get("recommendation", "")

        logger.info(f"Layer 2 (Vision): score={score}, approved={approved}")
        if issues:
            for issue in issues:
                logger.warning(f"  Vision issue: {issue}")

        return ReviewResult(
            approved=approved, score=score,
            issues=issues, recommendation=rec,
        )

    except ImportError:
        logger.warning("anthropic package not installed — skipping Layer 2.")
        return ReviewResult(approved=True, score=8, recommendation="Layer 2 skipped (package missing).")
    except Exception as e:
        logger.warning(f"Layer 2 vision review error: {e} — defaulting to approved.")
        return ReviewResult(approved=True, score=7, recommendation=f"Layer 2 unavailable: {e}")


# ---------------------------------------------------------------------------
# Combined review entry point
# ---------------------------------------------------------------------------

def review_image(
    image_bytes: bytes,
    target_w: int,
    target_h: int,
    api_key: str = "",
) -> ReviewResult:
    """
    Review image quality using Pillow only.
    api_key parameter is accepted but ignored (no external API needed).
    """
    """
    Run Layer 1 (Pillow) always. Run Layer 2 (Claude Vision) only if api_key is set.
    Both layers must pass for the image to be approved.
    """
    from PIL import Image, ImageFilter, ImageStat

    issues: list[str] = []
    passed: list[str] = []
    t = THRESHOLDS

    # ------------------------------------------------------------------
    # Check 1 — File integrity
    # ------------------------------------------------------------------
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        return ReviewResult(
            approved=False, score=0,
            issues=[f"Corrupted image file: {e}"],
            recommendation="Regenerate — image cannot be opened.",
        )
    passed.append("file_integrity")

    w, h = img.size

    # ------------------------------------------------------------------
    # Check 2 — Dimensions
    # ------------------------------------------------------------------
    w_diff = abs(w - target_w) / target_w
    h_diff = abs(h - target_h) / target_h
    if w_diff > 0.15 or h_diff > 0.15:
        issues.append(f"Dimensions {w}×{h} vs target {target_w}×{target_h} (>{15}% off).")
    else:
        passed.append("dimensions")

    # ------------------------------------------------------------------
    # Check 3 — Not blank (brightness)
    # ------------------------------------------------------------------
    stat = ImageStat.Stat(img)
    mean_brightness = sum(stat.mean) / 3
    if mean_brightness < t["min_brightness"]:
        issues.append(f"Image too dark (mean brightness {mean_brightness:.1f} < {t['min_brightness']}).")
    elif mean_brightness > t["max_brightness"]:
        issues.append(f"Image too bright/washed out (mean {mean_brightness:.1f} > {t['max_brightness']}).")
    else:
        passed.append("brightness")

    # ------------------------------------------------------------------
    # Check 4 — Pixel variance (not a solid colour block)
    # ------------------------------------------------------------------
    mean_stddev = sum(stat.stddev) / 3
    if mean_stddev < t["min_stddev"]:
        issues.append(f"Very low pixel variance ({mean_stddev:.1f}) — image may be a solid block.")
    else:
        passed.append("variance")

    # ------------------------------------------------------------------
    # Check 5 — Sharpness (Laplacian edge detection)
    # ------------------------------------------------------------------
    edges     = img.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    edge_mean = edge_stat.mean[0]
    edge_density = edge_mean / 255
    if edge_density < t["min_edge_density"]:
        issues.append(f"Image appears blurry or lacks detail (edge density {edge_density:.3f}).")
    else:
        passed.append("sharpness")

    # ------------------------------------------------------------------
    # Check 6 — Entropy (information content)
    # ------------------------------------------------------------------
    entropy = img.convert("L").entropy()
    if entropy < t["min_entropy"]:
        issues.append(f"Low image entropy ({entropy:.2f}) — image lacks visual complexity.")
    else:
        passed.append("entropy")

    # ------------------------------------------------------------------
    # Check 7 — Brand orange colour present
    # ------------------------------------------------------------------
    small = img.resize((100, 100))          # sample for speed
    pixels = list(small.getdata())
    orange_count = sum(
        1 for px in pixels
        if _colour_distance(px, BRAND_ORANGE) <= ORANGE_TOLERANCE
    )
    orange_pct = orange_count / len(pixels)
    if orange_pct < t["brand_orange_pct"]:
        issues.append(
            f"Brand orange (#F8A30E) not detected ({orange_pct*100:.2f}% pixels). "
            "Overlay may not have applied correctly."
        )
    else:
        passed.append("brand_orange")

    # ------------------------------------------------------------------
    # Check 8 — Text area darkness (bottom 30% should be dark for readability)
    # ------------------------------------------------------------------
    band_top  = int(h * 0.70)
    text_band = img.crop((0, band_top, w, h))
    text_stat = ImageStat.Stat(text_band)
    text_mean = sum(text_stat.mean) / 3
    if text_mean > t["text_area_max_mean"]:
        issues.append(
            f"Bottom text area too bright (mean {text_mean:.1f} > {t['text_area_max_mean']}). "
            "Text may not be readable against the background."
        )
    else:
        passed.append("text_area_darkness")

    # ------------------------------------------------------------------
    # Check 9 — File size sanity
    # ------------------------------------------------------------------
    size_kb = len(image_bytes) / 1024
    if size_kb < t["min_file_kb"]:
        issues.append(f"File suspiciously small ({size_kb:.1f}KB < {t['min_file_kb']}KB).")
    else:
        passed.append("file_size")

    # ------------------------------------------------------------------
    # Score and verdict
    # ------------------------------------------------------------------
    total_checks = len(passed) + len(issues)
    pass_rate    = len(passed) / total_checks if total_checks else 0
    score        = max(1, round(pass_rate * 10))

    # Hard-fail conditions (image should never be posted)
    hard_fails = [i for i in issues if any(kw in i for kw in
                  ["Corrupted", "too dark", "too bright", "solid block"])]

    approved = score >= 7 and len(hard_fails) == 0

    if approved:
        recommendation = f"Layer 1 passed — {len(passed)}/{total_checks} checks."
    else:
        recommendation = f"Layer 1 rejected — {len(issues)} issue(s). Regenerate."

    logger.info(
        f"Layer 1 (Pillow): score={score}/10, approved={approved}, "
        f"passed={len(passed)}/{total_checks}"
    )
    if issues:
        for issue in issues:
            logger.warning(f"  Layer 1 issue: {issue}")

    l1_result = ReviewResult(
        approved=approved, score=score,
        issues=issues, passed_checks=passed,
        recommendation=recommendation,
    )

    if not l1_result.approved:
        return l1_result

    # ------------------------------------------------------------------
    # Layer 2 — Claude Vision (only if API key provided)
    # ------------------------------------------------------------------
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set — Layer 2 skipped, using Layer 1 result.")
        return l1_result

    logger.info("Running Layer 2 (Claude Vision)...")
    l2 = _layer2_vision(image_bytes, api_key)

    combined_score  = min(l1_result.score, l2.score)
    combined_issues = l1_result.issues + l2.issues
    combined_passed = l1_result.approved and l2.approved

    return ReviewResult(
        approved=combined_passed,
        score=combined_score,
        issues=combined_issues,
        passed_checks=passed,
        recommendation=l2.recommendation or l1_result.recommendation,
    )
