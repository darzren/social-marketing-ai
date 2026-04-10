"""
Local image post test — generates a fresh AI image and applies the brand overlay.
Always uses Pollinations.ai for generation (same as production).

Usage:
    python scripts/test_image_post.py
    python scripts/test_image_post.py --image-type gear_closeup
    python scripts/test_image_post.py --image-type lifestyle --text "Train harder.\nJaked by VelocX NZ"
    python scripts/test_image_post.py --platform facebook
    python scripts/test_image_post.py --use-clean   # use local clean images (faster, no internet)

Image types: race_action, training, gear_closeup, lifestyle, open_water, team
"""

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.image_generator import (
    PLATFORM_SPECS, PLATFORM_KEYS,
    pick_clean_image, load_clean_image, generate_image,
    overlay_logo_and_text,
    _compose_caption,
)
from src.image_reviewer import review_image

OUTPUT_DIR = Path("test_output")
LOGO_PATH  = Path("assets/logos/velocx_nz_logo.png")

SAMPLE_PENDING = {
    "type": "image",
    "facebook": {
        "content_angle": "The race start — 2 seconds that decide everything",
        "image_type": "race_action",
        "image_prompt": "competitive swimmer race dive off blocks, dark dramatic pool, orange accent lighting, cinematic",
        "overlay_text": "Built to race.\nJaked competitive swimwear\nvelocx.co.nz",
        "caption": (
            "The race starts before you hit the water.\n\n"
            "Elite swimmers know the first 15 metres are where medals are won — "
            "the dive, the underwater phase, the breakout stroke.\n\n"
            "Jaked's race suits are engineered to hold your streamline longer, "
            "so every race start works harder for you.\n\n"
            "What's your weakness off the blocks?"
        ),
        "engagement_bait": "Drop a fire emoji if you drill your starts.",
        "hashtags": [
            "#VelocxNZ", "#Jaked", "#SwimFast", "#RaceReady",
            "#CompetitiveSwimming", "#SwimNZ", "#NZSwimmers",
            "#SwimStart", "#TrainToWin",
        ],
        "call_to_action": "What's your weakness off the blocks?",
    },
}


def run_test(image_type: str, overlay_text: str | None, platforms: list[str],
             use_clean: bool = False, run_review: bool = False):
    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Build pending data with chosen options
    pending = json.loads(json.dumps(SAMPLE_PENDING))   # deep copy
    for platform in platforms:
        if platform not in pending:
            pending[platform] = dict(pending["facebook"])
        pending[platform]["image_type"] = image_type
        if overlay_text is not None:
            pending[platform]["overlay_text"] = overlay_text

    print(f"\nImage type  : {image_type}")
    print(f"Overlay text: {overlay_text or pending['facebook'].get('overlay_text')}")
    print(f"Platforms   : {platforms}\n")

    for platform in platforms:
        if platform not in PLATFORM_KEYS:
            print(f"  Unknown platform '{platform}' — skipping.")
            continue

        spec = PLATFORM_SPECS[platform]
        w, h = spec["pollinations_w"], spec["pollinations_h"]
        pdata = pending.get(platform, pending["facebook"])
        img_type = pdata.get("image_type", image_type)
        ov_text  = pdata.get("overlay_text")

        print("-" * 55)
        print(f"Platform : {platform.upper()}  ({w}×{h})")

        # Image source
        if use_clean:
            clean_path = pick_clean_image(img_type)
            if clean_path:
                print(f"Source   : clean image — {clean_path.name}")
                image_bytes = load_clean_image(clean_path, w, h)
            else:
                print(f"Source   : Pollinations.ai (no matching clean image for '{img_type}')")
                prompt = pdata.get("image_prompt", "competitive swimmer, cinematic dark pool")
                image_bytes = generate_image(prompt, platform)
        else:
            prompt = pdata.get("image_prompt", "competitive swimmer, cinematic dark pool")
            print(f"Source   : Pollinations.ai")
            print(f"Prompt   : {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
            image_bytes = generate_image(prompt, platform)

        # Apply overlay
        result = overlay_logo_and_text(
            image_bytes=image_bytes,
            logo_path=LOGO_PATH,
            platform=platform,
            overlay_text=ov_text,
        )

        out_path = OUTPUT_DIR / f"imagepost_{platform}_{image_type}_{ts}.jpg"
        out_path.write_bytes(result)
        print(f"Saved    : {out_path.name}")

        # Optional review step
        if run_review:
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            review = review_image(result, w, h, api_key)
            status = "APPROVED" if review.approved else "REJECTED"
            print(f"Review   : {status} (score={review.score}/10)")
            if review.issues:
                for issue in review.issues:
                    print(f"           - {issue}")
            print(f"           {review.recommendation}")

        # Show caption preview
        caption = _compose_caption(pdata)
        print(f"Caption  :\n{caption[:200]}{'...' if len(caption) > 200 else ''}\n")

    print("Done. Opening test_output/ ...")
    import subprocess
    subprocess.Popen(["explorer", str(OUTPUT_DIR.resolve())])


def main():
    parser = argparse.ArgumentParser(description="Local image post test")
    parser.add_argument(
        "--image-type", default="race_action",
        choices=["race_action", "training", "gear_closeup", "lifestyle", "open_water", "team"],
        help="Image type to test",
    )
    parser.add_argument(
        "--text", default=None,
        help="Override overlay text (e.g. 'Train harder.'). Use 'none' to disable.",
    )
    parser.add_argument(
        "--platform", default="all",
        choices=["all", "facebook", "instagram", "tiktok"],
        help="Platform to test (default: all)",
    )
    parser.add_argument(
        "--use-clean", action="store_true",
        help="Use local clean images instead of generating (faster, no internet needed)",
    )
    parser.add_argument(
        "--review", action="store_true",
        help="Run image review after generation (Layer 1 always; Layer 2 needs ANTHROPIC_API_KEY)",
    )
    args = parser.parse_args()

    overlay_text = None if args.text == "none" else args.text
    platforms = list(PLATFORM_KEYS) if args.platform == "all" else [args.platform]

    run_test(args.image_type, overlay_text, platforms,
             use_clean=args.use_clean, run_review=args.review)


if __name__ == "__main__":
    main()
