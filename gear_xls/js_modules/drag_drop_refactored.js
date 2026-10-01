// Модуль для функционала перетаскивания блоков (drag & drop)
// РЕФАКТОРЕД: Теперь использует отдельные сервисы для управления drag&drop функциональностью

// Главная функция инициализации перетаскивания блоков
function initDragAndDrop() {
    // Инициализируем новый DragDropService, если он доступен
    if (typeof DragDropService !== 'undefined') {
        DragDropService.init();
        console.log('DragDropService initialized successfully');
    } else {
        console.warn('DragDropService not available, using legacy drag&drop implementation');
        initLegacyDragAndDrop();
    }
}

// Функция для инициализации старой версии drag&drop (для обратной совместимости)
function initLegacyDragAndDrop() {
    // Флаг для предотвращения drag при двойном клике
    var preventDrag = false;
    var offsetX = 0, offsetY = 0;
    var compactRowsDragPaused = false;

    function pauseCompactRowsForLegacyDrag() {
        if (
            !compactRowsDragPaused &&
            window.ScheduleCompactRows &&
            typeof window.ScheduleCompactRows.pauseForInteraction === 'function'
        ) {
            window.ScheduleCompactRows.pauseForInteraction('drag');
            compactRowsDragPaused = true;
        }
    }

    function resumeCompactRowsAfterLegacyDrag(refresh) {
        if (
            compactRowsDragPaused &&
            window.ScheduleCompactRows &&
            typeof window.ScheduleCompactRows.resumeAfterInteraction === 'function'
        ) {
            window.ScheduleCompactRows.resumeAfterInteraction('drag', { refresh: !!refresh });
        }
        compactRowsDragPaused = false;
    }
    
    // Функция для привязки к сетке с учетом точных размеров и границ
    function snapToGrid(left, top) {
        // Если доступен новый GridSnapService, используем его
        if (typeof GridSnapService !== 'undefined' && window.draggedBlock) {
            return GridSnapService.snapToGrid(left, top, window.draggedBlock);
        }
        
        // Fallback к старой реализации
        return legacySnapToGrid(left, top);
    }
    
    // Старая реализация привязки к сетке (сохранена для совместимости)
    function legacySnapToGrid(left, top) {
        var container = window.draggedBlock.parentElement;
        var containerRect = container.getBoundingClientRect();
        var containerStyle = window.getComputedStyle(container);
        var padLeft = parseFloat(containerStyle.paddingLeft) || 0;
        var padTop = parseFloat(containerStyle.paddingTop) || 0;
        
        // Получаем таблицу и ее ячейки
        var table = container.querySelector('.schedule-grid');
        var timeCell = table.querySelector('th.time-cell');
        var timeCellWidth = timeCell ? timeCell.getBoundingClientRect().width : measuredTimeColWidth;
        var headerHeight = table.querySelector('thead').getBoundingClientRect().height;
        
        // Находим все ячейки расписания (кроме ячеек времени)
        var dayCells = Array.from(table.querySelectorAll('td:not(.time-cell)'));
        
        // Только если есть ячейки в таблице
        if (dayCells.length > 0) {
            // Группируем ячейки по дням
            var cellsByDay = {};
            dayCells.forEach(function(cell) {
                var day = cell.className.match(/day-(\w+)/);
                if (day && day[1]) {
                    if (!cellsByDay[day[1]]) {
                        cellsByDay[day[1]] = [];
                    }
                    cellsByDay[day[1]].push(cell);
                }
            });
            
            // Рассчитываем абсолютную позицию (относительно окна)
            var absoluteLeft = left + containerRect.left - container.scrollLeft;
            var absoluteTop = top + containerRect.top - container.scrollTop;
            
            // Находим ближайшую ячейку
            var closestCell = null;
            var minDistance = Infinity;
            
            for (var day in cellsByDay) {
                cellsByDay[day].forEach(function(cell) {
                    
                    // Проверяем только видимые ячейки
                    if (window.getComputedStyle(cell).display !== 'none') {
                        var cellRect = cell.getBoundingClientRect();
                        var cellCenterX = cellRect.left + cellRect.width / 2;
                        var cellCenterY = cellRect.top + cellRect.height / 2;
                        
                        // Используем взвешенное расстояние, чтобы горизонтальное расстояние 
                        // было более значимым для привязки
                        var distanceX = Math.abs(absoluteLeft - cellCenterX);
                        var distanceY = Math.abs(absoluteTop - cellCenterY);
                        var distance = distanceX * 2 + distanceY;
                        
                        if (distance < minDistance) {
                            minDistance = distance;
                            closestCell = cell;
                        }
                    }
                });
            }
            
            // Если нашли ближайшую ячейку
            if (closestCell) {
                var closestCellRect = closestCell.getBoundingClientRect();
                var day = closestCell.className.match(/day-(\w+)/)[1];
                var colIndex = parseInt(closestCell.getAttribute('data-col')) || 0;
                
                // Определяем ряд
                var rowIndex = parseInt(closestCell.getAttribute('data-row')) || 0;
                
                // Определяем точные координаты для привязки
                var dayHeaders = table.querySelectorAll('th.day-' + day);
                var headerLeftPosition = 0;
                
                if (dayHeaders.length > 0) {
                    // Если у нас есть заголовки дня, используем их для определения левой позиции
                    var dayHeaderRect = dayHeaders[colIndex].getBoundingClientRect();
                    headerLeftPosition = dayHeaderRect.left - containerRect.left + container.scrollLeft;
                } else {
                    // Запасной вариант - используем позицию ячейки
                    headerLeftPosition = closestCellRect.left - containerRect.left + container.scrollLeft;
                }
                
                // Устанавливаем точное позиционирование
                var snappedLeft = headerLeftPosition;
                var snappedTop = headerHeight + padTop + (rowIndex * (gridCellHeight + borderWidth));
                
                // ВАЖНОЕ ИЗМЕНЕНИЕ: НЕ применяем компенсацию здесь, 
                // вместо этого сохраняем исходное положение без компенсации
                // Компенсация будет применена позже в updateActivityPositions
                
                // Обновляем data-аттрибуты блока
                window.draggedBlock.setAttribute('data-day', day);
                window.draggedBlock.setAttribute('data-col-index', colIndex);
                window.draggedBlock.setAttribute('data-start-row', rowIndex);
                window.draggedBlock.removeAttribute('data-original-top');
                window.draggedBlock.removeAttribute('data-compensated');
                
                // Обновляем класс для соответствия новому дню
                window.draggedBlock.className = window.draggedBlock.className.replace(/activity-day-\w+/, 'activity-day-' + day);
                
                return { left: snappedLeft, top: snappedTop };
            }
        }
        
        // Если не нашли подходящую ячейку или нет видимых ячеек,
        // используем традиционный подход с исправлением точности
        
        // Получаем смещение внутри контейнера для определения дня
        var offsetWithinContainer = left - timeCellWidth - padLeft;
        if (offsetWithinContainer < 0) offsetWithinContainer = 0;
        
        // Собираем интервалы ширины по дням
        var dayOffsets = [];
        var cumWidth = 0;
        daysOrder.forEach(function(d) {
            var dayWidth = 0;
            var headers = table.querySelectorAll('th.day-' + d);
            headers.forEach(function(h) {
                if (window.getComputedStyle(h).display !== 'none') {
                    dayWidth += h.getBoundingClientRect().width;
                }
            });
            var startPx = cumWidth;
            var endPx = cumWidth + dayWidth;
            dayOffsets.push({ day: d, startPx: startPx, endPx: endPx });
            cumWidth = endPx;
        });
        
        // Определяем день по смещению
        var chosenDay = dayOffsets.find(function(obj) {
            return offsetWithinContainer >= obj.startPx && offsetWithinContainer < obj.endPx;
        });
        if (!chosenDay && dayOffsets.length > 0) {
            chosenDay = dayOffsets[dayOffsets.length - 1]; 
        } else if (!chosenDay) {
            chosenDay = { day: daysOrder[0], startPx: 0, endPx: dayCellWidth };
        }
        
        // Вычисляем индекс столбца в рамках выбранного дня
        var offsetWithinDay = offsetWithinContainer - chosenDay.startPx;
        var newColIndex = Math.floor(offsetWithinDay / dayCellWidth);
        
        // Получаем только ВИДИМЫЕ заголовки колонок выбранного дня
        var visibleHeaders = Array.from(table.querySelectorAll('th.day-' + chosenDay.day))
            .filter(function(header) {
                return window.getComputedStyle(header).display !== 'none';
            });
        
        // Проверяем границы индекса
        if (newColIndex < 0) {
            newColIndex = 0;
        }
        if (visibleHeaders.length > 0 && newColIndex >= visibleHeaders.length) {
            newColIndex = visibleHeaders.length - 1;
        }
        
        // Рассчитываем левую позицию с учетом видимых колонок
        var leftOffset = timeCellWidth + padLeft;
        
        // Прибавляем ширину всех предыдущих дней
        for (var i = 0; i < daysOrder.length; i++) {
            var d = daysOrder[i];
            if (d === chosenDay.day) break;
            var headers = table.querySelectorAll('th.day-' + d);
            headers.forEach(function(h) {
                if (window.getComputedStyle(h).display !== 'none') {
                    leftOffset += h.getBoundingClientRect().width;
                }
            });
        }
        
        // Прибавляем ширину нужного количества колонок текущего дня
        var currentDayHeaders = visibleHeaders;
        for (var j = 0; j < newColIndex; j++) {
            leftOffset += currentDayHeaders[j].getBoundingClientRect().width;
        }
        
        var snappedLeft = leftOffset;
        
        // Скорректированная вертикальная позиция
        var rowIndex = Math.round((top - headerHeight - padTop) / (gridCellHeight + borderWidth));
        var snappedTop = headerHeight + padTop + (rowIndex * (gridCellHeight + borderWidth));
        
        // ВАЖНОЕ ИЗМЕНЕНИЕ: НЕ применяем компенсацию здесь,
        // а сохраняем исходное положение без компенсации
        
        // Обновляем атрибуты блока
        window.draggedBlock.setAttribute('data-day', chosenDay.day);
        window.draggedBlock.setAttribute('data-col-index', newColIndex);
        window.draggedBlock.setAttribute('data-start-row', rowIndex);
        window.draggedBlock.removeAttribute('data-original-top');
        window.draggedBlock.removeAttribute('data-compensated');
        
        // Обновляем класс дня
        window.draggedBlock.className = window.draggedBlock.className.replace(/activity-day-\w+/, 'activity-day-' + chosenDay.day);
        
        return { left: snappedLeft, top: snappedTop };
    }
    
    // Навешиваем обработчики на activity-block (старая версия для совместимости)
    document.querySelectorAll('.activity-block').forEach(function(block) {
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
                    window.draggedBlock = block;
                    pauseCompactRowsForLegacyDrag();
                    var rect = block.getBoundingClientRect();
                    offsetX = e.clientX - rect.left;
                    offsetY = e.clientY - rect.top;
                    block.style.opacity = 0.7;
                }
            }, 200); // 200 мс - стандартное время для определения двойного клика
            
            e.preventDefault(); // Предотвращаем выделение текста при перетаскивании
        });
        
        // Обработчик двойного клика
        block.addEventListener('dblclick', function(e) {
            // Очищаем таймаут и сбрасываем флаг
            if (clickTimeout) {
                clearTimeout(clickTimeout);
            }
            isPotentialDoubleClick = false;
            
            // Устанавливаем флаг предотвращения drag на короткое время
            preventDrag = true;
            setTimeout(() => { preventDrag = false; }, 500);
            
            // Если был начат процесс перетаскивания, отменяем его
            if (window.draggedBlock === block) {
                window.draggedBlock.style.opacity = 1;
                window.draggedBlock = null;
                resumeCompactRowsAfterLegacyDrag(true);
            }
            
            // Предотвращаем запуск перетаскивания
            e.stopPropagation();
            e.preventDefault();
            
            // Сохраняем позицию блока перед редактированием
            var origLeft = block.style.left;
            var origTop = block.style.top;
            
            // Открываем диалог редактирования только если не открыт
            if (!window.editDialogOpen) {
                openEditDialog(block, origLeft, origTop);
            }
        });
    });

    document.addEventListener('mousemove', function(e) {
        if (window.draggedBlock && !window.editDialogOpen && !preventDrag) {
            var container = window.draggedBlock.parentElement;
            var rect = container.getBoundingClientRect();
            var scrollX = container.scrollLeft;
            var scrollY = container.scrollTop;
            var newLeft = e.clientX - rect.left - offsetX + scrollX;
            var newTop  = e.clientY - rect.top  - offsetY + scrollY;
            var snapped = snapToGrid(newLeft, newTop);
            window.draggedBlock.style.left = snapped.left + 'px';
            window.draggedBlock.style.top = snapped.top + 'px';
        }
    });

    document.addEventListener('mouseup', function(e) {
        if (window.draggedBlock && !window.editDialogOpen) {
            try {
            window.draggedBlock.style.opacity = 1;
            
            // Используем новый BlockDropService если доступен, иначе старую функцию  
            if (typeof BlockDropService !== 'undefined') {
                BlockDropService.processBlockDrop(window.draggedBlock);
            } else {
                processBlockDrop(window.draggedBlock);
            }
            
            } finally {
                window.draggedBlock = null;
                resumeCompactRowsAfterLegacyDrag(true);
            }
        }
    });
}

