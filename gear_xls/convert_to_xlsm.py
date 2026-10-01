#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для конвертации Excel-файла расписания из .xlsx в .xlsm, 
добавления VBA-модуля и кнопки запуска макроса.

Использование:
python convert_to_xlsm.py source_file.xlsx [output_file.xlsm]
"""

import os
import sys
import time
import shutil
import logging
import win32com.client
import pythoncom

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('convert_to_xlsm')

def convert_xlsx_to_xlsm_with_vba(source_file, output_file=None):
    """
    Конвертирует .xlsx файл в .xlsm, добавляет VBA-модуль и кнопку.
    
    Args:
        source_file (str): Путь к исходному .xlsx файлу
        output_file (str, optional): Путь к выходному .xlsm файлу
    
    Returns:
        str: Путь к созданному .xlsm файлу или None в случае ошибки
    """
    try:
        # Проверяем существование исходного файла
        if not os.path.exists(source_file):
            logger.error(f"Исходный файл не найден: {source_file}")
            return None
        
        # Получаем абсолютные пути
        source_file = os.path.abspath(source_file)
        
        # Если не указан выходной файл, создаем имя по умолчанию
        if not output_file:
            base_dir = os.path.dirname(source_file)
            base_name = os.path.splitext(os.path.basename(source_file))[0]
            output_file = os.path.join(base_dir, f"{base_name}.xlsm")
        else:
            output_file = os.path.abspath(output_file)
        
        # Получаем путь к текущему скрипту и модулю VBA
        script_dir = os.path.dirname(os.path.abspath(__file__))
        module_path = os.path.join(script_dir, "Modul1.bas")
        
        # Проверяем наличие файла с VBA-модулем
        if not os.path.exists(module_path):
            logger.error(f"Файл с VBA-модулем не найден: {module_path}")
            return None
        
        # Инициализация COM для текущего потока
        logger.info("Инициализация COM...")
        pythoncom.CoInitialize()
        
        try:
            # Создаем объект Excel
            logger.info("Создание объекта Excel...")
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            
            # Открываем исходную книгу
            logger.info(f"Открытие файла: {source_file}")
            wb = excel.Workbooks.Open(source_file)
            
            # Сохраняем как XLSM
            logger.info(f"Сохранение как XLSM: {output_file}")
            wb.SaveAs(output_file, FileFormat=52)  # 52 = xlOpenXMLWorkbookMacroEnabled
            
            # Импорт VBA модуля
            logger.info(f"Импорт VBA модуля: {module_path}")
            vba_project = wb.VBProject
            vba_project.VBComponents.Import(module_path)
            
            # Получаем лист Schedule
            logger.info("Получение листа Schedule...")
            try:
                ws = wb.Worksheets("Schedule")
            except:
                logger.warning("Лист Schedule не найден. Используем первый лист.")
                ws = wb.Worksheets(1)
            
            # Добавляем кнопку с использованием метода Shapes
            logger.info("Добавление кнопки...")
            # Константы Excel для типа формы: msoFormControl = 0
            btn = ws.Shapes.AddFormControl(0, 615, 20, 120, 30)  # left, top, width, height
            btn.Name = "RunMacroButton"
            btn.TextFrame.Characters().Text = "Create Planning"
            btn.OnAction = "CreateSchedulePlanning"
            
            # Сохраняем изменения
            logger.info("Сохранение изменений...")
            wb.Save()
            
            # Закрываем книгу и Excel
            logger.info("Закрытие Excel...")
            wb.Close(SaveChanges=False)  # Уже сохранили выше
            excel.Quit()
            
            # Очистка COM объектов
            logger.info("Очистка COM объектов...")
            del btn
            del ws
            del vba_project
            del wb
            del excel
            
            logger.info(f"Конвертация успешно завершена: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Ошибка при работе с Excel: {e}")
            import traceback
            traceback.print_exc()
            try:
                excel.Quit()
            except:
                pass
            return None
            
        finally:
            # Освобождаем COM
            pythoncom.CoUninitialize()
            
    except Exception as e:
        logger.error(f"Ошибка при конвертации файла: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """
    Основная функция для запуска из командной строки
    """
    # Проверяем аргументы командной строки
    if len(sys.argv) < 2:
        print("Использование: python convert_to_xlsm.py source_file.xlsx [output_file.xlsm]")
        sys.exit(1)
    
    # Получаем пути к файлам
    source_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) >= 3 else None
    
    # Запускаем конвертацию
    result = convert_xlsx_to_xlsm_with_vba(source_file, output_file)
    
    if result:
        print(f"Конвертация успешно завершена. Создан файл: {result}")
        sys.exit(0)
    else:
        print("Ошибка при конвертации файла. См. лог для подробностей.")
        sys.exit(1)

if __name__ == "__main__":
    main()