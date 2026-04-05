"""
Agent runner — called by the CCR remote trigger.
Generates a timestamped pending post and commits it to GitHub.

Usage: python run_agent.py --industry velocx_nz --github-token <token>
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry", required=True)
    parser.add_argument("--github-token", required=True)
    parser.add_argument("--github-repo", default="darzren/social-marketing-ai")
    args = parser.parse_args()

    industry = args.industry
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pending_file = Path(f"data/content_ready/{industry}_{timestamp}_pending.json")

    # Load brand config
    config_path = Path(f"config/industries/{industry}.json")
    if not config_path.exists():
        print(f"ERROR: No config found at {config_path}")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    print(f"Industry:  {config['display_name']}")
    print(f"Timestamp: {timestamp}")
    print(f"Output:    {pending_file}")
    print()

    # The agent (CCR) will write the post content using the Write tool
    # This script handles setup and git operations around it.
    # If the pending file already exists (written by the agent), skip generation prompt.
    if not pending_file.exists():
        print("ERROR: Pending file not found.")
        print("The CCR agent should write the post using the Write tool before this step.")
        sys.exit(1)

    # Commit and push to trigger GitHub Actions
    repo_url = f"https://{args.github_token}@github.com/{args.github_repo}.git"
    commands = [
        ["git", "config", "user.email", "agent@claude.ai"],
        ["git", "config", "user.name", "Claude-Agent"],
        ["git", "remote", "set-url", "origin", repo_url],
        ["git", "add", "data/content_ready/"],
        ["git", "commit", "-m", f"content: {industry} {timestamp}"],
        ["git", "push"],
    ]

    for cmd in commands:
        display = " ".join(c if "token" not in c.lower() and "https" not in c else "***" for c in cmd)
        print(f"Running: {display}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FAILED: {result.stderr}")
            sys.exit(1)

    print(f"\nSUCCESS: {pending_file.name} committed and pushed.")
    print("GitHub Actions will now post to Facebook.")


if __name__ == "__main__":
    main()