// === СТАРЫЕ ФУНКЦИИ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ===

// Обрабатывает перемещение блока после отпускания
function processBlockDrop(block) {
    // Если доступен новый BlockDropService, используем его
    if (typeof BlockDropService !== 'undefined') {
        BlockDropService.processBlockDrop(block);
        return;
    }
    
    // Fallback к старой реализации
    legacyProcessBlockDrop(block);
}

// Старая реализация processBlockDrop для совместимости
function legacyProcessBlockDrop(block) {
    var container = block.parentElement;
    var table = container.querySelector('.schedule-grid');
    var day = block.getAttribute('data-day');
    
    if (!day) {
        console.error('Атрибут data-day не найден в блоке');
        return;
    }
    
    // Получаем левую позицию блока
    var blockLeft = parseFloat(block.style.left) || 0;
    
    // Находим все заголовки для этого дня
    var dayHeaders = Array.from(table.querySelectorAll('th.day-' + day));
    
    // Фильтруем только видимые заголовки
    var visibleHeaders = dayHeaders.filter(function(header) {
        return window.getComputedStyle(header).display !== 'none';
    });
    
    // Найдем ближайший заголовок по горизонтали
    var closestHeader = null;
    var minDistance = Infinity;
    var bestColIndex = -1;
    
    for (var i = 0; i < visibleHeaders.length; i++) {
        var headerRect = visibleHeaders[i].getBoundingClientRect();
        var headerCenter = headerRect.left + headerRect.width / 2;
        
        // Получаем координаты центра блока
        var blockRect = block.getBoundingClientRect();
        var blockCenter = blockRect.left + blockRect.width / 2;
        
        var distance = Math.abs(blockCenter - headerCenter);
        if (distance < minDistance) {
            minDistance = distance;
            closestHeader = visibleHeaders[i];
            bestColIndex = i;
        }
    }
    
    // Если нашли подходящий заголовок, используем его индекс
    if (closestHeader && bestColIndex !== -1) {
        console.log('Найден ближайший заголовок:', closestHeader, 'индекс:', bestColIndex);
        
        // Обновляем атрибуты блока
        updateBlockDropAttributes(block, day, bestColIndex, table);
        
        // Обновляем позиции всех блоков
        updateActivityPositions();
    } else {
        console.warn('Не удалось найти подходящий заголовок для блока');
        // Используем существующий метод как запасной вариант
        fallbackProcessBlockDrop(block);
    }
}

