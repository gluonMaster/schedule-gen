"""
Модуль с методами для HTML-экспорта расписания
"""

import re
import html as html_lib
import hashlib
import colorsys
import tempfile
import webbrowser
import json
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime
from lesson_label_utils import get_lesson_type, label_text_or_empty, should_show_subject_line

ORGANIZATION_NAME = 'Kinder- und Elternzentrum "KOLIBRI" e.V.'
WEEKDAYS = {day: index for index, day in enumerate(('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'), 1)}


def _hex_to_rgb(value):
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))


def _hsv_to_hex(hue, saturation, value):
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    return f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'


def _relative_luminance(rgb):
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first, second):
    lighter, darker = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def cta_palette(bg_color, border_color):
    """Tint the CTA to the card it sits on; a white card borrows the building outline hue."""
    hue, saturation, _ = colorsys.rgb_to_hsv(*_hex_to_rgb(bg_color))
    if saturation < 0.05:
        hue = colorsys.rgb_to_hsv(*_hex_to_rgb(border_color))[0]
    fill = _hsv_to_hex(hue, 0.28, 0.93)
    line = _hsv_to_hex(hue, 0.60, 0.55)
    # Darken the label until the tinted chip keeps a readable contrast on every fill.
    value = 0.34
    text = _hsv_to_hex(hue, 0.85, value)
    while value > 0.04 and _contrast_ratio(_hex_to_rgb(fill), _hex_to_rgb(text)) < 4.5:
        value -= 0.02
        text = _hsv_to_hex(hue, 0.85, value)
    return fill, line, text


def trial_intake_settings():
    """Read the editor's existing persisted configuration on EVERY export."""
    path = Path(__file__).resolve().parents[1] / 'config.json'
    settings = json.loads(path.read_text(encoding='utf-8')).get('trial_intake', {}) if path.exists() else {}
    enabled = settings.get('cta_enabled', False)
    origin = settings.get('portal_origin', '')
    if not isinstance(enabled, bool) or not isinstance(origin, str):
        raise ValueError('trial-intake: invalid editor configuration')
    origin = origin.strip().rstrip('/')
    if origin:
        url = urlsplit(origin)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.path or url.query or url.fragment or any(c.isspace() for c in origin)
                or any(c in origin for c in '\\<>"')):
            raise ValueError('trial-intake: portal_origin must be an HTTPS origin')
    if enabled and not origin:
        raise ValueError('trial-intake: portal_origin is required before enabling CTA')
    return enabled, origin


