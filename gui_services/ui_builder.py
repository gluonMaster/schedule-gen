import tkinter as tk
from tkinter import ttk


class UIBuilder:
    """Строитель пользовательского интерфейса"""
    
    @staticmethod
    def create_main_window(root, title="Единый интерфейс оптимизации расписания", geometry="800x600"):
        """Настройка главного окна"""
        root.title(title)
        root.geometry(geometry)
        
        # Применяем тему оформления
        style = ttk.Style()
        try:
            style.theme_use("clam")  # Более современная тема, если доступна
        except:
            pass  # Используем тему по умолчанию, если "clam" недоступна
    
    @staticmethod
    def create_main_frame(root, padding="20"):
        """Создание основного фрейма"""
        main_frame = ttk.Frame(root, padding=padding)
        main_frame.pack(fill=tk.BOTH, expand=True)
        return main_frame
    
    @staticmethod
    def create_title_label(parent, text="Управление оптимизацией", font=("Arial", 16, "bold")):
        """Создание заголовка"""
        title_label = ttk.Label(parent, text=text, font=font)
        title_label.pack(pady=10)
        return title_label
    
    @staticmethod
    def create_info_frame(parent, title="Информация"):
        """Создание информационной панели"""
        info_frame = ttk.LabelFrame(parent, text=title)
        info_frame.pack(fill=tk.X, pady=10)
        return info_frame
    
    @staticmethod
    def create_info_labels(info_frame):
        """Создание информационных меток"""
        dir_label = ttk.Label(info_frame, text="Рабочий каталог: не выбран")
        dir_label.pack(anchor=tk.W, padx=10, pady=5)
        
        # Убираем метку для файла, так как выбор файла больше не используется
        file_label = None
        
        return dir_label, file_label

    @staticmethod
    def create_academic_year_label(info_frame):
        """Создание цветной метки учебного года."""
        year_label = tk.Label(
            info_frame,
            text="Учебный год: не указан",
            anchor=tk.W,
            padx=8,
            pady=3,
            font=("Arial", 10, "bold"),
        )
        year_label.pack(anchor=tk.W, padx=10, pady=(0, 5))
        return year_label
    
    @staticmethod
    def create_buttons_frame(parent):
        """Создание контейнера для кнопок"""
        buttons_frame = ttk.Frame(parent)
        buttons_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        return buttons_frame
    
    @staticmethod
    def create_single_button(parent, text, command, width=30):
        """Создает кнопку на всю ширину"""
        btn = ttk.Button(parent, text=text, command=command, width=width)
        btn.pack(fill=tk.X, pady=5, padx=20)
        return btn
    
    @staticmethod
    def create_double_button_row(parent, text1, command1, text2, command2):
        """Создает две кнопки в одной строке (50% на 50%)"""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=5, padx=20)
        
        btn1 = ttk.Button(row_frame, text=text1, command=command1)
        btn1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn2 = ttk.Button(row_frame, text=text2, command=command2)
        btn2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        return btn1, btn2
    
    @staticmethod
    def create_triple_button_row(parent, text1, command1, text2, command2, text3, command3):
        """Создает три кнопки в одной строке (33% на 33% на 34%)"""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=5, padx=20)
        
        btn1 = ttk.Button(row_frame, text=text1, command=command1)
        btn1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        
        btn2 = ttk.Button(row_frame, text=text2, command=command2)
        btn2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 3))
        
        btn3 = ttk.Button(row_frame, text=text3, command=command3)
        btn3.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        
        return btn1, btn2, btn3
    
    @staticmethod
    def create_log_frame(parent, title="Лог действий"):
        """Создание фрейма для лога"""
        log_frame = ttk.LabelFrame(parent, text=title)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        return log_frame
    
    @staticmethod
    def create_log_text(log_frame, height=10, width=80):
        """Создание текстового поля для лога"""
        log_text = tk.Text(log_frame, height=height, width=width, wrap=tk.WORD)
        log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Добавляем скроллбар для лога
        scrollbar = ttk.Scrollbar(log_text, command=log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.config(yscrollcommand=scrollbar.set)
        
        return log_text
    
    @staticmethod
    def create_status_bar(root):
        """Создание статус бара"""
        status_bar = ttk.Label(root, text="Готов к работе", relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        return status_bar