function findClosestRowByTopInRefactored(block, day, colIndex, table) {
    var blockTop = parseFloat(block.style.top) || 0;
    var container = block.parentElement;
    var containerRect = container.getBoundingClientRect();
    var borderTop = parseFloat(window.getComputedStyle(container).borderTopWidth) || 0;
    var blockTopViewport = blockTop + containerRect.top + borderTop - container.scrollTop;

    var cells = Array.from(table.querySelectorAll('td.day-' + day + '[data-col="' + colIndex + '"]'));
    var closestRow = 0;
    var minDist = Infinity;
    cells.forEach(function(cell) {
        var cellRect = cell.getBoundingClientRect();
        var dist = Math.abs(cellRect.top - blockTopViewport);
        if (dist < minDist) {
            minDist = dist;
            closestRow = parseInt(cell.getAttribute('data-row')) || 0;
        }
    });
    return closestRow;
}

// Вспомогательная функция для обновления атрибутов блока
function updateBlockDropAttributes(block, day, colIndex, table) {
    // Determine start row: prefer the value already set by snapToClosestCell during drag
    var startRow = block.getAttribute('data-start-row');
    if (startRow === null || startRow === '') {
        // Fallback: find closest row by vertical proximity (same logic as BlockDropService)
        startRow = String(findClosestRowByTopInRefactored(block, day, colIndex, table));
    }

    block.setAttribute('data-col-index', colIndex);
    block.setAttribute('data-day', day);
    block.setAttribute('data-start-row', startRow);
    // data-row-span unchanged

    block.removeAttribute('data-original-top');
    block.removeAttribute('data-compensated');

    block.className = block.className.replace(/activity-day-\w+/, 'activity-day-' + day);
}

