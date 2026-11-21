"""
ui/strings.py — все пользовательские строки интерфейса.

Вынесены из Python-кода в один модуль с UTF-8, чтобы исключить проблемы
с кодировкой ANSI и упростить будущий перевод через QTranslator.
"""
from __future__ import annotations

# --- бренд и общее ---
APP_BRAND = "WinBoost Pro"
APP_DESCRIPTION = "системный оптимизатор"
READY = "Готово"
YES = "Да"
NO = "Нет"
OK = "OK"
CANCEL = "Отмена"
ADMIN_REQUIRED = "Нужны права администратора."
ERROR = "Ошибка"
WARNING = "Внимание"
FREE_RAM_PREFIX = "Свободно RAM: "
DONE_LABEL = "ГОТОВО"

# --- меню и трей ---
MENU_FILE = "Файл"
MENU_HELP = "Справка"
MENU_TOGGLE_THEME = "Переключить тему"
MENU_EXIT = "Выход"
MENU_ABOUT = "О программе"
TRAY_SHOW = "Показать окно"
ABOUT_TITLE = "О программе"
ABOUT_TEXT = (
    "<b>WinBoost Pro</b> — системный оптимизатор<br>Версия {version}<br><br>"
    "Очистка кэша, управление службами, деинсталлятор и мониторинг "
    "автозагрузки.<br>Построено на PySide6 (Qt)."
)

# --- навигация ---
NAV_HOME = "Главная"
NAV_CLEAN = "Очистка"
NAV_SERVICES = "Службы"
NAV_PROGRAMS = "Программы"
NAV_STARTUP = "Автозагрузка"
NAV_SETTINGS = "Настройки"

# --- главная ---
DASHBOARD_TITLE = "Оптимизация Windows"
DASHBOARD_EYEBROW = "WINBOOST · АНАЛИЗ СИСТЕМЫ"
DASHBOARD_DESC = (
    "Сначала анализируем конфигурацию, затем вы выбираете изменения\n"
    "и проверяете их последствия перед применением."
)
DASHBOARD_HINT = "Анализ не изменяет настройки и не удаляет файлы"
BTN_START_OPTIMIZATION = "Начать оптимизацию"
METRIC_CPU = "ЗАГРУЗКА CPU"
METRIC_GPU = "ЗАГРУЗКА GPU"
METRIC_RAM = "ЗАНЯТО RAM"
METRIC_SCORE = "УРОВЕНЬ ОПТИМИЗАЦИИ"
SYSTEM_STATE = "СОСТОЯНИЕ СИСТЕМЫ"
EXPERT_MENU = "ЭКСПЕРТНОЕ МЕНЮ · ЧТО ОЧИЩАТЬ"
QUICK_CLEAN = "Быстрая очистка"
QUICK_CLEAN_BTN = "БЫСТРАЯ\nОЧИСТКА"
ESTIMATE_HINT = "Выполните анализ, чтобы увидеть потенциальный объём очистки"
ESTIMATE_RESULT = "Доступно к очистке: {size}"
LOG_PLACEHOLDER = "Здесь появляется детальный лог очистки…"
NOT_AVAILABLE = "н/д"
PERCENT = "{value}%"

# --- очистка ---
CLEAN_TITLE = "Очистка"
CLEAN_SUBTITLE = "Кэш браузеров, временные файлы и эскизы"
BTN_SCAN = "Просканировать"
BTN_CLEAN = "Очистка"
BTN_CLEAN_START = "Очистить"
SCAN_TITLE = "--- Сканирование ---"
CLEAN_CHECK_TITLE = "--- Проверка запущенных процессов ---"
CLEAN_PROGRESS_TITLE = "--- Очистка ---"
SELECT_TARGET = "Выберите хотя бы одну цель."
CONFIRM_CLEAN_TITLE = "Подтверждение"
CONFIRM_CLEAN_TEXT = "Начать удаление выбранных данных?"
BROWSER_RUNNING_TITLE = "Браузер запущен"
BROWSER_RUNNING_TEXT = "Закройте процессы:\n\n{lines}\n\nПосле закрытия нажмите «Повторить»."
CLOSE_BROWSERS_TITLE = "Закройте браузеры"
CLOSE_BROWSERS_TEXT = "Процессы мешают очистке:\n\n{lines}\n\nЗакройте их и повторите."
CLEAN_CANCELLED = "Очистка отменена."
CLEAN_DONE = "Удалено папок: {dirs}, файлов: {files}. Освобождено: {size}"
CLEAN_NOTIFY = "Очистка завершена: {size}"

