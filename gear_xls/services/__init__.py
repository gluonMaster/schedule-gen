"""
Пакет сервисов для генератора расписания.

Содержит бизнес-логику и сервисы для обработки расписания занятий.
"""

__version__ = '1.1.0' 
__author__ = 'Schedule Generator Team'

# Импортируем основные сервисы для удобства
from .schedule_pipeline import SchedulePipeline, SchedulePipelineError
from .color_service import ColorService

__all__ = [
    'SchedulePipeline',
    'SchedulePipelineError',
    'ColorService'
]