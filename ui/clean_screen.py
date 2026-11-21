"""
ui/clean_screen.py — экран «Очистка» (детальный режим).

Сохраняет исходную логику: чекбоксы, сканирование, очистка, лог и прогресс.
 Управление потоками выполняет MainWindow.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import strings as S
from .theme import add_shadow
from .widgets import AnimatedButton
from cache import build_targets


class CleanScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        title = QLabel(S.NAV_CLEAN)
        title.setObjectName("heroTitle")
        subtitle = QLabel(S.CLEAN_SUBTITLE)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        add_shadow(card, blur=15, dy=3)

        self.checkboxes: dict[str, QCheckBox] = {}
        for key, target in build_targets().items():
            cb = QCheckBox(target.label)
            cb.setChecked(True)
            self.checkboxes[key] = cb
            card_layout.addWidget(cb)
        layout.addWidget(card)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, stretch=1)

        buttons = QHBoxLayout()
        self.scan_btn = AnimatedButton(S.BTN_SCAN)
        self.clean_btn = AnimatedButton(S.BTN_CLEAN_START)
        self.clean_btn.setObjectName("accent")
        self.scan_btn.clicked.connect(self._scan)
        self.clean_btn.clicked.connect(self._clean)
        buttons.addWidget(self.scan_btn)
        buttons.addWidget(self.clean_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        try:
            self.main.clean_log.connect(self.log.append)
            self.main.clean_progress.connect(self.progress.setValue)
            self.main.clean_state.connect(self._set_busy)
        except Exception:
            pass

    def selected_keys(self) -> list[str]:
        return [k for k, cb in self.checkboxes.items() if cb.isChecked()]

    def _set_busy(self, busy: bool) -> None:
        self.scan_btn.setEnabled(not busy)
        self.clean_btn.setEnabled(not busy)
        for cb in self.checkboxes.values():
            cb.setEnabled(not busy)

    def _scan(self) -> None:
        keys = self.selected_keys()
        if keys:
            self.main.start_scan(keys)

    def _clean(self) -> None:
        keys = self.selected_keys()
        if keys:
            self.main.start_clean(keys)
