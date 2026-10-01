// Полный набор кабинетов для каждого здания
var BUILDING_ROOMS = {
    'Villa': ['K.06', 'K.07', 'K.08', 'K.11', '0.05', '0.06', '0.08',
              '1.03', '1.05', '1.06', '1.09', '2.03', '2.04', '2.05', '2.07', '2.09'],
    'Kolibri': ['0.3', '2.2', '2.3', '2.4', '2.5', '2.6', '2.7']
};

var MENU_DAYS = Array.isArray(window.daysOrder)
    ? window.daysOrder.slice()
    : ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
var _menuModalEscapeHandler = null;
var _menuInitialized = false;

var _addColumnDialogOpen = false;
var _addColumnAutocompleteCtrl = null; // current autocomplete controller for room input
var _addColumnRoomItems = []; // mutable list used by the room autocomplete (updated on building change)
var _addColumnEscHandler = null; // keydown handler for Escape — stored at module level so _closeAddColumnDialog can remove it

function currentMenuRole() {
    return window.USER_ROLE || 'viewer';
}

function canManageScheduleStructure() {
    return currentMenuRole() === 'admin';
}

function canAddColumn() {
    return ['admin', 'editor', 'organizer'].indexOf(currentMenuRole()) !== -1;
}

function _syncStructureMenuVisibility() {
    var addColItem = document.getElementById('menuItemAddColumn');
    if (addColItem) {
        addColItem.style.display = canAddColumn() ? '' : 'none';
    }
    var newSchedItem = document.getElementById('menuItemNewSchedule');
    if (newSchedItem) {
        newSchedItem.style.display = canManageScheduleStructure() ? '' : 'none';
    }
}

// === Menu open/close ===
function toggleMenu() {
    var dropdown = document.getElementById('menuDropdown');
    if (!dropdown) return;
    dropdown.classList.toggle('open');
}

function closeMenu() {
    var dropdown = document.getElementById('menuDropdown');
    if (dropdown) dropdown.classList.remove('open');
}

function _initPublishMenuItem() {
    var publishItem = document.getElementById('menu-publish-item');
    if (!publishItem) return;

    publishItem.style.display = (window.USER_ROLE === 'admin') ? '' : 'none';
    if (publishItem.__publishBound) return;
    publishItem.__publishBound = true;

    publishItem.addEventListener('click', function(e) {
        e.stopPropagation();
        closeMenu();
        if (typeof window.publishSchedule === 'function') {
            window.publishSchedule();
        } else {
            console.warn('publishSchedule is not available');
        }
    });
}

// === Confirmation modal helpers ===
function showMenuConfirmModal(message, onConfirm) {
    hideMenuConfirmModal();

    var overlay = document.createElement('div');
    overlay.className = 'menu-modal-overlay open';
    overlay.innerHTML = [
        '<div class="menu-modal">',
        '  <p>' + message + '</p>',
        '  <button class="menu-modal-btn-yes">Да, создать</button>',
        '  <button class="menu-modal-btn-cancel">Отмена</button>',
        '</div>'
    ].join('');

    document.body.appendChild(overlay);

    var yesBtn = overlay.querySelector('.menu-modal-btn-yes');
    var cancelBtn = overlay.querySelector('.menu-modal-btn-cancel');

    if (yesBtn) {
        yesBtn.addEventListener('click', function() {
            hideMenuConfirmModal();
            if (typeof onConfirm === 'function') {
                onConfirm();
            }
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', function() {
            hideMenuConfirmModal();
        });
    }

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            hideMenuConfirmModal();
        }
    });

    _menuModalEscapeHandler = function(e) {
        if (e.key === 'Escape') {
            hideMenuConfirmModal();
        }
    };
    document.addEventListener('keydown', _menuModalEscapeHandler);
}

function hideMenuConfirmModal() {
    var overlay = document.querySelector('.menu-modal-overlay');
    if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
    }
    if (_menuModalEscapeHandler) {
        document.removeEventListener('keydown', _menuModalEscapeHandler);
        _menuModalEscapeHandler = null;
    }
}

