// Модуль для редактирования блоков занятий с поддержкой разных зданий
// ОБНОВЛЕН: использует BuildingService вместо дублированных функций

// Функция инициализации редактирования блоков занятий
function initBlockEditing() {
    // Добавляем стили для диалогового окна
    var style = document.createElement('style');
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
            position: relative; /* Для предотвращения всплытия событий */
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
        .edit-dialog input, .edit-dialog textarea, .edit-dialog select {
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            margin-top: 5px;
        }
        .edit-dialog textarea {
            min-height: 60px;
            resize: vertical;
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
    `;
    document.head.appendChild(style);
}

function refreshCompactRowsAfterBlockEdit() {
    if (window.ScheduleCompactRows && typeof window.ScheduleCompactRows.refresh === 'function') {
        window.ScheduleCompactRows.refresh();
    } else if (typeof window.updateActivityPositions === 'function') {
        window.updateActivityPositions();
    }
}

function reapplyLessonTypeFilterAfterBlockEdit() {
    if (typeof reapplyLessonTypeFilter === 'function') {
        reapplyLessonTypeFilter();
        return;
    }
    refreshCompactRowsAfterBlockEdit();
}

// Функция открытия диалога редактирования с поддержкой зданий
function openEditDialog(block, origLeft, origTop, building) {
    if (
        typeof window.USER_ROLE !== 'undefined' &&
        window.USER_ROLE === 'organizer' &&
        block &&
        block.getAttribute('data-lesson-type') !== 'trial'
    ) {
        alert("Организатор может редактировать только пробные/разовые занятия.");
        return;
    }

    console.log("Открытие диалога редактирования");
    
    // Устанавливаем флаг, что диалог открыт
    if (typeof window.closeEditDialog === 'function') {
        window.closeEditDialog();
    }
    document.querySelectorAll('.dialog-overlay').forEach(function(existingOverlay) {
        if (
            existingOverlay.querySelector &&
            existingOverlay.querySelector('#edit-form') &&
            existingOverlay.parentNode
        ) {
            existingOverlay.parentNode.removeChild(existingOverlay);
        }
    });

    window.editDialogOpen = true;
    
    // Восстанавливаем позицию блока, если она была изменена при двойном клике
    if (origLeft && origTop) {
        block.style.left = origLeft;
        block.style.top = origTop;
    }

    // Сохраняем текущие значения атрибутов для сравнения после редактирования
    var currentDay = block.getAttribute('data-day');
    var currentColIndex = block.getAttribute('data-col-index');
    var originalLessonType = (block.getAttribute('data-lesson-type') || '').trim();
    var wasExistingGroupBlock = originalLessonType === 'group' || (!originalLessonType && !block.getAttribute('data-block-id'));
    
    // ИСПОЛЬЗУЕМ НОВЫЙ BuildingService вместо дублированной функции
    var currentBuilding = building || block.getAttribute('data-building') || 
                         BuildingService.determineBuildingForBlock(block);
    
    // Извлекаем текущие данные из блока
    var blockContent = block.innerHTML;
    var subject = '';
    var teacher = '';
    var students = '';
    var room = '';
    var timeRange = '';

    // Парсим содержимое блока
    var subjectElement = block.querySelector('strong');
    if (subjectElement) {
        subject = subjectElement.textContent || '';
    }

    // Разбиваем HTML по тегам <br>
    var parts = blockContent.split('<br>');
    // Удаляем теги из первого элемента (subject)
    var cleanSubject = parts[0].replace(/<\/?[^>]+(>|$)/g, "").trim();
    subject = cleanSubject;
    
    // Получаем остальные значения
    if (parts.length > 1) teacher = parts[1].trim();
    if (parts.length > 2) students = parts[2].trim();
    if (parts.length > 3) room = parts[3].trim();
    if (parts.length > 4) timeRange = parts[4].trim();

    console.log("Извлеченные данные:", {
        subject: subject,
        teacher: teacher,
        students: students,
        room: room,
        timeRange: timeRange,
        building: currentBuilding
    });
    
    // ИСПОЛЬЗУЕМ BuildingService для получения списка зданий
    var availableBuildings = BuildingService.getAvailableBuildings();
    var buildingOptions = availableBuildings.map(function(b) {
        return `<option value="${b}" ${currentBuilding === b ? 'selected' : ''}>${b}</option>`;
    }).join('');

    // Создаем HTML диалогового окна
    var dialogHTML = `
        <div class="edit-dialog" onclick="event.stopPropagation();">
            <h3>Редактирование занятия</h3>
            <form id="edit-form">
                <label>
                    Здание:
                    <select id="edit-building">
                        ${buildingOptions}
                    </select>
                </label>
                <label>
                    Предмет:
                    <input type="text" id="edit-subject" value="${subject}" required>
                </label>
                <label>
                    Преподаватель:
                    <input type="text" id="edit-teacher" value="${teacher}">
                </label>
                <label>
                    Группа/Ученики:
                    <input type="text" id="edit-students" value="${students}">
                </label>
                <label>
                    Кабинет:
                    <input type="text" id="edit-room" value="${room}">
                </label>
                <label>
                    Время (HH:MM-HH:MM):
                    <input type="text" id="edit-time" value="${timeRange}" pattern="[0-9]{2}:[0-9]{2}-[0-9]{2}:[0-9]{2}" 
                        placeholder="09:00-10:30" title="Формат: ЧЧ:ММ-ЧЧ:ММ">
                </label>
                <div class="button-row">
                    <button type="button" id="cancel-edit">Отмена</button>
                    <button type="submit">Сохранить</button>
                </div>
            </form>
        </div>
    `;

    // Создаем и добавляем диалог на страницу
    var dialogElement = document.createElement('div');
    dialogElement.className = 'dialog-overlay';
    dialogElement.innerHTML = dialogHTML;
    document.body.appendChild(dialogElement);

    function findInDialog(selector) {
        return dialogElement.querySelector(selector);
    }

    var formElement = findInDialog('#edit-form');
    var cancelButton = findInDialog('#cancel-edit');

    if (formElement) {
        // Guard immediately so a later initialization error cannot turn Save into page reload.
        formElement.addEventListener('submit', function(e) {
            e.preventDefault();
        }, true);
    }

    // --- Секция дат и кнопка конвертации для trial-блоков ---
    var _editLessonType = block.getAttribute('data-lesson-type');
    if (_editLessonType === 'trial' && window.TrialUI) {
        window.TrialUI.injectTrialStyles();
        var _editForm = dialogElement.querySelector('#edit-form');
        var _editButtonRow = _editForm ? _editForm.querySelector('.button-row') : null;
        if (_editForm && _editButtonRow) {
            // Парсим trial_dates из data-атрибута блока
            var _existingDates = [];
            try {
                var _raw = block.getAttribute('data-trial-dates');
                if (_raw) _existingDates = JSON.parse(_raw);
            } catch (e) { _existingDates = []; }

            // Секция дат перед кнопками
            var _editDatesSection = window.TrialUI.buildTrialDatesSection(_existingDates);
            _editDatesSection.id = 'edit-trial-dates-section';
            _editForm.insertBefore(_editDatesSection, _editButtonRow);
        }

        // Кнопка «Сделать регулярным» после button-row
        var _currentRole = typeof window.USER_ROLE !== 'undefined' ? window.USER_ROLE : '';
        var _allowedConvertRoles = ['admin', 'editor', 'organizer'];
        if (_editButtonRow && _allowedConvertRoles.indexOf(_currentRole) !== -1) {
            window.TrialUI.renderConvertButton(block, _currentRole, _editButtonRow.parentNode, function (updatedBlock) {
                // Закрываем диалог и обновляем блок через refreshIndividualLayer
                closeDialog();
                if (typeof window.refreshIndividualLayer === 'function') {
                    window.refreshIndividualLayer();
                }
            });
        }
    }

    // === Autocomplete dropdowns (spiskiData) ===
    var subjectsList = (typeof spiskiData !== 'undefined' && spiskiData && Array.isArray(spiskiData.subjects)) ? spiskiData.subjects : [];
    var teachersList = (typeof spiskiData !== 'undefined' && spiskiData && Array.isArray(spiskiData.teachers)) ? spiskiData.teachers : [];
    var groupsList = (typeof spiskiData !== 'undefined' && spiskiData && Array.isArray(spiskiData.groups)) ? spiskiData.groups : [];

    var buildingSelect = findInDialog('#edit-building');
    var roomInput = findInDialog('#edit-room');

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
        createAutocompleteInput(findInDialog('#edit-subject'), subjectsList, { allowCustom: true, spiskiKey: 'subjects' });
        createAutocompleteInput(findInDialog('#edit-teacher'), teachersList, { allowCustom: true, spiskiKey: 'teachers' });
        createAutocompleteInput(findInDialog('#edit-students'), groupsList, { allowCustom: true, spiskiKey: 'groups' });
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

        if (buildingSelect) {
            buildingSelect.addEventListener('change', function() {
                _refreshRoomProxyItems(buildingSelect.value);
            });
        }
    }

    // Нужно предотвратить скролл страницы
    document.body.style.overflow = 'hidden';

    // Ставим фокус на первое поле
    setTimeout(function() {
        var subjectField = findInDialog('#edit-subject');
        if (subjectField) {
            subjectField.focus();
        }
    }, 100);

    // Предотвращаем скролл страницы при клике на overlay
    dialogElement.addEventListener('click', function(e) {
        if (e.target === dialogElement) {
            closeDialog();
            e.preventDefault();
            e.stopPropagation();
        }
    });

    // Функция закрытия диалога
    function closeDialog() {
        if (dialogElement.parentNode) {
            dialogElement.parentNode.removeChild(dialogElement);
        }
        document.body.style.overflow = '';
        window.editDialogOpen = false;
        document.removeEventListener('keydown', handleEscape);
        if (window.closeEditDialog === closeDialog) {
            window.closeEditDialog = null;
        }
    }
    window.closeEditDialog = closeDialog;

    // Обработчик отправки формы
    if (formElement) {
        formElement.addEventListener('submit', function(e) {
            console.log("Форма отправлена");
            
            // Важно! Предотвращаем действие по умолчанию
            e.preventDefault();
            e.stopPropagation();
            
            // Получаем значения из формы
            var newBuilding = findInDialog('#edit-building').value;
            var newSubject = findInDialog('#edit-subject').value;
            var newTeacher = findInDialog('#edit-teacher').value;
            var newStudents = findInDialog('#edit-students').value;
            var newRoom = findInDialog('#edit-room').value;
            var newTime = findInDialog('#edit-time').value;
            
            console.log("Новые значения:", {
                building: newBuilding,
                subject: newSubject,
                teacher: newTeacher,
                students: newStudents,
                room: newRoom,
                time: newTime
            });
            
            // Проверяем формат времени
            var timeRegex = /^([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2})$/;
            var timeMatch = newTime.match(timeRegex);
            
            if (!timeMatch) {
                alert('Пожалуйста, введите время в формате ЧЧ:ММ-ЧЧ:ММ');
                return;
            }

            // Закрываем диалог до обновления блока
            closeDialog();

            // Получаем необходимые данные для определения изменений
            var day = block.getAttribute('data-day');
            var oldBuilding = block.getAttribute('data-building') || BuildingService.determineBuildingForBlock(block);
            var buildingChanged = (newBuilding !== oldBuilding);
            var roomChanged = (newRoom.trim() !== room.trim());
            var targetBuilding = buildingChanged ? newBuilding : oldBuilding;
            var targetRoom = newRoom.trim();
            
            console.log("Анализ изменений:", {
                day: day,
                oldBuilding: oldBuilding,
                targetBuilding: targetBuilding,
                oldRoom: room,
                targetRoom: targetRoom,
                buildingChanged: buildingChanged,
                roomChanged: roomChanged
            });
            
            // Обновляем содержимое блока
            block.innerHTML = `<strong>${newSubject}</strong><br>${newTeacher}<br>${newStudents}<br>${newRoom}<br>${newTime}`;

            // Refresh lesson type and re-apply filter after subject may have changed
            if (wasExistingGroupBlock) {
                block.setAttribute('data-lesson-type', 'group');
            }
            if (typeof updateBlockLessonType === 'function') {
                updateBlockLessonType(block);
            }
            // Обновляем отображение блока, если изменилось время
            if (newTime !== timeRange) {
                console.log("Обновление позиции блока из-за изменения времени");
                updateBlockPosition(block, newTime);
            }
            
            // Если изменилось здание, сначала перемещаем блок в новое здание
            if (buildingChanged) {
                console.log("Перемещение блока в другое здание:", targetBuilding);
                var moveSuccess = BuildingService.moveBlockToBuilding(block, targetBuilding);
                if (!moveSuccess) {
                    console.error("Не удалось переместить блок в здание:", targetBuilding);
                    alert(`Ошибка: не удалось переместить блок в здание ${targetBuilding}`);
                    return false;
                }
            } else {
                // Обновляем атрибут здания, даже если здание не изменилось
                block.setAttribute('data-building', targetBuilding);
            }
            
            // Если изменился кабинет или здание, обрабатываем колонки
            if (roomChanged || buildingChanged) {
                if (targetRoom === '') {
                    console.warn("Пустое название кабинета, пропускаем обработку колонок");
                } else {
                    console.log("Поиск/создание колонки для кабинета:", targetRoom, "в здании:", targetBuilding, "в день:", day);
                    
                    // Ищем существующую колонку в целевом здании
                    var colIndex = findMatchingColumnInBuilding(day, targetRoom, targetBuilding);
                    console.log("Результат поиска колонки:", colIndex);
                    
                    // Если колонка не найдена, создаем новую
                    if (colIndex === -1) {
                        console.log("Колонка не найдена, создаем новую");
                        colIndex = addColumnIfMissing(day, targetRoom, targetBuilding);
                        console.log("Результат создания колонки:", colIndex);
                        
                        if (colIndex === -1) {
                            console.error("Не удалось создать колонку для кабинета:", targetRoom);
                            alert(`Ошибка: не удалось создать колонку для кабинета ${targetRoom}`);
                            return false;
                        }
                    } else {
                        console.log("Найдена существующая колонка с индексом:", colIndex);
                    }
                    
                    // Устанавливаем индекс колонки для блока
                    console.log("Установка индекса колонки:", colIndex, "для блока");
                    block.setAttribute('data-col-index', colIndex);
                    
                    // Проверяем, что атрибут установился
                    var setColIndex = block.getAttribute('data-col-index');
                    console.log("Проверка установленного data-col-index:", setColIndex);
                }
            }
            
            reapplyLessonTypeFilterAfterBlockEdit();

            if (wasExistingGroupBlock && typeof window.normalizeGroupBlockRuntimeState === 'function') {
                window.normalizeGroupBlockRuntimeState(block);
            }
            if (typeof ConflictDetector !== 'undefined') {
                ConflictDetector.highlightConflicts();
            }
            
            return false; // Дополнительное предотвращение отправки формы
        });
    }

    // Обработчик кнопки отмены
    if (cancelButton) {
        cancelButton.addEventListener('click', function(e) {
            console.log("Нажата кнопка отмены");
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

// ФУНКЦИЯ УДАЛЕНА: moveBlockToBuilding теперь является методом BuildingService

// ФУНКЦИЯ УДАЛЕНА: findScheduleContainerForBuilding теперь является методом BuildingService

// Экспортируем функции
window.openEditDialog = openEditDialog;
window.initBlockEditing = initBlockEditing;

// Обратная совместимость для старых функций (с предупреждениями)
window.moveBlockToBuilding = function(block, newBuilding) {
    console.warn('Deprecated: use BuildingService.moveBlockToBuilding() instead');
    return BuildingService.moveBlockToBuilding(block, newBuilding);
};

window.findScheduleContainerForBuilding = function(buildingName) {
    console.warn('Deprecated: use BuildingService.findScheduleContainerForBuilding() instead');
    return BuildingService.findScheduleContainerForBuilding(buildingName);
};
