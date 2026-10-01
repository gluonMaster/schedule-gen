// Модуль с вспомогательными функциями для блоков расписания

// Функция для форматирования времени в формат ЧЧ:ММ
function formatTimeToHHMM(hours, minutes) {
    return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
}

// Функция для парсинга времени из формата ЧЧ:ММ-ЧЧ:ММ
function parseTimeRange(timeRange) {
    var times = timeRange.match(/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/);
    if (!times) {
        return null;
    }
    
    return {
        startHour: parseInt(times[1]),
        startMinute: parseInt(times[2]),
        endHour: parseInt(times[3]),
        endMinute: parseInt(times[4]),
        startMinutes: parseInt(times[1]) * 60 + parseInt(times[2]),
        endMinutes: parseInt(times[3]) * 60 + parseInt(times[4])
    };
}

// Функция для конвертации времени в минуты
function timeToMinutes(hour, minute) {
    return hour * 60 + minute;
}

// Функция для конвертации минут в объект времени {hour, minute}
function minutesToTime(minutes) {
    return {
        hour: Math.floor(minutes / 60),
        minute: minutes % 60
    };
}

// Функция для проверки пересечения временных интервалов
function checkTimeOverlap(time1Start, time1End, time2Start, time2End) {
    return (time1Start < time2End && time1End > time2Start);
}

// Функция для получения первого свободного временного слота
function getFirstFreeTimeSlot(day, colIndex, durationMinutes) {
    var blocks = document.querySelectorAll(`.activity-block[data-day="${day}"][data-col-index="${colIndex}"]`);
    var occupiedSlots = [];
    
    // Собираем все занятые временные слоты
    blocks.forEach(function(block) {
        var content = block.innerHTML;
        var timeRangeMatch = content.match(/(\d{2}:\d{2}-\d{2}:\d{2})$/);
        if (timeRangeMatch) {
            var timeRange = timeRangeMatch[1];
            var parsedTime = parseTimeRange(timeRange);
            if (parsedTime) {
                occupiedSlots.push({
                    start: parsedTime.startMinutes,
                    end: parsedTime.endMinutes
                });
            }
        }
    });
    
    // Сортируем слоты по времени начала
    occupiedSlots.sort(function(a, b) {
        return a.start - b.start;
    });
    
    // Определяем начало учебного дня (обычно 9:00)
    var dayStartMinutes = 9 * 60;
    var dayEndMinutes = 21 * 60; // Конец учебного дня (обычно 21:00)
    
    // Ищем первый свободный слот нужной длительности
    var currentStart = dayStartMinutes;
    
    for (var i = 0; i < occupiedSlots.length; i++) {
        var slot = occupiedSlots[i];
        
        // Если между текущим началом и началом занятого слота достаточно времени
        if (slot.start - currentStart >= durationMinutes) {
            // Нашли свободный слот
            return {
                start: currentStart,
                end: currentStart + durationMinutes
            };
        }
        
        // Перемещаем указатель на конец занятого слота
        currentStart = Math.max(currentStart, slot.end);
    }
    
    // Проверяем есть ли место после последнего занятого слота
    if (dayEndMinutes - currentStart >= durationMinutes) {
        return {
            start: currentStart,
            end: currentStart + durationMinutes
        };
    }
    
    // Если не нашли свободный слот, возвращаем null
    return null;
}

// Функция для проверки валидности цвета
function isValidColor(color) {
    return /^#[0-9A-F]{6}$/i.test(color) || 
           /^rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)$/i.test(color);
}

// Экспортируем функции
window.formatTimeToHHMM = formatTimeToHHMM;
window.parseTimeRange = parseTimeRange;
window.timeToMinutes = timeToMinutes;
window.minutesToTime = minutesToTime;
window.checkTimeOverlap = checkTimeOverlap;
window.getFirstFreeTimeSlot = getFirstFreeTimeSlot;
window.isValidColor = isValidColor;