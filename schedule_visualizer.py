import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.colors as mcolors
import numpy as np
from datetime import datetime, timedelta
import random

def time_to_minutes(time_str):
    """Конвертирует время из строкового формата 'HH:MM' в минуты от начала дня"""
    hours, minutes = map(int, time_str.split(':'))
    return hours * 60 + minutes

def minutes_to_time(minutes):
    """Конвертирует минуты от начала дня в строковый формат 'HH:MM'"""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def generate_color(seed):
    """Генерирует стабильный цвет на основе seed"""
    random.seed(hash(seed))
    h = random.random()
    s = 0.5 + random.random() * 0.3  # Средняя насыщенность
    l = 0.7 + random.random() * 0.2   # Более светлый оттенок
    return mcolors.hsv_to_rgb((h, s, l))

def wrap_text(text, width):
    """Разбивает текст на строки, чтобы вместить его в блок указанной ширины"""
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) + len(current_line) <= width:
            current_line.append(word)
            current_length += len(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
            current_length = len(word)
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return '\n'.join(lines)

def create_schedule_visualization(excel_file, output_pdf):
    """Создает визуализацию расписания из Excel-файла и сохраняет в PDF"""
    # Загрузка данных из Excel
    df = pd.read_excel(excel_file, sheet_name='Schedule')
    
    # Конвертация времени из строкового формата в минуты
    df['start_minutes'] = df['start_time'].apply(time_to_minutes)
    df['end_minutes'] = df['end_time'].apply(time_to_minutes)
    
    # Определение дней недели и их порядка
    days_order = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    days_in_schedule = sorted(df['day'].unique(), key=lambda x: days_order.index(x) if x in days_order else 999)
    
    # Определение минимального и максимального времени
    min_time = df['start_minutes'].min()
    max_time = df['end_minutes'].max()
    
    # Словарь для хранения цветов предметов
    subject_colors = {}
    for subject in df['subject'].unique():
        subject_colors[subject] = generate_color(subject)
    
    # Создание PDF для сохранения визуализации
    with PdfPages(output_pdf) as pdf:
        # Создание общего расписания
        create_full_schedule_visualization(df, days_in_schedule, min_time, max_time, subject_colors, pdf)
        
        # Создание индивидуальных расписаний для преподавателей
        for teacher in sorted(df['teacher'].unique()):
            teacher_df = df[df['teacher'] == teacher]
            create_individual_schedule(teacher_df, f"Stundenplan: {teacher}", days_in_schedule, min_time, max_time, subject_colors, pdf)
        
        # Создание индивидуальных расписаний для групп
        for group in sorted(df['group'].unique()):
            group_df = df[df['group'] == group]
            create_individual_schedule(group_df, f"Расписание группы: {group}", days_in_schedule, min_time, max_time, subject_colors, pdf)

def create_full_schedule_visualization(df, days, min_time, max_time, subject_colors, pdf):
    """Создает полную визуализацию расписания"""
    create_individual_schedule(df, "Полное расписание", days, min_time, max_time, subject_colors, pdf)

def create_individual_schedule(df, title, days, min_time, max_time, subject_colors, pdf):
    """Создает индивидуальное расписание для группы или преподавателя"""
    if df.empty:
        return
    
    # Определение параметров для визуализации
    fig_width = 12
    fig_height = 16
    
    # Создаем фигуру
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    
    # Настройка осей
    ax.set_xlim(0, len(days))
    
    # Находим минимальное и максимальное время для данного расписания
    schedule_min_time = df['start_minutes'].min()
    schedule_max_time = df['end_minutes'].max()
    
    # Добавляем небольшой буфер
    schedule_min_time = max(0, schedule_min_time - 30)
    schedule_max_time = min(24*60, schedule_max_time + 30)
    
    ax.set_ylim(schedule_max_time, schedule_min_time)  # Инвертируем ось Y, чтобы время шло сверху вниз
    
    # Настройка заголовка и осей
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks([i + 0.5 for i in range(len(days))])
    ax.set_xticklabels(days, fontsize=12)
    
    # Добавление временных меток
    time_ticks = []
    time_labels = []
    
    hour_start = schedule_min_time // 60
    hour_end = (schedule_max_time + 59) // 60
    
    for hour in range(hour_start, hour_end + 1):
        minute = hour * 60
        if minute >= schedule_min_time and minute <= schedule_max_time:
            time_ticks.append(minute)
            time_labels.append(f"{hour:02d}:00")
    
    ax.set_yticks(time_ticks)
    ax.set_yticklabels(time_labels, fontsize=10)
    
    # Добавляем сетку
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Отрисовка занятий
    for _, lesson in df.iterrows():
        day_idx = days.index(lesson['day']) if lesson['day'] in days else 0
        
        # Координаты и размеры блока
        x = day_idx
        y = lesson['start_minutes']
        width = 1
        height = lesson['end_minutes'] - lesson['start_minutes']
        
        # Текст для отображения в блоке
        group = lesson['group']
        teacher = lesson['teacher']
        room = lesson['room']
        building = lesson['building']
        time_str = f"{lesson['start_time']}-{lesson['end_time']}"
        subject = lesson['subject']
        
        text = f"{group}\n{teacher}\n{room}, {building}\n{time_str}"
        
        # Создаем прямоугольник для занятия
        color = subject_colors.get(subject, (0.8, 0.8, 0.8))
        rect = patches.Rectangle((x, y), width, height, linewidth=1, 
                                 edgecolor='black', facecolor=color, alpha=0.8)
        ax.add_patch(rect)
        
        # Добавляем текст внутри блока
        text_x = x + width / 2
        text_y = y + height / 2
        
        # Определяем размер шрифта в зависимости от высоты блока
        font_size = min(9, max(6, height / 15))
        
        # Добавляем текст, центрированный внутри блока
        ax.text(text_x, text_y, text, ha='center', va='center', 
                fontsize=font_size, color='black', 
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7))
    
    # Настройка внешнего вида графика
    plt.tight_layout()
    
    # Сохранение в PDF
    pdf.savefig(fig)
    plt.close()

if __name__ == "__main__":
    create_schedule_visualization("optimized_schedule.xlsx", "schedule_visualization.pdf")
    print("Визуализация расписания создана и сохранена в файл 'schedule_visualization.pdf'")