# --- службы ---
SERVICES_TITLE = "Службы"
SERVICES_SUBTITLE = "Управление службами и профили оптимизации"
PROFILE_LABEL = "Профиль:"
PROFILE_PLACEHOLDER = "— выберите профиль —"
BTN_APPLY_PROFILE = "Применить профиль"
BTN_RESTORE_COPY = "Восстановить из копии"
BTN_REFRESH = "Обновить"
BTN_STOP_SERVICE = "Остановить"
BTN_START_SERVICE = "Запустить"
BTN_CHANGE_TYPE = "Тип запуска"
PROFILE_CONFIRM_TITLE = "Подтверждение профиля"
PROFILE_CONFIRM_TEXT = "Исходные настройки будут сохранены в резервную копию. Продолжить?"
PROFILE_PLAN_TEXT = "Будут изменены следующие службы:\n"
PROFILE_BLOCKED_NOTE = "Заблокированные службы не будут изменены."
PROFILE_MAX_WARNING = (
    "Профиль отключит обновления, печать и индексацию.\nПродолжить?"
)
PROFILE_APPLIED = "Применено: {ok} из {total}"
PROFILE_NOTIFY = "Профиль применён: {ok}/{total}"
SERVICE_CONTROL_DONE = "{status}: {msg}"
START_TYPE_TITLE = "Тип запуска"
START_TYPE_TEXT = "Служба: {name}\nСейчас: {current}"
RESTORE_TITLE = "Восстановление"
RESTORE_SERVICE_TEXT = "Восстановить исходные типы запуска?"

# --- программы ---
PROGRAMS_TITLE = "Программы"
PROGRAMS_SUBTITLE = "Установленные приложения и очистка остатков"
SEARCH_PLACEHOLDER = "Поиск программы…"
BTN_UNINSTALL = "Удалить"
BTN_CLEAN_LEFTOVERS = "Принудительно вычистить хвосты"
MENU_FIND_LEFTOVERS = "Найти остатки"
NO_LEFTOVERS = "Остатки не найдены."
LEFTOVERS_TITLE = "Найдены остатки"
LEFTOVERS_TEXT = "Будут удалены только перечисленные объекты:\n\n{lines}"
LEFTOVERS_INFO = "Реестр будет экспортирован в .reg. Продолжить?"
NO_UNINSTALLER_TITLE = "Нет деинсталлятора"
NO_UNINSTALLER_TEXT = (
    "У «{name}» нет команды удаления.\nУдалить запись реестра с резервной копией?"
)
CONFIRM_UNINSTALL_TEXT = "Запустить деинсталлятор «{name}»?"
SUGGEST_LEFTOVERS_TITLE = "Очистка остатков"
SUGGEST_LEFTOVERS_TEXT = "Просканировать остатки программы?"
LEFTOVERS_DONE = "Удалено остатков: {ok} из {total}"
LEFTOVERS_NOTIFY = "Очистка остатков: {ok}/{total}"

# --- автозагрузка ---
STARTUP_TITLE = "Автозагрузка"
STARTUP_SUBTITLE = (
    "Программы из реестра, папки автозагрузки и Планировщика заданий"
)
BTN_DISABLE = "Отключить"
BTN_ENABLE = "Включить"
BTN_DELETE = "Удалить запись"
BTN_DELETE_BROKEN = "Удалить битую ссылку"
BTN_OPEN_FOLDER = "Открыть папку"
BTN_RUN_TOOL = "Запустить"
TOOL_PUBLISHER = "Утилита"
COL_NAME = "Имя программы"
COL_PATH = "Путь к файлу"
COL_ARGS = "Аргументы"
COL_SOURCE = "Источник"
COL_STATUS = "Статус"
STATUS_ENABLED = "Включено"
STATUS_DISABLED = "Отключено"
BROKEN_MARK = " [битая ссылка]"
STARTUP_EMPTY = "Записи автозагрузки не найдены."
STARTUP_SELECT = "Выберите запись в списке."
STARTUP_CONFIRM_TITLE = "Подтверждение"
STARTUP_CONFIRM_DISABLE = "Отключить запись «{name}»?"
STARTUP_CONFIRM_ENABLE = "Включить запись «{name}»?"
STARTUP_CONFIRM_DELETE = "Удалить запись «{name}»?"
STARTUP_DONE = "{action}: {name} — {msg}"
STARTUP_SCAN_ERROR = "Ошибка чтения автозагрузки: {error}"
ACTION_DISABLED = "Отключение"
ACTION_ENABLED = "Включение"
ACTION_DELETED = "Удаление"
ACTION_BROKEN_DELETED = "Удаление битой ссылки"

