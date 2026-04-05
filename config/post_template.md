# Social Media Post Template

Use this template when generating all social media posts.
Apply to every platform post regardless of industry or brand.
Adapt the language, tone, and examples to fit the specific brand config.

---

## Structure

```
[HOOK — scroll stopper, 1 line, include emoji]
🔥 "Something bold and curiosity-driving…"

[BLANK LINE]

[RELATABLE PROBLEM — 1–2 lines]
If you've ever struggled with [problem specific to audience], you're not alone…

[BLANK LINE]

[STORY / DEMO — use 👉 bullets, 2–3 lines]
We tried [product/approach] and here's what happened:
👉 [Specific result 1]
👉 [Specific result 2]
👉 [Unexpected or surprising outcome]

[BLANK LINE]

[EMOTIONAL TRIGGER — 1 line, add emoji]
Honestly… we didn't expect this 😳

[BLANK LINE]

[VALUE / TAKEAWAY — use ✔️ bullets, 2–3 lines]
Here's why it works:
✔️ [Benefit 1]
✔️ [Benefit 2]
✔️ [Benefit 3]

[BLANK LINE]

[SOFT CTA — 1 line, question format]
Would you try this? 👇

[BLANK LINE]

[ENGAGEMENT BAIT — 1 line, drives comments]
Comment "[KEYWORD]" below and we'll [deliver something of value] 💡
```

---

## Rules

- **Max 200 words** (excluding hashtags)
- Hook must stop the scroll — use a bold claim, question, or surprising statement
- Every section separated by a blank line — never wall-of-text
- Keep each line to 1–2 sentences
- Use **bold text** for 1–2 key phrases
- Include 3–6 emojis placed naturally throughout — not all at the end
- Tone: friendly, conversational, easy to skim — adapt to brand voice
- The SOFT CTA asks a question to invite replies
- The ENGAGEMENT BAIT drives comment volume — use a brand-relevant keyword
  (e.g. "Comment 'FAST' and we'll DM you our training guide" for a swimwear brand)
- Hashtags on the very last line, separated by spaces
- `post_text` contains everything EXCEPT hashtags and the engagement bait line
- `engagement_bait` is the comment-prompt line only

---

## Output format

Return STRICT JSON ONLY — no explanation, no markdown wrapper:

```json
{
  "content_angle": "one-line description of the angle or hook used",
  "post_text": "full post body: hook + problem + story + emotional trigger + value + soft CTA — NO hashtags, NO engagement bait",
  "engagement_bait": "Comment '[KEYWORD]' below and we'll [value offer] 💡",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3"],
  "call_to_action": "the soft CTA question line repeated here for reporting"
}
```

**Field rules:**
- `post_text` — the main body following the 8-section structure above
- `post_text` must NOT contain hashtags or the engagement bait line
- `engagement_bait` — the comment-prompt line only (appended after post_text when published)
- `hashtags` — brand config tags plus any trending tags from research
- `content_angle` — used by the history checker to detect repetition in future runs
- `call_to_action` — the soft CTA question for tracking and reporting