// === "Создать новое расписание" entry point ===
function handleNewSchedule() {
    closeMenu();
    if (!canManageScheduleStructure()) {
        alert('Создание нового расписания доступно только администратору.');
        return;
    }
    showMenuConfirmModal(
        'Вы уверены, что хотите создать новое расписание? Все текущие данные будут удалены.',
        function() {
            _doCreateNewSchedule();
        }
    );
}

// Opens the "Добавить колонку" dialog.
// prefillBuilding and prefillDay are optional; if provided the selects are pre-filled and disabled.
function openAddColumnDialog(prefillBuilding, prefillDay) {
    if (_addColumnDialogOpen) return;
    closeMenu();
    if (!canAddColumn()) {
        alert('Добавление колонок недоступно для вашей роли.');
        return;
    }
    _addColumnDialogOpen = true;

    var overlay = document.createElement('div');
    overlay.className = 'menu-modal-overlay open';
    overlay.id = 'addColumnOverlay';
    overlay.innerHTML = _buildAddColumnDialogHTML(prefillBuilding, prefillDay);
    document.body.appendChild(overlay);

    // Wire up building selector → room autocomplete update.
    var buildingSelect = overlay.querySelector('#addColBuilding');
    var daySelect = overlay.querySelector('#addColDay');
    var roomInput = overlay.querySelector('#addColRoom');

    // Initialize autocomplete for room input (items array is updated in-place on building change).
    _setAddColumnRoomItems(buildingSelect.value);
    _addColumnAutocompleteCtrl = _initRoomAutocomplete(roomInput, _addColumnRoomItems);

    if (buildingSelect) {
        buildingSelect.addEventListener('change', function() {
            _setAddColumnRoomItems(buildingSelect.value);
        });
    }

    // Submit button.
    var submitBtn = overlay.querySelector('#addColSubmit');
    if (submitBtn) {
        submitBtn.addEventListener('click', function() {
            _handleAddColumnSubmit(overlay, buildingSelect, daySelect, roomInput);
        });
    }

    // Cancel button.
    var cancelBtn = overlay.querySelector('#addColCancel');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', function() {
            _closeAddColumnDialog(overlay);
        });
    }

    // Click outside closes.
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) _closeAddColumnDialog(overlay);
    });

    // Escape closes.
    // Store handler at module level so _closeAddColumnDialog can remove it
    // even when the dialog is closed via Cancel/Submit (not only via Escape).
    _addColumnEscHandler = function(e) {
        if (e.key === 'Escape') {
            _closeAddColumnDialog(overlay);
        }
    };
    document.addEventListener('keydown', _addColumnEscHandler);
}

function _buildAddColumnDialogHTML(prefillBuilding, prefillDay) {
    // Build available buildings from DOM (schedule-container), fall back to BUILDING_ROOMS keys.
    var buildingMap = {};
    document.querySelectorAll('.schedule-container').forEach(function(c) {
        var b = c.getAttribute('data-building');
        if (b) buildingMap[b] = true;
    });
    if (Object.keys(buildingMap).length === 0 && BUILDING_ROOMS) {
        Object.keys(BUILDING_ROOMS).forEach(function(b) { buildingMap[b] = true; });
    }

    var buildings = Object.keys(buildingMap);
    if (prefillBuilding && buildings.indexOf(prefillBuilding) === -1) {
        buildings.unshift(prefillBuilding);
    }
    if (buildings.length === 0) {
        buildings = ['Villa', 'Kolibri'];
    }

    var days = (typeof MENU_DAYS !== 'undefined' && MENU_DAYS) ? MENU_DAYS : ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
    if (prefillDay && days.indexOf(prefillDay) === -1) {
        days = days.slice();
        days.unshift(prefillDay);
    }

    var selectedBuilding = prefillBuilding || buildings[0];
    var selectedDay = prefillDay || days[0];

    var buildingOptions = buildings.map(function(b) {
        var sel = (b === selectedBuilding) ? ' selected' : '';
        return '<option value="' + b + '"' + sel + '>' + b + '</option>';
    }).join('');

    var dayOptions = days.map(function(d) {
        var sel = (d === selectedDay) ? ' selected' : '';
        return '<option value="' + d + '"' + sel + '>' + d + '</option>';
    }).join('');

    var buildingDisabled = prefillBuilding ? ' disabled' : '';
    var dayDisabled = prefillDay ? ' disabled' : '';

    return [
        '<div class="menu-modal">',
        '  <p style="font-weight:600;margin-top:0;">Добавить колонку</p>',
        '  <div style="text-align:left;margin-bottom:12px;">',
        '    <label style="display:block;font-size:13px;margin-bottom:4px;">Здание</label>',
        '    <select id="addColBuilding"' + buildingDisabled + ' style="width:100%;padding:6px;font-size:13px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box;">',
        buildingOptions,
        '    </select>',
        '  </div>',
        '  <div style="text-align:left;margin-bottom:12px;">',
        '    <label style="display:block;font-size:13px;margin-bottom:4px;">День</label>',
        '    <select id="addColDay"' + dayDisabled + ' style="width:100%;padding:6px;font-size:13px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box;">',
        dayOptions,
        '    </select>',
        '  </div>',
        '  <div style="text-align:left;margin-bottom:16px;">',
        '    <label style="display:block;font-size:13px;margin-bottom:4px;">Кабинет</label>',
        '    <input id="addColRoom" type="text" placeholder="Введите название кабинета"',
        '           style="width:100%;padding:6px;font-size:13px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box;">',
        '  </div>',
        '  <div style="text-align:right;">',
        '    <button id="addColSubmit" class="menu-modal-btn-yes" style="margin-right:8px;">Вставить</button>',
        '    <button id="addColCancel" class="menu-modal-btn-cancel">Отмена</button>',
        '  </div>',
        '</div>'
    ].join('\n');
}

