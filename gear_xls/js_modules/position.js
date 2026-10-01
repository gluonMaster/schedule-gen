// Модуль для позиционирования элементов расписания

// Убеждаемся, что daysOrder определена
if (typeof window.daysOrder === 'undefined') {
    window.daysOrder = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
}

// Returns start row derived from time text in block content, or null on failure.
// Uses the LAST match to avoid false positives from subject/teacher text that looks like a time.
function deriveStartRowFromBlock(block, table) {
    var text = block.textContent || '';
    var all = text.match(/\d{1,2}:\d{2}\s*[-\u2013]\s*\d{1,2}:\d{2}/g);
    if (!all) { console.warn('deriveStartRowFromBlock: no time found in block text'); return null; }
    var last = all[all.length - 1].match(/^(\d{1,2}):(\d{2})/);
    if (!last) { return null; }
    var startMinutes = parseInt(last[1], 10) * 60 + parseInt(last[2], 10);
    var gStart = (typeof gridStart !== 'undefined') ? gridStart : 9 * 60;
    var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;
    var row = Math.floor((startMinutes - gStart) / tInterval);
    if (isNaN(row) || row < 0) { console.warn('deriveStartRowFromBlock: invalid row', row); return null; }
    return String(row);
}

// Returns row span derived from time text in block content, or null on failure.
// Uses the LAST match to avoid false positives from subject/teacher text that looks like a time.
function deriveRowSpanFromBlock(block) {
    var text = block.textContent || '';
    var all = text.match(/(\d{1,2}):(\d{2})\s*[-\u2013]\s*(\d{1,2}):(\d{2})/g);
    if (!all) { console.warn('deriveRowSpanFromBlock: no time range found in block text'); return null; }
    var m = all[all.length - 1].match(/^(\d{1,2}):(\d{2})\s*[-\u2013]\s*(\d{1,2}):(\d{2})$/);
    if (!m) { return null; }
    var startMin = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    var endMin   = parseInt(m[3], 10) * 60 + parseInt(m[4], 10);
    var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;
    var span = Math.floor((endMin - startMin) / tInterval);
    if (isNaN(span) || span <= 0) { console.warn('deriveRowSpanFromBlock: invalid span', span); return null; }
    return String(span);
}

// Модифицированная функция обновления позиций activity-block
function updateActivityPositions() {
    document.querySelectorAll('.schedule-container').forEach(function(container) {
        var table = container.querySelector('.schedule-grid');
        if (!table) return;

        var containerRect = container.getBoundingClientRect();
        var containerStyle = window.getComputedStyle(container);
        var borderLeft = parseFloat(containerStyle.borderLeftWidth) || 0;
        var borderTop = parseFloat(containerStyle.borderTopWidth) || 0;

        // Find the maximum data-row value present in this table (for boundary clamping)
        var allDataCells = table.querySelectorAll('td[data-row]');
        var maxRow = 0;
        allDataCells.forEach(function(cell) {
            var r = parseInt(cell.getAttribute('data-row'), 10);
            if (!isNaN(r) && r > maxRow) maxRow = r;
        });

        container.querySelectorAll('.activity-block').forEach(function(block) {
            var day = block.getAttribute('data-day');
            var col = block.getAttribute('data-col-index');
            var startRow = block.getAttribute('data-start-row');
            var rowSpan = block.getAttribute('data-row-span');

            // Backward-compat fallback: if data-start-row is missing, derive from time text
            if (startRow === null || startRow === '') {
                startRow = deriveStartRowFromBlock(block, table);
                if (startRow === null) return; // cannot position
                block.setAttribute('data-start-row', startRow);
            }
            if (rowSpan === null || rowSpan === '') {
                rowSpan = deriveRowSpanFromBlock(block);
                if (rowSpan === null) return;
                block.setAttribute('data-row-span', rowSpan);
            }

            startRow = parseInt(startRow, 10);
            rowSpan = parseInt(rowSpan, 10);
            col = parseInt(col, 10);

            // Find anchor cell
            var startCell = table.querySelector(
                'td.day-' + day + '[data-col="' + col + '"][data-row="' + startRow + '"]'
            );
            if (!startCell) {
                console.warn('updateActivityPositions: anchor cell not found for block', day, col, startRow);
                return;
            }

            var startCellRect = startCell.getBoundingClientRect();

            // Find end boundary cell (the cell AT startRow + rowSpan)
            var endRow = startRow + rowSpan;
            var endCell = table.querySelector(
                'td.day-' + day + '[data-col="' + col + '"][data-row="' + endRow + '"]'
            );
            var endCellTop;
            if (endCell) {
                endCellTop = endCell.getBoundingClientRect().top;
            } else {
                // Block extends to or past the last row - use bottom of last available cell
                var lastCell = table.querySelector(
                    'td.day-' + day + '[data-col="' + col + '"][data-row="' + maxRow + '"]'
                );
                endCellTop = lastCell
                    ? lastCell.getBoundingClientRect().bottom
                    : startCellRect.bottom;
            }

            // Convert viewport-relative coordinates to container-relative (position:absolute origin)
            var left = startCellRect.left - containerRect.left - borderLeft + container.scrollLeft;
            var top = startCellRect.top - containerRect.top - borderTop + container.scrollTop;
            var width = startCellRect.width;
            var height = endCellTop - startCellRect.top;

            block.style.left = left + 'px';
            block.style.top = top + 'px';
            block.style.width = width + 'px';
            block.style.height = height + 'px';
        });
    });
}

