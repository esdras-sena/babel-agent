"""Strip emojis / pictographic symbols from any text (UI, LLM, STT, TTS)."""
from __future__ import annotations

import re

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # emoticons, symbols, pictographs, transport, flags...
    "\U00002600-\U000027BF"  # misc symbols, dingbats
    "\U00002B00-\U00002BFF"  # arrows/stars
    "\U00002190-\U000021FF"  # arrows
    "\U00002300-\U000023FF"  # misc technical
    "\U000025A0-\U000025FF"  # geometric shapes
    "\U00002580-\U0000259F"  # block elements
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # ZWJ
    "\U000020E3"             # keycap
    "\U000E0000-\U000E007F"  # tags
    "]+"
)


def strip_emojis(text: str) -> str:
    if not text:
        return text
    out = _EMOJI_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", out).strip()
