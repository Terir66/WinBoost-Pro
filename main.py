"""
main.py — точка входа WinBoost Pro.

ГАРАНТИРОВАННЫЕ ПРАВА АДМИНИСТРАТОРА:
проверка ctypes.windll.shell32.IsUserAnAdmin() выполняется САМОЙ ПЕРВОЙ,
до создания QApplication и окна. Если прав нет — один раз вызывается
ShellExecuteW(..., "runas", ...) и процесс завершается.
"""
from __future__ import annotations

import ctypes
import datetime
import subprocess
import sys
import traceback

from PySide6.QtCore import Qt, QTranslator
from PySide6.QtWidgets import QApplication, QMessageBox

from cache import APP_NAME, APP_VERSION, app_data_dir
from ui.theme import apply_theme
from ui.main_window import MainWindow

ERROR_LOG = app_data_dir() / "winboost_errors.log"


def _write_error(text: str) -> None:
    try:
        with ERROR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n{text}\n")
    except Exception:
        pass


def global_excepthook(exc_type, exc_value, exc_tb) -> None:
    """Перехватывает необработанные исключения в основном потоке."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _write_error(text)
    try:
        app = QApplication.instance()
        if app and app.activeWindow():
            QMessageBox.critical(
                app.activeWindow(), APP_NAME,
                f"Ошибка, приложение продолжает работать.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\nПодробности: {ERROR_LOG}",
            )
    except Exception:
        pass


def main() -> int:
    sys.excepthook = global_excepthook

    # ------------------------------------------------------------------
    # ПРОВЕРКА ПРАВ ДО СОЗДАНИЯ ОКНА.
    # Если процесс запущен не от имени администратора, bcdedit и HKLM
    # вернут «Access is denied». Перезапускаем себя один раз через UAC.
    # ------------------------------------------------------------------
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            params = " ".join(
                subprocess.list2cmdline(arg) for arg in sys.argv[1:]
            ) if len(sys.argv) > 1 else ""
            ctypes.windll.shell32.ShellExecuteW(
                None,            # NULL
                "runas",         # запрос UAC
                sys.executable,  # этот же exe / python.exe
                params,
                None,
                1,               # SW_SHOWNORMAL
            )
            return 0
    except Exception as exc:
        _write_error(f"Ошибка повышения прав: {exc}")

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} Pro")
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)  # остаёмся в трее

    # QTranslator: если скомпилированный .qm есть — подключаем.
    try:
        translations = app_data_dir() / "translations"
        qm = translations / "ru_RU.qm"
        if qm.exists():
            translator = QTranslator(app)
            if translator.load(str(qm)):
                app.installTranslator(translator)
    except Exception:
        pass

    try:
        apply_theme(app, "dark")
    except Exception:
        pass

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