function _setAddColumnRoomItems(building) {
    // Pick the room list for this building from spiskiData (injected by html_javascript.py).
    var roomList = [];
    if (typeof spiskiData !== 'undefined' && spiskiData) {
        if (building === 'Villa') {
            roomList = spiskiData.rooms_Villa || [];
        } else if (building === 'Kolibri') {
            roomList = spiskiData.rooms_Kolibri || [];
        } else {
            // Try generic key or fall back to empty.
            roomList = spiskiData['rooms_' + building] || [];
        }
    }

    // Update the shared items array in-place to avoid re-attaching event listeners.
    _addColumnRoomItems.length = 0;
    roomList.forEach(function(r) { _addColumnRoomItems.push(r); });
}

function _initRoomAutocomplete(roomInput, items) {
    if (typeof createAutocompleteInput === 'function') {
        return createAutocompleteInput(roomInput, items, { allowCustom: false });
    }
    return null;
}

function _handleAddColumnSubmit(overlay, buildingSelect, daySelect, roomInput) {
    var building = buildingSelect.value;
    var day = daySelect.value;
    var room = (roomInput.value || '').trim();

    // Validate: non-empty.
    if (!room) {
        alert('Пожалуйста, введите название кабинета');
        roomInput.focus();
        return;
    }

    // Validate: no dangerous characters.
    if (/[<>"'&]/.test(room)) {
        alert('Название кабинета содержит недопустимые символы: < > & " \'');
        roomInput.focus();
        return;
    }

    // Call addColumnIfMissing — returns existing index if column already exists.
    var prevCount = -1;
    var container = (typeof BuildingService !== 'undefined')
        ? BuildingService.findScheduleContainerForBuilding(building)
        : null;
    if (container) {
        var table = container.querySelector('.schedule-grid');
        prevCount = table ? table.querySelectorAll('thead th.day-' + day).length : -1;
    }

    var colIndex = (typeof addColumnIfMissing === 'function')
        ? addColumnIfMissing(day, room, building)
        : -1;

    var newCount = -1;
    if (container) {
        var table2 = container.querySelector('.schedule-grid');
        newCount = table2 ? table2.querySelectorAll('thead th.day-' + day).length : -1;
    }

    var wasNew = (newCount > prevCount);

    if (wasNew) {
        if (typeof updateActivityPositions === 'function') {
            updateActivityPositions();
        }
        _showNotification('Добавлена колонка ' + day + ' ' + room);
    } else {
        _showNotification('Колонка ' + day + ' ' + room + ' уже существует');
    }

    _closeAddColumnDialog(overlay);
}

function _closeAddColumnDialog(overlay) {
    _addColumnDialogOpen = false;
    _addColumnAutocompleteCtrl = null;
    // Always remove the Escape handler — mirrors the hideMenuConfirmModal pattern.
    if (_addColumnEscHandler) {
        document.removeEventListener('keydown', _addColumnEscHandler);
        _addColumnEscHandler = null;
    }
    if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
    }
}