// Делаем функцию глобально доступной
window.updateActivityPositions = updateActivityPositions;

// Функция для обновления позиции и размера блока при изменении времени
function updateBlockPosition(block, newTimeRange) {
    var times = newTimeRange.match(/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/);
    if (!times) {
        console.error('updateBlockPosition: bad time format:', newTimeRange);
        return;
    }
    var startMinutes = parseInt(times[1], 10) * 60 + parseInt(times[2], 10);
    var endMinutes = parseInt(times[3], 10) * 60 + parseInt(times[4], 10);
    if (endMinutes <= startMinutes) {
        console.error('updateBlockPosition: end time must be after start time:', newTimeRange);
        return;
    }

    var gStart = (typeof gridStart !== 'undefined') ? gridStart : 9 * 60;
    var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;

    var newStartRow = Math.floor((startMinutes - gStart) / tInterval);
    var newRowSpan = Math.floor((endMinutes - startMinutes) / tInterval);
    if (newStartRow < 0 || newRowSpan <= 0) {
        console.error('updateBlockPosition: time range is outside the schedule grid:', newTimeRange);
        return;
    }

    block.setAttribute('data-start-row', newStartRow);
    block.setAttribute('data-row-span', newRowSpan);
    block.setAttribute('data-start-time', times[1] + ':' + times[2]);
    block.setAttribute('data-end-time', times[3] + ':' + times[4]);

    updateActivityPositions();
}

window.updateBlockPosition = updateBlockPosition;

// Функция для обновления колонки блока при изменении кабинета
function updateBlockColumn(block, newRoom) {
    var container = block.parentElement;
    var table = container.querySelector('.schedule-grid');
    var day = block.getAttribute('data-day');
    
    if (!day) {
        console.error('Не найден атрибут data-day у блока');
        return;
    }
    
    // Получаем все заголовки колонок текущего дня
    var dayHeaders = table.querySelectorAll('th.day-' + day);
    var newColIndex = -1;
    
    console.log('Поиск кабинета:', newRoom, 'в заголовках дня:', day);
    console.log('Количество найденных заголовков:', dayHeaders.length);
    
    // Ищем заголовок с указанным кабинетом
    for (var i = 0; i < dayHeaders.length; i++) {
        var headerText = dayHeaders[i].innerText || dayHeaders[i].textContent;
        console.log('Заголовок ' + i + ':', headerText);
        
        if (headerText.includes(newRoom)) {
            newColIndex = i;
            console.log('Найдено соответствие в колонке:', i);
            break;
        }
    }
    
    // Если не нашли точное соответствие, проверяем частичное соответствие
    if (newColIndex === -1) {
        for (var i = 0; i < dayHeaders.length; i++) {
            var headerText = dayHeaders[i].innerText || dayHeaders[i].textContent;
            // Удаляем название дня из заголовка и проверяем, что осталось
            var roomPart = headerText.replace(day, '').trim();
            console.log('Часть кабинета в заголовке ' + i + ':', roomPart);
            
            if (roomPart === newRoom) {
                newColIndex = i;
                console.log('Найдено частичное соответствие в колонке:', i);
                break;
            }
        }
    }
    
    // Если нашли колонку для нового кабинета
    if (newColIndex !== -1) {
        var currentColIndex = parseInt(block.getAttribute('data-col-index'));
        if (newColIndex !== currentColIndex) {
            console.log('Обновление колонки с', currentColIndex, 'на', newColIndex);
            
            // Обновляем атрибут колонки
            block.setAttribute('data-col-index', newColIndex);
            
            // Вызываем обновление позиции блока
            updateActivityPositions();
        } else {
            console.log('Колонка не изменилась');
        }
    } else {
        console.warn('Не найдена колонка для кабинета:', newRoom);
    }
}
