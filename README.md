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
git clone https://github.com/Terir66/WinBoost-Pro.git
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

Результат: `dist\WinBoost.exe`. Готовый бинарник выложен в
[GitHub Releases](https://github.com/Terir66/WinBoost-Pro/releases/latest):

```
https://github.com/Terir66/WinBoost-Pro/releases/download/v1.0.0/WinBoost.exe
```

Папки `dist/`, `build/` и `*.spec` исключены через `.gitignore` — в репозитории
хранятся только исходники. Хэш актуального exe публикуется на странице релиза
(кнопка `Copy to clipboard digest`).

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

## Windows SmartScreen

exe пока **не подписан кодом**, поэтому Windows может показать
«Windows защитил ваш компьютер». Это репутация файла, а не вирус: приложение
открытый исходник. Ни в коем случае не отключайте SmartScreen и Defender.

Что можно сделать:

1. **После скачивания снять маркер «скачано из интернета»:**
   ```powershell
   Unblock-File -Path .\WinBoost.exe
   ```
   или запустите готовый скрипт:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\tools\unblock.ps1
   ```
2. В окне SmartScreen нажать **«Дополнительные сведения» → «Выполнить всё равно»**.
   После нескольких запусков репутация файла повышается.
3. Отправить файл на анализ в Microsoft:
   https://www.microsoft.com/en-us/wdsi/filesubmission
4. **Гарантированный способ** — подписать exe сертификатом подписи кода
   (лучше EV). Это убирает предупреждение сразу:
   ```powershell
   signtool sign /f cert.pfx /p PASSWORD /tr http://timestamp.digicert.com /td sha256 /fd sha256 WinBoost.exe
   ```

Мы намеренно не меняем системные настройки безопасности: обойти SmartScreen
программно — значит сделать приложение похожим на вредоносное.

## Лицензия

[MIT](LICENSE). Вы можете изменить год/автора в `LICENSE` перед публикацией.
