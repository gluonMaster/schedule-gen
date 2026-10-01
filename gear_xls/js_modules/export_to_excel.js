// Модуль для экспорта расписания в Excel

// Функция для сбора данных со всех блоков занятий
function collectScheduleData(options) {
    // Структура для хранения данных расписания
    var scheduleData = [];
    var includeHidden = !!(options && options.includeHidden);

    // Проходим по всем контейнерам расписания (по зданиям)
    document.querySelectorAll('.schedule-container').forEach(function(container) {
        var building = container.getAttribute('data-building');
        
        // Получаем таблицу и высоту заголовка
        var table = container.querySelector('.schedule-grid');
        var headerHeight = table.querySelector('thead').getBoundingClientRect().height;
        
        // Начало сетки берётся из глобала gridStart, эмитируемого html_javascript.py
        
        // Проходим по всем блокам активностей в этом здании
        container.querySelectorAll('.activity-block').forEach(function(block) {
            var explicitLessonType = (block.getAttribute('data-lesson-type') || '').trim();
            if (
                typeof window.normalizeGroupBlockRuntimeState === 'function' &&
                (explicitLessonType === 'group' || (!explicitLessonType && !block.getAttribute('data-block-id')))
            ) {
                window.normalizeGroupBlockRuntimeState(block);
            }

            // В обычном режиме пропускаем скрытые блоки, но для публикации
            // может понадобиться полный снимок расписания независимо от скрытых дней.
            if (!includeHidden && window.getComputedStyle(block).display === 'none') {
                return;
            }
            
            // Извлекаем данные из блока
            var day = block.getAttribute('data-day');
            var colIndex = parseInt(block.getAttribute('data-col-index'));
            
            // Получаем заголовок колонки для определения кабинета
            var roomName = '';
            var roomDisplay = '';
            var dayHeaders = table.querySelectorAll('th.day-' + day);
            if (dayHeaders.length > colIndex) {
                var headerContent = dayHeaders[colIndex].innerText.trim();
                // Удаляем из текста код дня (Mo, Di и т.д.)
                roomName = headerContent.replace(day, '').trim();
                // Сохраняем отображаемое имя кабинета
                roomDisplay = roomName;
            }
            
            // Извлекаем текстовое содержимое блока для получения остальных данных
            var blockContent = block.innerHTML;
            var lines = blockContent
                .replace(/<br>/g, '\n')  // Заменяем <br> на переносы строк
                .replace(/<[^>]*>/g, '') // Удаляем все HTML-теги
                .split('\n')              // Разбиваем по строкам
                .map(line => line.trim()) // Удаляем лишние пробелы
                .filter(line => line);    // Удаляем пустые строки
            
            // Извлекаем время начала и конца из содержимого блока
            var timeMatch = null;
            var startTime = '';
            var endTime = '';
            var duration = 0;
            var rowTimeRange = resolveTimeRangeFromRowsForExport(block);

            if (rowTimeRange) {
                startTime = rowTimeRange.startTime;
                endTime = rowTimeRange.endTime;
                duration = rowTimeRange.duration;
                timeMatch = true;
            }
            
            // Ищем строку с временем в последних строках
            for (var i = lines.length - 1; !timeMatch && i >= 0; i--) {
                timeMatch = lines[i].match(/(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})/);
                if (timeMatch) {
                    startTime = timeMatch[1];
                    endTime = timeMatch[2];
                    
                    // Вычисляем продолжительность из извлеченного времени
                    var startParts = startTime.split(':');
                    var endParts = endTime.split(':');
                    var startMinutes = parseInt(startParts[0]) * 60 + parseInt(startParts[1]);
                    var endMinutes = parseInt(endParts[0]) * 60 + parseInt(endParts[1]);
                    
                    // Проверяем, что время логично
                    if (startMinutes < endMinutes && startMinutes >= 0 && endMinutes <= 24*60) {
                        duration = endMinutes - startMinutes;
                        break;
                    } else {
                        console.warn('Извлеченное время выглядит неверно: ' + startTime + '-' + endTime);
                        timeMatch = null; // Сбрасываем, чтобы использовать резервный метод
                    }
                }
            }
            
            // Если время не найдено в содержимом блока, используем расчет по позиции (резервный вариант)
            if (!timeMatch) {
                console.warn('Время не найдено в содержимом блока, используем data-start-row/data-row-span');

                var gStart    = (typeof gridStart !== 'undefined') ? gridStart : 9 * 60;
                var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;

                var attrStartRow = parseInt(block.getAttribute('data-start-row'));
                var attrRowSpan  = parseInt(block.getAttribute('data-row-span'));

                if (!isNaN(attrStartRow) && !isNaN(attrRowSpan) && attrRowSpan > 0) {
                    var startMinutes = gStart + attrStartRow * tInterval;
                    var endMinutes   = gStart + (attrStartRow + attrRowSpan) * tInterval;
                    startTime = minutesToTime(startMinutes);
                    endTime   = minutesToTime(endMinutes);
                    duration  = endMinutes - startMinutes;
                } else {
                    console.error('collectScheduleData: missing data-start-row/data-row-span and no time text found');
                    // Keep startTime/endTime/duration at their zero-values; the export will contain empty time
                }
            }

            // Извлекаем данные из содержимого блока
            var subject = lines[0] || '';  // Первая строка - название предмета
            var teacher = lines[1] || '';  // Вторая строка - преподаватель
            var students = lines[2] || ''; // Третья строка - группа студентов
            
            // Получаем цвет блока
            var blockColor = window.getComputedStyle(block).backgroundColor;
            // Преобразуем в HEX формат
            var hexColor = rgbToHex(blockColor);
            
            // Создаем запись активности для экспорта
            var lessonType = block.getAttribute('data-lesson-type') || 'group';
            var trialDatesJson = '';

            if (lessonType === 'trial') {
                var rawTrialDates = block.getAttribute('data-trial-dates');
                if (rawTrialDates) {
                    try {
                        var parsedTrialDates = JSON.parse(rawTrialDates);
                        if (Array.isArray(parsedTrialDates)) {
                            trialDatesJson = JSON.stringify(parsedTrialDates);
                        }
                    } catch (error) {
                        console.warn('Не удалось распарсить data-trial-dates для экспорта:', error);
                    }
                }
            }

            var activity = {
                subject: subject,
                students: students,
                teacher: teacher,
                room: roomName,
                room_display: roomDisplay,
                building: building,
                day: day,
                start_time: startTime,  // Строка в формате "HH:MM"
                end_time: endTime,      // Строка в формате "HH:MM"
                duration: duration,
                color: hexColor,
                lesson_type: lessonType,
                trial_dates_json: trialDatesJson
            };
            
            // Добавляем активность в общий список
            scheduleData.push(activity);
        });
    });
    
    return scheduleData;
}