def catalog_lesson(lesson, day):
    """TIN-06: public fields and identity from the exact rendered group lesson."""
    if get_lesson_type(lesson) != 'group':
        return None
    values = {key: unicodedata.normalize('NFC', label_text_or_empty(lesson.get(source)))
              for key, source in [('subject', 'subject'), ('group', 'group'),
                                  ('start', 'start_time'), ('end', 'end_time'),
                                  ('teacher', 'teacher'), ('room', 'room'), ('building', 'building')]}
    values['weekday'] = WEEKDAYS.get(day)
    if (not values['weekday'] or any(not values[k] or len(values[k].encode('utf-16-le')) // 2 > 160
                                  or re.search(r'[\x00-\x1f\x7f]', values[k])
                                  for k in ('subject', 'group', 'teacher', 'room', 'building'))
            or values['building'] not in ('Kolibri', 'Villa')
            or any(not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', values[k]) for k in ('start', 'end'))
            or values['end'] <= values['start']):
        # Do not leak source rows or personal data into operator logs.
        raise ValueError('trial-intake: incomplete public lesson context; check subject/day/time/group/teacher/room/building')
    identity = [values[k] for k in ('subject', 'group', 'weekday', 'start', 'end', 'teacher', 'room', 'building')]
    values['id'] = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    return values


class HtmlExportMixin:
    """Миксин с методами для HTML-экспорта"""

    def export_to_html(self, output_path=None):
        """
        Экспортирует расписание в HTML с улучшенной адаптивностью для мобильных устройств

        Args:
            output_path (str, optional): Путь для сохранения HTML-файла
                Если не указан, создается временный файл и открывается в браузере

        Returns:
            bool: True, если экспорт успешен, иначе False
        """
        try:
            cta_enabled, portal_origin = trial_intake_settings()
            catalog = {}
            # Создаем HTML-документ
            html = []
            html.append('<!DOCTYPE html>')
            html.append('<html lang="ru">')
            html.append('<head>')
            html.append('    <meta charset="UTF-8">')
            html.append('    <meta name="viewport" content="width=device-width, initial-scale=1.0">')

            # Заголовок
            title = "Stundenplan"
            if self.config:
                title = self.config.get('general', 'title', "Stundenplan")
            title = str(title)
            if ORGANIZATION_NAME not in title:
                title = re.sub(r'\bKolibri\b', lambda _: ORGANIZATION_NAME, title, flags=re.I)
            title = html_lib.escape(title, quote=True)

            html.append(f'    <title>{title}</title>')

            # Стили с улучшенной адаптивностью
            html.append('    <style>')
            html.append('''
            :root {
                --primary-color: #4a6da7;
                --text-color: #333;
                --bg-color: #fff;
                --header-bg: #f3f4f6;
                --card-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                --border-radius: 10px;
                --lesson-height: 130px;
                --lesson-min-width: 200px;
            }

            @media (prefers-color-scheme: dark) {
                :root {
                    --primary-color: #6d8fc9;
                    --text-color: #f0f0f0;
                    --bg-color: #121212;
                    --header-bg: #1e1e1e;
                    --card-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                }
            }

            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
                    Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                color: var(--text-color);
                background-color: var(--bg-color);
                padding: 16px;
                transition: background-color 0.3s, color 0.3s;
            }

            h1 {
                text-align: center;
                margin-bottom: 20px;
                color: var(--primary-color);
                font-size: 1.8rem;
            }

            .schedule-container {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(var(--lesson-min-width), 1fr));
                gap: 16px;
                max-width: 1400px;
                margin: 0 auto;
            }

            .day-column {
                display: flex;
                flex-direction: column;
                margin-bottom: 20px;
            }

            .day-header {
                text-align: center;
                font-weight: bold;
                padding: 10px;
                background-color: var(--header-bg);
                border-radius: var(--border-radius) var(--border-radius) 0 0;
                margin-bottom: 10px;
                position: sticky;
                top: 0;
                z-index: 10;
            }

            .lesson-block {
                margin-bottom: 10px;
                padding: 10px;
                border:6px solid;
                border-radius: var(--border-radius);
                min-height: var(--lesson-height);
                box-shadow: var(--card-shadow);
                display: flex;
                flex-direction: column;
                transition: transform 0.2s, box-shadow 0.2s;
            }

            .lesson-block:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 10px rgba(0, 0, 0, 0.15);
            }

            .lesson-time {
                font-weight: bold;
                font-size: 1rem;
                margin-bottom: 5px;
            }

            .lesson-group {
                font-size: 1.1rem;
                font-weight: bold;
                margin-bottom: 5px;
            }

            .lesson-teacher {
                margin-bottom: 5px;
            }

            .lesson-location {
                font-style: italic;
                margin-top: auto;
            }
            .lesson-location, .organization-name { overflow-wrap: anywhere; }
            .organization-name { text-align: center; margin: 0 0 20px; }
            .trial-intake-link { display: flex; flex-direction: column; align-items: center;
                margin-top: 10px; padding: 7px 10px; min-height: 36px;
                border: 1px solid var(--cta-line, #176b54); border-radius: 8px;
                background: var(--cta-bg, #eef6f2); color: var(--cta-fg, #10503f);
                font-size: 0.74rem; font-weight: 600; line-height: 1.25; letter-spacing: 0.01em;
                text-align: center; text-decoration: none; text-wrap: balance;
                transition: background-color 0.15s, border-color 0.15s, color 0.15s; }
            .trial-intake-link .cta-ru { font-weight: 500; }
            @media (hover: hover) {
                .trial-intake-link:hover { background: var(--cta-fg, #10503f);
                    border-color: var(--cta-fg, #10503f); color: var(--cta-bg, #eef6f2); }
            }
            .trial-intake-link:focus-visible { outline: 3px solid #c17800; outline-offset: 2px; }

            .footer {
                text-align: center;
                margin-top: 30px;
                font-size: 0.8rem;
                color: #666;
                padding: 10px;
            }

            /* Адаптивность для мобильных устройств */
            @media (max-width: 768px) {
                .schedule-container {
                    grid-template-columns: 1fr;
                }

                .day-column {
                    margin-bottom: 30px;
                }

                h1 {
                    font-size: 1.5rem;
                }

                .lesson-block {
                    min-height: auto;
                    padding: 12px;
                }

                .trial-intake-link {
                    min-height: 42px;
                    padding: 9px 12px;
                    font-size: 0.8rem;
                }
            }

            /* Горизонтальный скролл на десктопе */
            @media (min-width: 769px) {
                .schedule-wrapper {
                    overflow-x: auto;
                    width: 100%;
                }
                .schedule-container {
                    /* Делаем ряд без переноса */
                    display: flex;
                    flex-wrap: nowrap;
                    gap: 16px;           /* тот же отступ между «ячейками» */
                }
                .day-column {
                    /* фиксируем ширину каждой колонки */
                    flex: 0 0 var(--lesson-min-width);
                }
            }

            /* Кнопка переключения темной/светлой темы */
            .theme-toggle {
                position: fixed;
                top: 20px;
                right: 20px;
                background: var(--primary-color);
                color: white;
                border: none;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.2rem;
                box-shadow: var(--card-shadow);
                z-index: 100;
            }

            /* Скрываем элемент для печати */
            @media print {
                .theme-toggle {
                    display: none;
                }
            }

            /* Visual indicator for non-group lessons */
            .lesson-block[data-lesson-type="individual"],
            .lesson-block[data-lesson-type="nachhilfe"],
            .lesson-block[data-lesson-type="trial"] {
                box-shadow: inset 4px 0 0 #1976d2, var(--card-shadow, 0 1px 3px rgba(0,0,0,.15));
            }

            .lesson-subject {
                font-size: 0.78em;
                color: #555;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 100%;
                font-style: italic;
            }
            ''')
            html.append('    </style>')
            html.append('</head>')
            html.append('<body>')

            # Кнопка переключения темы
            html.append('    <button class="theme-toggle" id="themeToggle">🌓</button>')

            # Заголовок
            html.append(f'    <h1>{title}</h1>')
            html.append(f'    <p class="organization-name">{html_lib.escape(ORGANIZATION_NAME)}</p>')

            # Контейнер расписания
            html.append('    <div class="schedule-wrapper">')
            html.append('        <div class="schedule-container">')

            # Анализируем количество блоков для каждого дня, чтобы решить, нужны ли подстолбцы
            day_subcolumns, subcolumn_count = self._analyze_subcolumns_for_html()

            # Создаем колонку для каждого дня недели с учетом подстолбцов
            for day in self.days_of_week:
                day_name = self.day_translations.get(day, day)

                # Если день требует подстолбцов
                if day in day_subcolumns:
                    sc_count = subcolumn_count[day]
                    for sc_idx, subcolumn in enumerate(day_subcolumns[day]):
                        html.append('        <div class="day-column">')
                        html.append(f'            <div class="day-header">{day_name} ({sc_idx+1}/{sc_count})</div>')

                        # Добавляем блоки для этого подстолбца
                        for lesson in subcolumn:
                            html.append(self._generate_lesson_block_html(lesson, day, catalog, cta_enabled, portal_origin))

                        html.append('        </div>')
                else:
                    # Обычный день без подстолбцов
                    html.append('        <div class="day-column">')
                    html.append(f'            <div class="day-header">{day_name}</div>')

                    # Добавляем блоки занятий для текущего дня
                    if day in self.schedule_by_day:
                        lessons = self.schedule_by_day[day]

                        # Сортируем занятия строго по времени начала
                        lessons = sorted(lessons, key=lambda x: x['start_time_mins'])

                        for lesson in lessons:
                            html.append(self._generate_lesson_block_html(lesson, day, catalog, cta_enabled, portal_origin))

                    html.append('        </div>')

            html.append('        </div>')
            html.append('    </div>')
            if len(catalog) > 500:
                raise ValueError('trial-intake: catalog exceeds 500 public lessons')
            catalog_json = json.dumps({'version': 1, 'lessons': list(catalog.values())}, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
            html.append(f'    <script type="application/json" id="trial-intake-catalog">{catalog_json}</script>')

            # Добавляем информацию о дате создания
            html.append(f'    <div class="footer">Создано: {datetime.now().strftime("%d.%m.%Y %H:%M")}</div>')

            # JavaScript для переключения темы
            html.append('''
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    const themeToggle = document.getElementById('themeToggle');
                    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

                    // Установка начальной темы на основе системных предпочтений
                    if (prefersDark) {
                        document.documentElement.classList.add('dark-theme');
                    }

                    // Обработчик для кнопки переключения темы
                    themeToggle.addEventListener('click', function() {
                        document.documentElement.classList.toggle('dark-theme');

                        if (document.documentElement.classList.contains('dark-theme')) {
                            document.documentElement.style.setProperty('--text-color', '#f0f0f0');
                            document.documentElement.style.setProperty('--bg-color', '#121212');
                            document.documentElement.style.setProperty('--header-bg', '#1e1e1e');
                        } else {
                            document.documentElement.style.setProperty('--text-color', '#333');
                            document.documentElement.style.setProperty('--bg-color', '#fff');
                            document.documentElement.style.setProperty('--header-bg', '#f3f4f6');
                        }
                    });

                    // Добавляем возможность фильтрации по группе/преподавателю (простой поиск)
                    const scheduleContainer = document.querySelector('.schedule-container');
                    const title = document.querySelector('h1');

                    const searchBox = document.createElement('input');
                    searchBox.type = 'text';
                    searchBox.placeholder = 'Suche nach Fach, Gruppe oder Lehrer(in)....';
                    searchBox.style.display = 'block';
                    searchBox.style.margin = '0 auto 20px';
                    searchBox.style.padding = '8px 12px';
                    searchBox.style.borderRadius = '5px';
                    searchBox.style.border = '1px solid #ddd';
                    searchBox.style.width = '90%';
                    searchBox.style.maxWidth = '400px';

                    title.after(searchBox);

                    searchBox.addEventListener('input', function(e) {
                        const query = e.target.value.toLowerCase();
                        const lessonBlocks = document.querySelectorAll('.lesson-block');

                        lessonBlocks.forEach(block => {
                            const subjectElement = block.querySelector('.lesson-subject');
                            const subject = subjectElement ? subjectElement.textContent.toLowerCase() : '';
                            const group = block.querySelector('.lesson-group').textContent.toLowerCase();
                            const teacher = block.querySelector('.lesson-teacher').textContent.toLowerCase();
                            const location = block.querySelector('.lesson-location').textContent.toLowerCase();

                            if (subject.includes(query) || group.includes(query) || teacher.includes(query) || location.includes(query)) {
                                block.style.display = 'flex';
                            } else {
                                block.style.display = 'none';
                            }
                        });
                    });
                });
            </script>
            ''')

            html.append('</body>')
            html.append('</html>')

            # Формируем HTML-документ
            html_content = '\n'.join(html)
            if len(html_content.encode('utf-8')) > 1024 * 1024:
                raise ValueError('trial-intake: HTML exceeds the portal reader size limit')

            # Если указан путь для сохранения файла, записываем HTML
            if output_path:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"HTML-файл сохранен: {output_path}")
                return True
            else:
                # Иначе создаем временный файл и открываем его в браузере
                with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as temp_file:
                    temp_path = temp_file.name
                    temp_file.write(html_content.encode('utf-8'))

                # Открываем файл в браузере
                webbrowser.open('file://' + temp_path.replace('\\', '/'))
                print(f"HTML-файл открыт в браузере")
                return True

        except Exception as e:
            print(f"Ошибка при экспорте в HTML: {e}")
            return False

    def _analyze_subcolumns_for_html(self):
        """
        Анализирует распределение блоков по дням недели для HTML-экспорта
        и определяет необходимость разделения на подстолбцы

        Returns:
            tuple: (словарь подстолбцов, словарь количества подстолбцов)
        """
        # Для хранения подстолбцов и их количества
        day_subcolumns = {}
        subcolumn_count = {}

        # Анализируем распределение блоков и создаем подстолбцы при необходимости
        for day in self.days_of_week:
            if day in self.schedule_by_day:
                lessons = sorted(self.schedule_by_day[day], key=lambda l: l['start_time_mins'])

                # Если количество блоков превышает порог для 2 страниц, создаем подстолбцы
                pages_needed = (len(lessons) + self.blocks_per_page - 1) // self.blocks_per_page

                if pages_needed > self.max_pages_per_column:
                    # Вычисляем количество необходимых подстолбцов
                    subcolumns_needed = (pages_needed + self.max_pages_per_column - 1) // self.max_pages_per_column
                    subcolumn_count[day] = subcolumns_needed

                    # Распределяем блоки по подстолбцам
                    blocks_per_subcolumn = (len(lessons) + subcolumns_needed - 1) // subcolumns_needed

                    # Создаем подстолбцы и распределяем блоки
                    day_subcolumns[day] = []
                    for i in range(subcolumns_needed):
                        start_idx = i * blocks_per_subcolumn
                        end_idx = min((i + 1) * blocks_per_subcolumn, len(lessons))
                        day_subcolumns[day].append(lessons[start_idx:end_idx])
                else:
                    # Если подстолбцы не нужны, используем 1 столбец
                    subcolumn_count[day] = 1

        return day_subcolumns, subcolumn_count

    def _generate_lesson_block_html(self, lesson, day=None, catalog=None, cta_enabled=False, portal_origin=''):
        """
        Генерирует HTML-код для блока занятия с улучшенным форматированием

        Args:
            lesson (dict): Информация о занятии

        Returns:
            str: HTML-код блока занятия
        """
        # Генерируем HTML для одного блока занятия
        if lesson.get('hidden') or lesson.get('internal') or lesson.get('public') is False:
            return ''
        model = catalog_lesson(lesson, day)
        if model:
            if catalog is not None:
                catalog[model['id']] = model
            # A single normalized model drives the displayed fields, JSON and link.
            lesson = {**lesson, **model, 'start_time': model['start'], 'end_time': model['end']}
        block_html = []

#        # Определяем цвет блока на основе первого слова в названии группы
#        group_name = lesson['group']
#
#        # Проверяем, является ли название группы шаблоном "цифра+буква"
#        if re.match(r'^\d+[A-Za-z]$', group_name):
#            # Все группы вида "1A", "3D", "12E" должны иметь одинаковый цвет
#            color_key = "DIGIT_LETTER_GROUP"
#        else:
#            # Получаем первое слово из названия группы
#            first_word = group_name.split()[0] if ' ' in group_name else group_name
#            color_key = first_word
#
#        # Генерируем HEX-цвет на основе ключа
#        hash_obj = hashlib.md5(color_key.encode())
#        hash_int = int(hash_obj.hexdigest(), 16)
#        hue = (hash_int % 1000) / 1000.0
#        r_bg, g_bg, b_bg = colorsys.hsv_to_rgb(hue, 0.5, 0.95)
#        bg_color = f'#{int(r_bg*255):02x}{int(g_bg*255):02x}{int(b_bg*255):02x}'

        # Определяем цвет блока на основе специальных правил
        group_name = label_text_or_empty(lesson.get('group', ''))
        teacher_name = label_text_or_empty(lesson.get('teacher', ''))
        building_name = label_text_or_empty(lesson.get('building', ''))
        room_name = label_text_or_empty(lesson.get('room', ''))
        subject_val = label_text_or_empty(lesson.get('subject', ''))
        start_time = label_text_or_empty(lesson.get('start_time', ''))
        end_time = label_text_or_empty(lesson.get('end_time', ''))
        lower_group = group_name.lower() if group_name else ""

        # Правило 1: Если входит число+буква (например 2D, 11B) -> бледно-зеленый
        if re.match(r'^\d+[A-Za-z]$', group_name):
            bg_color = '#ccffcc'  # бледно-зеленый в HEX
            #bg_color = '#ffffff'

        # Правило 2: Если содержит слово "kunst" -> бледно-голубой
        elif "kunst" in lower_group:
            bg_color = '#ccf2ff'  # бледно-голубой в HEX
            #bg_color = '#ffffff'

        # Правило 3: Если содержит слово "tanz" -> бледно-желтый
        elif "tanz" in lower_group:
            bg_color = '#ffffcc'  # бледно-желтый в HEX
            #bg_color = '#ffffff'

        # Правило 4: Во всех остальных случаях -> белый
        else:
            bg_color = '#ffffff'  # белый в HEX

        # Определяем цвет контура на основе названия здания
        hash_obj = hashlib.md5(building_name.encode())
        hash_int = int(hash_obj.hexdigest(), 16)
        hue_border = (hash_int % 1000) / 1000.0
        r_border, g_border, b_border = colorsys.hsv_to_rgb(hue_border, 0.8, 0.7)
        border_color = f'#{int(r_border*255):02x}{int(g_border*255):02x}{int(b_border*255):02x}'

        # Определяем цвет текста (черный или белый) в зависимости от яркости фона
#        luminance = 0.299 * r_bg + 0.587 * g_bg + 0.114 * b_bg
#        text_color = '#000000' if luminance > 0.5 else '#ffffff'
        text_color = '#000000'

        # Добавляем атрибут данных для возможности фильтрации
        _lesson_type = get_lesson_type(lesson)
        escape = lambda value: html_lib.escape(value, quote=True)
        data_attributes = (
            f'data-group="{escape(group_name)}" '
            f'data-teacher="{escape(teacher_name)}" '
            f'data-building="{escape(building_name)}" '
            f'data-lesson-type="{escape(_lesson_type)}"'
        )
        if model:
            data_attributes += f' data-lesson-id="{model["id"]}"'
        # Здание рядом с номером комнаты остаётся коротким маркером Kolibri/Villa,
        # полное название учреждения стоит один раз в шапке документа.
        group_name, teacher_name, room_name, start_time, end_time, building_name = map(
            escape, (group_name, teacher_name, room_name, start_time, end_time, building_name))

        # Палитра CTA выводится из заливки карточки, поэтому кнопка всегда в её тоне
        cta_style = ''
        if model and cta_enabled:
            cta_bg, cta_line, cta_fg = cta_palette(bg_color, border_color)
            cta_style = f' --cta-bg: {cta_bg}; --cta-line: {cta_line}; --cta-fg: {cta_fg};'

        # Формируем HTML для блока занятия с улучшенным дизайном
        block_html.append(f'            <div class="lesson-block" {data_attributes} style="background-color: {bg_color}; border-color: {border_color}; color: {text_color};{cta_style}">')
        block_html.append(f'                <div class="lesson-time">{start_time}-{end_time}</div>')
        if should_show_subject_line(lesson):
            subject_html = html_lib.escape(subject_val, quote=True)
            block_html.append(f'                <div class="lesson-subject">{subject_html}</div>')
        block_html.append(f'                <div class="lesson-group">{group_name}</div>')
        block_html.append(f'                <div class="lesson-teacher">{teacher_name}</div>')
        block_html.append(f'                <div class="lesson-location">{room_name}, {building_name}</div>')
        if model and cta_enabled:
            url = escape(f'{portal_origin}/probestunde?lesson={model["id"]}')
            block_html.append(f'                <a class="trial-intake-link" href="{url}"><span class="cta-de">Probestunde anfragen /</span><span class="cta-ru">Запросить пробное</span></a>')
        block_html.append('            </div>')

        return '\n'.join(block_html)
