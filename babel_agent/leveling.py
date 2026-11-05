"""Automatic CEFR leveling A1–C2 with hysteresis."""

from __future__ import annotations

from dataclasses import dataclass

from babel_agent.config import CEFR_LEVELS

# Rolling window size for accuracy estimates
WINDOW = 12
# Promote when accuracy >= PROMOTE_THRESHOLD over WINDOW turns with signal
PROMOTE_THRESHOLD = 0.78
# Demote when accuracy <= DEMOTE_THRESHOLD
DEMOTE_THRESHOLD = 0.42
# Need this many consecutive "up"/"down" signals (or window fills) before move
MIN_SIGNAL_STREAK = 3


@dataclass
class LevelState:
    level: str
    rolling_correct: int = 0
    rolling_total: int = 0
    up_streak: int = 0
    down_streak: int = 0
    history: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = []


def clamp_level(level: str) -> str:
    level = (level or "A1").upper().strip()
    return level if level in CEFR_LEVELS else "A1"


def accuracy(state: LevelState) -> float | None:
    if state.rolling_total <= 0:
        return None
    return state.rolling_correct / state.rolling_total


def _idx(level: str) -> int:
    return CEFR_LEVELS.index(clamp_level(level))


def apply_turn(
    state: LevelState,
    *,
    mistakes: int,
    successes: int,
    level_signal: str = "same",
) -> tuple[LevelState, str | None]:
    """Update rolling stats and maybe promote/demote.

    Returns (new_state, change_note) where change_note is None or a short
    human string like 'Promoted A1 -> A2'.
    """
    level = clamp_level(state.level)
    signal = (level_signal or "same").lower().strip()
    if signal not in {"up", "down", "same"}:
        signal = "same"

    # Each turn contributes one observation: success-weighted
    turn_score = 1.0
    if mistakes > 0 and successes == 0:
        turn_score = 0.0
    elif mistakes > 0 and successes > 0:
        turn_score = successes / (successes + mistakes)
    elif mistakes == 0 and successes == 0:
        # Neutral turn — slight credit if tutor said "same"/up, else mid
        turn_score = 0.6 if signal != "down" else 0.4

    history = list(state.history) + [turn_score]
    if len(history) > WINDOW:
        history = history[-WINDOW:]

    rolling_total = len(history)
    rolling_correct = sum(1 for s in history if s >= 0.5)
    # Prefer continuous average for thresholds
    avg = sum(history) / rolling_total if rolling_total else 0.5

    up_streak = state.up_streak + 1 if signal == "up" else 0
    down_streak = state.down_streak + 1 if signal == "down" else 0

    new_level = level
    note: str | None = None
    i = _idx(level)

    can_promote = rolling_total >= MIN_SIGNAL_STREAK and (
        (avg >= PROMOTE_THRESHOLD and up_streak >= MIN_SIGNAL_STREAK)
        or (avg >= PROMOTE_THRESHOLD and rolling_total >= WINDOW and up_streak >= 1)
    )
    can_demote = rolling_total >= MIN_SIGNAL_STREAK and (
        (avg <= DEMOTE_THRESHOLD and down_streak >= MIN_SIGNAL_STREAK)
        or (avg <= DEMOTE_THRESHOLD and rolling_total >= WINDOW and down_streak >= 1)
    )

    if can_promote and i < len(CEFR_LEVELS) - 1:
        new_level = CEFR_LEVELS[i + 1]
        note = f"Promoted {level} -> {new_level}"
        # Reset streaks / soft-reset window so we don't thrash
        history = history[-3:]
        up_streak = 0
        down_streak = 0
    elif can_demote and i > 0:
        new_level = CEFR_LEVELS[i - 1]
        note = f"Demoted {level} -> {new_level}"
        history = history[-3:]
        up_streak = 0
        down_streak = 0

    return (
        LevelState(
            level=new_level,
            rolling_correct=sum(1 for s in history if s >= 0.5),
            rolling_total=len(history),
            up_streak=up_streak,
            down_streak=down_streak,
            history=history,
        ),
        note,
    )