// Обрабатывает перемещение блока после отпускания
// Обновленная функция fallbackProcessBlockDrop
function fallbackProcessBlockDrop(block) {
    // --- 1. Основные вычисления координат и смещений ---
    var container = block.parentElement;
    var containerRect = container.getBoundingClientRect();
    var containerStyle = window.getComputedStyle(container);
    var containerLeftPadding = parseFloat(containerStyle.paddingLeft) || 0;
    
    // Текущее абсолютное left перетянутого блока:
    var absoluteLeft = parseFloat(block.style.left) || 0;
    
    // Смещение внутри контейнера (без учёта колонки времени и отступов)
    var offsetWithinContainer = absoluteLeft 
    - containerLeftPadding 
    - measuredTimeColWidth;
    if (offsetWithinContainer < 0) offsetWithinContainer = 0;
    
    // --- 2. Собираем интервалы ширины по дням ---
    var table = container.querySelector('.schedule-grid');
    var dayOffsets = [];
    var cumWidth = 0;
    
    daysOrder.forEach(function(d) {
        var dayWidth = 0;
        var headers = table.querySelectorAll('th.day-' + d);
        headers.forEach(function(h) {
            if (window.getComputedStyle(h).display !== 'none') {
                dayWidth += h.getBoundingClientRect().width;
            }
        });
        var startPx = cumWidth;
        var endPx = cumWidth + dayWidth;
        dayOffsets.push({ day: d, startPx: startPx, endPx: endPx });
        cumWidth = endPx;
    });
    
    // --- 3. Определяем день ---
    var chosenDay = dayOffsets.find(function(obj) {
        return offsetWithinContainer >= obj.startPx && offsetWithinContainer < obj.endPx;
    });
    if (!chosenDay && dayOffsets.length > 0) {
        chosenDay = dayOffsets[dayOffsets.length - 1]; 
    } else if (!chosenDay) {
        chosenDay = { day: daysOrder[0], startPx: 0, endPx: dayCellWidth };
    }
    
    // --- 4. Вычисляем индекс столбца в рамках выбранного дня ---
    var offsetWithinDay = offsetWithinContainer - chosenDay.startPx;
    var newColIndex = Math.floor(offsetWithinDay / dayCellWidth);
    
    // Получаем только ВИДИМЫЕ заголовки колонок выбранного дня
    var visibleHeaders = Array.from(table.querySelectorAll('th.day-' + chosenDay.day))
        .filter(function(header) {
            return window.getComputedStyle(header).display !== 'none';
        });
    
    // Проверяем границы индекса
    if (newColIndex < 0) {
        newColIndex = 0;
    }
    if (visibleHeaders.length > 0 && newColIndex >= visibleHeaders.length) {
        newColIndex = visibleHeaders.length - 1;
    }
    
    // --- 5. Записываем новые data-атрибуты в сам блок ---
    updateBlockDropAttributes(block, chosenDay.day, newColIndex, table);
    
    // Вызываем обновление позиций блоков для корректного позиционирования
    updateActivityPositions();
}