# --- резервное копирование ---
BACKUP_TITLE = "Резервное копирование"
BACKUP_SUBTITLE = (
    "Копия сохраняет состояния служб и записи автозагрузки "
    "перед оптимизацией"
)
BACKUP_QUESTION = (
    "Создать точку восстановления? WinBoost сохранит текущее состояние "
    "служб и записей автозагрузки. Это позволит вернуть всё в исходное "
    "состояние в настройках."
)
BACKUP_RESTORE_BLOCK = "Восстановление"
BACKUP_LIST_HINT = "Доступные копии: дата, время, размер"
BTN_RESTORE = "Восстановить"
BTN_REFRESH_BACKUPS = "Обновить список"
NO_BACKUPS = "Резервных копий пока нет."
BACKUP_CONFIRM_RESTORE = "Восстановить состояние из копии {name}?"
BACKUP_RESTORED = "Восстановлено: {ok} из {total}"
BACKUP_CREATED = "Резервная копия создана: {name}"
BACKUP_FAILED = "Не удалось создать резервную копию: {error}"
SETTINGS_TITLE = "Настройки"
SETTINGS_SUBTITLE = "Резервные копии и восстановление системы"
THEME_SWITCH_TOOLTIP = "Сменить тему (Light / Dark)"

# --- продвинутые твики ---
NAV_TWEAKS = "Твики"
TWEAKS_TITLE = "Продвинутые твики"
TWEAKS_SUBTITLE = (
    "Команды bcdedit, powercfg и реестра. Применяются только после подтверждения"
)
BTN_CHECK_STATUS = "Проверить статус"
BTN_APPLY = "Применить"
REBOOT_NOTE = " (Требуется перезагрузка)"
TWEAK_BSOD_WARNING = (
    "Внимание: Продвинутая настройка. Изменение параметров загрузки или "
    "реестра может привести к нестабильной работе системы или синим экранам "
    "(BSOD). Рекомендуется создать точку восстановления системы. "
    "Вы уверены, что хотите применить: {name}?"
)
TWEAK_LAPTOP_WARNING = (
    "ВНИМАНИЕ: Вы используете ноутбук. Отключение HPET и Dynamic Tick может "
    "привести к сбоям синхронизации звука и микрофона."
)
TWEAK_TEMP_CONFIRM = (
    "Жёсткая очистка %temp% удалит файлы безвозвратно. Продолжить?"
)
TWEAK_NO_ADMIN = (
    "Для продвинутых твиков нужны права администратора. "
    "Перезапустить WinBoost Pro с запросом UAC?"
)
TWEAK_REBOOT_QUESTION = (
    "Изменения внесены. Чтобы они вступили в силу, требуется "
    "перезагрузка компьютера. Перезагрузить сейчас?"
)
BTN_REBOOT_NOW = "Перезагрузить"
BTN_LATER = "Позже"
DEBUG_CHECKBOX = "Показать вывод команд (DEBUG)"
BTN_SELECT_ALL = "Выбрать все"
BTN_CLEAR_SELECTION = "Снять выделение"
BTN_START_TWEAKS = "Начать"
TWEAK_AUTO_BACKUP_NOTE = "Резервная копия будет создана автоматически перед применением."
TWEAK_SELECTED_COUNT = "Выбрано твиков: {count}"
TWEAK_NOTHING_SELECTED = "Выберите хотя бы один твик."
TWEAK_BACKUP_DONE = "Бекап создан автоматически: {name}"
TWEAK_BATCH_DONE = "Применено твиков: {ok} из {total}"
TWEAK_STATUS_TITLE = "Статус команды"
TWEAK_DONE = "{name}: команда выполнена"
TWEAK_FAILED = "{name}: ошибка — {error}"
TWEAK_REBOOT_REQUIRED = "{name}: применено, требуется перезагрузка"

COL_DATE = "Дата"
COL_TIME = "Время"
COL_SIZE = "Размер"
