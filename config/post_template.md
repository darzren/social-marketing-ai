# Social Media Post Template

Use this template when generating all social media posts.
Apply to every platform post regardless of industry or brand.

---

## Structure

```
HOOK LINE 👇

Short paragraph (1–2 lines)

Another short paragraph (1–2 lines)

Optional relatable line

**Key takeaway or emphasis**

Call-to-action (1 line)

#hashtag1 #hashtag2 #hashtag3
```

---

## Rules

- **Max 120 words** (excluding hashtags)
- Start with a strong HOOK on line 1 — include an emoji
- Use line breaks between every section — no walls of text
- Keep each line short: 1–2 sentences max
- Use **text** formatting for 1–2 key phrases
- Include 2–5 emojis placed naturally (not all at the end)
- Tone: friendly, conversational, easy to skim
- End with a clear call-to-action on its own line
- Hashtags on the final line, separated by spaces

---

## Output format

Return STRICT JSON ONLY — no explanation, no markdown wrapper:

```json
{
  "content_angle": "one-line description of the angle or hook used",
  "post_text": "the full post body including hook, paragraphs, emphasis, and CTA — NO hashtags here",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3"],
  "call_to_action": "the CTA line repeated here for reporting"
}
```

- `post_text` must follow the template structure above
- `post_text` must NOT include hashtags (they go in the `hashtags` array)
- `hashtags` combines relevant tags from the brand config plus any trending tags found in research
- `content_angle` is used by the history checker to detect repetition in future runs