// === Core schedule creation logic ===
function _doCreateNewSchedule() {
    // Step 1: Remove all activity blocks from all containers
    document.querySelectorAll('.schedule-container .activity-block').forEach(function(b) {
        b.parentNode.removeChild(b);
    });

    // Step 2: Capture current grid row count before removing tables (keeps bounds consistent)
    var anyTable = document.querySelector('.schedule-container .schedule-grid');
    var rowCount = anyTable ? anyTable.querySelectorAll('tbody tr').length : null;

    // Step 3: Remove existing schedule-grid tables from all containers
    document.querySelectorAll('.schedule-container .schedule-grid').forEach(function(t) {
        t.parentNode.removeChild(t);
    });

    // Step 4: Rebuild tables for each building
    var containers = document.querySelectorAll('.schedule-container');
    containers.forEach(function(container) {
        var building = container.getAttribute('data-building');
        var rooms = BUILDING_ROOMS[building];
        if (!rooms) {
            console.warn('Нет конфигурации кабинетов для здания:', building);
            return;
        }

        var table = _buildFullTable(building, rooms, rowCount);
        container.appendChild(table);
    });

    // Step 6: Finalize
    if (typeof updateActivityPositions === 'function') {
        updateActivityPositions();
    }

    // Step 7: Reset day visibility to "all days visible"
    document.querySelectorAll('.toggle-day-button.active').forEach(function(btn) {
        btn.classList.remove('active');
    });
    MENU_DAYS.forEach(function(day) {
        document.querySelectorAll('th.day-' + day + ', td.day-' + day).forEach(function(cell) {
            cell.style.display = '';
        });
    });

    _showNotification('Создано новое пустое расписание');
}

// === Table builder ===
function _buildFullTable(building, rooms, rowCount) {
    var gStart = (typeof gridStart !== 'undefined') ? gridStart : 540;   // 09:00
    var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;
    var cellH = (typeof gridCellHeight !== 'undefined') ? gridCellHeight : 15;
    var dcw = (typeof dayCellWidth !== 'undefined') ? dayCellWidth : 100;
    var tcw = 80;

    // Prefer the rowCount derived from the old table to preserve actual gridEnd.
    var rowsCount = rowCount;
    if (!rowsCount || rowsCount <= 0) {
        var gEnd = 1200; // 20:00 fallback
        rowsCount = Math.floor((gEnd - gStart) / tInterval) + 1; // inclusive end
    }

    var table = document.createElement('table');
    table.className = 'schedule-grid';

    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');

    var timeTh = document.createElement('th');
    timeTh.className = 'time-cell';
    timeTh.textContent = 'Время';
    timeTh.style.width = tcw + 'px';
    headRow.appendChild(timeTh);

    MENU_DAYS.forEach(function(day) {
        for (var col = 0; col < rooms.length; col++) {
            var th = document.createElement('th');
            th.className = 'day-' + day;
            th.setAttribute('data-day', day);
            th.setAttribute('data-col', col);
            th.setAttribute('data-room', rooms[col]);
            th.innerHTML = day + '<br>' + rooms[col];
            th.style.width = dcw + 'px';
            headRow.appendChild(th);
        }
    });

    thead.appendChild(headRow);

    var tbody = document.createElement('tbody');
    var timeStep = Math.max(1, Math.floor(15 / tInterval));

    for (var r = 0; r < rowsCount; r++) {
        var tr = document.createElement('tr');

        var timeTd = document.createElement('td');
        timeTd.className = 'time-cell';
        timeTd.setAttribute('data-row', r);
        timeTd.setAttribute('data-col', 'time');
        timeTd.textContent = (r % timeStep === 0) ? _formatTime(gStart + r * tInterval) : '';
        timeTd.style.height = cellH + 'px';
        tr.appendChild(timeTd);

        MENU_DAYS.forEach(function(day) {
            for (var col = 0; col < rooms.length; col++) {
                var td = document.createElement('td');
                td.className = 'day-' + day;
                td.setAttribute('data-row', r);
                td.setAttribute('data-col', col);
                td.style.height = cellH + 'px';
                tr.appendChild(td);
            }
        });

        tbody.appendChild(tr);
    }

    table.appendChild(thead);
    table.appendChild(tbody);
    return table;
}

