// Сервис для управления drag & drop функциональностью блоков расписания

var DragDropService = (function() {
    'use strict';
    
    // Приватные переменные
    var preventDrag = false;
    var offsetX = 0;
    var offsetY = 0;
    var draggedBlock = null;
    var dragSnapshot = null;
    var compactRowsDragPaused = false;

    function getAuthUi() {
        return window.SchedGenAuthUI || null;
    }

    function getCurrentRole() {
        return window.USER_ROLE || 'viewer';
    }

    function getBlockLessonType(block) {
        return block ? (block.getAttribute('data-lesson-type') || 'group') : 'group';
    }

    function canDragBlock(block) {
        var authUi = getAuthUi();
        var role = getCurrentRole();
        var lessonType = getBlockLessonType(block);

        if (!block || block.getAttribute('data-block-id')) {
            return false;
        }
        if (authUi && typeof authUi.isEditMode === 'function' && !authUi.isEditMode()) {
            return false;
        }
        if (authUi && typeof authUi.canMutateBlock === 'function') {
            return authUi.canMutateBlock(role, block);
        }
        if (role === 'admin') return true;
        if (role === 'editor') return lessonType !== 'group';
        if (role === 'organizer') return lessonType === 'trial';
        return false;
    }

    function pauseCompactRowsForDrag() {
        if (
            !compactRowsDragPaused &&
            window.ScheduleCompactRows &&
            typeof window.ScheduleCompactRows.pauseForInteraction === 'function'
        ) {
            window.ScheduleCompactRows.pauseForInteraction('drag');
            compactRowsDragPaused = true;
        }
    }

    function resumeCompactRowsAfterDrag(refresh) {
        if (
            compactRowsDragPaused &&
            window.ScheduleCompactRows &&
            typeof window.ScheduleCompactRows.resumeAfterInteraction === 'function'
        ) {
            window.ScheduleCompactRows.resumeAfterInteraction('drag', { refresh: !!refresh });
        }
        compactRowsDragPaused = false;
    }
    
    // Приватные методы
    function initializeBlockEvents() {
        document.querySelectorAll('.activity-block').forEach(function(block) {
            if (!canDragBlock(block)) {
                return;
            }
            // Отслеживаем состояние для определения двойного клика
            let clickTimeout = null;
            let isPotentialDoubleClick = false;
            
            block.addEventListener('mousedown', function(e) {
                // Если открыт диалог редактирования или установлен флаг preventDrag, не начинаем drag
                if (window.editDialogOpen || preventDrag || isPotentialDoubleClick) {
                    e.preventDefault();
                    e.stopPropagation();
                    return;
                }
                
                // Устанавливаем флаг потенциального двойного клика
                isPotentialDoubleClick = true;
                
                // Устанавливаем timeout для определения, был ли это одиночный клик
                clickTimeout = setTimeout(function() {
                    // Если таймаут сработал до второго клика, значит это был одиночный клик
                    // и можно начать перетаскивание
                    isPotentialDoubleClick = false;
                    
                    if (!window.editDialogOpen && !preventDrag) {
                        startDrag(block, e);
                    }
                }, 200); // 200 мс - стандартное время для определения двойного клика
                
                e.preventDefault(); // Предотвращаем выделение текста при перетаскивании
            });
            
            // Обработчик двойного клика
            block.addEventListener('dblclick', function(e) {
                handleDoubleClick(block, e, clickTimeout, isPotentialDoubleClick);
                isPotentialDoubleClick = false;
                clickTimeout = null;
            });
        });
        
        // Глобальные обработчики для перемещения и отпускания
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }
    
    function startDrag(block, event) {
        draggedBlock = block;
        dragSnapshot = createDragSnapshot(block);
        pauseCompactRowsForDrag();
        window.draggedBlock = block; // Поддерживаем совместимость с существующим кодом
        
        var rect = block.getBoundingClientRect();
        offsetX = event.clientX - rect.left;
        offsetY = event.clientY - rect.top;
        block.style.opacity = 0.7;
    }
    
    function handleDoubleClick(block, event, clickTimeout, isPotentialDoubleClick) {
        // Очищаем таймаут
        if (clickTimeout) {
            clearTimeout(clickTimeout);
        }
        
        // Устанавливаем флаг предотвращения drag на короткое время
        preventDrag = true;
        setTimeout(() => { preventDrag = false; }, 500);
        
        // Если был начат процесс перетаскивания, отменяем его
        if (draggedBlock === block) {
            restoreDragSnapshot(dragSnapshot);
            draggedBlock = null;
            window.draggedBlock = null;
            dragSnapshot = null;
            resumeCompactRowsAfterDrag(true);
        }
        
        // Предотвращаем запуск перетаскивания
        event.stopPropagation();
        event.preventDefault();
        
        // Сохраняем позицию блока перед редактированием
        var origLeft = block.style.left;
        var origTop = block.style.top;
        
        // Открываем диалог редактирования только если не открыт
        if (!window.editDialogOpen) {
            openEditDialog(block, origLeft, origTop);
        }
    }
    
    function handleMouseMove(event) {
        if (draggedBlock && !window.editDialogOpen && !preventDrag) {
            var container = draggedBlock.parentElement;
            var rect = container.getBoundingClientRect();
            var scrollX = container.scrollLeft;
            var scrollY = container.scrollTop;
            var newLeft = event.clientX - rect.left - offsetX + scrollX;
            var newTop = event.clientY - rect.top - offsetY + scrollY;
            
            // Используем GridSnapService для привязки к сетке
            if (typeof GridSnapService !== 'undefined') {
                var snapped = GridSnapService.snapToGrid(newLeft, newTop, draggedBlock);
                draggedBlock.style.left = snapped.left + 'px';
                draggedBlock.style.top = snapped.top + 'px';
            } else {
                // Fallback без привязки к сетке
                draggedBlock.style.left = newLeft + 'px';
                draggedBlock.style.top = newTop + 'px';
            }
        }
    }
    
    function handleMouseUp(event) {
        if (draggedBlock && !window.editDialogOpen) {
            try {
            draggedBlock.style.opacity = 1;
            
            // Используем BlockDropService для обработки завершения перетаскивания
            if (typeof BlockDropService !== 'undefined') {
                BlockDropService.processBlockDrop(draggedBlock);
            } else {
                // Fallback - используем старую функцию
                if (typeof processBlockDrop === 'function') {
                    processBlockDrop(draggedBlock);
                }
            }
            
            } finally {
                draggedBlock = null;
                window.draggedBlock = null;
                dragSnapshot = null;
                resumeCompactRowsAfterDrag(true);
            }
        }
    }
    
    // Drag cancellation helpers.
    function createDragSnapshot(block) {
        if (!block) {
            return null;
        }
        return {
            block: block,
            left: block.style.left || '',
            top: block.style.top || '',
            opacity: block.style.opacity || '',
            day: block.getAttribute('data-day'),
            colIndex: block.getAttribute('data-col-index'),
            startRow: block.getAttribute('data-start-row'),
            className: block.className
        };
    }

    function restoreDragSnapshot(snapshot) {
        if (!snapshot || !snapshot.block) {
            return;
        }
        snapshot.block.style.left = snapshot.left;
        snapshot.block.style.top = snapshot.top;
        snapshot.block.style.opacity = snapshot.opacity || '1';
        restoreAttribute(snapshot.block, 'data-day', snapshot.day);
        restoreAttribute(snapshot.block, 'data-col-index', snapshot.colIndex);
        restoreAttribute(snapshot.block, 'data-start-row', snapshot.startRow);
        if (snapshot.className) {
            snapshot.block.className = snapshot.className;
        }
    }

    function restoreAttribute(element, name, value) {
        if (value === null || typeof value === 'undefined') {
            element.removeAttribute(name);
            return;
        }
        element.setAttribute(name, value);
    }

    // Публичный API
    return {
        init: function() {
            initializeBlockEvents();
        },
        
        getDraggedBlock: function() {
            return draggedBlock;
        },
        
        isDragging: function() {
            return draggedBlock !== null;
        },
        
        setPreventDrag: function(value) {
            preventDrag = value;
        }
    };
})();

// Делаем сервис глобально доступным
window.DragDropService = DragDropService;
