#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для подготовки JavaScript-кода к вставке в Python-строки.
Автоматически экранирует фигурные скобки, обратные слеши и другие специальные символы.
"""

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import sys

class JSToPythonConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("JavaScript в Python конвертер")
        self.root.geometry("900x700")
        
        # Фрейм для кнопок и параметров
        control_frame = tk.Frame(root, padx=10, pady=10)
        control_frame.pack(fill=tk.X)
        
        # Кнопки для управления
        open_btn = tk.Button(control_frame, text="Открыть JS файл", command=self.open_file, width=20)
        open_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.process_btn = tk.Button(control_frame, text="Конвертировать", command=self.process_javascript, width=20, state=tk.DISABLED)
        self.process_btn.grid(row=0, column=1, padx=5, pady=5)
        
        self.save_btn = tk.Button(control_frame, text="Сохранить в файл", command=self.save_to_file, width=20, state=tk.DISABLED)
        self.save_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # Опции форматирования
        options_frame = tk.LabelFrame(control_frame, text="Опции", padx=10, pady=5)
        options_frame.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W+tk.E)
        
        self.indent_var = tk.IntVar(value=8)
        tk.Label(options_frame, text="Отступ:").pack(side=tk.LEFT)
        tk.Entry(options_frame, textvariable=self.indent_var, width=3).pack(side=tk.LEFT, padx=5)
        
        # Текстовые области для исходного и конвертированного кода
        panes_frame = tk.PanedWindow(root, orient=tk.VERTICAL)
        panes_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Исходный JavaScript
        source_frame = tk.LabelFrame(panes_frame, text="Исходный JavaScript код")
        self.source_text = scrolledtext.ScrolledText(source_frame, wrap=tk.NONE, height=15)
        self.source_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        panes_frame.add(source_frame)
        
        # Конвертированный Python
        result_frame = tk.LabelFrame(panes_frame, text="Код для вставки в Python")
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.NONE, height=15)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        panes_frame.add(result_frame)
        
        # Привязка событий
        self.source_text.bind("<KeyRelease>", self.update_buttons)
        
        # Статус
        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var.set("Готов к работе. Откройте файл или вставьте код.")
        
        # Инициализация переменных
        self.current_file = None
    
    def open_file(self):
        file_path = filedialog.askopenfilename(
            title="Выберите JavaScript файл",
            filetypes=[("JavaScript файлы", "*.js"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                self.source_text.delete(1.0, tk.END)
                self.source_text.insert(tk.END, content)
                self.current_file = file_path
                self.update_buttons()
                self.status_var.set(f"Открыт файл: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
    
    def update_buttons(self, event=None):
        if len(self.source_text.get(1.0, tk.END).strip()) > 0:
            self.process_btn.config(state=tk.NORMAL)
        else:
            self.process_btn.config(state=tk.DISABLED)
            
        if len(self.result_text.get(1.0, tk.END).strip()) > 0:
            self.save_btn.config(state=tk.NORMAL)
        else:
            self.save_btn.config(state=tk.DISABLED)
    
    def process_javascript(self):
        js_code = self.source_text.get(1.0, tk.END)
        
        if not js_code.strip():
            self.status_var.set("Ошибка: Исходный код пуст.")
            return
        
        # Применяем преобразования
        python_code = self.convert_js_to_python_string(js_code)
        
        # Выводим результат
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, python_code)
        self.update_buttons()
        self.status_var.set("Конвертация завершена. Можно сохранить результат.")
    
    def convert_js_to_python_string(self, js_code):
        # Удаление лишних пробелов и табуляций в начале строк
        js_code = js_code.rstrip()
        
        # Заменяем одиночные фигурные скобки на двойные для f-строк в Python
        js_code = js_code.replace('{', '{{').replace('}', '}}')
        
        # Экранируем обратные слеши
        js_code = js_code.replace('\\', '\\\\')
        
        # Специальная обработка для регулярных выражений
        # В JavaScript: var regex = /pattern/;
        # В Python строке: var regex = /pattern/;
        js_code = re.sub(r'(/.+?/[gim]?)', lambda m: m.group(1).replace('\\\\', '\\'), js_code)
        
        # Отменяем двойное экранирование для уже экранированных фигурных скобок в регулярных выражениях
        js_code = re.sub(r'\\\\{', '\\{', js_code)
        js_code = re.sub(r'\\\\}', '\\}', js_code)
        
        # Экранируем кавычки, но не трогаем уже экранированные
        js_code = js_code.replace('\\"', '____ESCAPED_DOUBLE_QUOTE____')
        js_code = js_code.replace('"', '\\"')
        js_code = js_code.replace('____ESCAPED_DOUBLE_QUOTE____', '\\"')
        
        # Разбиваем на строки и добавляем отступы
        lines = js_code.split('\n')
        indent = ' ' * self.indent_var.get()
        
        # Форматируем для Python строки
        python_code = []
        for i, line in enumerate(lines):
            if i == 0:
                python_code.append(f'return f"""{line}')
            elif i == len(lines) - 1:
                python_code.append(f'{indent}{line}"""')
            else:
                python_code.append(f'{indent}{line}')
        
        return '\n'.join(python_code)
    
    def save_to_file(self):
        if not self.result_text.get(1.0, tk.END).strip():
            messagebox.showwarning("Предупреждение", "Нечего сохранять. Сначала выполните конвертацию.")
            return
            
        default_filename = "converted_js.py"
        if self.current_file:
            default_filename = os.path.splitext(os.path.basename(self.current_file))[0] + "_python.py"
            
        file_path = filedialog.asksaveasfilename(
            title="Сохранить как",
            defaultextension=".py",
            initialfile=default_filename,
            filetypes=[("Python файлы", "*.py"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(self.result_text.get(1.0, tk.END))
            self.status_var.set(f"Файл сохранен: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {e}")

def main():
    root = tk.Tk()
    app = JSToPythonConverter(root)
    root.mainloop()

if __name__ == "__main__":
    main()