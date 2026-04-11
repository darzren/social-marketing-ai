# Health Check Agent Instructions

Runs 20 minutes after the daily post agent.
Verifies today's post succeeded. If not, diagnoses and fixes automatically.

> **This agent is brand-agnostic.** Substitute `{INDUSTRY}` with the value set
> in your session entry file (e.g. `velocx_nz`).

---

## Step 1 — Get today's date prefix
```
python -c "import datetime; print(datetime.datetime.now().strftime('%Y%m%d'))"
```
Note the output (e.g. `20260410`) — used to match today's files.

## Step 2 — Check post status

Use Glob to find files matching today's date prefix:
- `data/content_posted/{INDUSTRY}_TODAY*_posted.json`
- `data/content_ready/{INDUSTRY}_TODAY*_pending.json`

Read any files found. Determine which case applies:

| Case | Condition | Action |
|------|-----------|--------|
| A | Posted file exists + all platforms `success: true` | ✅ Report OK, done |
| B | Posted file exists + one or more platforms `success: false` | Fix and retry (Step 4B) |
| C | Pending file exists + no posted file | Re-trigger GitHub Actions (Step 4C) |
| D | No pending, no posted file | Full re-run (Step 4D) |

---

## Step 3A — All good

Report success. Include:
- The posted filename
- Platform results
- No further action needed.

---

## Step 4B — Posted file shows platform failure

Read the `results` field in the posted file to identify the error.

**Image generation errors** (Pollinations 500, timeout, etc.):
1. Read the original `image_prompt` from `content.facebook.image_prompt`
2. Shorten it to under 300 characters
3. Write a new image pending file:
   `data/content_ready/{INDUSTRY}_NEWTIMESTAMP_image_pending.json`
   with the shortened prompt and same caption/hashtags
4. Push to GitHub → triggers the post workflow to retry

**Facebook API errors** (token expired, permissions):
- These cannot be fixed automatically
- Report the exact error message
- Instruct the user to check the Facebook token in the `{INDUSTRY}` GitHub Environment secrets

**All other errors**:
- Report the error
- If it looks transient (timeout, network), write and push the same pending file again to retry

---

## Step 4C — Pending file exists, no posted file

GitHub Actions either didn't trigger or failed mid-run.

1. Read the pending file
2. Check `type` field:
   - If `"image"`: check `content.facebook.image_prompt` length
     - If over 400 chars → shorten to 350 chars
   - If `"text"`: content is fine as-is
3. Rewrite the pending file with a minor update (add `"retry": true` at top level)
4. Stage and push to GitHub — this triggers the workflow again

```
git config user.email agent@claude.ai
git config user.name Claude-Agent
git remote set-url origin https://GITHUB_TOKEN@github.com/darzren/social-marketing-ai.git
git add data/content_ready/
git commit -m "retry: re-trigger GitHub Actions for {INDUSTRY}"
git push
```

---

## Step 4D — No files at all (daily agent failed)

The daily agent never completed. Run the full daily job now:
Read and follow `agents/brands/{INDUSTRY}.md` → which calls `agents/DAILY_POST_AGENT.md`.

---

## Step 5 — Report

Always end with a clear summary:
- **Brand**: `{INDUSTRY}`
- **Status**: OK / Fixed and retried / Cannot fix automatically
- **Root cause**: what went wrong
- **Action taken**: what was done to resolve it
- **Next check**: if retried, note that GitHub Actions should complete within 5 minutes