function validateScheduleDataForExcelExport(scheduleData) {
    for (var i = 0; i < scheduleData.length; i++) {
        var activity = scheduleData[i] || {};
        var day = String(activity.day || '').trim();
        var lessonType = String(activity.lesson_type || 'group').trim() || 'group';

        if (day === 'So' && lessonType !== 'trial') {
            return {
                ok: false,
                message: 'Экспорт остановлен: воскресенье доступно только для trial-занятий.'
            };
        }
    }
    return { ok: true };
}

// Вспомогательная функция преобразования минут в формат времени HH:MM
function _prepareSearchForExcelExport(options) {
    var search = window.ScheduleSearch;

    if (!search || typeof search.prepareForSerialization !== 'function') {
        return false;
    }
    return search.prepareForSerialization(options);
}

function minutesToTime(minutes) {
    var hours = Math.floor(minutes / 60);
    var mins = minutes % 60;
    return hours.toString().padStart(2, '0') + ':' + mins.toString().padStart(2, '0');
}

function resolveTimeRangeFromRowsForExport(block) {
    var gStart = (typeof gridStart !== 'undefined') ? gridStart : 9 * 60;
    var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;
    var attrStartRow = parseInt(block.getAttribute('data-start-row'), 10);
    var attrRowSpan = parseInt(block.getAttribute('data-row-span'), 10);
    var startMinutes;
    var endMinutes;

    if (isNaN(attrStartRow) || isNaN(attrRowSpan) || attrStartRow < 0 || attrRowSpan <= 0) {
        return null;
    }

    startMinutes = gStart + attrStartRow * tInterval;
    endMinutes = gStart + (attrStartRow + attrRowSpan) * tInterval;
    return {
        startTime: minutesToTime(startMinutes),
        endTime: minutesToTime(endMinutes),
        duration: endMinutes - startMinutes
    };
}

