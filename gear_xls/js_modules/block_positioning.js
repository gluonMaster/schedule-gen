// Модуль для создания и позиционирования новых блоков занятий

function refreshCompactRowsAfterBlockPositioning() {
    if (window.ScheduleCompactRows && typeof window.ScheduleCompactRows.refresh === 'function') {
        window.ScheduleCompactRows.refresh();
    } else if (typeof window.updateActivityPositions === 'function') {
        window.updateActivityPositions();
    }
}

function reapplyLessonTypeFilterAfterBlockPositioning() {
    if (typeof reapplyLessonTypeFilter === 'function') {
        reapplyLessonTypeFilter();
        return;
    }
    refreshCompactRowsAfterBlockPositioning();
}

// Функция для создания и добавления нового блока в расписание
function createNewBlock(building, day, colIndex, subject, teacher, students, room, timeRange, backgroundColor) {
    console.log(`Создание нового блока в здании: ${building}, день: ${day}, колонка: ${colIndex}`);
    
    // Находим контейнер расписания для указанного здания
    var container = BuildingService.findScheduleContainerForBuilding(building);
    if (!container) {
        console.error(`Не найден контейнер расписания для здания ${building}`);
        // Пробуем использовать первый контейнер как запасной вариант
        container = document.querySelector('.schedule-container');
        if (!container) {
            alert(`Ошибка: не найден контейнер расписания для здания ${building}`);
            return;
        }
    }
    
    // Создаем новый блок
    var newBlock = document.createElement('div');
    newBlock.className = `activity-block activity-day-${day}`;
    newBlock.setAttribute('data-day', day);
    newBlock.setAttribute('data-col-index', colIndex);
    newBlock.setAttribute('data-building', building);
    
    // Применяем выбранный цвет фона
    newBlock.style.backgroundColor = backgroundColor || '#FFFBD3'; // Желтый по умолчанию, если цвет не указан
    
    // Определяем и устанавливаем контрастный цвет текста
    if (typeof getContrastTextColor === 'function') {
        newBlock.style.color = getContrastTextColor(newBlock.style.backgroundColor);
    }
    
    // ВАЖНО: устанавливаем фиксированную ширину 100px, такую же как у оригинальных блоков
    newBlock.style.width = '100px';
    
    // Устанавливаем содержимое блока
    newBlock.innerHTML = `<strong>${subject}</strong><br>${teacher}<br>${students}<br>${room}<br>${timeRange}`;
    
    // Добавляем блок в контейнер
    container.appendChild(newBlock);
    
    // Устанавливаем начальные позиции блока
    positionNewBlock(newBlock, timeRange);
    
    // Добавляем обработчики событий для нового блока
    addEventListenersToBlock(newBlock);
}

// Функция для позиционирования нового блока
function positionNewBlock(block, timeRange) {
    var times = timeRange.match(/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/);
    var syncedBlockContent = false;
    if (!times) {
        console.error('positionNewBlock: bad time format:', timeRange);
        return;
    }
    var startMinutes = parseInt(times[1]) * 60 + parseInt(times[2]);
    var endMinutes   = parseInt(times[3]) * 60 + parseInt(times[4]);

    var gStart    = (typeof gridStart !== 'undefined') ? gridStart : 9 * 60;
    var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;

    var startRow = Math.floor((startMinutes - gStart) / tInterval);
    var rowSpan  = Math.floor((endMinutes - startMinutes) / tInterval);

    block.setAttribute('data-start-row', startRow);
    block.setAttribute('data-row-span',  rowSpan);

    // Remove stale legacy attributes if present (e.g. from old HTML files)
    block.removeAttribute('data-original-top');
    block.removeAttribute('data-compensated');

    // Sync block text so room name matches column header
    if (typeof syncBlockContent === 'function') {
        syncBlockContent(block);
        syncedBlockContent = true;
    }

    if (!syncedBlockContent || typeof reapplyLessonTypeFilter !== 'function') {
        reapplyLessonTypeFilterAfterBlockPositioning();
    }
}

// Экспортируем функции для использования в других модулях
window.createNewBlock = createNewBlock;
window.positionNewBlock = positionNewBlock;
