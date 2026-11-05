"""Native desktop UI (PySide6) for Babel Agent — not a browser app."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from babel_agent import ollama_client, stt, tts
from babel_agent.audio_capture import (
    AudioRecorder,
    VadController,
    VAD_POLL_MS,
    VAD_POST_PLAYBACK_DELAY_MS,
    device_label,
    friendly_mic_name,
    list_input_devices,
    resolve_input_device,
)
from babel_agent.config import asset_path, load_settings, save_settings
from babel_agent import audio_output
from babel_agent.config import (
    CEFR_LEVELS,
    DEFAULT_LEVEL,
    DEFAULT_MODE,
    DEFAULT_NATIVE,
    DEFAULT_TARGET,
    LANGUAGES,
    ensure_dirs,
)
from babel_agent.practice_modes import mode_keys_labels
from babel_agent.tutor import TutorSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

APP_STYLESHEET = """
QMainWindow, QWidget#centralRoot {
    background-color: #0f1117;
    color: #e8eaef;
    font-family: "Segoe UI", "Inter", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}

QFrame#topBar, QFrame#setupStrip, QFrame#actionBar,
QFrame#chatCard, QFrame#sideCard, QFrame#inputBar {
    background-color: #171a22;
    border: 1px solid #2a2f3a;
    border-radius: 14px;
}

QLabel#appTitle {
    color: #f3f4f6;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.2px;
}

QLabel#sectionCaption {
    color: #9aa3b2;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

QLabel#fieldLabel {
    color: #9aa3b2;
    font-size: 11px;
    font-weight: 600;
}

QLabel#statusPill {
    background-color: #222733;
    color: #c7cdd8;
    border: 1px solid #323847;
    border-radius: 10px;
    padding: 6px 12px;
}

QLabel#statusLine {
    color: #a8b0bf;
    font-size: 12px;
}

QLabel#cefrBadge {
    background-color: #312e81;
    color: #e0e7ff;
    border: 1px solid #4338ca;
    border-radius: 16px;
    padding: 14px 10px;
    font-size: 22px;
    font-weight: 800;
    qproperty-alignment: AlignCenter;
}

QLabel#hintLabel {
    color: #6b7280;
    font-size: 11px;
}

QLabel#transcriptLabel {
    color: #8b93a7;
    font-size: 12px;
    padding: 4px 2px;
}

QComboBox {
    background-color: #1e2330;
    color: #e8eaef;
    border: 1px solid #323847;
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 28px;
}
QComboBox:hover { border-color: #4f46e5; }
QComboBox:disabled {
    color: #6b7280;
    background-color: #151820;
    border-color: #252a35;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1e2330;
    color: #e8eaef;
    border: 1px solid #323847;
    selection-background-color: #4338ca;
    selection-color: #ffffff;
    outline: 0;
}

QLineEdit {
    background-color: #1e2330;
    color: #e8eaef;
    border: 1px solid #323847;
    border-radius: 10px;
    padding: 10px 14px;
    min-height: 20px;
    selection-background-color: #4338ca;
}
QLineEdit:focus { border-color: #6366f1; }
QLineEdit:disabled {
    color: #6b7280;
    background-color: #151820;
    border-color: #252a35;
}

QTextEdit {
    background-color: #12151c;
    color: #e8eaef;
    border: 1px solid #2a2f3a;
    border-radius: 12px;
    padding: 10px;
    selection-background-color: #4338ca;
}
QTextEdit:disabled {
    color: #6b7280;
    background-color: #10131a;
}

QCheckBox {
    color: #c7cdd8;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #3b4252;
    background: #1e2330;
}
QCheckBox::indicator:checked {
    background: #4f46e5;
    border-color: #6366f1;
}
QCheckBox:disabled { color: #6b7280; }

QPushButton {
    background-color: #252b3a;
    color: #e8eaef;
    border: 1px solid #3a4152;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2e3548;
    border-color: #4f46e5;
}
QPushButton:pressed { background-color: #1b2030; }
QPushButton:disabled {
    color: #5b6475;
    background-color: #171a22;
    border-color: #252a35;
}

QPushButton#primaryBtn {
    background-color: #4f46e5;
    border-color: #6366f1;
    color: #ffffff;
    padding: 10px 18px;
    font-size: 14px;
}
QPushButton#primaryBtn:hover {
    background-color: #6366f1;
    border-color: #818cf8;
}
QPushButton#primaryBtn:disabled {
    background-color: #2a2f45;
    border-color: #32364a;
    color: #6b7280;
}

QPushButton#dangerBtn {
    background-color: #3f1d24;
    border-color: #7f1d1d;
    color: #fecaca;
}
QPushButton#dangerBtn:hover {
    background-color: #5b232c;
    border-color: #b91c1c;
}
QPushButton#dangerBtn:disabled {
    background-color: #24161a;
    border-color: #3a2228;
    color: #6b7280;
}

QPushButton#ghostBtn {
    background-color: transparent;
    border: 1px solid #323847;
    color: #a8b0bf;
    padding: 6px 12px;
    font-weight: 500;
}
QPushButton#ghostBtn:hover {
    background-color: #1e2330;
    border-color: #4f46e5;
    color: #e8eaef;
}

QPushButton#sendSmallBtn {
    background-color: #252b3a;
    border: 1px solid #3a4152;
    color: #9aa3b2;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 500;
    border-radius: 8px;
}

