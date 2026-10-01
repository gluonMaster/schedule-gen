// Модуль для работы с диалогом создания новых блоков

// Функция для открытия диалога создания нового блока
function openCreateBlockDialog(e, preselectedDay, preselectedCol, preselectedRow, preselectedBuilding) {
    console.log('Открытие диалога создания с параметрами:', {
        preselectedDay: preselectedDay,
        preselectedCol: preselectedCol,
        preselectedRow: preselectedRow,
        preselectedBuilding: preselectedBuilding
    });
    
    // Устанавливаем флаг, что диалог открыт
    window.editDialogOpen = true;
    
    // Определяем доступные здания 
    var buildings = ["Villa", "Kolibri"];
    
    // Создаем список доступных зданий
    var buildingOptions = buildings.map(function(building) {
        return `<option value="${building}" ${preselectedBuilding === building ? 'selected' : ''}>${building}</option>`;
    }).join('');
    
    // Создаем список доступных дней из существующей конфигурации
    var daysOptions = daysOrder.map(function(day) {
        return `<option value="${day}" ${preselectedDay === day ? 'selected' : ''}>${day}</option>`;
    }).join('');
    
    var shouldPreselectNewRoom = preselectedCol === '__new__' || typeof preselectedCol === 'undefined';
    
    // Получаем список всех колонок для выбранного дня и здания
    function getColumnsForDayAndBuilding(day, building) {
        var columns = [];
        var isNewRoomSelected = shouldPreselectNewRoom;
        // Находим контейнер расписания для указанного здания
        var buildingContainer = null;
        var buildingHeaders = document.querySelectorAll('h2');
        
        for (var i = 0; i < buildingHeaders.length; i++) {
            if (buildingHeaders[i].textContent.includes(building)) {
                // Находим ближайший schedule-container после заголовка здания
                buildingContainer = buildingHeaders[i].nextElementSibling;
                while (buildingContainer && !buildingContainer.classList.contains('schedule-container')) {
                    buildingContainer = buildingContainer.nextElementSibling;
                }
                break;
            }
        }
        
        if (buildingContainer) {
            buildingContainer.querySelectorAll(`.schedule-grid th.day-${day}`).forEach(function(header, index) {
                var headerText = header.textContent.trim();
                columns.push(`<option value="${index}" ${preselectedCol === index ? 'selected' : ''}>${headerText}</option>`);
            });
        } else {
            console.warn(`Не найден контейнер расписания для здания ${building}`);
        }

        columns.push(`<option value="__new__" ${isNewRoomSelected ? 'selected' : ''}>+ Новый кабинет...</option>`);
        
        return columns.join('');
    }
    
    // Для обратной совместимости определяем функцию getColumnsForDay
    function getColumnsForDay(day) {
        // По умолчанию используем первое здание (Villa)
        return getColumnsForDayAndBuilding(day, 'Villa');
    }
    
    // Определяем начальный день и здание
    var initialDay = preselectedDay || daysOrder[0];
    var initialBuilding = preselectedBuilding || "Villa"; // По умолчанию Villa
    
    // Предопределенные цвета для палитры
    var predefinedColors = [
        '#FFD3D3', // светло-красный
        '#FFE9D3', // светло-оранжевый
        '#FFFBD3', // светло-желтый
        '#E3FFD3', // светло-зеленый
        '#D3FFFB', // светло-голубой
        '#D3DEFF', // светло-синий
        '#EED3FF', // светло-фиолетовый
        '#FFD3F4', // светло-розовый
        '#D3D3D3'  // светло-серый
    ];
    
    // Создаем HTML для выбора цвета
    var colorPickerHTML = '';
    
    // Добавляем предопределенные цвета
    colorPickerHTML += '<div class="color-palette">';
    predefinedColors.forEach(function(color) {
        colorPickerHTML += `<div class="color-option" style="background-color: ${color}" data-color="${color}"></div>`;
    });
    colorPickerHTML += '</div>';
    
    // Добавляем поле для ручного ввода цвета
    colorPickerHTML += '<div class="custom-color">';
    colorPickerHTML += '<input type="color" id="custom-color-picker" value="#FFFBD3">';
    colorPickerHTML += '<input type="text" id="color-value" value="#FFFBD3" placeholder="#RRGGBB или RGB(r,g,b)">';
    colorPickerHTML += '</div>';
    
    // Создаем HTML диалогового окна
    var dialogHTML = `
        <div class="edit-dialog" onclick="event.stopPropagation();">
            <h3>Создание нового занятия</h3>
            <form id="create-form">
                <label>
                    Здание:
                    <select id="new-building" required>
                        ${buildingOptions}
                    </select>
                </label>
                <label>
                    День:
                    <select id="new-day" required>
                        ${daysOptions}
                    </select>
                </label>
                <label>
                    Колонка:
                    <select id="new-column">
                        ${getColumnsForDayAndBuilding(initialDay, initialBuilding)}
                    </select>
                </label>
                <label>
                    Предмет:
                    <input type="text" id="new-subject" required placeholder="Математика">
                </label>
                <label>
                    Преподаватель:
                    <input type="text" id="new-teacher" placeholder="Иванов И.И.">
                </label>
                <label>
                    Группа/Ученики:
                    <input type="text" id="new-students" placeholder="10А">
                </label>
                <label>
                    Кабинет:
                    <input type="text" id="new-room" placeholder="305">
                    <small id="new-room-hint" class="room-hint">Введите название нового кабинета</small>
                </label>
                <label>
                    Время (ЧЧ:ММ-ЧЧ:ММ):
                    <input type="text" id="new-time" value="${getTimeByRow(preselectedRow || 0)}" 
                           pattern="[0-9]{2}:[0-9]{2}-[0-9]{2}:[0-9]{2}" 
                           placeholder="09:00-10:30" title="Формат: ЧЧ:ММ-ЧЧ:ММ" required>
                </label>
                <label>
                    Цвет фона:
                    ${colorPickerHTML}
                </label>
                <div class="button-row">
                    <button type="button" id="cancel-create">Отмена</button>
                    <button type="submit">Создать</button>
                </div>
            </form>
        </div>
    `;
    
    // Создаем и добавляем диалог на страницу
    var dialogElement = document.createElement('div');
    dialogElement.className = 'dialog-overlay';
    dialogElement.innerHTML = dialogHTML;
    document.body.appendChild(dialogElement);
    
    // Добавляем стили для диалога, если их еще нет
    if (!document.getElementById('create-dialog-styles')) {
        var style = document.createElement('style');
        style.id = 'create-dialog-styles';
        style.textContent = `
            .dialog-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: rgba(0, 0, 0, 0.5);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 9999;
            }
            .edit-dialog {
                background-color: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
                width: 400px;
                max-width: 90%;
            }
            .edit-dialog h3 {
                margin-top: 0;
                color: #333;
                border-bottom: 1px solid #eee;
                padding-bottom: 10px;
            }
            .edit-dialog form {
                display: flex;
                flex-direction: column;
            }
            .edit-dialog label {
                margin-bottom: 10px;
                display: flex;
                flex-direction: column;
            }
            .edit-dialog input, .edit-dialog select {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                margin-top: 5px;
            }
            .edit-dialog input.new-room-highlight {
                border-color: #4CAF50;
                box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.15);
            }
            .room-hint {
                display: none;
                margin-top: 6px;
                color: #2e7d32;
                font-size: 12px;
                font-weight: 600;
            }
            .room-hint.active {
                display: block;
            }
            .edit-dialog .button-row {
                display: flex;
                justify-content: flex-end;
                margin-top: 15px;
                gap: 10px;
            }
            .edit-dialog button {
                padding: 8px 15px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-weight: bold;
            }
            .edit-dialog button[type="submit"] {
                background-color: #4CAF50;
                color: white;
            }
            .edit-dialog button[type="button"] {
                background-color: #f1f1f1;
                color: #333;
            }
            .edit-dialog button:hover {
                opacity: 0.9;
            }
            .color-palette {
                display: flex;
                flex-wrap: wrap;
                gap: 5px;
                margin-top: 5px;
                margin-bottom: 10px;
            }
            .color-option {
                width: 25px;
                height: 25px;
                border-radius: 4px;
                cursor: pointer;
                border: 1px solid #ddd;
                transition: transform 0.2s;
            }
            .color-option:hover {
                transform: scale(1.1);
            }
            .color-option.selected {
                border: 2px solid #333;
                transform: scale(1.1);
            }
            .custom-color {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-top: 5px;
            }
            .custom-color input[type="color"] {
                height: 30px;
                width: 50px;
                padding: 0;
                border: 1px solid #ddd;
            }
            .custom-color input[type="text"] {
                flex: 1;
            }
        `;
        document.head.appendChild(style);
    }
    
    // Предотвращаем скролл страницы
    document.body.style.overflow = 'hidden';

    // --- Секция типа занятия и дат (trial_ui) ---
    if (window.TrialUI) {
        window.TrialUI.injectTrialStyles();
        var _createForm = dialogElement.querySelector('#create-form');
        var _createButtonRow = _createForm ? _createForm.querySelector('.button-row') : null;
        var _currentRole = typeof window.USER_ROLE !== 'undefined' ? window.USER_ROLE : '';
        if (_createForm && _createButtonRow && (_currentRole === 'admin' || _currentRole === 'editor' || _currentRole === 'organizer')) {
            // Dropdown выбора типа занятия
            var _typeWrapper = document.createElement('label');
            _typeWrapper.id = 'create-lesson-type-wrapper';
            _typeWrapper.textContent = 'Тип занятия:';
            var _typeSelect = document.createElement('select');
            _typeSelect.id = 'new-lesson-type';
            _typeSelect.style.marginTop = '5px';
            if (_currentRole === 'organizer') {
                // Организатор может создавать только пробные/разовые занятия
                var _optTrial = document.createElement('option');
                _optTrial.value = 'trial';
                _optTrial.textContent = 'Пробное/разовое';
                _typeSelect.appendChild(_optTrial);
                _typeSelect.disabled = true;
            } else {
                var _optAuto = document.createElement('option');
                _optAuto.value = '';
                _optAuto.textContent = 'авто (по предмету)';
                var _optTrial2 = document.createElement('option');
                _optTrial2.value = 'trial';
                _optTrial2.textContent = 'Пробное/разовое';
                _typeSelect.appendChild(_optAuto);
                _typeSelect.appendChild(_optTrial2);
            }
            _typeWrapper.appendChild(_typeSelect);
            _createForm.insertBefore(_typeWrapper, _createButtonRow);

            // Секция дат (скрыта по умолчанию для не-organizer)
            var _datesSection = window.TrialUI.buildTrialDatesSection([]);
            _datesSection.id = 'create-trial-dates-section';
            _datesSection.style.display = (_currentRole === 'organizer') ? '' : 'none';
            _createForm.insertBefore(_datesSection, _createButtonRow);

            // Переключение видимости секции дат при смене типа
            _typeSelect.addEventListener('change', function () {
                _datesSection.style.display = (_typeSelect.value === 'trial') ? '' : 'none';
            });
        }
    }

    // Получаем выбранное здание или используем первое
    var initialBuilding = preselectedBuilding || buildings[0];

    // Обработчики для выбора дня и здания
    var buildingSelect = document.getElementById('new-building');
    var daySelect = document.getElementById('new-day');
    var columnSelect = document.getElementById('new-column');
    var roomInput = document.getElementById('new-room');
    var roomHint = document.getElementById('new-room-hint');

    // === Autocomplete dropdowns (spiskiData) ===
    var subjectsList = (typeof spiskiData !== 'undefined' && spiskiData && Array.isArray(spiskiData.subjects)) ? spiskiData.subjects : [];
    var teachersList = (typeof spiskiData !== 'undefined' && spiskiData && Array.isArray(spiskiData.teachers)) ? spiskiData.teachers : [];
    var groupsList = (typeof spiskiData !== 'undefined' && spiskiData && Array.isArray(spiskiData.groups)) ? spiskiData.groups : [];

    // Rooms are building-specific. Use a proxy array updated in-place on building changes
    // to avoid re-attaching event listeners to the same input element.
    var roomProxyItems = [];

    function _refreshRoomProxyItems(buildingName) {
        var src = getRoomListForBuilding(buildingName);
        roomProxyItems.length = 0;
        src.forEach(function(r) { roomProxyItems.push(r); });
    }

    _refreshRoomProxyItems(buildingSelect ? buildingSelect.value : '');

    if (typeof createAutocompleteInput === 'function') {
        createAutocompleteInput(document.getElementById('new-subject'), subjectsList, { allowCustom: true, spiskiKey: 'subjects' });
        createAutocompleteInput(document.getElementById('new-teacher'), teachersList, { allowCustom: true, spiskiKey: 'teachers' });
        createAutocompleteInput(document.getElementById('new-students'), groupsList, { allowCustom: true, spiskiKey: 'groups' });
        createAutocompleteInput(roomInput, roomProxyItems, {
            allowCustom: true,
            onAddItem: function(v) {
                // Persist in-memory (survives building switches within session).
                var building = buildingSelect ? buildingSelect.value : '';
                if (building) addRoomToBuildingList(building, v);
                // Persist to server (survives HTML regeneration).
                if (building && typeof _persistSpiskiToServer === 'function') {
                    _persistSpiskiToServer('rooms_' + building, v);
                }
            }
        });
    }
    
    function setRoomInputMode(isNewRoomMode, shouldFocusRoom) {
        if (isNewRoomMode) {
            roomInput.value = '';
            roomInput.placeholder = 'Введите новый кабинет';
            roomInput.classList.add('new-room-highlight');
            roomHint.classList.add('active');
            
            if (shouldFocusRoom) {
                setTimeout(function() {
                    roomInput.focus();
                }, 0);
            }
            return;
        }
        
        roomInput.placeholder = '305';
        roomInput.classList.remove('new-room-highlight');
        roomHint.classList.remove('active');
    }
    
    function syncRoomWithSelectedColumn(shouldFocusRoom) {
        var selectedColumnValue = columnSelect.value;
        var isNewRoomMode = selectedColumnValue === '__new__';
        
        if (!isNewRoomMode) {
            var selectedOption = columnSelect.options[columnSelect.selectedIndex];
            if (selectedOption) {
                var selectedDay = daySelect.value;
                var selectedRoom = selectedOption.textContent.trim();
                // Убираем префикс дня из текста заголовка колонки
                if (selectedRoom.indexOf(selectedDay) === 0) {
                    selectedRoom = selectedRoom.substring(selectedDay.length).trim();
                }
                if (selectedRoom !== '') {
                    roomInput.value = selectedRoom;
                }
            }
        }
        
        setRoomInputMode(isNewRoomMode, shouldFocusRoom);
    }
    
    // Обновляем функцию получения колонок для учета здания
    function updateColumnOptions() {
        var selectedBuilding = buildingSelect.value;
        if (typeof _refreshRoomProxyItems === 'function') {
            _refreshRoomProxyItems(selectedBuilding);
        }
        var selectedDay = daySelect.value;
        var previousColumnValue = columnSelect.value;
        
        columnSelect.innerHTML = getColumnsForDayAndBuilding(selectedDay, selectedBuilding);
        
        if (previousColumnValue && columnSelect.querySelector(`option[value="${previousColumnValue}"]`)) {
            columnSelect.value = previousColumnValue;
        }
        
        syncRoomWithSelectedColumn(columnSelect.value === '__new__');
    }
    
    // Обработчики изменений в выпадающих списках
    buildingSelect.addEventListener('change', updateColumnOptions);
    daySelect.addEventListener('change', updateColumnOptions);
    columnSelect.addEventListener('change', function() {
        syncRoomWithSelectedColumn(true);
    });
    syncRoomWithSelectedColumn(columnSelect.value === '__new__');
    
    // Ставим фокус на первое поле
    setTimeout(function() {
        if (columnSelect.value === '__new__') {
            roomInput.focus();
            return;
        }
        
        document.getElementById('new-subject').focus();
    }, 100);
    
    // Предотвращаем закрытие диалога при клике на overlay
    dialogElement.addEventListener('click', function(e) {
        if (e.target === dialogElement) {
            closeDialog();
            e.preventDefault();
            e.stopPropagation();
        }
    });
    
    // Функция закрытия диалога
    function closeDialog() {
        document.body.removeChild(dialogElement);
        document.body.style.overflow = '';
        window.editDialogOpen = false;
    }
    
    // Инициализация выбора цвета
    setTimeout(function() {
        // Обработчики для предустановленных цветов
        document.querySelectorAll('.color-option').forEach(function(colorOption) {
            colorOption.addEventListener('click', function() {
                var color = this.getAttribute('data-color');
                document.getElementById('color-value').value = color;
                document.getElementById('custom-color-picker').value = color;
                
                // Добавляем выделение выбранному цвету
                document.querySelectorAll('.color-option').forEach(function(option) {
                    option.classList.remove('selected');
                });
                this.classList.add('selected');
            });
        });
        
        // Связываем HTML5 color picker с текстовым полем
        document.getElementById('custom-color-picker').addEventListener('input', function() {
            document.getElementById('color-value').value = this.value;
            // Снимаем выделение с предустановленных цветов
            document.querySelectorAll('.color-option').forEach(function(option) {
                option.classList.remove('selected');
            });
        });
        
        // Связываем текстовое поле с HTML5 color picker
        document.getElementById('color-value').addEventListener('input', function() {
            // Обновляем color picker, если введен корректный цвет в формате #RRGGBB
            if (/^#[0-9A-F]{6}$/i.test(this.value)) {
                document.getElementById('custom-color-picker').value = this.value;
                // Снимаем выделение с предустановленных цветов
                document.querySelectorAll('.color-option').forEach(function(option) {
                    option.classList.remove('selected');
                });
            }
        });
        
        // По умолчанию выбираем первый цвет
        document.querySelector('.color-option').classList.add('selected');
    }, 100);
    
    // Обработчик отправки формы
    var formElement = document.getElementById('create-form');
    if (formElement) {
        formElement.addEventListener('submit', function(e) {
            // Предотвращаем действие по умолчанию
            e.preventDefault();
            e.stopPropagation();
            
            // Получаем значения из формы
            var building = document.getElementById('new-building').value;
            var day = document.getElementById('new-day').value;
            var selectedColumnValue = document.getElementById('new-column').value;
            var colIndex = parseInt(selectedColumnValue, 10);
            var subject = document.getElementById('new-subject').value;
            var teacher = document.getElementById('new-teacher').value;
            var students = document.getElementById('new-students').value;
            var room = document.getElementById('new-room').value;
            var timeRange = document.getElementById('new-time').value;
            var backgroundColor = document.getElementById('color-value').value;
            var trimmedRoom = room.trim();
            var isNewColumnSelected = selectedColumnValue === '__new__' || isNaN(colIndex);
            
            // Валидируем кабинет до любых изменений таблицы
            if (!trimmedRoom) {
                alert('Пожалуйста, введите название кабинета');
                roomInput.focus();
                return;
            }
            
            if (/[<>&"']/.test(trimmedRoom)) {
                alert('Название кабинета содержит недопустимые символы: < > & " \'');
                roomInput.focus();
                roomInput.select();
                return;
            }
            
            // Проверяем формат времени
            var timeRegex = /^([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2})$/;
            var timeMatch = timeRange.match(timeRegex);
            
            if (!timeMatch) {
                alert('Пожалуйста, введите время в формате ЧЧ:ММ-ЧЧ:ММ');
                return;
            }
            
            // Проверяем формат цвета
            if (!/^#[0-9A-F]{6}$/i.test(backgroundColor) && 
                !/^rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)$/i.test(backgroundColor)) {
                alert('Пожалуйста, введите корректный цвет в формате #RRGGBB или RGB(r,g,b)');
                return;
            }
            
            // Информируем, если кабинет уже есть в других днях, но отсутствует в выбранном
            if (typeof findMatchingColumnInBuilding === 'function') {
                var daysList = Array.isArray(window.daysOrder) ? window.daysOrder : [];
                var roomExistsInSelectedDay = findMatchingColumnInBuilding(day, trimmedRoom, building) !== -1;
                var roomExistsInOtherDays = false;
                
                if (!roomExistsInSelectedDay) {
                    for (var dayIdx = 0; dayIdx < daysList.length; dayIdx++) {
                        var otherDay = daysList[dayIdx];
                        if (otherDay === day) {
                            continue;
                        }
                        
                        if (findMatchingColumnInBuilding(otherDay, trimmedRoom, building) !== -1) {
                            roomExistsInOtherDays = true;
                            break;
                        }
                    }
                }
                
                if (roomExistsInOtherDays) {
                    console.log(`Кабинет "${trimmedRoom}" уже существует в других днях, создаём столбец для ${day}`);
                }
            }
            
            // Определяем итоговую колонку только после успешной валидации
            var finalColIndex = colIndex;
            if (isNewColumnSelected) {
                if (typeof addColumnIfMissing !== 'function') {
                    alert('Функция addColumnIfMissing не найдена');
                    console.warn('Функция addColumnIfMissing не найдена');
                    return;
                }
                
                var forcedColIndex = addColumnIfMissing(day, trimmedRoom, building);
                if (forcedColIndex === -1) {
                    alert(`Не удалось создать или найти колонку для кабинета ${trimmedRoom}`);
                    console.warn(`Не удалось создать или найти колонку для кабинета ${trimmedRoom}`);
                    return;
                }
                
                finalColIndex = forcedColIndex;
                console.log(`Выбрана новая колонка: ${finalColIndex} для кабинета ${trimmedRoom}`);
            } else if (typeof addColumnIfMissing === 'function') {
                console.log(`Проверка необходимости создания колонки для кабинета ${trimmedRoom}`);
                var newColIndex = addColumnIfMissing(day, trimmedRoom, building);
                
                if (newColIndex !== -1) {
                    finalColIndex = newColIndex;
                    console.log(`Используется колонка в позиции ${finalColIndex} для кабинета ${trimmedRoom}`);
                } else {
                    console.warn(`Не удалось создать или найти колонку для кабинета ${trimmedRoom}`);
                }
            } else {
                console.warn('Функция addColumnIfMissing не найдена');
            }
            
            // Показываем контрастный цвет текста в предпросмотре
            if (typeof getContrastTextColor === 'function') {
                var previewTextColor = getContrastTextColor(backgroundColor);
                console.log(`Выбран цвет фона: ${backgroundColor}, контрастный цвет текста: ${previewTextColor}`);
            }
            
            // Закрываем диалог
            closeDialog();
            
            // Создаем новый блок с учетом здания
            createNewBlock(building, day, finalColIndex, subject, teacher, students, trimmedRoom, timeRange, backgroundColor);
            
            // Проверяем конфликты после создания блока (setTimeout даёт DOM обновиться)
            setTimeout(function() {
                if (typeof ConflictDetector !== 'undefined') {
                    ConflictDetector.highlightConflicts();
                }
            }, 0);
            
            return false;
        });
    }
    
    // Обработчик кнопки отмены
    var cancelButton = document.getElementById('cancel-create');
    if (cancelButton) {
        cancelButton.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            closeDialog();
        });
    }
    
    // Закрытие по Escape
    function handleEscape(e) {
        if (e.key === 'Escape') {
            closeDialog();
            document.removeEventListener('keydown', handleEscape);
        }
    }
    document.addEventListener('keydown', handleEscape);
}

// Функция для получения времени по номеру строки
function getTimeByRow(rowIndex) {
    // Начальное время (обычно 9:00)
    var startHour = 9;
    var startMinute = 0;
    
    // Длительность одного интервала
    var interval = window.timeInterval || 5; // минут
    
    // Рассчитываем начальное время для заданной строки
    var totalMinutes = (startHour * 60) + startMinute + (rowIndex * interval);
    var startTime = formatTime(Math.floor(totalMinutes / 60), totalMinutes % 60);
    
    // По умолчанию длительность занятия - 2 часа (или 24 интервала по 5 минут)
    var endMinutes = totalMinutes + (24 * interval);
    var endTime = formatTime(Math.floor(endMinutes / 60), endMinutes % 60);
    
    return startTime + '-' + endTime;
}

// Функция для форматирования времени в формат ЧЧ:ММ
function formatTime(hours, minutes) {
    return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
}

// Экспортируем функции
window.openCreateBlockDialog = openCreateBlockDialog;
window.getTimeByRow = getTimeByRow;
window.formatTime = formatTime;
