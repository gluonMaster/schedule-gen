// Модуль для функционала перетаскивания блоков (drag & drop)

// Функция инициализации перетаскивания блоков
function initDragAndDrop() {
    // Флаг для предотвращения drag при двойном клике
    var preventDrag = false;
    var offsetX = 0, offsetY = 0;
    
    // Функция для привязки к сетке с учетом точных размеров и границ
    function snapToGrid(left, top) {
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
                    var cellRect = cell.getBoundingClientRect();
                    
                    // Проверяем только видимые ячейки
                    if (window.getComputedStyle(cell).display !== 'none') {
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
                window.draggedBlock.setAttribute('data-compensated', 'false'); // Важно: устанавливаем false!
                
                // Сохраняем исходное положение блока без компенсации
                window.draggedBlock.setAttribute('data-original-top', snappedTop);
                
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
        window.draggedBlock.setAttribute('data-compensated', 'false'); // Устанавливаем false!
        
        // Сохраняем оригинальную позицию до компенсации
        window.draggedBlock.setAttribute('data-original-top', snappedTop);
        
        // Обновляем класс дня
        window.draggedBlock.className = window.draggedBlock.className.replace(/activity-day-\w+/, 'activity-day-' + chosenDay.day);
        
        return { left: snappedLeft, top: snappedTop };
    }
    
    // Навешиваем обработчики на activity-block
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
            window.draggedBlock.style.opacity = 1;
            processBlockDrop(window.draggedBlock);
            window.draggedBlock = null;
        }
    });
}

function processBlockDrop(block) {
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
        block.setAttribute('data-col-index', bestColIndex);
        block.setAttribute('data-day', day);
        
        // КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: сохраняем новое исходное положение блока
        // после перетаскивания (но без учета компенсации)
        var headerHeight = table.querySelector('thead').getBoundingClientRect().height;
        var currentTop = parseFloat(block.style.top);
        
        // Определяем номер строки для текущей позиции
        var rowIndex = Math.floor((currentTop - headerHeight) / (gridCellHeight + borderWidth));
        
        // Вычисляем текущую компенсацию, которая была применена
        var factor = window.compensationFactor || 0.4;
        var exponent = window.compensationExponent || 1.02;
        var compensation = Math.pow(rowIndex, exponent) * factor;
        
        // Определяем истинное положение без компенсации для новой позиции
        var originalTopForNewPosition = currentTop + compensation;
        
        // Обновляем data-original-top с новым значением
        block.setAttribute('data-original-top', originalTopForNewPosition);
        
        // Помечаем блок как требующий новой компенсации
        block.setAttribute('data-compensated', 'false');
        
        // Обновляем класс для соответствия дню
        block.className = block.className.replace(/activity-day-\w+/, 'activity-day-' + day);
        
        // Обновляем позиции всех блоков
        updateActivityPositions();
    } else {
        console.warn('Не удалось найти подходящий заголовок для блока');
        // Используем существующий метод как запасной вариант
        fallbackProcessBlockDrop(block);
    }
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
    block.setAttribute('data-day', chosenDay.day);
    block.setAttribute('data-col-index', newColIndex);
    
    // КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: сохраняем новое исходное положение блока
    var headerHeight = table.querySelector('thead').getBoundingClientRect().height;
    var currentTop = parseFloat(block.style.top);
    
    // Определяем номер строки для текущей позиции
    var rowIndex = Math.floor((currentTop - headerHeight) / (gridCellHeight + borderWidth));
    
    // Вычисляем текущую компенсацию, которая была применена
    var factor = window.compensationFactor || 0.4;
    var exponent = window.compensationExponent || 1.02;
    var compensation = Math.pow(rowIndex, exponent) * factor;
    
    // Определяем истинное положение без компенсации для новой позиции
    var originalTopForNewPosition = currentTop + compensation;
    
    // Обновляем data-original-top с новым значением
    block.setAttribute('data-original-top', originalTopForNewPosition);
    
    // Помечаем блок как требующий новой компенсации
    block.setAttribute('data-compensated', 'false');
    
    // Обновляем класс для соответствия новому дню
    block.className = block.className.replace(/activity-day-\w+/, 'activity-day-' + chosenDay.day);
    
    // Вызываем обновление позиций блоков для корректного позиционирования
    updateActivityPositions();
}