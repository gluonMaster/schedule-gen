#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Основной модуль программы генератора расписания.
Запускает графический интерфейс и координирует работу всех компонентов.
"""

import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import threading
import webbrowser

# Импортируем новый сервис пайплайна
from services.schedule_pipeline import SchedulePipeline, SchedulePipelineError
from utils import create_output_directories
from integration import load_spiski_data, reset_web_editor_state

# Глобальная переменная для выбранного файла
selected_file = None

# Константы конфигурации (вынесены в начало для лучшей видимости)
TIME_INTERVAL = 5  # Интервал времени в минутах
BORDER_WIDTH = 0.5   # Толщина границы ячейки в пикселях
SERVER_PORT = 5000   # Порт для Flask-сервера


def choose_file():
    """Открывает диалог выбора файла и сохраняет путь к выбранному файлу."""
    global selected_file
    selected_file = filedialog.askopenfilename(
        title="Выберите файл с расписанием",
        filetypes=[("Excel файлы", "*.xlsx"), ("Все файлы", "*.*")]
    )
    if selected_file:
        file_button.config(text=f"Выбран: {os.path.basename(selected_file)}")
    else:
        file_button.config(text="Выберите Excel-файл с расписанием")


def run_script():
    """
    Запускает обработку выбранного файла и генерацию расписаний.
    Использует SchedulePipeline для инкапсуляции основной логики.
    """
    global selected_file
    
    # Проверяем что файл выбран
    if not selected_file:
        messagebox.showerror("Ошибка", "Пожалуйста, сначала выберите Excel файл!")
        return
    
    # Создаем директории для выходных файлов
    output_dirs = create_output_directories()
    
    # Создаем экземпляр пайплайна с настройками
    pipeline = SchedulePipeline(
        time_interval=TIME_INTERVAL, 
        border_width=BORDER_WIDTH
    )
    
    try:
        # Выполняем основную обработку через пайплайн
        spiski_data = load_spiski_data()
        result = pipeline.process_excel_to_outputs(selected_file, output_dirs, spiski_data=spiski_data)
        reset_web_editor_state(result.get("individual_blocks"))
        print(f"Обработка завершена:")
        print(f"  - Занятий обработано: {result['activities_count']}")
        print(f"  - Зданий создано: {result['buildings_count']}")
        print(f"  - HTML файл: {result['html_file']}")
        
        # Создаем директорию для экспорта Excel-файлов, если её нет
        excel_export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "excel_exports")
        if not os.path.exists(excel_export_dir):
            os.makedirs(excel_export_dir)
        
        if os.name != "nt":
            # Legacy non-Windows path keeps the direct helper for local debugging.
            threading.Thread(target=start_flask_server, daemon=True).start()
        
        # Автоматически открываем веб-браузер с HTML-расписанием
        # webbrowser.open(f'file://{os.path.abspath(result["html_file"])}')
          # Показываем сообщение об успешном завершении
        messagebox.showinfo(
            "Готово!", 
            f"Веб-версия успешно создана.\n\n"
            f"Обработано занятий: {result['activities_count']}\n"
            f"Создано зданий: {result['buildings_count']}\n"
            f"HTML: {os.path.abspath(os.path.dirname(result['html_file']))}\n\n"
            f"Расписание готово к использованию.\n"
            f"Для экспорта в Excel используйте кнопку 'Экспорт в Excel' в веб-интерфейсе."
        )
        
    except SchedulePipelineError as e:
        # Обрабатываем ошибки пайплайна
        messagebox.showerror("Ошибка обработки", str(e))
        print(f"Ошибка пайплайна: {e}")
        
    except Exception as e:
        # Обрабатываем неожиданные ошибки
        messagebox.showerror("Неожиданная ошибка", f"Произошла неожиданная ошибка: {e}")
        print(f"Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()


def start_flask_server():
    """Запускает Flask-сервер в отдельном потоке."""
    if os.name == "nt":
        print("Windows v1: gear_xls/main.py больше не управляет жизненным циклом Flask-сервера.")
        print("Используйте tray launcher или GUI-кнопки 3.1 / 3.2.")
        return
    try:
        import subprocess
        import os
        import sys
        
        # Путь к скрипту server_routes.py
        server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_routes.py")
        
        # Проверяем существование файла
        if not os.path.exists(server_script):
            print(f"Ошибка: файл {server_script} не найден")
            return
        
        # Запускаем сервер в отдельном процессе
        print(f"Запуск Flask-сервера: {server_script}")
        
        # Используем текущий интерпретатор Python
        python_exec = sys.executable
        
        subprocess.Popen(
            [python_exec, server_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        print("Flask-сервер запущен в отдельном процессе")
        print("Функция экспорта будет работать до тех пор пока запущен процесс Flask-сервера")
        
    except Exception as e:
        print(f"Ошибка при запуске Flask-сервера: {e}")
        import traceback
        traceback.print_exc()


def validate_selected_file():
    """
    Проверяет валидность выбранного файла без полной обработки.
    Обновляет интерфейс в зависимости от результата.
    """
    global selected_file
    
    if not selected_file:
        return
    
    # Создаем временный экземпляр пайплайна для валидации
    pipeline = SchedulePipeline()
    
    if pipeline.validate_excel_file(selected_file):
        file_button.config(bg="#d4edda")  # Зеленоватый фон для валидного файла
        run_button.config(state=tk.NORMAL)
    else:
        file_button.config(bg="#f8d7da")  # Красноватый фон для невалидного файла  
        run_button.config(state=tk.DISABLED)
        messagebox.showwarning(
            "Предупреждение", 
            f"Выбранный файл может содержать ошибки или не соответствует ожидаемому формату.\n\n"
            f"Убедитесь что:\n"
            f"- Файл содержит лист 'Schedule'\n"
            f"- Первая строка содержит заголовки\n"
            f"- Есть данные о занятиях"
        )


def main():
    """Основная функция, создающая и запускающая GUI приложение."""
    global file_button, run_button
    
    # Создаем главное окно
    root = tk.Tk()
    root.title("Генератор расписания из Excel")

    # Параметры окна
    root.geometry("600x280")
    root.resizable(False, False)

    # Создаем фрейм для размещения кнопок с отступами
    frame = tk.Frame(root, padx=20, pady=20)
    frame.pack(expand=True, fill='both')

    # Добавляем заголовок
    title_label = tk.Label(
        frame, 
        text="Генератор расписания из Excel-файла", 
        font=("Arial", 14, "bold")
    )
    title_label.pack(pady=(0, 15))

    # Кнопка для выбора Excel файла
    file_button = tk.Button(
        frame, 
        text="Выберите Excel-файл с расписанием", 
        command=lambda: [choose_file(), validate_selected_file()],  # Валидация после выбора
        width=50,
        height=2
    )
    file_button.pack(pady=10)

    # Кнопка для запуска обработки (изначально неактивна)
    run_button = tk.Button(
        frame, 
        text="Создать веб-приложение для редактирования расписания", 
        command=run_script, 
        width=50,
        height=2,
        bg="#90ee90",  # Нежно-зеленый фон для кнопки запуска
        state=tk.DISABLED  # Изначально неактивна
    )
    run_button.pack(pady=10)
    
    # Информационная метка о функции экспорта
    info_label = tk.Label(
        frame,
        text="Примечание: В веб-версии расписания будет доступна кнопка\n"
             "'Экспорт в Excel' для обратного преобразования",
        font=("Arial", 9),
        fg="#555555"
    )
    info_label.pack(pady=5)
    
    # Метка с информацией о версии и настройках
    pipeline_info = SchedulePipeline().get_pipeline_info()
    version_label = tk.Label(
        frame,
        text=f"Настройки: интервал {pipeline_info['time_interval']}мин, "
             f"границы {pipeline_info['border_width']}px | v{pipeline_info['version']}",
        font=("Arial", 8),
        fg="#888888"
    )
    version_label.pack(pady=(10, 0))

    # Запуск главного цикла обработки событий
    root.mainloop()


if __name__ == "__main__":
    main()
    