// Вспомогательная функция для преобразования RGB в HEX
function rgbToHex(rgb) {
    // Если это уже HEX
    if (rgb.startsWith('#')) {
        return rgb;
    }
    
    // Если это RGB
    var rgbMatch = rgb.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (rgbMatch) {
        var r = parseInt(rgbMatch[1]);
        var g = parseInt(rgbMatch[2]);
        var b = parseInt(rgbMatch[3]);
        return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }
    
    // Если это RGBA
    var rgbaMatch = rgb.match(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)/);
    if (rgbaMatch) {
        var r = parseInt(rgbaMatch[1]);
        var g = parseInt(rgbaMatch[2]);
        var b = parseInt(rgbaMatch[3]);
        return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    }
    
    // Если формат не распознан
    return '#CCCCCC';
}

// Функция проверки доступности сервера
function checkServerAvailability(callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/', true);
    xhr.timeout = 2000; // 2 секунды на ответ
    
    xhr.onload = function() {
        if (xhr.status === 200) {
            console.log('Сервер доступен');
            callback(true);
        } else {
            console.error('Сервер недоступен, статус:', xhr.status);
            callback(false);
        }
    };
    
    xhr.ontimeout = function() {
        console.error('Таймаут при проверке сервера');
        callback(false);
    };
    
    xhr.onerror = function() {
        console.error('Ошибка при проверке сервера');
        callback(false);
    };
    
    xhr.send();
}

function _refreshIndividualBeforeExport(onReady, onError) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/individual_lessons', true);
    xhr.setRequestHeader('Accept', 'application/json');

    xhr.onload = function() {
        var data = null;
        var refreshResult = null;

        if (xhr.status === 200) {
            try {
                data = JSON.parse(xhr.responseText);
            } catch (e) {
                onReady();
                return;
            }

            if (window.refreshIndividualLayer) {
                refreshResult = window.refreshIndividualLayer(data);
                if (refreshResult && typeof refreshResult.then === 'function') {
                    refreshResult.then(function() {
                        onReady();
                    }).catch(function() {
                        onReady();
                    });
                    return;
                }
            }

            onReady();
        } else if (xhr.status === 401) {
            if (typeof window.handleSessionExpired === 'function') {
                window.handleSessionExpired();
            }
            onError('session_expired');
        } else {
            onError('server_error_' + xhr.status);
        }
    };

    xhr.onerror = function() {
        onError('network_error');
    };

    xhr.send();
}