QPushButton#recordBtn {
    background-color: #1e2330;
    color: #f3f4f6;
    border: 3px solid #ef4444;
    border-radius: 56px;
    font-size: 15px;
    font-weight: 700;
    min-width: 112px;
    max-width: 112px;
    min-height: 112px;
    max-height: 112px;
    padding: 0;
}
QPushButton#recordBtn:hover {
    background-color: #2a1520;
    border-color: #f87171;
}
QPushButton#recordBtn:checked {
    background-color: #dc2626;
    border-color: #fecaca;
    color: #ffffff;
}
QPushButton#recordBtn:disabled {
    background-color: #171a22;
    border-color: #3a4152;
    color: #5b6475;
}

QSplitter::handle {
    background-color: transparent;
    width: 8px;
}
"""


# ---------------------------------------------------------------------------
# Background workers (keep UI responsive during STT / LLM / TTS)
# ---------------------------------------------------------------------------


class SessionStartWorker(QObject):
    finished = Signal(object, object, object, object)  # opening, note, path, error
    status = Signal(str)

    def __init__(self, session: TutorSession, kwargs: dict) -> None:
        super().__init__()
        self.session = session
        self.kwargs = kwargs

    @Slot()
    def run(self) -> None:
        try:
            self.status.emit("Asking Ollama for the opening…")
            opening = self.session.start(**self.kwargs)
            self.status.emit("Synthesizing tutor voice…")
            path, note = tts.synthesize(opening, target_language=self.kwargs["target"])
            self.finished.emit(opening, note, path, None)
        except Exception as exc:
            logger.exception("Session start failed")
            self.finished.emit("", "", None, exc)


class TurnWorker(QObject):
    """Process user audio path or typed text → STT (if needed) → LLM → TTS."""

    finished = Signal(str, str, str, object, object)  # user, reply, tts_note, audio_path, error
    status = Signal(str)

    def __init__(
        self,
        session: TutorSession,
        *,
        audio_path: str | None = None,
        typed_text: str | None = None,
        target: str = "",
        native: str = "",
        bluetooth: bool = False,
    ) -> None:
        super().__init__()
        self.bluetooth = bluetooth
        self.session = session
        self.audio_path = audio_path
        self.typed_text = typed_text
        self.target = target
        self.native = native

    @Slot()
    def run(self) -> None:
        try:
            if self.typed_text:
                text = self.typed_text.strip()
            else:
                if not self.audio_path:
                    raise RuntimeError("No audio captured.")
                self.status.emit("Transcribing speech…")
                text = stt.transcribe(
                    self.audio_path,
                    target_language=self.target,
                    native_language=self.native,
                    bluetooth=self.bluetooth,
                )
                if not text:
                    raise RuntimeError(
                        "Could not hear any speech. Try again closer to the mic."
                    )
                note = stt.backend_note()
                if note:
                    self.status.emit(note)

            self.status.emit(f"You said: «{text}» — thinking…")
            reply, meta = self.session.handle_user_text(text)
            self.status.emit("Synthesizing tutor voice…")
            path, note = tts.synthesize(reply, target_language=self.session.target)
            change = meta.get("level_change")
            if change:
                note = f"{note} | {change}"
            self.finished.emit(text, reply, note, path, None)
        except Exception as exc:
            logger.exception("Turn failed")
            self.finished.emit("", "", "", None, exc)


class SessionEndWorker(QObject):
    finished = Signal(str, object)  # message, error|None

    def __init__(self, session: TutorSession) -> None:
        super().__init__()
        self.session = session

    @Slot()
    def run(self) -> None:
        try:
            msg = self.session.end()
            self.finished.emit(msg, None)
        except Exception as exc:
            logger.exception("Session end failed")
            self.finished.emit("", exc)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Babel Agent")
        icon_file = asset_path("icon.png")
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))
        self.resize(1180, 780)
        self.setMinimumSize(920, 640)
        self.setStyleSheet(APP_STYLESHEET)

        ensure_dirs()
        self.session = TutorSession()
        self.memory = self.session.memory
        _st = load_settings()
        self.recorder = AudioRecorder(device=_st.get("input_device_name") or _st.get("input_device_index"))
        self._busy = False
        self._thread: QThread | None = None
        self._worker: QObject | None = None

        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)
        self._current_audio_path: str | None = None
        self._play_when_ready = False
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_player_error)
        self._cli_player = audio_output.CliPlayer()
        self._output_sink_pref: str | None = _st.get("output_sink") or None

        # Phone-call / hands-free state
        mode = str(_st.get("conversation_mode") or "call").lower()
        self._conversation_mode = "ptt" if mode == "ptt" else "call"
        self._call_muted = False
        self._call_listening = False
        self._awaiting_playback = False
        self._playback_backend: str | None = None  # "cli" | "qt"
        self._qt_play_started = False
        self._vad = VadController()
        self._vad_timer = QTimer(self)
        self._vad_timer.setInterval(VAD_POLL_MS)
        self._vad_timer.timeout.connect(self._on_vad_tick)
        self._playback_watch = QTimer(self)
        self._playback_watch.setInterval(100)
        self._playback_watch.timeout.connect(self._check_playback_done)
        self._arm_delay = QTimer(self)
        self._arm_delay.setSingleShot(True)
        self._arm_delay.timeout.connect(self._arm_listen)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status_end)

        self._build_ui()
        self._refresh_models()
        self._refresh_level_and_memory()
        self._set_session_controls(active=False)
        self._apply_mode_ui()

    # -- layout -------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("centralRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 14)
        outer.setSpacing(12)

        # 1) Top bar --------------------------------------------------------
        top = QFrame()
        top.setObjectName("topBar")
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(16, 12, 16, 12)
        top_l.setSpacing(12)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.setContentsMargins(0, 0, 0, 0)
        logo_file = asset_path("icon.png")
        if logo_file.exists():
            logo = QLabel()
            logo.setObjectName("appLogo")
            pix = QPixmap(str(logo_file))
            logo.setPixmap(pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
            logo.setFixedSize(36, 36)
            brand.addWidget(logo)
        title = QLabel("Babel Agent")
        title.setObjectName("appTitle")
        brand.addWidget(title)
        top_l.addLayout(brand)

        self.ollama_label = QLabel()
        self.ollama_label.setObjectName("statusPill")
        self.ollama_label.setWordWrap(False)
        self.ollama_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_l.addWidget(self.ollama_label, stretch=1)

        model_cap = QLabel("Model")
        model_cap.setObjectName("fieldLabel")
        top_l.addWidget(model_cap)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.setEditable(False)
        top_l.addWidget(self.model_combo)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("ghostBtn")
        self.refresh_btn.clicked.connect(self._refresh_models)
        top_l.addWidget(self.refresh_btn)

        mic_cap = QLabel("Mic")
        mic_cap.setObjectName("fieldLabel")
        top_l.addWidget(mic_cap)
        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(220)
        self.mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        top_l.addWidget(self.mic_combo)
        out_cap = QLabel("Output")
        out_cap.setObjectName("fieldLabel")
        top_l.addWidget(out_cap)
        self.out_combo = QComboBox()
        self.out_combo.setMinimumWidth(200)
        self.out_combo.currentIndexChanged.connect(self._on_output_changed)
        top_l.addWidget(self.out_combo)
        outer.addWidget(top)
        self._refresh_mics()
        self._refresh_outputs()

        # 2) Setup strip ----------------------------------------------------
        setup = QFrame()
        setup.setObjectName("setupStrip")
        setup_l = QHBoxLayout(setup)
        setup_l.setContentsMargins(16, 10, 16, 10)
        setup_l.setSpacing(10)

        def _add_field(caption: str, widget: QWidget) -> None:
            box = QVBoxLayout()
            box.setSpacing(4)
            lab = QLabel(caption)
            lab.setObjectName("fieldLabel")
            box.addWidget(lab)
            box.addWidget(widget)
            setup_l.addLayout(box)

        self.target_combo = QComboBox()
        self.target_combo.addItems(list(LANGUAGES))
        self.target_combo.setCurrentText(DEFAULT_TARGET)
        _add_field("Target", self.target_combo)

        self.native_combo = QComboBox()
        self.native_combo.addItems(list(LANGUAGES))
        self.native_combo.setCurrentText(DEFAULT_NATIVE)
        _add_field("Native", self.native_combo)

        self.mode_combo = QComboBox()
        for key, label in mode_keys_labels():
            self.mode_combo.addItem(label, key)
        idx = self.mode_combo.findData(DEFAULT_MODE)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        _add_field("Mode", self.mode_combo)

        self.level_combo = QComboBox()
        self.level_combo.addItems(list(CEFR_LEVELS))
        learner_level = self.memory.get_learner().get("cefr_level") or DEFAULT_LEVEL
        self.level_combo.setCurrentText(learner_level)
        _add_field("CEFR", self.level_combo)

        auto_box = QVBoxLayout()
        auto_box.setSpacing(4)
        auto_lab = QLabel("Leveling")
        auto_lab.setObjectName("fieldLabel")
        auto_box.addWidget(auto_lab)
        self.level_auto = QCheckBox("Automatic")
        self.level_auto.setChecked(bool(self.memory.get_learner().get("level_auto", 1)))
        auto_box.addWidget(self.level_auto)
        setup_l.addLayout(auto_box)

        apply_wrap = QVBoxLayout()
        apply_wrap.addStretch(1)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("ghostBtn")
        apply_btn.clicked.connect(self._apply_level)
        apply_wrap.addWidget(apply_btn)
        setup_l.addLayout(apply_wrap)
        setup_l.addStretch(1)
        outer.addWidget(setup)

        # 3) Primary action bar ---------------------------------------------
        action = QFrame()
        action.setObjectName("actionBar")
        action_l = QHBoxLayout(action)
        action_l.setContentsMargins(16, 14, 16, 14)
        action_l.setSpacing(16)

        sess_col = QVBoxLayout()
        sess_col.setSpacing(8)
        self.start_btn = QPushButton("Start session")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self._start_session)
        sess_col.addWidget(self.start_btn)
        self.end_btn = QPushButton("End session")
        self.end_btn.setObjectName("dangerBtn")
        self.end_btn.clicked.connect(self._end_session)
        sess_col.addWidget(self.end_btn)
        action_l.addLayout(sess_col)

        mode_col = QVBoxLayout()
        mode_col.setSpacing(4)
        mode_lab = QLabel("Talk mode")
        mode_lab.setObjectName("fieldLabel")
        mode_col.addWidget(mode_lab)
        self.conv_mode_combo = QComboBox()
        self.conv_mode_combo.addItem("Phone call", "call")
        self.conv_mode_combo.addItem("Push-to-talk", "ptt")
        mi = self.conv_mode_combo.findData(self._conversation_mode)
        self.conv_mode_combo.setCurrentIndex(mi if mi >= 0 else 0)
        self.conv_mode_combo.setToolTip(
            "Phone call: tutor speaks, then listens until you finish — no Record tap.\n"
            "Push-to-talk: tap Record for each answer."
        )
        self.conv_mode_combo.currentIndexChanged.connect(self._on_conv_mode_changed)
        mode_col.addWidget(self.conv_mode_combo)
        self.mute_btn = QPushButton("Mute call")
        self.mute_btn.setObjectName("ghostBtn")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setToolTip("Pause auto-listening in Phone call mode. Unmute to resume.")
        self.mute_btn.clicked.connect(self._toggle_mute)
        mode_col.addWidget(self.mute_btn)
        action_l.addLayout(mode_col)

        action_l.addStretch(1)

        rec_col = QVBoxLayout()
        rec_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rec_col.setSpacing(6)
        self.record_btn = QPushButton("Record")
        self.record_btn.setObjectName("recordBtn")
        self.record_btn.setCheckable(True)
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.clicked.connect(self._toggle_record)
        rec_col.addWidget(self.record_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.send_rec_btn = QPushButton("Send last take")
        self.send_rec_btn.setObjectName("sendSmallBtn")
        self.send_rec_btn.setToolTip("Optional — recording auto-sends when you stop.")
        self.send_rec_btn.clicked.connect(self._send_recording)
        rec_col.addWidget(self.send_rec_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        action_l.addLayout(rec_col)

        action_l.addStretch(1)

        status_col = QVBoxLayout()
        status_col.setSpacing(6)
        status_cap = QLabel("Status")
        status_cap.setObjectName("fieldLabel")
        status_col.addWidget(status_cap)
        self.status_label = QLabel("Ready — start a session. Phone call listens after the tutor speaks.")
        self.status_label.setObjectName("statusLine")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(260)
        status_col.addWidget(self.status_label)
        status_col.addStretch(1)
        action_l.addLayout(status_col, stretch=1)
        outer.addWidget(action)

        # 4 + 5) Main: chat + side panel ------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        chat_card = QFrame()
        chat_card.setObjectName("chatCard")
        chat_l = QVBoxLayout(chat_card)
        chat_l.setContentsMargins(14, 12, 14, 12)
        chat_l.setSpacing(8)
        chat_cap = QLabel("Conversation")
        chat_cap.setObjectName("sectionCaption")
        chat_l.addWidget(chat_cap)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Your session conversation appears here…")
        chat_l.addWidget(self.chat, stretch=1)

        self.transcript_label = QLabel("Last transcript: —")
        self.transcript_label.setObjectName("transcriptLabel")
        self.transcript_label.setWordWrap(True)
        chat_l.addWidget(self.transcript_label)

        # 6) Bottom type-to-send
        input_bar = QFrame()
        input_bar.setObjectName("inputBar")
        text_row = QHBoxLayout(input_bar)
        text_row.setContentsMargins(10, 8, 10, 8)
        text_row.setSpacing(8)
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Or type in the target language…")
        self.text_input.returnPressed.connect(self._send_text)
        text_row.addWidget(self.text_input, stretch=1)
        self.send_text_btn = QPushButton("Send")
        self.send_text_btn.setObjectName("primaryBtn")
        self.send_text_btn.clicked.connect(self._send_text)
        text_row.addWidget(self.send_text_btn)
        chat_l.addWidget(input_bar)

        splitter.addWidget(chat_card)

        side = QFrame()
        side.setObjectName("sideCard")
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(14, 12, 14, 12)
        side_l.setSpacing(10)

        side_cap = QLabel("Learner")
        side_cap.setObjectName("sectionCaption")
        side_l.addWidget(side_cap)

        self.level_display = QLabel("A1")
        self.level_display.setObjectName("cefrBadge")
        self.level_display.setMinimumHeight(64)
        side_l.addWidget(self.level_display)

        mem_cap = QLabel("Mistakes & successes")
        mem_cap.setObjectName("fieldLabel")
        side_l.addWidget(mem_cap)

        self.memory_panel = QTextEdit()
        self.memory_panel.setReadOnly(True)
        side_l.addWidget(self.memory_panel, stretch=1)

        refresh_mem = QPushButton("Refresh memory")
        refresh_mem.setObjectName("ghostBtn")
        refresh_mem.clicked.connect(self._refresh_level_and_memory)
        side_l.addWidget(refresh_mem)

        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([780, 320])
        outer.addWidget(splitter, stretch=1)

        hint = QLabel(
            "Install Ollama yourself and pull models (`ollama pull …`). "
            "This app only lists local models — it never installs or pulls them."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self._last_recording: Path | None = None

    # -- helpers ------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        enabled = not busy
        self.start_btn.setEnabled(enabled and not self.session.active)
        self.end_btn.setEnabled(enabled and self.session.active)
        ptt = self._conversation_mode == "ptt"
        self.record_btn.setEnabled(enabled and self.session.active and ptt)
        self.send_rec_btn.setEnabled(enabled and self.session.active and ptt)
        self.send_text_btn.setEnabled(enabled and self.session.active)
        self.text_input.setEnabled(enabled and self.session.active)
        self.refresh_btn.setEnabled(enabled)
        if hasattr(self, "mute_btn"):
            self.mute_btn.setEnabled(self.session.active and self._conversation_mode == "call")
        self._apply_mode_ui()

    def _set_session_controls(self, active: bool) -> None:
        self.start_btn.setEnabled(not active and not self._busy)
        self.end_btn.setEnabled(active and not self._busy)
        ptt = self._conversation_mode == "ptt"
        self.record_btn.setEnabled(active and not self._busy and ptt)
        self.send_rec_btn.setEnabled(active and not self._busy and ptt)
        self.send_text_btn.setEnabled(active and not self._busy)
        self.text_input.setEnabled(active and not self._busy)
        if hasattr(self, "mute_btn"):
            self.mute_btn.setEnabled(active and self._conversation_mode == "call")
            if not active:
                self.mute_btn.setChecked(False)
                self._call_muted = False
                self.mute_btn.setText("Mute call")
        self._apply_mode_ui()

    def _append_chat(self, role: str, text: str) -> None:
        body = self._esc(text)
        if role == "user":
            html = (
                '<table width="100%" cellspacing="0" cellpadding="0" style="margin:6px 0;">'
                '<tr><td align="right">'
                '<table cellspacing="0" cellpadding="10" bgcolor="#4338ca" width="78%">'
                "<tr><td>"
                '<font color="#c7d2fe" size="2"><b>You</b></font><br>'
                f'<font color="#ffffff">{body}</font>'
                "</td></tr></table>"
                "</td></tr></table>"
            )
        else:
            html = (
                '<table width="100%" cellspacing="0" cellpadding="0" style="margin:6px 0;">'
                "<tr><td align=\"left\">"
                '<table cellspacing="0" cellpadding="10" bgcolor="#252b3a" width="82%">'
                "<tr><td>"
                '<font color="#a5b4fc" size="2"><b>Tutor</b></font><br>'
                f'<font color="#e8eaef">{body}</font>'
                "</td></tr></table>"
                "</td></tr></table>"
            )
        self.chat.append(html)
        self.chat.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _esc(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

    def _on_media_status(self, status) -> None:
        """Start playback only once media is actually loaded/buffered."""
        if not self._play_when_ready:
            return
        ready = (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        )
        if status in ready:
            self._play_when_ready = False
            self._player.play()

    def _on_player_error(self, error, error_string: str = "") -> None:
        msg = error_string or str(error)
        logger.warning("Media player error: %s", msg)
        try:
            self.status_label.setText(f"Audio playback issue: {msg[:80]}")
        except Exception:
            pass

    def _play_audio(self, path: str | None) -> None:
        # Never listen while the tutor is speaking (echo on BT headsets).
        self._disarm_listen(cancel_rec=True)
        if not path:
            self._schedule_listen_after_playback()
            return
        p = Path(path)
        if not p.is_file():
            self._schedule_listen_after_playback()
            return
        # Keep a strong ref so the path string / file isn't GC'd mid-play.
        self._current_audio_path = str(p.resolve())
        self._play_when_ready = False
        self._player.stop()
        self._cli_player.stop()
        self._awaiting_playback = False
        self._playback_backend = None
        self._qt_play_started = False
        self._playback_watch.stop()
        # Preferred path on Linux: paplay/pw-play straight to the chosen Pulse/PipeWire
        # sink. Qt's QAudioOutput binds to the device present at startup and goes
        # silent when a Bluetooth headset flips A2DP<->HFP (e.g. when the BT mic opens).
        if audio_output.has_cli_player():
            sink = audio_output.resolve_sink(self._output_sink_pref)
            if self._cli_player.play(self._current_audio_path, sink):
                self._awaiting_playback = True
                self._playback_backend = "cli"
                self._playback_watch.start()
                return
        try:
            from PySide6.QtMultimedia import QMediaDevices
            self._audio_out.setDevice(QMediaDevices.defaultAudioOutput())
        except Exception:
            pass
        # Clear source so GStreamer does not reuse a stale buffer for the same URL.
        # Keep awaiting=False while clearing so StoppedState does not arm the mic early.
        self._player.setSource(QUrl())
        self._play_when_ready = True
        self._playback_backend = "qt"
        self._awaiting_playback = True
        self._player.setSource(QUrl.fromLocalFile(self._current_audio_path))
        # If the backend already reports ready synchronously, play now.
        status = self._player.mediaStatus()
        ready = (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        )
        if status in ready:
            self._play_when_ready = False
            self._player.play()

    def _refresh_level_and_memory(self) -> None:
        learner = self.memory.get_learner()
        mode = "auto" if learner.get("level_auto") else "manual"
        level = learner.get("cefr_level", "?")
        if self.session.active:
            level = self.session.level
            mode = "auto" if self.session.level_auto else "manual"
        self.level_display.setText(f"{level}\n{mode}")
        self.memory_panel.setPlainText(self.memory.memory_panel_text())

    def _update_meter(self) -> None:
        if not self.recorder.is_recording:
            return
        rms, peak = self.recorder.level()
        bars = min(20, int(min(1.0, rms * 6) * 20))
        meter = f"[{'#'*bars}{'-'*(20-bars)}]  peak {int(peak*100)}%"
        name = getattr(self, "_rec_name", "")
        if self._call_listening:
            hint = "speak — I will stop when you finish"
            if self._vad.speech_seen:
                hint = "listening… pause when done"
            self.status_label.setText(f"Your turn — {name}  {meter} — {hint}")
        else:
            self.status_label.setText(
                f"Recording · {name}  {meter} — tap to stop & send"
            )

    def _refresh_mics(self) -> None:
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        devs = list_input_devices()
        chosen = resolve_input_device(self.recorder.device)
        for d in devs:
            self.mic_combo.addItem(device_label(d), d["index"])
            self.mic_combo.setItemData(self.mic_combo.count() - 1, d["name"], Qt.ItemDataRole.ToolTipRole)
        if not devs:
            self.mic_combo.addItem("(no input devices)", None)
        pos = self.mic_combo.findData(chosen)
        if pos >= 0:
            self.mic_combo.setCurrentIndex(pos)
        self.mic_combo.blockSignals(False)
        logging.getLogger(__name__).info("Mic default resolved to %s (%s)", chosen, self.mic_combo.currentText())
        cur = load_settings()
        name = self.mic_combo.itemData(self.mic_combo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
        if name and (cur.get("input_device_name") != name):
            if not cur.get("input_device_name") or name.startswith("bluez_input"):
                save_settings({"input_device_index": chosen, "input_device_name": name})
                self.recorder.set_device(name)

    def _refresh_outputs(self) -> None:
        self.out_combo.blockSignals(True)
        self.out_combo.clear()
        self.out_combo.addItem("System default", "__default__")
        for d in audio_output.list_sinks():
            self.out_combo.addItem(d["label"], d["name"])
            self.out_combo.setItemData(self.out_combo.count() - 1, d["name"], Qt.ItemDataRole.ToolTipRole)
        want = self._output_sink_pref
        if not want:
            # Default: Bluetooth sink if present, else system default.
            bt = [self.out_combo.itemData(i) for i in range(self.out_combo.count())
                  if str(self.out_combo.itemData(i)).startswith("bluez_output")]
            want = bt[0] if bt else "__default__"
            self._output_sink_pref = want
        pos = self.out_combo.findData(want)
        if pos < 0 and str(want).startswith("bluez_output."):
            mac = str(want).split(".")[1]
            for i in range(self.out_combo.count()):
                if mac in str(self.out_combo.itemData(i)):
                    pos = i
                    break
        self.out_combo.setCurrentIndex(pos if pos >= 0 else 0)
        self.out_combo.blockSignals(False)
        logger.info("Output sink resolved to %s", self.out_combo.currentData())

    def _on_output_changed(self, _i: int) -> None:
        name = self.out_combo.currentData()
        if not name:
            return
        self._output_sink_pref = name
        save_settings({"output_sink": name})
        self.status_label.setText(f"Output set to {self.out_combo.currentText()}")

    def _on_mic_changed(self, _i: int) -> None:
        idx = self.mic_combo.currentData()
        if idx is None:
            return
        name = self.mic_combo.itemData(self.mic_combo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
        self.recorder.set_device(name or idx)
        save_settings({"input_device_index": idx, "input_device_name": name})
        self.status_label.setText(f"Mic set to {self.mic_combo.currentText()}")

    def _refresh_models(self) -> None:
        if hasattr(self, "mic_combo") and not self.recorder.is_recording:
            self._refresh_mics()
        if hasattr(self, "out_combo"):
            self._refresh_outputs()
        ok, models, msg = ollama_client.status_message()
        backends = ", ".join(tts.available_backends()) or "none"
        prefix = "[OK]" if ok else "[--]"
        short = msg if len(msg) < 72 else msg[:69] + "…"
        self.ollama_label.setText(f"{prefix}  {short}   ·   TTS: {backends}")
        self.ollama_label.setToolTip(f"{msg}\nTTS backends: {backends}")
        current = self.model_combo.currentText()
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
            if current in models:
                self.model_combo.setCurrentText(current)
            else:
                self.model_combo.setCurrentIndex(0)
        else:
            self.model_combo.addItem("(no models — pull one with ollama)")

    def _apply_level(self) -> None:
        level = self.level_combo.currentText()
        auto = self.level_auto.isChecked()
        self.memory.set_level(level, auto=auto)
        if self.session.active:
            self.session.level = level
            self.session.level_auto = auto
        self._refresh_level_and_memory()
        self.status_label.setText(f"Level set to {level} (auto={auto})")

    def _run_worker(self, worker: QObject, finished_slot) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)  # type: ignore[attr-defined]
        worker.finished.connect(finished_slot)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        if hasattr(worker, "status"):
            worker.status.connect(self.status_label.setText)
        self._thread = thread
        self._worker = worker
        self._set_busy(True)
        thread.start()

    # -- actions ------------------------------------------------------------

    def _start_session(self) -> None:
        model = self.model_combo.currentText().strip()
        if not model or model.startswith("("):
            QMessageBox.warning(
                self,
                "No model",
                "No Ollama model selected.\n\n"
                "Install Ollama from https://ollama.com, pull a model "
                "(e.g. `ollama pull llama3.2`), then click Refresh.",
            )
            return
        ok, models, msg = ollama_client.status_message()
        if not ok or model not in models:
            QMessageBox.warning(self, "Ollama", msg)
            return

        if self.session.active:
            self.session.end()

        kwargs = dict(
            target=self.target_combo.currentText(),
            native=self.native_combo.currentText(),
            level=self.level_combo.currentText(),
            mode=self.mode_combo.currentData() or DEFAULT_MODE,
            model=model,
            level_auto=self.level_auto.isChecked(),
        )
        self.chat.clear()
        worker = SessionStartWorker(self.session, kwargs)
        self._run_worker(worker, self._on_session_started)

    @Slot(object, object, object, object)
    def _on_session_started(self, opening, note, path, err) -> None:
        self._set_busy(False)
        if err is not None:
            QMessageBox.critical(self, "Start failed", str(err))
            self._set_session_controls(active=False)
            return

        self._append_chat("tutor", opening or "")
        self._set_session_controls(active=True)
        self._refresh_level_and_memory()
        mode_lbl = "Phone call" if self._conversation_mode == "call" else "Push-to-talk"
        self.status_label.setText(
            f"Session started · {mode_lbl} · {self.session.model} · "
            f"{self.session.mode} · {self.session.level} · TTS: {note}"
        )
        self._play_audio(path if isinstance(path, str) else None)

    def _end_session(self) -> None:
        self._disarm_listen(cancel_rec=True)
        self._awaiting_playback = False
        self._playback_watch.stop()
        self._arm_delay.stop()
        self._cli_player.stop()
        try:
            self._player.stop()
        except Exception:
            pass
        if self.recorder.is_recording:
            self.recorder.cancel()
        self.record_btn.setChecked(False)
        self.record_btn.setText("Record")
        worker = SessionEndWorker(self.session)
        self._run_worker(worker, self._on_session_ended)

    @Slot(str, object)
    def _on_session_ended(self, msg: str, err) -> None:
        self._set_busy(False)
        self._disarm_listen(cancel_rec=True)
        if err:
            QMessageBox.warning(self, "End session", str(err))
        self._set_session_controls(active=False)
        self.status_label.setText(msg or "Session ended.")
        self._refresh_level_and_memory()

    def _toggle_record(self) -> None:
        if not self.session.active:
            self.record_btn.setChecked(False)
            return
        if self._conversation_mode != "ptt":
            # Phone call owns the mic; Record is a manual fallback only in PTT.
            self.record_btn.setChecked(False)
            self.status_label.setText("Phone call mode listens automatically — switch Talk mode to Push-to-talk for Record.")
            return
        if self.record_btn.isChecked():
            try:
                self.recorder.start()
            except Exception as exc:
                self.record_btn.setChecked(False)
                QMessageBox.critical(self, "Mic error", str(exc))
                return
            self.record_btn.setText("Stop")
            self._rec_name = friendly_mic_name(self.recorder.active_device_name)
            self.status_label.setText(f"Recording · {self._rec_name} — tap again to stop & send.")
            if not hasattr(self, "_meter_timer"):
                self._meter_timer = QTimer(self)
                self._meter_timer.setInterval(150)
                self._meter_timer.timeout.connect(self._update_meter)
            self._meter_timer.start()
            self._last_recording = None
        else:
            path = self.recorder.stop()
            if hasattr(self, "_meter_timer"):
                self._meter_timer.stop()
            self.record_btn.setText("Record")
            if path is None:
                self.status_label.setText("No audio captured.")
                self._last_recording = None
            else:
                self._last_recording = path
                m = self.recorder.last_meta
                self.status_label.setText(
                    f"Captured {m.get('duration', 0):.1f}s · peak {int(m.get('peak', 0)*100)}% · {m.get('device_name', '')} — transcribing…"
                )
                self._send_recording()

    def _send_recording(self) -> None:
        was_call = self._call_listening
        self._vad_timer.stop()
        self._call_listening = False
        if self.recorder.is_recording:
            path = self.recorder.stop()
            self.record_btn.setChecked(False)
            self.record_btn.setText("Record")
            self._last_recording = path
        if hasattr(self, "_meter_timer"):
            self._meter_timer.stop()
        path = self._last_recording
        if path is None or not path.is_file():
            if was_call and self._conversation_mode == "call" and self.session.active and not self._call_muted:
                self.status_label.setText("Did not catch audio — listening again.")
                self._schedule_listen_after_playback(delay_ms=400)
                return
            if not was_call:
                QMessageBox.information(
                    self,
                    "No recording",
                    "Tap Record, speak, then stop — audio sends automatically.",
                )
            return
        worker = TurnWorker(
            self.session,
            audio_path=str(path),
            target=self.target_combo.currentText(),
            native=self.native_combo.currentText(),
            bluetooth=bool(self.recorder.last_meta.get("bluetooth") or self.recorder.active_is_bluetooth),
        )
        self._run_worker(worker, self._on_turn_done)

    def _send_text(self) -> None:
        text = self.text_input.text().strip()
        if not text:
            return
        self._disarm_listen(cancel_rec=True)
        self.text_input.clear()
        worker = TurnWorker(self.session, typed_text=text)
        self._run_worker(worker, self._on_turn_done)

    @Slot(str, str, str, object, object)
    def _on_turn_done(self, user: str, reply: str, note: str, audio_path, err) -> None:
        self._set_busy(False)
        self._set_session_controls(active=self.session.active)
        if err:
            QMessageBox.warning(self, "Turn failed", str(err))
            self.status_label.setText(str(err))
            if self.session.active and self._conversation_mode == "call" and not self._call_muted:
                self._schedule_listen_after_playback(delay_ms=600)
            return
        if not user or len(user.strip()) < 3:
            note = (note or "") + " (Transcript looks empty — check the Mic dropdown.)"
        if user:
            self._append_chat("user", user)
            self.transcript_label.setText(f"Last transcript: {user}")
        if reply:
            self._append_chat("tutor", reply)
        self._refresh_level_and_memory()
        self.status_label.setText(note or "Done.")
        self._last_recording = None
        # Empty user turn in call mode with no tutor reply: re-arm listen.
        if (
            self.session.active
            and self._conversation_mode == "call"
            and not reply
            and not isinstance(audio_path, str)
        ):
            self._schedule_listen_after_playback(delay_ms=500)
            return
        if isinstance(audio_path, str):
            self._play_audio(audio_path)
        elif self.session.active and self._conversation_mode == "call":
            self._schedule_listen_after_playback(delay_ms=300)

    # -- phone-call / VAD ---------------------------------------------------

    def _is_call_mode(self) -> bool:
        return self._conversation_mode == "call"

    def _apply_mode_ui(self) -> None:
        if not hasattr(self, "record_btn"):
            return
        call = self._is_call_mode()
        # Record stays visible as optional fallback hint in call mode, but disabled.
        self.record_btn.setVisible(True)
        self.send_rec_btn.setVisible(not call)
        if hasattr(self, "mute_btn"):
            self.mute_btn.setVisible(call)
            self.mute_btn.setEnabled(self.session.active and call and not self._busy)

    def _on_conv_mode_changed(self, _i: int = 0) -> None:
        data = self.conv_mode_combo.currentData()
        self._conversation_mode = "ptt" if data == "ptt" else "call"
        save_settings({"conversation_mode": self._conversation_mode})
        if self._conversation_mode == "ptt":
            self._disarm_listen(cancel_rec=True)
            self._arm_delay.stop()
            self._call_muted = False
            if hasattr(self, "mute_btn"):
                self.mute_btn.setChecked(False)
                self.mute_btn.setText("Mute call")
            self.status_label.setText("Push-to-talk — tap Record for each answer.")
        else:
            self.status_label.setText("Phone call — tutor speaks, then listens until you finish.")
            if self.session.active and not self._busy and not self._call_muted and not self._awaiting_playback:
                self._schedule_listen_after_playback(delay_ms=200)
        self._set_session_controls(active=self.session.active)

    def _toggle_mute(self) -> None:
        self._call_muted = self.mute_btn.isChecked()
        if self._call_muted:
            self.mute_btn.setText("Unmute call")
            self._disarm_listen(cancel_rec=True)
            self._arm_delay.stop()
            self._awaiting_playback = False
            self._playback_watch.stop()
            self.status_label.setText("Call muted — auto-listen paused. Unmute or End session.")
        else:
            self.mute_btn.setText("Mute call")
            self.status_label.setText("Call unmuted — listening for your turn.")
            if self.session.active and not self._busy:
                self._schedule_listen_after_playback(delay_ms=200)

    def _disarm_listen(self, cancel_rec: bool = False) -> None:
        self._vad_timer.stop()
        self._call_listening = False
        if cancel_rec and self.recorder.is_recording:
            self.recorder.cancel()
        if hasattr(self, "_meter_timer"):
            self._meter_timer.stop()
        self.record_btn.setChecked(False)
        if self._conversation_mode == "ptt":
            self.record_btn.setText("Record")

    def _schedule_listen_after_playback(self, delay_ms: int | None = None) -> None:
        """Arm VAD listening after TTS finishes (or immediately if nothing to play)."""
        if not self.session.active or not self._is_call_mode() or self._call_muted or self._busy:
            return
        self._arm_delay.stop()
        ms = VAD_POST_PLAYBACK_DELAY_MS if delay_ms is None else delay_ms
        self._arm_delay.start(max(50, int(ms)))

    def _check_playback_done(self) -> None:
        if not self._awaiting_playback:
            self._playback_watch.stop()
            return
        if self._playback_backend == "cli":
            if not self._cli_player.is_playing():
                self._awaiting_playback = False
                self._playback_watch.stop()
                self._on_tutor_finished_speaking()
        # qt path handled via playbackStateChanged / mediaStatus

    def _on_playback_state(self, state) -> None:
        if not self._awaiting_playback or self._playback_backend != "qt":
            return
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._qt_play_started = True
            return
        if state == QMediaPlayer.PlaybackState.StoppedState and self._qt_play_started:
            self._qt_play_started = False
            self._awaiting_playback = False
            self._playback_watch.stop()
            self._on_tutor_finished_speaking()

    def _on_media_status_end(self, status) -> None:
        if not self._awaiting_playback or self._playback_backend != "qt":
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._awaiting_playback = False
            self._playback_watch.stop()
            self._on_tutor_finished_speaking()

    def _on_tutor_finished_speaking(self) -> None:
        self._schedule_listen_after_playback()

    def _arm_listen(self) -> None:
        if not self.session.active or not self._is_call_mode() or self._call_muted or self._busy:
            return
        if self._awaiting_playback or self._cli_player.is_playing():
            return
        if self.recorder.is_recording:
            return
        try:
            self.recorder.start()
        except Exception as exc:
            self.status_label.setText(f"Mic error: {exc}")
            QMessageBox.critical(self, "Mic error", str(exc))
            return
        self._vad.reset()
        self._call_listening = True
        self._rec_name = friendly_mic_name(self.recorder.active_device_name)
        self._last_recording = None
        self.record_btn.setChecked(True)
        self.record_btn.setText("Listening")
        self.status_label.setText(f"Your turn — speak ({self._rec_name})")
        if not hasattr(self, "_meter_timer"):
            self._meter_timer = QTimer(self)
            self._meter_timer.setInterval(150)
            self._meter_timer.timeout.connect(self._update_meter)
        self._meter_timer.start()
        self._vad_timer.start()
        logger.info("Call listen armed on %s", self.recorder.active_device_name)

    def _on_vad_tick(self) -> None:
        if not self._call_listening or not self.recorder.is_recording:
            self._vad_timer.stop()
            return
        rms, _peak = self.recorder.level()
        dt = VAD_POLL_MS / 1000.0
        if self._vad.feed(rms, dt):
            logger.info("VAD end reason=%s speech=%.2fs silence=%.2fs",
                        self._vad.reason, self._vad.speech_accum, self._vad.silence_accum)
            self._finish_call_utterance()

    def _finish_call_utterance(self) -> None:
        if not self._call_listening:
            return
        self._vad_timer.stop()
        self._call_listening = False
        path = self.recorder.stop()
        if hasattr(self, "_meter_timer"):
            self._meter_timer.stop()
        self.record_btn.setChecked(False)
        self.record_btn.setText("Record")
        if path is None:
            self.status_label.setText("No speech detected — listening again.")
            self._schedule_listen_after_playback(delay_ms=400)
            return
        self._last_recording = path
        m = self.recorder.last_meta
        self.status_label.setText(
            f"Captured {m.get('duration', 0):.1f}s · peak {int(m.get('peak', 0)*100)}% · "
            f"{m.get('device_name', '')} — transcribing…"
        )
        self._send_recording()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._disarm_listen(cancel_rec=True)
        self._arm_delay.stop()
        self._playback_watch.stop()
        self._cli_player.stop()
        if self.recorder.is_recording:
            self.recorder.cancel()
        if self.session.active:
            try:
                self.session.end()
            except Exception:
                pass
        super().closeEvent(event)


def build_window() -> MainWindow:
    """Construct the main window (for tests / launch)."""
    ensure_dirs()
    return MainWindow()


def launch() -> None:
    """Open the native desktop application window."""
    ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # High-DPI friendly
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Babel Agent")
    app.setApplicationDisplayName("Babel Agent")
    app.setDesktopFileName("babel-agent")
    app.setOrganizationName("BabelAgent")
    app.setStyle("Fusion")
    icon_file = asset_path("icon.png")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))
    win = build_window()
    win.show()
    sys.exit(app.exec())
