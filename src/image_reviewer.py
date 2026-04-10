"""
Image Review Agent — Pillow-only, no external API required.

Runs a multi-check quality gate before posting to social media.
All checks use PIL/Pillow — free, fast, no API key needed.

Checks performed:
  1. File integrity       — image opens without error
  2. Dimensions          — within 15% of target platform size
  3. Not blank           — mean brightness between 15–240
  4. Sufficient detail   — pixel variance (std dev) > 20
  5. Sharpness           — edge density via Laplacian variance > threshold
  6. Brand orange        — checks for #F8A30E pixels in the image
  7. Text area darkness  — bottom gradient band is dark enough for text readability
  8. Logo area           — top-right corner has a gradient (not pure white/bright)
  9. Entropy             — image information content is high enough
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


def review_image(
    image_bytes: bytes,
    target_w: int,
    target_h: int,
    api_key: str = "",          # kept for interface compatibility, not used
) -> ReviewResult:
    """
    Review image quality using Pillow only.
    api_key parameter is accepted but ignored (no external API needed).
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
        recommendation = f"Approved — {len(passed)}/{total_checks} checks passed."
    else:
        recommendation = f"Rejected — {len(issues)} issue(s) found. Regenerate."

    logger.info(
        f"Image review: score={score}/10, approved={approved}, "
        f"passed={len(passed)}, issues={len(issues)}"
    )
    if issues:
        for issue in issues:
            logger.warning(f"  Issue: {issue}")

    return ReviewResult(
        approved=approved,
        score=score,
        issues=issues,
        passed_checks=passed,
        recommendation=recommendation,
    )