function _showTemporaryExportToast(message) {
    var existing = document.getElementById('exportAutoUnhideToast');
    if (existing) {
        if (existing._hideTimer) {
            clearTimeout(existing._hideTimer);
        }
        existing.remove();
    }

    var toast = document.createElement('div');
    toast.id = 'exportAutoUnhideToast';
    toast.textContent = message;
    toast.style.cssText = [
        'position: fixed',
        'right: 20px',
        'bottom: 20px',
        'z-index: 9999',
        'max-width: 360px',
        'padding: 10px 14px',
        'border-radius: 8px',
        'background: rgba(33, 37, 41, 0.92)',
        'color: #fff',
        'font-size: 13px',
        'box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2)',
        'pointer-events: none'
    ].join('; ');
    document.body.appendChild(toast);

    toast._hideTimer = setTimeout(function() {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 1800);
}

function _exportWithAutoUnhide() {
    _prepareSearchForExcelExport();

    var hiddenButtons = Array.from(
        document.querySelectorAll('.toggle-day-button.active')
    );

    if (hiddenButtons.length > 0) {
        _showTemporaryExportToast(
            'Скрытые дни временно раскрываются для полной выгрузки...'
        );
        hiddenButtons.forEach(function(btn) {
            var dayCode = btn.getAttribute('data-day');
            if (dayCode && typeof toggleDay === 'function') {
                toggleDay(btn, dayCode);
            }
        });
    }

    var restored = false;
    function restoreHiddenDays() {
        if (restored) {
            return;
        }
        restored = true;
        hiddenButtons.forEach(function(btn) {
            var dayCode = btn.getAttribute('data-day');
            if (dayCode && typeof toggleDay === 'function') {
                toggleDay(btn, dayCode);
            }
        });
    }

    try {
        exportScheduleToExcel(restoreHiddenDays, { searchPrepared: true });
    } catch (e) {
        restoreHiddenDays();
        throw e;
    }
}

// Инициализация экспорта в Excel
function initExcelExport() {
    // Находим кнопку экспорта
    var exportButton = document.getElementById('exportToExcel');
    if (exportButton) {
        // Очищаем старые обработчики событий путем клонирования элемента
        var newExportButton = exportButton.cloneNode(true);
        exportButton.parentNode.replaceChild(newExportButton, exportButton);
        exportButton = newExportButton;
        
        // Добавляем обработчик клика на кнопку
        exportButton.addEventListener('click', function() {
            _exportWithAutoUnhide();
        });
        console.log('Инициализирован обработчик экспорта в Excel');
    } else {
        console.error('Кнопка exportToExcel не найдена');
    }
}

// Основная функция экспорта расписания в Excel
function exportScheduleToExcel(onDone, options) {
    var _done = (typeof onDone === 'function') ? onDone : function() {};
    var _options = options || {};
    var _doneCalled = false;
    function _callDone() {
        if (_doneCalled) {
            return;
        }
        _doneCalled = true;
        _done();
    }

    try {
        // Проверяем наличие конфликтов перед экспортом
        if (!_options.searchPrepared) {
            _prepareSearchForExcelExport();
        }
        if (typeof ConflictDetector !== 'undefined' && ConflictDetector.hasConflicts()) {
            var summary = ConflictDetector.getConflictSummary();
            var proceed = confirm(
                'В расписании обнаружены конфликты (блоки выделены красным):\n\n' +
                summary +
                '\n\nЭкспортировать расписание с конфликтами?\n' +
                '(При запуске планировщика "Учесть изменения" такое расписание может дать ошибку INFEASIBLE)'
            );
            if (!proceed) {
                _callDone();
                return;
            }
        }
        console.log('Начинаем сбор данных для экспорта в Excel...');
        
        // Проверяем доступность сервера перед сбором данных
        checkServerAvailability(function(isAvailable) {
            if (!isAvailable) {
                showExportProgress('Сервер экспорта недоступен!', true);
                checkServerAndAdvise();
                _callDone();
                return;
            }

            _refreshIndividualBeforeExport(function() {
                // Собираем данные расписания
                var scheduleData = collectScheduleData();
                var exportValidation = validateScheduleDataForExcelExport(scheduleData);
                if (!exportValidation.ok) {
                    hideExportProgress();
                    alert(exportValidation.message);
                    _callDone();
                    return;
                }
                console.log('Собрано записей: ' + scheduleData.length);
                
                // Показываем индикатор процесса
                showExportProgress('Подготовка данных для экспорта...');
                
                // Получаем CSRF-токен для безопасности
                var csrfToken = document.getElementById('csrf_token')?.value || '';
                
                // Вместо формы используем XMLHttpRequest для прямой отправки и получения ответа
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/export_to_excel', true);
                
                // Обработка успешного завершения запроса
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        console.log('Получен ответ от сервера');
                        // Создаем временную ссылку для скачивания файла
                        var blob = new Blob([xhr.response], { 
                            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
                        });
                        var link = document.createElement('a');
                        link.href = window.URL.createObjectURL(blob);
                        link.download = 'schedule_export.xlsx';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        window.URL.revokeObjectURL(link.href);
                        
                        // Скрываем индикатор прогресса
                        hideExportProgress();
                        showExportProgress('Excel-файл успешно скачан!', true);
                        _callDone();
                        // Автоматическое закрытие через 2 секунды (оставляем возможность закрыть вручную)
                        setTimeout(function() {
                            // Проверяем, не закрыл ли пользователь сообщение сам
                            if (document.getElementById('exportProgress') && 
                                document.getElementById('exportProgress').style.display !== 'none') {
                                hideExportProgress();
                            }
                        }, 2000);
                    } else {
                        console.error('Ошибка при получении файла:', xhr.status, xhr.statusText);
                        hideExportProgress();
                        showExportProgress('Ошибка при получении файла: ' + xhr.statusText, true);
                        _callDone();
                    }
                };
                
                // Обработка ошибок сети
                xhr.onerror = function() {
                    console.error('Ошибка сети при отправке запроса');
                    hideExportProgress();
                    showExportProgress('Ошибка сети! Сервер недоступен.', true);
                    
                    // Проверяем доступность сервера и даем рекомендации
                    checkServerAndAdvise();
                    _callDone();
                };
                
                // Указываем, что нам нужен ответ в виде бинарных данных
                xhr.responseType = 'arraybuffer';
                
                // Устанавливаем заголовки запроса
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                
                // Формируем данные запроса
                var formData = 'schedule_data=' + encodeURIComponent(JSON.stringify(scheduleData)) + 
                              '&csrf_token=' + encodeURIComponent(csrfToken);
                
                // Отправляем запрос
                xhr.send(formData);
                
                console.log('Данные отправлены для создания Excel-файла');
            }, function() {
                hideExportProgress();
                alert('Не удалось синхронизировать индивидуальные занятия перед экспортом. Экспорт отменён.');
                _callDone();
            });
        });
    } catch (error) {
        console.error('Ошибка при экспорте в Excel:', error);
        hideExportProgress();
        showExportProgress('Ошибка при экспорте: ' + error.message, true);
        _callDone();
    }
}

