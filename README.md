# WinBoost Pro

Современный системный оптимизатор для **Windows 10/11** на **PySide6 (Qt)**.
Интерфейс выполнен в стиле тёмной темы BoosterX: сине-фиолетовые градиенты,
анимированные кнопки, боковая навигация и карточки.

> ⚠️ **Дисклеймер.** Инструмент меняет системные настройки (службы, реестр,
> загрузку Windows). Используйте на свой страх и риск. Перед применением
> продвинутых твиков создавайте резервную копию или точку восстановления Windows.

---

## Возможности

| Вкладка | Что делает |
|---|---|
| **Главная** | Анализ системы, метрики CPU/RAM/GPU, круглая кнопка быстрой очистки, экспертный выбор целей |
| **Очистка** | Кэш Chrome, Яндекс Браузера, системный Temp и эскизы; сканирование перед удалением, проверка занятых процессов и размера после удаления |
| **Службы** | Список всех служб, профили «Безопасный / Баланс / Максимальная производительность», проверка зависимостей и критических служб, резервная копия |
| **Программы** | Установленные программы из реестра, живой поиск, деинсталлятор, очистка «хвостов» |
| **Автозагрузка** | WMI + реестр + `shell:startup` + Планировщик; аргументы, источник, статус, кликабельный путь, битые ссылки |
| **Твики** | 10 команд `bcdedit` / `powercfg` / `winreg` / DNS / Temp; пакетный выбор и кнопка «Начать», автоматический бекап, предупреждение о BSOD и перезагрузке |
| **Настройки** | Список резервных копий, восстановление служб и автозагрузки из JSON |

---

## Требования

- Windows 10 / 11
- Python 3.10+ (тестировалось на 3.15)
- Права администратора — **обязательны**. При запуске без прав приложение один раз запрашивает UAC через `ShellExecuteW(..., "runas", ...)`.

---

## Установка и запуск

```powershell
git clone https://github.com/<ваш-логин>/WinBoost-Pro.git
cd WinBoost-Pro

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
python main.py
```

Если политика выполнения PowerShell запрещает активацию venv:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

---

## Сборка в один `.exe`

```powershell
python -m pip install pyinstaller

python -m PyInstaller --noconfirm --onefile --windowed --clean --name "WinBoost" --icon "winboost.ico" --hidden-import PySide6.QtCore --hidden-import PySide6.QtGui --hidden-import PySide6.QtWidgets --hidden-import psutil --hidden-import qtawesome --hidden-import pyqtgraph --hidden-import wmi --hidden-import win32api --hidden-import win32service --hidden-import win32com.client main.py
```

Результат: `dist\WinBoost.exe`. Готовый бинарник лучше выкладывать в
**GitHub Releases**, а не в репозиторий — папки `dist/`, `build/` и `*.spec`
уже исключены через `.gitignore`.

---

## Структура проекта

```
WinBoost/
├── main.py                 # точка входа, проверка прав и UAC
├── cache.py                # логика очистки кэша
├── services.py             # управление службами, профили, зависимости
├── uninstaller.py          # реестр Uninstall и деинсталляция
├── startup.py              # WMI/реестр/Планировщик — автозагрузка
├── backup.py               # JSON-бекапы служб и автозагрузки
├── ui/
│   ├── main_window.py      # каркас, сайдбар, координация потоков
│   ├── theme.py            # палитра, QSS, тени, шрифты
│   ├── widgets.py          # AnimatedButton, ServiceCard и др.
│   ├── dashboard.py
│   ├── clean_screen.py
│   ├── services_screen.py
│   ├── programs_screen.py
│   ├── autostart_screen.py
│   ├── tweaks_tab.py       # продвинутые твики
│   ├── settings_screen.py
│   ├── strings.py          # все русские строки интерфейса
│   └── system_info.py
├── translations/ru_RU.ts   # источник переводов для QTranslator
├── requirements.txt
├── LICENSE
└── .gitignore
```

---

## Безопасность

- Все операции с реестром, `bcdedit` и службами требуют прав администратора.
- Перед применением профиля служб и пакета твиков создаётся JSON-бекап.
- Проверка зависимостей не даёт отключить критические службы.
- Команды твиков выполняются скрыто (`CREATE_NO_WINDOW`) и только после
  модального предупреждения о возможном BSOD.
- На ноутбуке дополнительно предупреждается о риске сбоев звука и микрофона.
- Чекбокс **«Показать вывод команд (DEBUG)»** показывает `stdout`/`stderr`
  для диагностики `Access is denied` и ошибок BCD.

Резервные копии и логи сохраняются в `%LOCALAPPDATA%\WinBoost\`, бекапы твиков —
в папке `backups\` рядом с приложением (исключена из Git).

---

## Лицензия

[MIT](LICENSE). Вы можете изменить год/автора в `LICENSE` перед публикацией.
