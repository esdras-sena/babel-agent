"""Lightweight smoke tests (stdlib + project modules that need no GPU)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from babel_agent.leveling import LevelState, apply_turn, clamp_level
from babel_agent.memory import Memory
from babel_agent.tutor import split_reply_and_memory


def test_leveling_promote():
    state = LevelState(level="A1")
    note = None
    for _ in range(3):
        state, note = apply_turn(
            state, mistakes=0, successes=2, level_signal="up"
        )
    assert state.level == "A2", state
    assert note and "A1 → A2" in note
    # More sustained success can promote again (hysteresis resets each jump)
    for _ in range(3):
        state, note = apply_turn(
            state, mistakes=0, successes=2, level_signal="up"
        )
    assert state.level == "B1", state


def test_leveling_hysteresis_no_thrash():
    state = LevelState(level="A2")
    state, _ = apply_turn(state, mistakes=1, successes=0, level_signal="down")
    state, _ = apply_turn(state, mistakes=1, successes=0, level_signal="down")
    # Only 2 downs — should not demote yet
    assert state.level == "A2"


def test_memory_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "learner.db"
        mem = Memory(db)
        assert mem.get_learner()["cefr_level"] == "A1"
        sid = mem.start_session(
            target="Spanish",
            native="Portuguese",
            mode="conversation",
            model="dummy",
            level="A1",
        )
        mem.record_feedback(
            sid,
            mistakes=[{"what": "gender", "wrong": "el casa", "correction": "la casa"}],
            successes=["Used present tense correctly"],
        )
        level, note = mem.apply_level_signal(
            mistakes_count=1, successes_count=1, level_signal="same", auto=True
        )
        assert level == "A1"
        assert mem.recent_mistakes()
        assert mem.recent_successes()
        mem.end_session(sid, end_level=level, summary="Talked about home.")
        panel = mem.memory_panel_text()
        assert "la casa" in panel or "gender" in panel


def test_split_memory():
    raw = (
        "¡Hola! ¿Cómo estás?\n"
        '<<<MEMORY>>>{"mistakes":[],"successes":["greeting"],"level_signal":"same"}'
    )
    spoken, meta = split_reply_and_memory(raw)
    assert "Hola" in spoken
    assert "<<<MEMORY>>>" not in spoken
    assert meta["successes"] == ["greeting"]
    assert meta["level_signal"] == "same"


def test_clamp():
    assert clamp_level("b1") == "B1"
    assert clamp_level("nope") == "A1"



def test_ollama_chat_disables_think():
    """chat() must send think=false by default so thinking models return content."""
    import babel_agent.ollama_client as oc

    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {"message": {"content": "Hola", "thinking": "secret"}}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, path, json=None):
            captured["path"] = path
            captured["json"] = json
            return FakeResp()

    class FakeHttpx:
        Client = FakeClient

    orig = oc._httpx
    oc._httpx = lambda: FakeHttpx  # type: ignore
    try:
        out = oc.chat("dummy", [{"role": "user", "content": "hi"}])
    finally:
        oc._httpx = orig
    assert out == "Hola"
    assert captured["json"].get("think") is False, captured
    # empty content falls back to thinking only if needed
    class EmptyContent:
        status_code = 200
        text = ""
        def json(self):
            return {"message": {"content": "  ", "thinking": "fallback text"}}
    class FC2(FakeClient):
        def post(self, path, json=None):
            return EmptyContent()
    class FH2:
        Client = FC2
    oc._httpx = lambda: FH2  # type: ignore
    try:
        out2 = oc.chat("dummy", [{"role": "user", "content": "hi"}], think=False)
    finally:
        oc._httpx = orig
    assert out2 == "fallback text"



def test_ui_import():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    from babel_agent.ui import build_window
    win = build_window()
    assert win.windowTitle() == "Babel Agent"
    win.close()



def test_stt_allowed_codes():
    from babel_agent.stt import _allowed_lang_codes

    assert _allowed_lang_codes("Spanish", "Portuguese") == ["es", "pt"]
    assert _allowed_lang_codes("Portuguese", "Spanish") == ["pt", "es"]
    # same language twice → single code
    assert _allowed_lang_codes("Spanish", "Spanish") == ["es"]
    # unknown filtered
    assert _allowed_lang_codes("Klingon", "Spanish") == ["es"]


def test_stt_never_unrestricted_auto_contract():
    """Dry check: locked transcribe path never passes language=None."""
    import ast
    import inspect
    from babel_agent import stt
    from babel_agent.stt import _allowed_lang_codes

    src = inspect.getsource(stt)
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "language"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is None
                ):
                    bad.append(ast.dump(node))
    assert not bad, bad
    tsrc = inspect.getsource(stt.transcribe)
    assert "_run_locked" in tsrc
    assert "language=lang_code" in tsrc
    assert _allowed_lang_codes("Spanish", "Portuguese") == ["es", "pt"]



def test_vad_controller():
    from babel_agent.audio_capture import VadController

    v = VadController(speech_rms=0.01, min_speech_s=0.4, silence_s=1.0, max_utterance_s=5.0)
    assert not v.feed(0.001, 0.5)  # lead-in silence
    assert not v.feed(0.05, 0.5)   # speech
    assert v.feed(0.001, 1.05)     # trailing silence
    assert v.reason == "silence"

    v2 = VadController(speech_rms=0.01, min_speech_s=0.2, silence_s=10.0, max_utterance_s=1.0)
    assert not v2.feed(0.05, 0.5)
    assert v2.feed(0.05, 0.6)
    assert v2.reason == "max_utterance"


if __name__ == "__main__":
    test_leveling_promote()
    test_leveling_hysteresis_no_thrash()
    test_memory_roundtrip()
    test_split_memory()
    test_clamp()
    test_ollama_chat_disables_think()
    test_vad_controller()
    print("all smoke tests passed")
