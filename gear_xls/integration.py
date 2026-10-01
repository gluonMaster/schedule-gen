#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Интеграционный модуль для объединения функциональности генерации расписания 
и экспорта обратно в Excel.
"""

import os
import shutil
import logging
import subprocess
import time
import webbrowser
import re
import json
import tempfile
import sys
import openpyxl
from pathlib import Path

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    # The pipeline imports gear_xls.* exchange modules; local gear_xls modules stay first.
    sys.path.append(PROJECT_ROOT)

# Импортируем новый сервис пайплайна
try:
    from .services.schedule_pipeline import SchedulePipeline, SchedulePipelineError
    from .utils import create_output_directories
except ImportError:
    from services.schedule_pipeline import SchedulePipeline, SchedulePipelineError
    from utils import create_output_directories

from gear_xls.runtime_paths import (
    get_excel_exports_dir,
    get_html_output_dir,
    get_js_modules_dir,
    get_schedule_html_path,
    get_schedule_state_dir,
    get_spiski_dir,
)
from gear_xls.schedule_exchange import ScheduleExchangeError, read_sync_metadata
from gear_xls.snapshot_guard import SnapshotConflictError, apply_generated_state, check_snapshot_current

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('integration')

# Константы конфигурации
DEFAULT_TIME_INTERVAL = 5
DEFAULT_BORDER_WIDTH = 0.5


def _spiski_sort_key(value: str):
    """Case-insensitive natural sort key (e.g. '2' < '10')."""
    parts = re.findall(r'\d+|\D+', (value or '').strip())
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.casefold()))
    return tuple(key)


def load_spiski_data() -> dict:
    """
    Loads the five spiski/*.txt files and returns a dictionary with suggestion lists.

    Returns:
        dict with keys:
            "subjects"      — list of strings from disciplins.txt
            "groups"        — list of strings from groups.txt
            "teachers"      — list of strings from teachers.txt
            "rooms_Villa"   — list of strings from kabinets_Villa.txt
            "rooms_Kolibri" — list of strings from kabinets_Kolibri.txt

        Missing or empty files produce an empty list for that key; no exception is raised.
    """
    spiski_dir = get_spiski_dir()

    file_map = {
        'subjects': 'disciplins.txt',
        'groups': 'groups.txt',
        'teachers': 'teachers.txt',
        'rooms_Villa': 'kabinets_Villa.txt',
        'rooms_Kolibri': 'kabinets_Kolibri.txt',
    }

    result = {}
    for key, filename in file_map.items():
        path = os.path.join(spiski_dir, filename)
        entries = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        entries.append(stripped)
            logger.info(f"Loaded spiski file: {filename} ({len(entries)} entries)")
        except FileNotFoundError:
            logger.warning(f"Spiski file not found (using empty list): {path}")
        except Exception as e:
            logger.warning(f"Error reading spiski file {path}: {e}")
        result[key] = sorted(entries, key=_spiski_sort_key)

    return result


def check_generation_origin(sync_metadata):
    """Early provenance check; apply_generated_state repeats it under the state locks."""
    try:
        check_snapshot_current(sync_metadata, get_schedule_state_dir())
    except (SnapshotConflictError, ScheduleExchangeError) as exc:
        raise SchedulePipelineError(str(exc)) from exc


def check_excel_generation_origin(excel_path):
    workbook = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    try:
        metadata = read_sync_metadata(workbook)
    except ScheduleExchangeError as exc:
        raise SchedulePipelineError(str(exc)) from exc
    finally:
        workbook.close()
    check_generation_origin(metadata)


def reset_web_editor_state(individual_blocks: list[dict] | None = None, sync_metadata=None,
                           html_source: str | None = None) -> None:
    """
    Apply a generated editor (managed JSON and, if given, prepared HTML) to the
    runtime state. Refuses stale/legacy snapshots for live data, restores the
    previous files on a failed write and leaves the edit lock untouched.
    """
    try:
        apply_generated_state(
            individual_blocks, sync_metadata, get_schedule_state_dir(),
            html_source=html_source,
            html_target=get_schedule_html_path() if html_source else None,
        )
    except (SnapshotConflictError, ScheduleExchangeError) as exc:
        raise SchedulePipelineError(str(exc)) from exc
    logger.info("Web editor runtime state applied in %s", get_schedule_state_dir())


def generate_editor_from_excel(excel_file_path: str, pipeline, spiski_data=None) -> dict:
    """Build the editor outside working outputs, then apply HTML/JSON under the state locks."""
    check_excel_generation_origin(excel_file_path)
    with tempfile.TemporaryDirectory(prefix="schedgen_editor_") as prepared_dir:
        result = pipeline.process_excel_to_outputs(
            excel_file_path, {"html": prepared_dir}, spiski_data=spiski_data
        )
        reset_web_editor_state(
            result.get("individual_blocks"),
            sync_metadata=result.get("sync_metadata"),
            html_source=result["html_file"],
        )
    result["html_file"] = get_schedule_html_path()
    return result


def setup_environment():
    """
    Подготавливает окружение для работы приложения:
    - Создает необходимые директории
    - Копирует JavaScript модуль export_to_excel.js в директорию с JS-модулями
    
    Returns:
        bool: True если подготовка успешна, False в случае ошибки
    """
    try:
        # Определяем текущую директорию
        output_dirs = [
            get_html_output_dir(),
            get_excel_exports_dir(),
            get_js_modules_dir(),
        ]
        
        for directory in output_dirs:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Директория {directory} создана или уже существует")
        
        # Копируем модуль export_to_excel.js в директорию с JS-модулями
        export_js_src = os.path.join(THIS_DIR, "export_to_excel.js")
        export_js_dst = os.path.join(get_js_modules_dir(), "export_to_excel.js")
        
        if os.path.exists(export_js_src):
            shutil.copy2(export_js_src, export_js_dst)
            logger.info(f"Модуль export_to_excel.js скопирован в {export_js_dst}")
        else:
            logger.warning(f"Модуль export_to_excel.js не найден в {export_js_src}")
        
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при подготовке окружения: {e}")
        import traceback
        traceback.print_exc()
        return False


def start_flask_server_subprocess():
    """
    Запускает Flask-сервер в отдельном процессе для обработки запросов экспорта.
    
    Returns:
        subprocess.Popen: Процесс Flask-сервера или None в случае ошибки
    """
    if os.name == "nt":
        logger.info(
            "Windows v1: direct Flask subprocess launch from integration.py is disabled; "
            "use the tray launcher or GUI control-plane instead."
        )
        return None
    try:
        import sys
        
        # Запускаем server_routes.py как отдельный процесс
        server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_routes.py")
        
        # Проверяем, что файл существует
        if not os.path.exists(server_script):
            logger.error(f"Скрипт сервера не найден: {server_script}")
            return None
        
        # Запускаем процесс
        process = subprocess.Popen(
            [sys.executable, server_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        logger.info(f"Flask-сервер запущен с PID {process.pid}")
        
        # Небольшая пауза, чтобы сервер успел запуститься
        time.sleep(1)
        
        return process
    
    except Exception as e:
        logger.error(f"Ошибка при запуске Flask-сервера: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_full_pipeline(excel_file_path: str,                     time_interval: int = DEFAULT_TIME_INTERVAL,
                     border_width: float = DEFAULT_BORDER_WIDTH,
                     open_browser: bool = True,
                     start_server: bool = True) -> bool:
    """
    Запускает полный процесс обработки Excel-файла:
    1. Парсинг Excel и генерация HTML
    2. Запуск Flask-сервера для обработки запросов экспорта (опционально)
    3. Открытие HTML-версии в браузере (опционально)
    
    Args:
        excel_file_path (str): Путь к исходному Excel-файлу
        time_interval (int): Интервал времени в минутах для сетки расписания
        border_width (float): Толщина границ ячеек в пикселях  
        open_browser (bool): Открывать ли браузер автоматически
        start_server (bool): Запускать ли Flask-сервер
        
    Returns:
        bool: True если процесс успешно запущен, False в случае ошибки
    """
    logger.info(f"Запуск полного пайплайна для файла: {excel_file_path}")
    logger.info(f"Параметры: interval={time_interval}, border={border_width}, "
               f"browser={open_browser}, server={start_server}")
    
    try:
        # Проверяем наличие файла
        if not os.path.exists(excel_file_path):
            logger.error(f"Excel-файл не найден: {excel_file_path}")
            return False
        
        # Настраиваем окружение
        if not setup_environment():
            logger.error("Не удалось подготовить окружение")
            return False
        
        # Создаем директории для выходных файлов
        create_output_directories()
        
        # Создаем экземпляр пайплайна с указанными настройками
        pipeline = SchedulePipeline(
            time_interval=time_interval,
            border_width=border_width
        )

        # Load suggestion lists from spiski/ files.
        spiski_data = load_spiski_data()
        
        # Выполняем основную обработку
        logger.info("Запуск обработки через SchedulePipeline...")
        result = generate_editor_from_excel(excel_file_path, pipeline, spiski_data=spiski_data)
        logger.info("Обработка завершена успешно:")
        logger.info(f"  - Входной файл: {excel_file_path}")
        logger.info(f"  - Занятий обработано: {result['activities_count']}")
        logger.info(f"  - Зданий создано: {result['buildings_count']}")
        logger.info(f"  - HTML файл: {result['html_file']}")
        
        # Запускаем Flask-сервер для обработки запросов экспорта (если требуется)
        server_process = None
        if start_server and os.name != "nt":
            logger.info("Запуск Flask-сервера...")
            server_process = start_flask_server_subprocess()
            if server_process:
                logger.info("Flask-сервер успешно запущен")
            else:
                logger.warning("Не удалось запустить Flask-сервер, экспорт в Excel будет недоступен")
        elif start_server:
            logger.info(
                "Windows v1: lifecycle Flask-сервера остаётся ответственностью tray launcher; "
                "direct subprocess launch skipped."
            )
        
        # Открываем HTML-файл в браузере (если требуется)
        if open_browser and os.path.exists(result['html_file']):
            logger.info("Открытие HTML-расписания в браузере...")
            webbrowser.open(f'file://{os.path.abspath(result["html_file"])}')
            logger.info(f"HTML-расписание открыто в браузере: {result['html_file']}")
        
        logger.info("Полный процесс обработки завершен успешно")
        return True
        
    except SchedulePipelineError as e:
        logger.error(f"Ошибка пайплайна при обработке: {e}")
        return False
        
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запуске полного процесса: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_and_run_pipeline(excel_file_path: str, **kwargs) -> bool:
    """
    Проверяет файл и запускает пайплайн только если файл валиден.
    
    Args:
        excel_file_path (str): Путь к Excel файлу
        **kwargs: Дополнительные параметры для run_full_pipeline
        
    Returns:
        bool: True если валидация прошла и пайплайн запущен успешно
    """
    logger.info(f"Валидация файла: {excel_file_path}")
    
    # Быстрая проверка валидности
    pipeline = SchedulePipeline()
    if not pipeline.validate_excel_file(excel_file_path):
        logger.error(f"Файл не прошел валидацию: {excel_file_path}")
        return False
    
    logger.info("Файл прошел валидацию, запуск полного пайплайна...")
    return run_full_pipeline(excel_file_path, **kwargs)


def get_pipeline_status() -> dict:
    """
    Возвращает информацию о состоянии пайплайна и доступных возможностях.
    
    Returns:
        dict: Словарь со статусом компонентов системы
    """
    status = {
        'pipeline_available': True,
        'environment_ready': False,
        'server_script_exists': False,
        'output_dirs_exist': False
    }
    
    try:
        # Проверяем готовность окружения
        status['environment_ready'] = setup_environment()
        
        # Проверяем наличие скрипта сервера
        server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_routes.py")
        status['server_script_exists'] = os.path.exists(server_script)
        
        # Проверяем наличие выходных директорий
        output_dirs = create_output_directories()
        status['output_dirs_exist'] = all(os.path.exists(d) for d in output_dirs.values())
        
        # Получаем информацию о версии пайплайна
        pipeline = SchedulePipeline()
        status['pipeline_info'] = pipeline.get_pipeline_info()
        
    except Exception as e:
        logger.error(f"Ошибка при получении статуса: {e}")
        status['error'] = str(e)
    
    return status


if __name__ == "__main__":
    import sys
    
    # Если передан аргумент - используем его как путь к файлу
    if len(sys.argv) > 1:
        excel_file = sys.argv[1]
        
        # Дополнительные параметры из командной строки
        time_interval = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TIME_INTERVAL
        border_width = float(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_BORDER_WIDTH
        
        success = run_full_pipeline(
            excel_file,
            time_interval=time_interval,
            border_width=border_width
        )
        
        sys.exit(0 if success else 1)
    else:
        print("Использование: python integration.py путь_к_excel_файлу.xlsx [интервал_времени] [толщина_границ]")
        print(f"По умолчанию: интервал={DEFAULT_TIME_INTERVAL}, границы={DEFAULT_BORDER_WIDTH}")
        
        # Показываем статус системы
        status = get_pipeline_status()
        print(f"\nСтатус системы:")
        for key, value in status.items():
            print(f"  {key}: {value}")
            
