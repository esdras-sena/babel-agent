"""SQLite learner memory: mistakes, successes, vocab, CEFR, sessions."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from babel_agent.config import DB_PATH, DEFAULT_LEVEL, DEFAULT_NATIVE, DEFAULT_TARGET, ensure_dirs
from babel_agent.leveling import LevelState, apply_turn, clamp_level


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS learner (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                target_language TEXT NOT NULL,
                native_language TEXT NOT NULL,
                cefr_level TEXT NOT NULL,
                level_auto INTEGER NOT NULL DEFAULT 1,
                leveling_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                target_language TEXT NOT NULL,
                native_language TEXT NOT NULL,
                practice_mode TEXT NOT NULL,
                model TEXT,
                start_level TEXT NOT NULL,
                end_level TEXT,
                summary TEXT
            );

            CREATE TABLE IF NOT EXISTS mistakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                created_at TEXT NOT NULL,
                what TEXT NOT NULL,
                wrong TEXT,
                correction TEXT,
                context TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS successes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                created_at TEXT NOT NULL,
                note TEXT NOT NULL,
                example TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                term TEXT NOT NULL,
                translation TEXT,
                notes TEXT,
                UNIQUE(term, translation)
            );

            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            """
        )
        row = conn.execute("SELECT id FROM learner WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO learner
                (id, target_language, native_language, cefr_level, level_auto, leveling_json, updated_at)
                VALUES (1, ?, ?, ?, 1, '{}', ?)
                """,
                (DEFAULT_TARGET, DEFAULT_NATIVE, DEFAULT_LEVEL, _now()),
            )


class Memory:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        init_db(self.db_path)

    def get_learner(self) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM learner WHERE id = 1").fetchone()
            return dict(row)

    def set_languages(self, target: str, native: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE learner SET target_language = ?, native_language = ?, updated_at = ?
                WHERE id = 1
                """,
                (target, native, _now()),
            )

    def set_level(self, level: str, *, auto: bool | None = None) -> None:
        level = clamp_level(level)
        with connect(self.db_path) as conn:
            if auto is None:
                conn.execute(
                    "UPDATE learner SET cefr_level = ?, updated_at = ? WHERE id = 1",
                    (level, _now()),
                )
            else:
                conn.execute(
                    """
                    UPDATE learner SET cefr_level = ?, level_auto = ?, updated_at = ?
                    WHERE id = 1
                    """,
                    (level, 1 if auto else 0, _now()),
                )

    def load_level_state(self) -> LevelState:
        learner = self.get_learner()
        raw = learner.get("leveling_json") or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        return LevelState(
            level=clamp_level(learner.get("cefr_level") or DEFAULT_LEVEL),
            rolling_correct=int(data.get("rolling_correct", 0)),
            rolling_total=int(data.get("rolling_total", 0)),
            up_streak=int(data.get("up_streak", 0)),
            down_streak=int(data.get("down_streak", 0)),
            history=list(data.get("history") or []),
        )

    def save_level_state(self, state: LevelState) -> None:
        payload = {
            "rolling_correct": state.rolling_correct,
            "rolling_total": state.rolling_total,
            "up_streak": state.up_streak,
            "down_streak": state.down_streak,
            "history": state.history,
        }
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE learner SET cefr_level = ?, leveling_json = ?, updated_at = ?
                WHERE id = 1
                """,
                (clamp_level(state.level), json.dumps(payload), _now()),
            )

    def start_session(
        self,
        *,
        target: str,
        native: str,
        mode: str,
        model: str | None,
        level: str,
    ) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO sessions
                (started_at, target_language, native_language, practice_mode, model, start_level)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_now(), target, native, mode, model, clamp_level(level)),
            )
            return int(cur.lastrowid)

    def end_session(self, session_id: int, *, end_level: str, summary: str | None) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE sessions SET ended_at = ?, end_level = ?, summary = ?
                WHERE id = ?
                """,
                (_now(), clamp_level(end_level), summary, session_id),
            )

    def add_turn(self, session_id: int, role: str, content: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO turns (session_id, created_at, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, _now(), role, content),
            )

    def record_feedback(
        self,
        session_id: int | None,
        *,
        mistakes: list[dict[str, Any]],
        successes: list[dict[str, Any] | str],
        vocab: list[dict[str, Any]] | None = None,
    ) -> None:
        with connect(self.db_path) as conn:
            for m in mistakes or []:
                if isinstance(m, str):
                    what, wrong, correction, context = m, None, None, None
                else:
                    what = m.get("what") or m.get("error") or m.get("mistake") or str(m)
                    wrong = m.get("wrong") or m.get("student")
                    correction = m.get("correction") or m.get("correct")
                    context = m.get("context")
                conn.execute(
                    """
                    INSERT INTO mistakes
                    (session_id, created_at, what, wrong, correction, context)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, _now(), what, wrong, correction, context),
                )
            for s in successes or []:
                if isinstance(s, str):
                    note, example = s, None
                else:
                    note = s.get("note") or s.get("success") or str(s)
                    example = s.get("example")
                conn.execute(
                    """
                    INSERT INTO successes (session_id, created_at, note, example)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_id, _now(), note, example),
                )
            for v in vocab or []:
                term = v.get("term") or v.get("word")
                if not term:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO vocabulary
                    (created_at, term, translation, notes)
                    VALUES (?, ?, ?, ?)
                    """,
                    (_now(), term, v.get("translation"), v.get("notes")),
                )

    def apply_level_signal(
        self,
        *,
        mistakes_count: int,
        successes_count: int,
        level_signal: str,
        force_manual_level: str | None = None,
        auto: bool = True,
    ) -> tuple[str, str | None]:
        """Update CEFR from performance. Returns (level, change_note)."""
        if not auto and force_manual_level:
            level = clamp_level(force_manual_level)
            self.set_level(level, auto=False)
            return level, None

        state = self.load_level_state()
        if not auto:
            # Keep current level; still update rolling stats lightly
            new_state, note = apply_turn(
                state,
                mistakes=mistakes_count,
                successes=successes_count,
                level_signal="same",
            )
            new_state.level = state.level
            self.save_level_state(new_state)
            return state.level, None

        new_state, note = apply_turn(
            state,
            mistakes=mistakes_count,
            successes=successes_count,
            level_signal=level_signal,
        )
        self.save_level_state(new_state)
        self.set_level(new_state.level, auto=True)
        return new_state.level, note

    def recent_mistakes(self, limit: int = 8) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT what, wrong, correction, context, created_at
                FROM mistakes ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_successes(self, limit: int = 8) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT note, example, created_at
                FROM successes ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_session_summaries(self, limit: int = 3) -> list[str]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT summary, start_level, end_level, practice_mode, started_at
                FROM sessions
                WHERE summary IS NOT NULL AND summary != ''
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    f"[{r['started_at'][:10]}] {r['practice_mode']} "
                    f"{r['start_level']}->{r['end_level'] or '?'}: {r['summary']}"
                )
            return out

    def memory_panel_text(self) -> str:
        mistakes = self.recent_mistakes()
        successes = self.recent_successes()
        learner = self.get_learner()
        lines = [
            f"**CEFR:** {learner['cefr_level']} "
            f"({'auto' if learner['level_auto'] else 'manual'})",
            "",
            "### Recent mistakes",
        ]
        if not mistakes:
            lines.append("_None yet._")
        else:
            for m in mistakes:
                bit = m["what"]
                if m.get("wrong") and m.get("correction"):
                    bit += f" — said «{m['wrong']}» -> «{m['correction']}»"
                lines.append(f"- {bit}")
        lines += ["", "### Recent successes"]
        if not successes:
            lines.append("_None yet._")
        else:
            for s in successes:
                lines.append(f"- {s['note']}")
        return "\n".join(lines)
