import tkinter as tk
from tkinter import ttk

# Импорт модулей из gui_services
from gui_services import UIBuilder, FileManager, ProcessManager, AppActions, Logger


class ApplicationInterface:
    def __init__(self, root):
        self.root = root

        # Настройка главного окна
        UIBuilder.create_main_window(root)

        # Создание основного фрейма
        main_frame = UIBuilder.create_main_frame(root)

        # Заголовок
        UIBuilder.create_title_label(main_frame)

        # Инициализация сервисов (без logger пока)
        self.process_manager = ProcessManager()
        self.app_actions = AppActions(self.process_manager)  # Без log_callback

        # Информационная панель
        info_frame = UIBuilder.create_info_frame(main_frame)
        self.dir_label, _ = UIBuilder.create_info_labels(info_frame)  # file_label больше не используется
        self.academic_year_label = UIBuilder.create_academic_year_label(info_frame)

        # Контейнер для кнопок
        buttons_frame = UIBuilder.create_buttons_frame(main_frame)

        # Лог действий
        log_frame = UIBuilder.create_log_frame(main_frame)
        log_text = UIBuilder.create_log_text(log_frame)

        # Статус бар
        status_bar = UIBuilder.create_status_bar(root)

        # Теперь инициализируем logger и устанавливаем его в app_actions
        self.logger = Logger(log_text, status_bar, root)
        self.app_actions.set_log_callback(self.logger.log_action)

        # Обновляем информацию о каталоге
        if self.app_actions.get_program_directory():
            directory = self.app_actions.get_program_directory()
            # Показываем только имя каталога, если путь слишком длинный
            if len(directory) > 60:
                display_dir = "..." + directory[-57:]
            else:
                display_dir = directory
            self.dir_label.config(text=f"Рабочий каталог: {display_dir}")
        else:
            self.dir_label.config(text="⚠ Рабочий каталог: не определен автоматически")
        self._update_academic_year_label()

        # Создание кнопок интерфейса
        self._create_buttons(buttons_frame)

    def _update_academic_year_label(self):
        """Показывает период учебного года из config.json."""
        academic_year = self.app_actions.get_academic_year_info()
        period = str(academic_year.get("period", "")).strip()
        color = str(academic_year.get("color", "#2E7D32")).strip() or "#2E7D32"

        text = f"Учебный год: {period}" if period else "Учебный год: не указан"
        foreground = self._get_contrast_text_color(color)

        try:
            self.academic_year_label.config(text=text, bg=color, fg=foreground)
        except tk.TclError:
            self.academic_year_label.config(text=text, bg="#2E7D32", fg="white")

        if period:
            self.root.title(f"Единый интерфейс оптимизации расписания - {period}")

    @staticmethod
    def _get_contrast_text_color(background_color):
        """Возвращает черный или белый цвет текста для hex-фона."""
        hex_color = background_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(char * 2 for char in hex_color)
        if len(hex_color) != 6:
            return "white"

        try:
            red = int(hex_color[0:2], 16)
            green = int(hex_color[2:4], 16)
            blue = int(hex_color[4:6], 16)
        except ValueError:
            return "white"

        brightness = (red * 299 + green * 587 + blue * 114) / 1000
        return "black" if brightness > 160 else "white"

    def _create_buttons(self, buttons_frame):
        """Создание всех кнопок интерфейса"""

        # Кнопки 2: Оптимизация
        UIBuilder.create_double_button_row(
            buttons_frame,
            "2. Запустить оптимизацию", self.app_actions.run_scheduler,
            "2.1. Открыть оптимизированное расписание", self.app_actions.open_optimized_schedule
        )

        # Кнопки 3: Веб-приложение
        UIBuilder.create_triple_button_row(
            buttons_frame,
            "3. Создать веб-приложение", self.app_actions.run_gear_xls,
            "3.1. Запустить сервер", self.app_actions.run_flask_server,
            "3.2. Открыть веб-приложение", self.app_actions.open_web_app
        )

        # Фильтр типа занятий (для визуализатора)
        filter_row = ttk.Frame(buttons_frame)
        filter_row.pack(fill='x', padx=5, pady=(4, 0))

        ttk.Label(filter_row, text="Фильтр типа занятий:").pack(side='left', padx=(0, 8))

        lesson_type_labels = [
            "Все",
            "Только групповые",
            "Только индивидуальные",
            "Только наххильфе",
            "Пробные/разовые",
            "Негрупповые"
        ]
        lesson_type_values = ['all', 'group', 'individual', 'nachhilfe', 'trial', 'non-group']

        self.lesson_type_var = tk.StringVar(value="Все")
        lesson_type_combo = ttk.Combobox(
            filter_row,
            textvariable=self.lesson_type_var,
            values=lesson_type_labels,
            state='readonly',
            width=26
        )
        lesson_type_combo.pack(side='left')

        def _on_lesson_type_changed(event=None):
            selected_label = self.lesson_type_var.get()
            if selected_label in lesson_type_labels:
                idx = lesson_type_labels.index(selected_label)
                value = lesson_type_values[idx]
                self.app_actions.set_lesson_type_filter(value)

        lesson_type_combo.bind('<<ComboboxSelected>>', _on_lesson_type_changed)

        # Кнопки 4: Визуализация
        UIBuilder.create_triple_button_row(
            buttons_frame,
            "4. Запустить визуализатор", self.app_actions.run_visualiser,
            "4.1. Открыть PDF-визуализацию", self.app_actions.open_pdf_visualization,
            "4.2. Открыть HTML-визуализацию", self.app_actions.open_html_visualization
        )

        # Кнопки 7: Работа с новыми предпочтениями
        UIBuilder.create_double_button_row(
            buttons_frame,
            "7.0. Создать и открыть новые предпочтения", self.app_actions.open_newpref,
            "7. Учесть изменения", self.app_actions.run_scheduler_newpref
        )

        UIBuilder.create_single_button(
            buttons_frame,
            "8. Запустить TV-визуализатор", self.app_actions.run_tv_visualiser
        )


if __name__ == "__main__":
    # Создаем экземпляр Tk
    root = tk.Tk()

    # Создаем приложение
    app = ApplicationInterface(root)

    # Запускаем основной цикл
    root.mainloop()
