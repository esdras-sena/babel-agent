"""Practice-mode prompts (original). Selected each session in the UI."""

from __future__ import annotations

PRACTICE_MODES: dict[str, dict] = {
    "conversation": {
        "label": "Free conversation",
        "prompt_lines": [
            "This session is free conversation in the target language.",
            "In your first message, briefly greet the student and ask what "
            "topic they want to talk about today, then follow their lead.",
        ],
    },
    "roleplay": {
        "label": "Role-play",
        "prompt_lines": [
            "This session is a two-person role-play "
            "(shop, restaurant, hotel, interview, travel, etc.).",
            "In your first message, ask which scenario they want and which "
            "role they will play; you take the other role.",
            "Stay in character after roles are set. Weave corrections (explained in the native language) into "
            "your in-character reply instead of breaking the scene.",
        ],
    },
    "vocab": {
        "label": "Vocabulary quiz",
        "prompt_lines": [
            "This session is a vocabulary quiz at the student's CEFR level.",
            "Your first message must already be the first quiz item — "
            "no long greeting. Mix: translate to target, translate to native, "
            "fill-in-the-blank, and use-in-a-sentence.",
            "After each answer, give short feedback, then the next item.",
        ],
    },
    "translation": {
        "label": "Translation practice",
        "prompt_lines": [
            "This session is translation practice both directions "
            "(native<->target) at the student's CEFR level.",
            "Your first message should give the first sentence to translate.",
            "Judge meaning over word-for-word literalness. Offer one better "
            "phrasing when useful, then the next sentence.",
        ],
    },
}


def mode_choices() -> list[tuple[str, str]]:
    """(label, value) pairs for UI dropdowns."""
    return [(v["label"], k) for k, v in PRACTICE_MODES.items()]


def mode_keys_labels() -> list[tuple[str, str]]:
    """(value, label) pairs for Qt combo boxes (data, display)."""
    return [(k, v["label"]) for k, v in PRACTICE_MODES.items()]


def prompt_extra(mode: str) -> list[str]:
    entry = PRACTICE_MODES.get(mode) or PRACTICE_MODES["conversation"]
    return list(entry["prompt_lines"])
