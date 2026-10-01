"""
Основной модуль для добавления ограничений в модель оптимизации.
Объединяет функциональность из отдельных модулей.
"""

from linked_constraints import add_linked_constraints
from resource_constraints import add_resource_conflict_constraints
from time_conflict_constraints import _add_time_conflict_constraints

# Re-экспорт основных функций для обратной совместимости
__all__ = ['add_linked_constraints', 'add_resource_conflict_constraints']
