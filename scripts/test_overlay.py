"""
Local overlay test — applies logo overlay to:
  1. Your clean images (direct, best quality)
  2. A Pollinations.ai generated image (to verify AI path also works)

Usage:
    python scripts/test_overlay.py

Outputs saved to: test_output/
"""

import io
import random
import sys
import urllib.parse
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.image_generator import overlay_logo_and_text, PLATFORM_SPECS

OUTPUT_DIR  = Path("test_output")
LOGO_PATH   = Path("assets/logos/velocx_nz_logo.png")
CLEAN_DIR   = Path("assets/clean_images")
TEST_PROMPT = "competitive swimmer butterfly stroke, dark cinematic pool, dramatic lighting"
OVERLAY_TEXT = "Built to race."


def load_and_crop(image_path: Path, target_w: int, target_h: int) -> bytes:
    """Load a clean image, crop/resize to the target platform dimensions."""
    img = Image.open(image_path).convert("RGB")
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio    = src_w / src_h

    if src_ratio > target_ratio:
        # Source is wider — crop sides
        new_w = int(src_h * target_ratio)
        left  = (src_w - new_w) // 2
        img   = img.crop((left, 0, left + new_w, src_h))
    else:
        # Source is taller — crop top/bottom (keep top — subject usually there)
        new_h = int(src_w / target_ratio)
        img   = img.crop((0, 0, src_w, new_h))

    img = img.resize((target_w, target_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def download_pollinations(width: int, height: int) -> bytes | None:
    try:
        seed    = random.randint(1, 999999)
        encoded = urllib.parse.quote(TEST_PROMPT[:400])
        url     = (f"https://image.pollinations.ai/prompt/{encoded}"
                   f"?width={width}&height={height}&model=flux&nologo=true&seed={seed}")
        print(f"    Downloading from Pollinations.ai ({width}x{height})...")
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"    Pollinations failed: {e}")
        return None


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    clean_images = [p for p in CLEAN_DIR.iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.stem != ".gitkeep"]

    for platform, spec in PLATFORM_SPECS.items():
        w = spec["pollinations_w"]
        h = spec["pollinations_h"]
        print(f"\n{'='*55}")
        print(f"Platform: {platform.upper()}  ({w}x{h})")

        # --- Test on each clean image ---
        for img_path in clean_images:
            print(f"  Clean image: {img_path.name}")
            image_bytes = load_and_crop(img_path, w, h)
            result = overlay_logo_and_text(
                image_bytes=image_bytes,
                logo_path=LOGO_PATH,
                platform=platform,
                overlay_text=OVERLAY_TEXT,
            )
            stem     = img_path.stem[:30].replace(" ", "_")
            out_path = OUTPUT_DIR / f"{platform}_{stem}.jpg"
            out_path.write_bytes(result)
            print(f"    Saved: {out_path.name}")

        # --- Test on one Pollinations image ---
        print(f"  AI generated image:")
        ai_bytes = download_pollinations(w, h)
        if ai_bytes:
            result = overlay_logo_and_text(
                image_bytes=ai_bytes,
                logo_path=LOGO_PATH,
                platform=platform,
                overlay_text=OVERLAY_TEXT,
            )
            out_path = OUTPUT_DIR / f"{platform}_ai_generated.jpg"
            out_path.write_bytes(result)
            print(f"    Saved: {out_path.name}")

    print(f"\nDone. Opening test_output/ ...")
    import subprocess
    subprocess.Popen(["explorer", str(OUTPUT_DIR.resolve())])


if __name__ == "__main__":
    main()
