import threading
import time
import tkinter as tk


class Logger:
    """Система логирования для GUI."""

    def __init__(self, log_text_widget, status_bar_widget, root_widget):
        self.log_text = log_text_widget
        self.status_bar = status_bar_widget
        self.root = root_widget

    def _dispatch_to_ui(self, callback):
        if threading.current_thread() is threading.main_thread():
            callback()
            return
        try:
            self.root.after(0, callback)
        except RuntimeError:
            pass

    def log_action(self, message):
        """Добавляет сообщение в лог и обновляет статус."""
        timestamp = time.strftime("%H:%M:%S")

        def update_widgets():
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.status_bar.config(text=message)
            self.root.update_idletasks()

        self._dispatch_to_ui(update_widgets)

    def clear_log(self):
        """Очистка лога."""

        def clear_widgets():
            self.log_text.delete(1.0, tk.END)

        self._dispatch_to_ui(clear_widgets)

    def set_status(self, message):
        """Установка статуса без записи в лог."""

        def update_status():
            self.status_bar.config(text=message)

        self._dispatch_to_ui(update_status)