function _formatTime(minutes) {
    var h = Math.floor(minutes / 60);
    var m = minutes % 60;
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
}

// === Notification helper ===
function _showNotification(message) {
    var note = document.createElement('div');
    note.textContent = message;
    note.style.cssText = [
        'position:fixed',
        'bottom:30px',
        'left:50%',
        'transform:translateX(-50%)',
        'background:#333',
        'color:#fff',
        'padding:12px 24px',
        'border-radius:6px',
        'z-index:10200',
        'font-size:14px',
        'box-shadow:0 4px 12px rgba(0,0,0,0.25)'
    ].join(';');

    document.body.appendChild(note);
    setTimeout(function() {
        if (note.parentNode) note.parentNode.removeChild(note);
    }, 3000);
}

// === Initialization ===
function initMenu() {
    if (_menuInitialized) {
        return;
    }

    document.addEventListener('click', function(e) {
        var btn = document.getElementById('menuButton');
        var dd = document.getElementById('menuDropdown');
        if (!dd) return;
        if (btn && btn.contains(e.target)) return;
        if (dd.contains(e.target)) return;
        closeMenu();
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeMenu();
    });

    var lessonFilterMenuStyle = document.getElementById('lessonTypeFilterMenuStyle');
    if (!lessonFilterMenuStyle) {
        lessonFilterMenuStyle = document.createElement('style');
        lessonFilterMenuStyle.id = 'lessonTypeFilterMenuStyle';
        lessonFilterMenuStyle.textContent = [
            '.lesson-filter-item.lesson-filter-active {',
            '    background-color: #e0e8ff;',
            '    font-weight: bold;',
            '}'
        ].join('\n');
        document.head.appendChild(lessonFilterMenuStyle);
    }

    // === Lesson type filter section ===
    var dropdown = document.getElementById('menuDropdown');
    _initPublishMenuItem();
    _syncStructureMenuVisibility();
    if (dropdown && !dropdown.querySelector('.lesson-filter-item')) {
        var separator = document.createElement('div');
        separator.style.cssText = 'border-top: 1px solid #ccc; margin: 4px 0;';
        dropdown.appendChild(separator);

        var filterHeader = document.createElement('div');
        filterHeader.textContent = 'Тип занятий';
        filterHeader.style.cssText = 'padding: 6px 16px 2px; font-size: 11px; color: #888; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em;';
        dropdown.appendChild(filterHeader);

        var filterItems = [
            { label: 'Все занятия', value: 'all' },
            { label: 'Только групповые', value: 'group' },
            { label: 'Только индивидуальные', value: 'individual' },
            { label: 'Только наххильфе', value: 'nachhilfe' },
            { label: 'Пробные занятия', value: 'trial' },
            { label: 'Негрупповые', value: 'non-group' }
        ];

        filterItems.forEach(function(item) {
            var el = document.createElement('div');
            el.className = 'menu-item lesson-filter-item';
            el.setAttribute('data-filter', item.value);
            el.textContent = item.label;
            el.style.cssText = 'padding: 8px 16px; cursor: pointer;';

            el.addEventListener('click', function(e) {
                e.stopPropagation();
                if (typeof applyLessonTypeFilter === 'function') {
                    applyLessonTypeFilter(item.value);
                }
            });
            dropdown.appendChild(el);
        });

        var allItem = dropdown.querySelector('.lesson-filter-item[data-filter="all"]');
        if (allItem) {
            allItem.classList.add('lesson-filter-active');
        }
    }

    _menuInitialized = true;
}

// Exports
window.initMenu = initMenu;
window.toggleMenu = toggleMenu;
window.closeMenu = closeMenu;
window.handleNewSchedule = handleNewSchedule;
window.openAddColumnDialog = openAddColumnDialog;

(function() {
    function syncPublishVisibility() {
        _initPublishMenuItem();
        _syncStructureMenuVisibility();
        var publishItem = document.getElementById('menu-publish-item');
        if (publishItem && window.USER_ROLE !== 'admin') {
            publishItem.style.display = 'none';
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', syncPublishVisibility);
    } else {
        syncPublishVisibility();
    }
})();
