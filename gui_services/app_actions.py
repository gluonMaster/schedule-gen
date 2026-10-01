import os
import sys
import glob
import threading
import time
import json
import shutil
import tkinter as tk
from tkinter import messagebox
from .file_manager import FileManager
from .process_manager import ProcessManager
from gear_xls.runtime_paths import get_schedule_url, resolve_project_root, validate_project_layout


class AppActions:
    """Действия приложения"""

    DEFAULT_CONFIG = {
        "copy_destination_path": "",
        "auto_copy_enabled": False,
        "academic_year": {
            "period": "2025-2026",
            "color": "#2E7D32",
        },
    }
    
    def __init__(self, process_manager: ProcessManager, log_callback=None):
        self.process_manager = process_manager
        self.log_action = log_callback if log_callback else self._dummy_log
        self.program_directory = self._auto_detect_root_directory()
        self.selected_xlsx_file = None
        self.lesson_type_filter = 'all'
    
    def _dummy_log(self, message):
        """Временная функция логирования для случаев, когда logger еще не инициализирован"""
        print(f"[LOG] {message}")
    
    def set_log_callback(self, log_callback):
        """Устанавливает функцию логирования после инициализации UI"""
        self.log_action = log_callback

    def _show_error(self, title: str, message: str):
        """Показывает ошибку из любого потока через основной Tk-root."""
        root = getattr(tk, "_default_root", None)
        if root is not None and threading.current_thread() is not threading.main_thread():
            try:
                root.after(0, lambda: messagebox.showerror(title, message))
                return
            except RuntimeError:
                pass
        messagebox.showerror(title, message)

    def _import_excel_automation(self):
        """Ленивая загрузка pywin32, чтобы GUI мог стартовать без Excel-COM зависимостей."""
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            self.log_action(f"Excel automation prerequisites missing: {exc}")
            self._show_error(
                "Ошибка Excel automation",
                "Для операций с Excel/VBA нужен pywin32 в текущем Python-окружении "
                "(модули pythoncom и win32com.client).",
            )
            return None, None
        return pythoncom, win32com.client

    def set_lesson_type_filter(self, value: str):
        """Sets the lesson type filter forwarded to the visualiser command."""
        self.lesson_type_filter = value
    
    def _auto_detect_root_directory(self):
        """Автоматическое определение корневого каталога программы"""
        try:
            current_dir = resolve_project_root()
            layout_errors = validate_project_layout(current_dir)
            if layout_errors:
                self.log_action("Предупреждение: структура проекта неполная:")
                for error in layout_errors:
                    self.log_action(f"  - {error}")
            else:
                self.log_action(f"Рабочий каталог определен: {current_dir}")
            return current_dir
        except Exception as e:
            self.log_action(f"Ошибка при автоматическом определении каталога: {e}")
            # В случае ошибки возвращаем каталог исполняемого файла
            try:
                if getattr(sys, 'frozen', False):
                    fallback_dir = os.path.dirname(sys.executable)
                else:
                    fallback_dir = os.getcwd()
                self.log_action(f"Использую резервный каталог: {fallback_dir}")
                return fallback_dir
            except:
                return None
    
    def _find_latest_xlsx_file(self):
        """Находит самый новый .xlsx файл в каталоге gear_xls/excel_exports/"""
        if not self.program_directory:
            return None
        
        exports_dir = FileManager.get_file_path(self.program_directory, "gear_xls", "excel_exports")
        if not os.path.exists(exports_dir):
            self.log_action(f"Каталог excel_exports не найден: {exports_dir}")
            return None
        
        # Ищем все .xlsx файлы в каталоге
        xlsx_pattern = os.path.join(exports_dir, "*.xlsx")
        xlsx_files = glob.glob(xlsx_pattern)
        
        if not xlsx_files:
            self.log_action("В каталоге excel_exports не найдено .xlsx файлов")
            return None
        
        # Находим самый новый файл по времени модификации
        latest_file = max(xlsx_files, key=os.path.getmtime)
        self.log_action(f"Найден самый новый .xlsx файл: {os.path.basename(latest_file)}")
        return latest_file
    
    def _convert_xlsx_to_xlsm_with_macro(self, xlsx_file):
        """Конвертирует .xlsx в .xlsm и добавляет VBA модуль"""
        try:
            pythoncom, win32_client = self._import_excel_automation()
            if not pythoncom or not win32_client:
                return None

            # Получаем пути
            base_name = os.path.splitext(os.path.basename(xlsx_file))[0]
            output_dir = os.path.dirname(xlsx_file)
            xlsm_file = os.path.join(output_dir, f"{base_name}.xlsm")
            
            # Путь к VBA модулю
            module_path = FileManager.get_file_path(self.program_directory, "gear_xls", "Modul1.bas")
            if not os.path.exists(module_path):
                self.log_action(f"Файл VBA модуля не найден: {module_path}")
                return None
            
            self.log_action("Инициализация COM для Excel...")
            pythoncom.CoInitialize()
            
            try:
                # Создаем объект Excel
                excel = win32_client.Dispatch("Excel.Application")
                excel.Visible = False
                excel.DisplayAlerts = False
                
                # Открываем исходную книгу
                self.log_action(f"Открытие файла: {os.path.basename(xlsx_file)}")
                wb = excel.Workbooks.Open(xlsx_file)
                
                # Сохраняем как XLSM
                self.log_action(f"Сохранение как XLSM: {os.path.basename(xlsm_file)}")
                wb.SaveAs(xlsm_file, FileFormat=52)  # 52 = xlOpenXMLWorkbookMacroEnabled
                
                # Импорт VBA модуля
                self.log_action("Импорт VBA модуля...")
                vba_project = wb.VBProject
                vba_project.VBComponents.Import(module_path)
                
                # Сохраняем изменения
                wb.Save()
                
                # Закрываем книгу и Excel
                wb.Close(SaveChanges=False)
                excel.Quit()
                
                self.log_action(f"Конвертация завершена: {os.path.basename(xlsm_file)}")
                return xlsm_file
                
            except Exception as e:
                self.log_action(f"Ошибка при работе с Excel: {e}")
                try:
                    excel.Quit()
                except:
                    pass
                return None
                
            finally:
                pythoncom.CoUninitialize()
                
        except Exception as e:
            self.log_action(f"Ошибка при конвертации: {e}")
            return None
    
    def _create_newpref_from_latest_excel(self):
        """Общий метод для создания newpref.xlsx из самого нового Excel файла
        
        Returns:
            str: Путь к созданному newpref.xlsx или None в случае ошибки
        """
        try:
            # Шаг 1: Находим самый новый .xlsx файл
            self.log_action("Шаг 1: Поиск самого нового .xlsx файла...")
            latest_xlsx = self._find_latest_xlsx_file()
            if not latest_xlsx:
                messagebox.showerror("Ошибка", "Не найдено .xlsx файлов в каталоге gear_xls/excel_exports/")
                return None
            
            # Шаг 2: Конвертируем в .xlsm с VBA модулем
            self.log_action("Шаг 2: Конвертация в .xlsm с VBA модулем...")
            xlsm_file = self._convert_xlsx_to_xlsm_with_macro(latest_xlsx)
            if not xlsm_file:
                messagebox.showerror("Ошибка", "Не удалось конвертировать файл в .xlsm")
                return None
            
            # Шаг 3: Запускаем макрос CreateSchedulePlanning
            self.log_action("Шаг 3: Запуск макроса CreateSchedulePlanning...")
            if not self._run_excel_macro(xlsm_file):
                messagebox.showerror("Ошибка", "Не удалось выполнить макрос CreateSchedulePlanning")
                return None
            
            # Шаг 4: Проверяем, что создался newpref.xlsx
            newpref_path = FileManager.get_file_path(self.program_directory, "xlsx_initial", "newpref.xlsx")
            if not os.path.exists(newpref_path):
                messagebox.showerror("Ошибка", f"Файл newpref.xlsx не был создан по пути: {newpref_path}")
                return None
            
            self.log_action("Файл newpref.xlsx успешно создан!")
            return newpref_path
            
        except Exception as e:
            self.log_action(f"Ошибка при создании newpref.xlsx: {e}")
            messagebox.showerror("Ошибка", f"Произошла ошибка: {e}")
            return None

    def _run_excel_macro(self, xlsm_file, macro_name="CreateSchedulePlanning"):
        """Запускает макрос в Excel файле"""
        try:
            pythoncom, win32_client = self._import_excel_automation()
            if not pythoncom or not win32_client:
                return False

            self.log_action(f"Запуск макроса {macro_name}...")
            pythoncom.CoInitialize()
            
            try:
                # Создаем объект Excel
                excel = win32_client.Dispatch("Excel.Application")
                excel.Visible = False
                excel.DisplayAlerts = False
                
                # Открываем XLSM файл
                wb = excel.Workbooks.Open(xlsm_file)
                
                # Запускаем макрос
                excel.Application.Run(macro_name)
                
                # Сохраняем изменения
                wb.Save()
                
                # Закрываем книгу и Excel
                wb.Close(SaveChanges=False)
                excel.Quit()
                
                self.log_action(f"Макрос {macro_name} успешно выполнен")
                return True
                
            except Exception as e:
                self.log_action(f"Ошибка при выполнении макроса: {e}")
                try:
                    excel.Quit()
                except:
                    pass
                return False
                
            finally:
                pythoncom.CoUninitialize()
                
        except Exception as e:
            self.log_action(f"Ошибка при запуске макроса: {e}")
            return False

    def _load_config(self):
        """Загружает конфигурацию из config.json"""
        try:
            config_path = os.path.join(self.program_directory, "config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return self._merge_config_with_defaults(json.load(f))
            else:
                # Создаем конфиг по умолчанию, если файл не существует
                default_config = self._get_default_config()
                self._save_config(default_config)
                return default_config
        except Exception as e:
            self.log_action(f"Ошибка при загрузке конфигурации: {e}")
            return self._get_default_config()

    def _get_default_config(self):
        """Возвращает копию конфигурации по умолчанию."""
        return {
            "copy_destination_path": self.DEFAULT_CONFIG["copy_destination_path"],
            "auto_copy_enabled": self.DEFAULT_CONFIG["auto_copy_enabled"],
            "academic_year": dict(self.DEFAULT_CONFIG["academic_year"]),
        }

    def _merge_config_with_defaults(self, config):
        """Добавляет отсутствующие ключи в конфигурацию без потери пользовательских значений."""
        merged_config = self._get_default_config()
        if not isinstance(config, dict):
            return merged_config

        for key, value in config.items():
            if key == "academic_year" and isinstance(value, dict):
                merged_config["academic_year"].update(value)
            else:
                merged_config[key] = value

        return merged_config

    def get_academic_year_info(self):
        """Возвращает настройки отображения учебного года."""
        academic_year = self._load_config().get("academic_year", {})
        if not isinstance(academic_year, dict):
            return dict(self.DEFAULT_CONFIG["academic_year"])
        return academic_year
    
    def _save_config(self, config):
        """Сохраняет конфигурацию в config.json"""
        try:
            config_path = os.path.join(self.program_directory, "config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.log_action(f"Ошибка при сохранении конфигурации: {e}")
    
    def _copy_visualization_files(self):
        """Копирует файлы визуализации в указанный каталог из конфигурации"""
        try:
            config = self._load_config()
            
            if not config.get("auto_copy_enabled", True):
                self.log_action("Автоматическое копирование отключено в конфигурации")
                return
            
            destination_path = config.get("copy_destination_path", "")
            
            if not destination_path:
                self.log_action("Путь для копирования не задан в конфигурации")
                return
            
            # Проверяем, существует ли каталог назначения
            if not os.path.exists(destination_path):
                self.log_action(f"Каталог назначения не существует: {destination_path}")
                return
            
            # Определяем исходные файлы для копирования
            visualiser_dir = FileManager.get_file_path(self.program_directory, "visualiser")
            files_to_copy = [
                ("enhanced_schedule_visualization.html", "enhanced_schedule_visualization.html"),
                ("enhanced_schedule_visualization.pdf", "enhanced_schedule_visualization.pdf")
            ]
            
            copied_files = []
            for source_file, dest_file in files_to_copy:
                source_path = os.path.join(visualiser_dir, source_file)
                dest_path = os.path.join(destination_path, dest_file)
                
                if os.path.exists(source_path):
                    try:
                        shutil.copy2(source_path, dest_path)
                        copied_files.append(dest_file)
                        self.log_action(f"Файл скопирован: {dest_file}")
                    except Exception as e:
                        self.log_action(f"Ошибка при копировании файла {source_file}: {e}")
                else:
                    self.log_action(f"Исходный файл не найден: {source_path}")
            
            if copied_files:
                self.log_action(f"Успешно скопировано файлов: {len(copied_files)} в {destination_path}")
            else:
                self.log_action("Не удалось скопировать ни одного файла")
                
        except Exception as e:
            self.log_action(f"Ошибка при копировании файлов визуализации: {e}")

    def get_program_directory(self):
        """Возвращает текущий рабочий каталог"""
        return self.program_directory

    def set_program_directory(self, directory):
        """Установка рабочего каталога"""
        self.program_directory = directory
    
    def set_selected_file(self, file_path):
        """Установка выбранного файла"""
        self.selected_xlsx_file = file_path
    
    def select_directory(self):
        """Обработчик для кнопки 1: Выбор рабочего каталога"""
        directory = FileManager.select_directory("Выберите рабочий каталог программы")
        if directory:
            self.program_directory = directory
            self.log_action(f"Выбран рабочий каталог: {directory}")
            return directory
        return None
    
    def run_scheduler(self):
        """Обработчик для кнопки 2: Запуск планировщика"""
        if not self._check_directory():
            return
        
        self.log_action("Запуск планировщика...")
        
        commands = [
            "python -X utf8 main_sch.py xlsx_initial/schedule_planning.xlsm --time-limit 300 --verbose --time-interval 5"
        ]
        
        def run_in_thread():
            self.process_manager.terminal_process = self.process_manager.execute_in_terminal(
                commands, self.program_directory)
        
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def open_optimized_schedule(self):
        """Обработчик для кнопки 2.1: Открытие оптимизированного расписания"""
        if not self._check_directory():
            return
        
        file_path = FileManager.get_file_path(self.program_directory, "visualiser", "optimized_schedule.xlsx")
        if FileManager.open_file(file_path, "оптимизированное расписание"):
            self.log_action(f"Открыт файл: {file_path}")
    
    def run_gear_xls(self):
        """Обработчик для кнопки 3: Запуск gear_xls"""
        if not self._check_directory():
            return
        
        self.log_action("Запуск gear_xls...")
        
        gear_dir = FileManager.get_file_path(self.program_directory, "gear_xls")
        commands = ["python main.py"]
        
        def run_in_thread():
            self.process_manager.terminal_process = self.process_manager.execute_in_terminal(
                commands, gear_dir)
        
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def run_flask_server(self):
        """Обработчик для кнопки 3.1: Запуск flask-сервера"""
        if not self._check_directory():
            return

        if os.name != "nt":
            if self.process_manager.is_flask_server_running(self.program_directory):
                messagebox.showinfo("Информация", "Flask-сервер уже запущен")
                return
            self.log_action("Запуск flask-сервера...")

            def run_in_thread():
                self.process_manager.flask_process = self.process_manager.start_new_terminal_with_commands(
                    self.program_directory)
                time.sleep(1)
                self.log_action("Терминал flask-сервера запущен. Пока окно терминала открыто Вы можете экспортировать расписание из веб-приложения в эксель-файл")

            threading.Thread(target=run_in_thread, daemon=True).start()
            return

        self.log_action("Запуск сервера через tray control-plane...")

        def run_in_thread():
            try:
                from gear_xls.windows_runtime import ControlPlaneError, send_control_command_or_raise

                response = send_control_command_or_raise("ensure_running", self.program_directory)
                self.log_action(response.message)
            except ControlPlaneError as exc:
                self.log_action(f"Ошибка запуска сервера: {exc.response.message}")
                self._show_error("Ошибка запуска сервера", exc.response.message)
            except Exception as exc:
                self.log_action(f"Ошибка запуска сервера: {exc}")
                self._show_error("Ошибка запуска сервера", str(exc))

        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def open_web_app(self):
        """Обработчик для кнопки 3.2: Открытие веб-приложения через Flask"""
        if not self._check_directory():
            return

        if os.name != "nt":
            if not self.process_manager.is_flask_server_running(self.program_directory):
                self.log_action("Flask-сервер не запущен. Запускаем автоматически...")
                self.run_flask_server()
                if not self.process_manager.wait_for_flask_server(self.program_directory, timeout=5.0, poll_interval=0.3):
                    self.log_action("Предупреждение: Flask-сервер не ответил за 5 секунд, открываем браузер всё равно")
            else:
                self.log_action("Flask-сервер уже запущен")

            import webbrowser
            schedule_url = get_schedule_url(self.program_directory)
            webbrowser.open(schedule_url)
            self.log_action(f"Открыто веб-приложение: {schedule_url}")
            return

        self.log_action("Открытие веб-приложения через tray control-plane...")

        def run_in_thread():
            try:
                from gear_xls.windows_runtime import ControlPlaneError, send_control_command_or_raise

                response = send_control_command_or_raise("open_web", self.program_directory)
                self.log_action(response.message)
            except ControlPlaneError as exc:
                self.log_action(f"Ошибка открытия веб-приложения: {exc.response.message}")
                self._show_error("Ошибка открытия веб-приложения", exc.response.message)
            except Exception as exc:
                self.log_action(f"Ошибка открытия веб-приложения: {exc}")
                self._show_error("Ошибка открытия веб-приложения", str(exc))

        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def run_visualiser(self):
        """Обработчик для кнопки 4: Запуск визуализатора"""
        if not self._check_directory():
            return
        
        self.log_action("Запуск визуализатора...")
        
        def run_in_thread():
            if not self._run_visualiser_command():
                self._show_error(
                    "Ошибка визуализатора",
                    "Визуализатор завершился с ошибкой. Подробности отображены в логе.",
                )
                return

            self.log_action("Копирование файлов визуализации после запуска кнопки 4...")
            self._copy_visualization_files()
        
        threading.Thread(target=run_in_thread, daemon=True).start()

    def _run_visualiser_command(self):
        """Запускает визуализатор и ждет завершения процесса."""
        visualiser_dir = FileManager.get_file_path(self.program_directory, "visualiser")
        commands = [f"python -X utf8 -u example_usage_enhanced.py --lesson-type {self.lesson_type_filter}"]

        visualiser_process, reader_thread = self.process_manager.execute_command_capture(
            commands, visualiser_dir, self.log_action
        )

        if not visualiser_process:
            self.log_action("Не удалось запустить визуализатор")
            return False

        visualiser_process.wait()
        if reader_thread:
            reader_thread.join(timeout=10)

        returncode = visualiser_process.returncode
        if returncode == 0:
            self.log_action("Визуализатор завершен")
            return True

        self.log_action(f"ОШИБКА: визуализатор завершился с кодом {returncode}")
        return False

    def run_tv_visualiser(self):
        """Starts the TV visualizer without copying output artifacts."""
        if not self._check_directory():
            return

        self.log_action("Starting TV visualizer...")

        def run_in_thread():
            if not self._run_tv_visualiser_command():
                self._show_error(
                    "TV visualizer error",
                    "TV visualizer finished with an error. Details are shown in the log.",
                )
                return

            output_path = FileManager.get_file_path(
                self.program_directory,
                "visualiserTV",
                "enhanced_schedule_visualization_tv.pdf",
            )
            self.log_action(f"TV visualizer finished: {output_path}")

        threading.Thread(target=run_in_thread, daemon=True).start()

    def _run_tv_visualiser_command(self):
        """Runs the TV visualizer and waits for completion."""
        visualiser_tv_dir = FileManager.get_file_path(self.program_directory, "visualiserTV")
        commands = ["python -X utf8 -u example_usage_enhanced.py"]

        tv_process, reader_thread = self.process_manager.execute_command_capture(
            commands, visualiser_tv_dir, self.log_action
        )

        if not tv_process:
            self.log_action("Failed to start TV visualizer")
            return False

        tv_process.wait()
        if reader_thread:
            reader_thread.join(timeout=10)

        returncode = tv_process.returncode
        if returncode == 0:
            return True

        self.log_action(f"ERROR: TV visualizer finished with code {returncode}")
        return False
    
    def open_pdf_visualization(self):
        """Обработчик для кнопки 4.1: Открытие PDF-визуализации"""
        if not self._check_directory():
            return
        
        file_path = FileManager.get_file_path(self.program_directory, "visualiser", "enhanced_schedule_visualization.pdf")
        if FileManager.open_file(file_path, "PDF-визуализацию"):
            self.log_action(f"Открыт файл: {file_path}")
    
    def open_html_visualization(self):
        """Обработчик для кнопки 4.2: Открытие HTML-визуализации"""
        if not self._check_directory():
            return
        
        file_path = FileManager.get_file_path(self.program_directory, "visualiser", "enhanced_schedule_visualization.html")
        if FileManager.open_web_file(file_path, "HTML-визуализацию"):
            self.log_action(f"Открыт файл: {file_path}")
    
    def select_xlsx_file(self):
        """Обработчик для кнопки 5: Выбор .xlsx файла"""
        if not self._check_directory():
            return
        
        excel_dir = FileManager.get_file_path(self.program_directory, "gear_xls", "excel_exports")
        xlsx_file = FileManager.select_xlsx_file(excel_dir, "Выберите .xlsx файл")
        
        if xlsx_file:
            self.selected_xlsx_file = xlsx_file
            filename = os.path.basename(xlsx_file)
            self.log_action(f"Выбран файл: {filename}")
            return filename
        return None
    
    def convert_to_xlsm(self):
        """Обработчик для кнопки 6: Конвертирование в .xlsm"""
        if not self._check_directory():
            return
        
        if not self.selected_xlsx_file:
            messagebox.showwarning("Предупреждение", "Сначала выберите .xlsx файл (шаг 5)")
            return
        
        self.log_action("Конвертирование в .xlsm...")
        
        xlsx_filename = os.path.basename(self.selected_xlsx_file)
        commands = [f"python convert_to_xlsm.py excel_exports/{xlsx_filename}"]
        
        def run_in_thread():
            self.process_manager.terminal_process = self.process_manager.execute_in_terminal(
                commands, FileManager.get_file_path(self.program_directory, "gear_xls"))
        
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def open_xlsm_file(self):
        """Обработчик для кнопки 6.1: Открытие .xlsm файла"""
        if not self._check_directory():
            return
        
        if not self.selected_xlsx_file:
            messagebox.showwarning("Предупреждение", "Сначала выберите .xlsx файл (шаг 5)")
            return
        
        xlsx_filename = os.path.basename(self.selected_xlsx_file)
        base_name = os.path.splitext(xlsx_filename)[0]
        
        xlsm_path = FileManager.get_file_path(self.program_directory, "gear_xls", "excel_exports", f"{base_name}.xlsm")
        
        if not FileManager.check_directory_exists(xlsm_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл .xlsm не найден: {xlsm_path}\n\nСначала конвертируйте .xlsx файл в .xlsm (кнопка 6)")
            return
        
        if FileManager.open_file(xlsm_path, ".xlsm файл"):
            self.log_action(f"Открыт файл: {xlsm_path}")
    
    def open_newpref(self):
        """Обработчик для кнопки 7.0: Сложная логика создания и открытия newpref.xlsx"""
        if not self._check_directory():
            return
        
        self.log_action("Начинаем процесс создания newpref.xlsx...")
        
        def process_in_thread():
            try:
                # Выполняем общую последовательность шагов а, б, в
                newpref_path = self._create_newpref_from_latest_excel()
                if not newpref_path:
                    return  # Ошибка уже отображена в _create_newpref_from_latest_excel
                
                # Шаг 5: Открываем созданный файл
                self.log_action("Шаг 4: Открытие созданного newpref.xlsx...")
                if FileManager.open_file(newpref_path, "newpref.xlsx"):
                    self.log_action("Процесс успешно завершен! Файл newpref.xlsx открыт.")
                    messagebox.showinfo("Успех", "Файл newpref.xlsx успешно создан и открыт!")
                else:
                    messagebox.showerror("Ошибка", "Не удалось открыть созданный файл newpref.xlsx")
                    
            except Exception as e:
                self.log_action(f"Ошибка в процессе создания newpref.xlsx: {e}")
                messagebox.showerror("Ошибка", f"Произошла ошибка: {e}")
        
        # Запускаем в отдельном потоке, чтобы не блокировать интерфейс
        threading.Thread(target=process_in_thread, daemon=True).start()
    
    def run_scheduler_newpref(self):
        """Обработчик для кнопки 7: Создание newpref.xlsx и запуск планировщика"""
        if not self._check_directory():
            return

        self.log_action("Начинаем процесс создания newpref.xlsx и запуска планировщика...")

        def process_in_thread():
            try:
                # Выполняем общую последовательность шагов а, б, в
                newpref_path = self._create_newpref_from_latest_excel()
                if not newpref_path:
                    return  # Ошибка уже отображена в _create_newpref_from_latest_excel

                # Шаг 4: Запускаем планировщик с newpref.xlsx
                self.log_action("Шаг 4: Запуск планировщика с newpref.xlsx...")

                commands = [
                    "python -X utf8 -u main_sch.py xlsx_initial/newpref.xlsx --time-limit 300 --verbose --time-interval 5"
                ]

                # Запоминаем mtime выходного файла до запуска (страховочная проверка)
                output_xlsx = FileManager.get_file_path(
                    self.program_directory, "visualiser", "optimized_schedule.xlsx"
                )
                mtime_before = os.path.getmtime(output_xlsx) if os.path.exists(output_xlsx) else None

                # Запускаем планировщик с перехватом вывода
                self.log_action("Ожидание завершения планировщика...")
                scheduler_process, reader_thread = self.process_manager.execute_command_capture(
                    commands, self.program_directory, self.log_action
                )

                if scheduler_process:
                    scheduler_process.wait()
                if reader_thread:
                    reader_thread.join(timeout=10)

                # --- Проверка результата ---
                returncode = scheduler_process.returncode if scheduler_process else 1
                mtime_after = os.path.getmtime(output_xlsx) if os.path.exists(output_xlsx) else None
                output_updated = (mtime_after is not None) and (mtime_after != mtime_before)

                scheduler_ok = (returncode == 0) and output_updated

                if not scheduler_ok:
                    if returncode != 0:
                        reason = (
                            "Планировщик завершился с ошибкой (INFEASIBLE / MODEL_INVALID / timeout / исключение).\n\n"
                            "Расписание содержит логические конфликты, которые нельзя разрешить автоматически:\n"
                            "— один преподаватель запланирован в двух местах одновременно,\n"
                            "— одна аудитория занята несколькими занятиями одновременно, или\n"
                            "— группа имеет пересекающиеся занятия.\n\n"
                            "Откройте веб-редактор, исправьте конфликты и повторите попытку.\n"
                            "Подробная диагностика отображена в панели логов выше."
                        )
                    else:
                        reason = (
                            "Планировщик завершился, но файл optimized_schedule.xlsx не был обновлён.\n"
                            "Возможно, решение не найдено в пределах лимита времени или произошла ошибка.\n"
                            "Подробности — в панели логов выше."
                        )
                    self.log_action(f"ОШИБКА: Оптимизация не удалась (returncode={returncode}). Pipeline прерван.")
                    messagebox.showerror(
                        "Ошибка оптимизации — изменения не применены",
                        reason
                    )
                    return

                self.log_action("Планировщик завершен успешно. Запускаем дополнительные действия...")

                # Дополнительные действия после завершения планировщика

                # Шаг 5: Запуск визуализатора
                self.log_action("Шаг 5: Запуск визуализатора...")
                if not self._run_visualiser_command():
                    self._show_error(
                        "Ошибка визуализатора",
                        "Визуализатор завершился с ошибкой. Копирование файлов не выполнено.",
                    )
                    return

                # Шаг 6: Копирование файлов визуализации
                self.log_action("Шаг 6: Копирование файлов визуализации...")
                self._copy_visualization_files()

                self.log_action("Весь процесс успешно завершен!")
                messagebox.showinfo(
                    "Успех",
                    "Файл newpref.xlsx создан, планировщик выполнен, визуализация обновлена.\n\n"
                    "Веб-редактор (gear_xls) не обновляется автоматически — "
                    "запустите его отдельно через соответствующую кнопку, если нужна актуальная версия."
                )

            except Exception as e:
                self.log_action(f"Ошибка в процессе создания newpref.xlsx и запуска планировщика: {e}")
                messagebox.showerror("Ошибка", f"Произошла ошибка: {e}")

        # Запускаем в отдельном потоке, чтобы не блокировать интерфейс
        threading.Thread(target=process_in_thread, daemon=True).start()

    def _check_directory(self):
        """Проверка установки рабочего каталога"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return False
        return True