// Функция-обработчик нажатия клавиши Esc
function handleEscapeKey(event) {
    if (event.key === 'Escape') {
        hideExportProgress();
        // Удаляем обработчик после закрытия, чтобы не накапливались
        document.removeEventListener('keydown', handleEscapeKey);
    }
}

// Функция для скрытия индикатора процесса экспорта
function hideExportProgress() {
    var progressDiv = document.getElementById('exportProgress');
    if (progressDiv) {
        progressDiv.style.display = 'none';
        // Удаляем обработчик Esc при закрытии
        document.removeEventListener('keydown', handleEscapeKey);
    }
}

// Функция для отображения индикатора процесса экспорта
function showExportProgress(message, isResult) {
    // Проверяем, существует ли уже индикатор
    if (document.getElementById('exportProgress')) {
        var messageBox = document.getElementById('exportProgress').querySelector('div');
        if (messageBox) {
            // Если это результат операции, добавляем кнопку закрытия
            if (isResult) {
                messageBox.innerHTML = `
                    <p style="margin: 0; text-align: center; position: relative; ${isResult ? 'color: green; font-weight: bold;' : ''}">
                        ${message}
                        <button onclick="hideExportProgress()" style="position: absolute; top: -5px; right: -5px; border: none; background: none; font-size: 20px; font-weight: bold; color: #555; cursor: pointer;" title="Закрыть сообщение">×</button>
                    </p>
                `;
                // Добавляем обработчик Esc
                document.addEventListener('keydown', handleEscapeKey);
            } else {
                messageBox.innerHTML = `<p style="margin: 0; text-align: center;">${message}</p>`;
            }
            document.getElementById('exportProgress').style.display = 'flex';
        }
        return;
    }
    
    // Создаем индикатор прогресса
    var progressDiv = document.createElement('div');
    progressDiv.id = 'exportProgress';
    progressDiv.style.position = 'fixed';
    progressDiv.style.top = '0';
    progressDiv.style.left = '0';
    progressDiv.style.width = '100%';
    progressDiv.style.height = '100%';
    progressDiv.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
    progressDiv.style.zIndex = '10000';
    progressDiv.style.display = 'flex';
    progressDiv.style.justifyContent = 'center';
    progressDiv.style.alignItems = 'center';
    
    var messageBox = document.createElement('div');
    messageBox.style.backgroundColor = 'white';
    messageBox.style.padding = '20px';
    messageBox.style.borderRadius = '5px';
    messageBox.style.boxShadow = '0 0 10px rgba(0, 0, 0, 0.3)';
    messageBox.style.maxWidth = '80%';
    
    // Если это результат операции, добавляем кнопку закрытия
    if (isResult) {
        messageBox.innerHTML = `
            <p style="margin: 0; text-align: center; position: relative; ${isResult ? 'color: green; font-weight: bold;' : ''}">
                ${message}
                <button onclick="hideExportProgress()" style="position: absolute; top: -5px; right: -5px; border: none; background: none; font-size: 20px; font-weight: bold; color: #555; cursor: pointer;" title="Закрыть сообщение">×</button>
            </p>
        `;
        // Добавляем обработчик Esc
        document.addEventListener('keydown', handleEscapeKey);
    } else {
        messageBox.innerHTML = `<p style="margin: 0; text-align: center;">${message}</p>`;
    }
    
    progressDiv.appendChild(messageBox);
    document.body.appendChild(progressDiv);
}

