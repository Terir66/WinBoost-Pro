"""
ui/services_screen.py — экран «Службы».

QGridLayout внутри QScrollArea, каждая служба — ServiceCard с раскрытием.
Логика (ServiceManager, профили, зависимости) осталась в services.py.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from . import strings as S
from .theme import add_shadow
from .widgets import AnimatedButton, ServiceCard

from services import PROFILES, ChangeItem, ServiceInfo


class ServicesScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.cards: dict[str, ServiceCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel(S.NAV_SERVICES)
        title.setObjectName("heroTitle")
        subtitle = QLabel(S.SERVICES_SUBTITLE)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # --- профили ---
        card = QFrame()
        card.setObjectName("card")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        # Тень на контейнере с активными кнопками в Qt может смещать рендер
        # дочерних виджетов — здесь используем только градиент и рамку.
        card_layout.addWidget(QLabel(S.PROFILE_LABEL))
        self.profile_combo = QComboBox()
        self.profile_combo.addItem(S.PROFILE_PLACEHOLDER, None)
        for name in PROFILES:
            self.profile_combo.addItem(name, name)
        self.profile_combo.setMinimumWidth(260)
        card_layout.addWidget(self.profile_combo)
        self.apply_btn = AnimatedButton(S.BTN_APPLY_PROFILE)
        self.apply_btn.setObjectName("accent")
        self.apply_btn.clicked.connect(self._apply_profile)
        card_layout.addWidget(self.apply_btn)
        self.restore_btn = AnimatedButton(S.BTN_RESTORE_COPY)
        self.restore_btn.clicked.connect(self.main.restore_services)
        card_layout.addWidget(self.restore_btn)
        self.refresh_btn = AnimatedButton(S.BTN_REFRESH)
        self.refresh_btn.clicked.connect(self.main.scan_services)
        card_layout.addWidget(self.refresh_btn)
        card_layout.addStretch()
        layout.addWidget(card)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # --- карточки служб ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.scroll.setMinimumWidth(0)
        self.content = QWidget()
        self.content.setMinimumWidth(0)
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, stretch=1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        layout.addWidget(self.log)

        try:
            self.main.service_log.connect(self.log.append)
            self.main.service_progress.connect(self.progress.setValue)
            self.main.services_ready.connect(self._render_services)
            self.main.plan_ready.connect(self._show_plan)
            self.main.service_state.connect(self._set_busy)
        except Exception:
            pass

    def _set_busy(self, busy: bool) -> None:
        for btn in (self.apply_btn, self.restore_btn, self.refresh_btn):
            btn.setEnabled(not busy)

    def _render_services(self, services: list[ServiceInfo]) -> None:
        try:
            while self.grid.count():
                item = self.grid.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            self.cards.clear()
            for index, svc in enumerate(services):
                callbacks = {
                    "stop": lambda name=svc.name: self.main.control_service(name, "stop"),
                    "start": lambda name=svc.name: self.main.control_service(name, "start"),
                    "type": lambda name=svc.name: self.main.control_service(name, "type"),
                }
                card = ServiceCard(svc.name, svc.display_name,
                                   svc.status, svc.start_type, callbacks)
                # карточка не должна «растягивать» сетку своей длинной подписью
                card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                self.cards[svc.name.lower()] = card
                self.grid.addWidget(card, index // 3, index % 3)
            for column in range(3):
                self.grid.setColumnStretch(column, 1)
        except Exception as exc:
            self.main.service_log.emit(f"Ошибка отображения служб: {exc}")

    def _apply_profile(self) -> None:
        profile = self.profile_combo.currentData()
        if profile:
            self.main.plan_profile(profile)

    def _show_plan(self, plan: list[ChangeItem]) -> None:
        if not plan:
            return
        lines = ["Будут изменены следующие службы:\n"]
        for item in plan:
            state = "⛔ " + item.reason if item.blocked else "✓"
            lines.append(
                f"{state} {item.name}: {item.current_start_type} → "
                f"{item.target_start_type}" + (f" — {item.comment}" if item.comment else "")
            )
        dialog = QMessageBox(self)
        dialog.setWindowTitle(S.PROFILE_CONFIRM_TITLE)
        dialog.setText("\n".join(lines[:40]))
        dialog.setInformativeText("Заблокированные службы не будут изменены. Продолжить?")
        dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if dialog.exec() == QMessageBox.Ok:
            applicable = [item for item in plan if not item.blocked]
            if applicable:
                self.main.apply_plan(applicable)
