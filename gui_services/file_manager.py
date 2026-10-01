import os
import platform
import subprocess
import webbrowser
from tkinter import filedialog, messagebox


class FileManager:
    """Управление файлами и их открытием"""
    
    @staticmethod
    def open_file(file_path, description="файл"):
        """Универсальный метод для открытия файлов в зависимости от ОС"""
        if not os.path.exists(file_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл не найден: {file_path}")
            return False
        
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", file_path])
            else:  # Linux и др.
                subprocess.Popen(["xdg-open", file_path])
            return True
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть {description}: {e}")
            return False
    
    @staticmethod
    def open_web_file(file_path, description="веб-файл"):
        """Открытие HTML файлов через браузер"""
        if not os.path.exists(file_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл не найден: {file_path}")
            return False
        
        try:
            webbrowser.open(f"file://{file_path}")
            return True
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть {description}: {e}")
            return False
    
    @staticmethod
    def select_directory(title="Выберите каталог"):
        """Диалог выбора каталога"""
        return filedialog.askdirectory(title=title)
    
    @staticmethod
    def select_xlsx_file(initial_dir, title="Выберите .xlsx файл"):
        """Диалог выбора xlsx файла"""
        if not os.path.exists(initial_dir):
            messagebox.showwarning("Предупреждение", 
                                  f"Каталог не найден: {initial_dir}")
            return None
        
        return filedialog.askopenfilename(
            title=title,
            initialdir=initial_dir,
            filetypes=[("Excel файлы", "*.xlsx")]
        )
    
    @staticmethod
    def check_directory_exists(directory):
        """Проверка существования каталога"""
        return os.path.exists(directory)
    
    @staticmethod
    def get_file_path(base_dir, *path_parts):
        """Безопасное создание пути к файлу"""
        return os.path.join(base_dir, *path_parts)
