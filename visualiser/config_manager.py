"""
Модуль управления настройками визуализации
Позволяет загружать и редактировать настройки визуализации расписания
"""

import os
import json
import configparser


class ConfigManager:
    """Класс для управления настройками визуализации"""
    
    def __init__(self, config_file=None):
        """
        Инициализирует менеджер настроек
        
        Args:
            config_file (str, optional): Путь к файлу настроек
        """
        # Значения по умолчанию
        self.default_config = {
            "general": {
                "title": "Stundenplan",
                "page_size": "A3",
                "orientation": "landscape",
                "font_name": "Helvetica"
            },
            "layout": {
                "margin": 30,
                "column_padding": 5,
                "block_padding": 3,
                "max_block_height": 65,
                "min_block_height": 30
            },
            "style": {
                "header_font_size": 14,
                "block_font_size": 10,
                "title_font_size": 18,
                "footer_font_size": 8,
                "line_width": 1.5
            },
            "colors": {
                "default_fill": "#f0f0f0",
                "default_border": "#000000",
                "default_text": "#000000",
                "header_background": "#e0e0e0",
                "header_text": "#000000"
            },
            "translations": {
                "Mo": "Понедельник",
                "Di": "Вторник",
                "Mi": "Среда",
                "Do": "Четверг",
                "Fr": "Пятница",
                "Sa": "Суббота",
                "So": "Воскресенье"
            }
        }
        
        # Текущие настройки
        self.config = self.default_config.copy()
        
        # Если указан файл настроек, загружаем их
        if config_file:
            self.load_config(config_file)
    
    def load_config(self, config_file):
        """
        Загружает настройки из файла
        
        Args:
            config_file (str): Путь к файлу настроек
        """
        if not os.path.exists(config_file):
            print(f"Файл настроек не найден: {config_file}")
            return
        
        # Определяем формат файла по расширению
        file_ext = os.path.splitext(config_file)[1].lower()
        
        if file_ext == '.json':
            # Загружаем из JSON
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                self._merge_config(loaded_config)
                print(f"Настройки успешно загружены из JSON-файла: {config_file}")
            except Exception as e:
                print(f"Ошибка при загрузке настроек из JSON: {e}")
        
        elif file_ext in ['.ini', '.cfg', '.conf']:
            # Загружаем из INI
            try:
                parser = configparser.ConfigParser()
                parser.read(config_file, encoding='utf-8')
                
                # Преобразуем конфигурацию из INI в наш формат
                loaded_config = {}
                for section in parser.sections():
                    loaded_config[section] = {}
                    for key, value in parser.items(section):
                        # Пробуем преобразовать строковые значения в числа или булевы значения
                        try:
                            if value.lower() in ['true', 'yes', '1']:
                                value = True
                            elif value.lower() in ['false', 'no', '0']:
                                value = False
                            elif value.replace('.', '', 1).isdigit():
                                value = float(value) if '.' in value else int(value)
                        except:
                            pass
                        
                        loaded_config[section][key] = value
                
                self._merge_config(loaded_config)
                print(f"Настройки успешно загружены из INI-файла: {config_file}")
            except Exception as e:
                print(f"Ошибка при загрузке настроек из INI: {e}")
        
        else:
            print(f"Неподдерживаемый формат файла настроек: {file_ext}")
    
    def save_config(self, config_file):
        """
        Сохраняет настройки в файл
        
        Args:
            config_file (str): Путь для сохранения файла настроек
        """
        # Определяем формат файла по расширению
        file_ext = os.path.splitext(config_file)[1].lower()
        
        if file_ext == '.json':
            # Сохраняем в JSON
            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                print(f"Настройки успешно сохранены в JSON-файл: {config_file}")
            except Exception as e:
                print(f"Ошибка при сохранении настроек в JSON: {e}")
        
        elif file_ext in ['.ini', '.cfg', '.conf']:
            # Сохраняем в INI
            try:
                parser = configparser.ConfigParser()
                
                # Преобразуем наш формат в формат INI
                for section, options in self.config.items():
                    parser[section] = {}
                    for key, value in options.items():
                        # Преобразуем не-строковые значения в строки
                        parser[section][key] = str(value)
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    parser.write(f)
                print(f"Настройки успешно сохранены в INI-файл: {config_file}")
            except Exception as e:
                print(f"Ошибка при сохранении настроек в INI: {e}")
        
        else:
            print(f"Неподдерживаемый формат файла настроек: {file_ext}")
    
    def reset_to_defaults(self):
        """Сбрасывает настройки к значениям по умолчанию"""
        self.config = self.default_config.copy()
        print("Настройки сброшены к значениям по умолчанию")
    
    def _merge_config(self, new_config):
        """
        Объединяет новые настройки с текущими
        
        Args:
            new_config (dict): Новые настройки
        """
        for section, options in new_config.items():
            if section not in self.config:
                self.config[section] = {}
            
            if isinstance(options, dict):
                for key, value in options.items():
                    self.config[section][key] = value
    
    def get(self, section, option, default=None):
        """
        Возвращает значение настройки
        
        Args:
            section (str): Раздел настроек
            option (str): Имя настройки
            default: Значение по умолчанию, если настройка не найдена
            
        Returns:
            Значение настройки или значение по умолчанию
        """
        try:
            return self.config[section][option]
        except KeyError:
            return default
    
    def set(self, section, option, value):
        """
        Устанавливает значение настройки
        
        Args:
            section (str): Раздел настроек
            option (str): Имя настройки
            value: Новое значение настройки
        """
        if section not in self.config:
            self.config[section] = {}
        
        self.config[section][option] = value


# Пример использования
if __name__ == "__main__":
    # Создаем менеджер настроек
    config = ConfigManager()
    
    # Выводим некоторые настройки по умолчанию
    print(f"Заголовок: {config.get('general', 'title')}")
    print(f"Размер страницы: {config.get('general', 'page_size')}")
    print(f"Максимальная высота блока: {config.get('layout', 'max_block_height')}")
    
    # Изменяем настройки
    config.set('general', 'title', 'Мое расписание')
    config.set('layout', 'max_block_height', 80)
    
    # Выводим измененные настройки
    print(f"Новый заголовок: {config.get('general', 'title')}")
    print(f"Новая максимальная высота блока: {config.get('layout', 'max_block_height')}")
    
    # Сохраняем настройки в файл
    config.save_config('schedule_config.json')
    
    # Сбрасываем настройки к значениям по умолчанию
    config.reset_to_defaults()
    
    # Загружаем настройки из файла
    config.load_config('schedule_config.json')