// Функция проверки доступности сервера и вывода рекомендаций
function checkServerAndAdvise() {
    var message = document.createElement('div');
    message.style.backgroundColor = '#f8f8f8';
    message.style.border = '1px solid #ddd';
    message.style.borderRadius = '5px';
    message.style.padding = '15px';
    message.style.margin = '10px 0';
    message.style.fontSize = '14px';
    message.style.lineHeight = '1.5';
    message.style.color = '#333';
    message.style.position = 'relative'; // Для позиционирования кнопки закрытия
    
    // Добавляем кнопку закрытия
    var closeButton = document.createElement('button');
    closeButton.innerHTML = '×';
    closeButton.style.position = 'absolute';
    closeButton.style.top = '5px';
    closeButton.style.right = '5px';
    closeButton.style.border = 'none';
    closeButton.style.background = 'none';
    closeButton.style.fontSize = '20px';
    closeButton.style.fontWeight = 'bold';
    closeButton.style.color = '#d9534f';
    closeButton.style.cursor = 'pointer';
    closeButton.title = 'Закрыть сообщение';
    closeButton.onclick = hideExportProgress;
    
    message.appendChild(closeButton);
    
    message.innerHTML += `
        <h4 style="margin-top: 0; color: #d9534f;">Сервер экспорта недоступен!</h4>
        <p>Возможные причины и решения:</p>
        <ol>
            <li>Flask-сервер не запущен. Запустите <code>server_routes.py</code> вручную.</li>
            <li>Порт 5000 занят другим приложением. Измените порт в <code>server_routes.py</code>.</li>
            <li>Брандмауэр блокирует соединение. Проверьте настройки брандмауэра.</li>
        </ol>
        <p>Для запуска сервера выполните в командной строке:</p>
        <pre style="background: #eee; padding: 5px;">python server_routes.py</pre>
        <p style="margin-top: 10px; text-align: center; font-style: italic; color: #666;">
            Нажмите ESC или кнопку × чтобы закрыть это сообщение
        </p>
    `;
    
    var progressDiv = document.getElementById('exportProgress');
    if (progressDiv) {
        var messageBox = progressDiv.querySelector('div');
        if (messageBox) {
            messageBox.appendChild(message);
        }
    }
    
    // Добавляем обработчик нажатия клавиши Esc
    document.addEventListener('keydown', handleEscapeKey);
}
