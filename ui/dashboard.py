"""
ui/dashboard.py — экран «Главная» в стиле BoosterX.

Главный hero-блок с анализом системы («Начать оптимизацию»), плитки метрик,
круглая кнопка быстрой очистки и плашки CPU/RAM/GPU с миганием >80%.
Логика анализа/очистки остаётся в MainWindow.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import strings as S
from .theme import add_shadow
from .widgets import AnimatedButton, QuickCleanWidget, SystemCard
from .system_info import SystemMonitorWorker, cpu_name, gpu_name

from cache import build_targets, human_size


class DashboardScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ---------------------------------------------------------------- HERO
        hero = QFrame()
        hero.setObjectName("hero")
        add_shadow(hero, blur=24, dy=6, alpha=110)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(30, 24, 30, 24)
        hero_layout.setSpacing(26)

        left = QVBoxLayout()
        eyebrow = QLabel(S.DASHBOARD_EYEBROW)
        eyebrow.setObjectName("sectionTitle")
        title = QLabel(S.DASHBOARD_TITLE)
        title.setObjectName("heroTitle")
        title.setWordWrap(True)
        title.setMinimumHeight(44)
        desc = QLabel(
            "Сначала анализируем конфигурацию, затем вы выбираете изменения\n"
            "и проверяете их последствия перед применением."
        )
        desc.setObjectName("subtitle")
        desc.setWordWrap(True)
        desc.setMinimumHeight(42)
        desc.setMaximumWidth(560)

        self.analyze_btn = AnimatedButton(S.BTN_START_OPTIMIZATION)
        self.analyze_btn.setObjectName("accent")
        self.analyze_btn.setFixedWidth(230)
        self.analyze_btn.setMinimumHeight(46)
        self.analyze_btn.clicked.connect(self._on_analyze)

        hint = QLabel(S.DASHBOARD_HINT)
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        hint.setMinimumHeight(26)

        left.addWidget(eyebrow)
        left.addWidget(title)
        left.addWidget(desc)
        left.addSpacing(12)
        left.addWidget(self.analyze_btn, alignment=Qt.AlignLeft)
        left.addSpacing(10)
        left.addWidget(hint)
        left.addStretch()
        hero_layout.addLayout(left, stretch=3)

        # плитки метрик
        grid = QGridLayout()
        grid.setSpacing(12)
        self.tile_cpu = self._metric_tile(S.METRIC_CPU, "0%")
        self.tile_gpu = self._metric_tile(S.METRIC_GPU, S.NOT_AVAILABLE)
        self.tile_ram = self._metric_tile(S.METRIC_RAM, "0%")
        self.tile_score = self._metric_tile(S.METRIC_SCORE, "—")
        for i, tile in enumerate((self.tile_cpu, self.tile_gpu,
                                  self.tile_ram, self.tile_score)):
            grid.addWidget(tile, i // 2, i % 2)
        hero_layout.addLayout(grid, stretch=2)
        layout.addWidget(hero)

        # ---------------------------------------------------------------- строки
        top = QHBoxLayout()
        top.setSpacing(16)

        clean_card = QFrame()
        clean_card.setObjectName("card")
        clean_layout = QVBoxLayout(clean_card)
        clean_layout.setContentsMargins(18, 14, 18, 14)
        clean_layout.setAlignment(Qt.AlignCenter)
        add_shadow(clean_card)
        self.quick = QuickCleanWidget()
        self.quick.clicked.connect(self._on_quick_clean)
        clean_layout.addWidget(self.quick, alignment=Qt.AlignCenter)
        self.quick_hint = QLabel(S.QUICK_CLEAN)
        self.quick_hint.setObjectName("subtitle")
        self.quick_hint.setAlignment(Qt.AlignCenter)
        clean_layout.addWidget(self.quick_hint)
        top.addWidget(clean_card, stretch=1)

        state_card = QFrame()
        state_card.setObjectName("card")
        state_layout = QVBoxLayout(state_card)
        state_layout.setContentsMargins(18, 14, 18, 14)
        state_layout.setSpacing(10)
        add_shadow(state_card)
        section = QLabel(S.SYSTEM_STATE)
        section.setObjectName("sectionTitle")
        state_layout.addWidget(section)
        self.cpu_card = SystemCard("CPU", "#4A7DFF")
        self.ram_card = SystemCard("RAM", "#8B5CF6")
        self.gpu_card = SystemCard("GPU", "#4ADE80")
        for card in (self.cpu_card, self.ram_card, self.gpu_card):
            state_layout.addWidget(card)
        self.cpu_info = QLabel(cpu_name())
        self.cpu_info.setObjectName("subtitle")
        state_layout.addWidget(self.cpu_info)
        self.gpu_info = QLabel(f"GPU: {gpu_name()}")
        self.gpu_info.setObjectName("subtitle")
        state_layout.addWidget(self.gpu_info)
        top.addWidget(state_card, stretch=2)
        layout.addLayout(top)

        # ---------------------------------------------------------------- цели
        targets_card = QFrame()
        targets_card.setObjectName("card")
        targets_layout = QVBoxLayout(targets_card)
        targets_layout.setContentsMargins(18, 12, 18, 12)
        add_shadow(targets_card)
        targets_title = QLabel(S.EXPERT_MENU)
        targets_title.setObjectName("sectionTitle")
        targets_layout.addWidget(targets_title)

        self.checkboxes: dict[str, QCheckBox] = {}
        check_row = QHBoxLayout()
        for key, target in build_targets().items():
            cb = QCheckBox(target.label)
            cb.setChecked(True)
            self.checkboxes[key] = cb
            check_row.addWidget(cb)
        check_row.addStretch()
        targets_layout.addLayout(check_row)

        self.estimate_label = QLabel(S.ESTIMATE_HINT)
        self.estimate_label.setObjectName("subtitle")
        targets_layout.addWidget(self.estimate_label)
        layout.addWidget(targets_card)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        self.log.setPlaceholderText(S.LOG_PLACEHOLDER)
        layout.addWidget(self.log)

        try:
            self.main.clean_log.connect(self.log.append)
            self.main.clean_progress.connect(self.quick.set_value)
            self.main.clean_state.connect(self._on_clean_state)
            self.main.scan_result.connect(self._on_scan_result)
            self.main.clean_state.connect(self._on_analyze_state)
        except Exception:
            pass

        # стартовые значения — без обращения к WMI в GUI-потоке
        self.cpu_card.set_value(0)
        self.ram_card.set_value(0, "—")
        self.gpu_card.set_value(0, gpu_name()[:34])

        # тяжёлый опрос GPU/Metrics вынесен в фоновый поток
        self.monitor_worker = SystemMonitorWorker(2500, self)
        self.monitor_worker.metrics.connect(self._apply_metrics)
        self.monitor_worker.start()

    def stop_monitor(self) -> None:
        try:
            if self.monitor_worker and self.monitor_worker.isRunning():
                self.monitor_worker.stop()
                self.monitor_worker.wait(1500)
        except Exception:
            pass

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _metric_tile(title: str, value: str) -> QFrame:
        tile = QFrame()
        tile.setObjectName("card")
        inner = QVBoxLayout(tile)
        inner.setContentsMargins(14, 10, 14, 10)
        t = QLabel(title)
        t.setObjectName("sectionTitle")
        v = QLabel(value)
        v.setObjectName("heroTitle")
        v.setProperty("metric", title)
        inner.addWidget(t)
        inner.addWidget(v)
        add_shadow(tile, blur=12, alpha=70)
        return tile

    def _set_metric(self, tile: QFrame, value: str) -> None:
        try:
            for label in tile.findChildren(QLabel):
                if label.property("metric"):
                    label.setText(value)
        except Exception:
            pass

    def selected_keys(self) -> list[str]:
        return [key for key, cb in self.checkboxes.items() if cb.isChecked()]

    def _on_analyze(self) -> None:
        keys = self.selected_keys() or list(self.checkboxes)
        self.main.start_scan(keys)

    def _on_quick_clean(self) -> None:
        keys = self.selected_keys() or list(self.checkboxes)
        self.main.start_clean(keys)

    def _on_analyze_state(self, busy: bool) -> None:
        self.analyze_btn.setEnabled(not busy)

    def _on_clean_state(self, busy: bool) -> None:
        self.quick.set_busy(busy)
        for cb in self.checkboxes.values():
            cb.setEnabled(not busy)

    def _on_scan_result(self, total: int) -> None:
        try:
            self.estimate_label.setText(
                f"Доступно к очистке: {human_size(total)}"
            )
        except Exception:
            self.estimate_label.setText("Доступно к очистке: н/д")

    def _apply_metrics(self, cpu: float, ram: float, gpu: float,
                       free_gb: float) -> None:
        """Вызывается сигналом из фонового потока — только обновление GUI."""
        try:
            gpu_text = f"{gpu:.0f}%" if gpu > 0 else gpu_name()[:34]
            self.cpu_card.set_value(cpu)
            self.ram_card.set_value(ram, f"{ram:.0f}% · {free_gb:.1f} ГБ свободно")
            self.gpu_card.set_value(gpu, gpu_text)
            self._set_metric(self.tile_cpu, f"{cpu:.0f}%")
            self._set_metric(self.tile_ram, f"{ram:.0f}%")
            self._set_metric(self.tile_gpu, gpu_text)
        except Exception:
            pass
