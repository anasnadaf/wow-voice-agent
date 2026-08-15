"""Speech control tags — markup the agent writes for the voice, not for the caller.

Rumik's muga model expects every utterance to open with one tone tag, which it
consumes to colour the delivery rather than reading aloud. That makes the tag an
instruction to the synthesiser, so it belongs in the audio and nowhere else: the
transcript, the dashboard, the MLflow trace and the model's own memory of what it
said should all show the sentence a caller actually heard.
"""

import re

TONE_TAGS = ("neutral", "happy", "excited", "sad", "angry", "whisper")
DEFAULT_TONE = "neutral"

# any bracketed word in the opening position — deliberately wider than TONE_TAGS
# so an invented tone ("[warm]") is caught and corrected rather than spoken
_LEADING_TAG = re.compile(r"^\s*\[([a-z_ -]{2,20})\]\s*", re.IGNORECASE)
# tone tags anywhere, plus muga's event tags (<laugh>, <sigh>, <chuckle>)
_ANY_TAG = re.compile(
    r"\[(?:" + "|".join(TONE_TAGS) + r")\]|<(?:laugh|chuckle|sigh)>",
    re.IGNORECASE,
)

MUGA_TONE_RULES = """\
## Speech tags (spoken delivery)
Begin EVERY reply with exactly one tone tag, then a single space, then your words:
- [neutral] — the default; use it for questions, facts and checkpoints
- [happy] — a warm acknowledgement, a caller who is engaged
- [excited] — only for the pitch, and only briefly
- [sad] — sincere regret, a budget or timeline that does not work
- [angry] — never use this on a sales call
- [whisper] — never use this on a sales call
Rules:
- Exactly one tag, at the very start. Never two, never mid-sentence, never at the end.
- The tag is the only bracketed text you may write. Invent no others.
- Never mention, explain or read out the tag — it shapes your voice, it is not speech.
Examples:
- [neutral] May I ask whether you're exploring this for your own use or as an investment?
- [happy] Bilkul, yeh Nandi Hills ke paas ka premium plot community hai.
- [sad] I completely understand, and I appreciate you hearing me out."""


# The rules above sit ahead of the whole transcript; this rides in the final
# position, where the model is least likely to have lost the format.
MUGA_TONE_REMINDER = (
    "Start this reply with exactly one tone tag — [neutral], [happy], [excited] "
    "or [sad] — followed by a single space, then your words. No other brackets."
)


def normalize_tone_tag(text: str) -> str:
    """Force a reply to open with exactly one supported tone tag.

    An unsupported or missing tag is replaced with the neutral default, so a
    model that invents "[warm]" cannot leak brackets into the caller's ear.
    """
    match = _LEADING_TAG.match(text)
    if match:
        tone = match.group(1).strip().lower()
        body = text[match.end() :]
        if tone not in TONE_TAGS:
            tone = DEFAULT_TONE
        return f"[{tone}] {body}" if body else f"[{tone}] "
    return f"[{DEFAULT_TONE}] {text.lstrip()}"


def strip_speech_tags(text: str) -> str:
    """The sentence as the caller heard it, with the synthesiser markup removed."""
    return re.sub(r"\s{2,}", " ", _ANY_TAG.sub("", text)).strip()
