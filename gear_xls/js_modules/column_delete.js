// Модуль удаления колонок и кнопок удаления в заголовках расписания

function removeColumn(building, day, colIndex) {
    // Step 1: Find container and table.
    var container = BuildingService.findScheduleContainerForBuilding(building);
    if (!container) {
        console.error('removeColumn: container not found for', building);
        return;
    }
    var table = container.querySelector('.schedule-grid');
    if (!table) {
        console.error('removeColumn: no schedule-grid in', building);
        return;
    }

    // Normalize header metadata before removal so the old index->room mapping
    // is built from the current logical column order, not raw DOM position.
    if (typeof refreshDayHeaderMetadata === 'function') {
        refreshDayHeaderMetadata(table, day);
    }

    // Step 2: Guard: do not remove the last column of a day.
    var dayHeaders = Array.from(table.querySelectorAll('thead th.day-' + day));
    if (dayHeaders.length <= 1) {
        alert('Невозможно удалить последнюю колонку дня ' + day);
        return;
    }

    // Step 3: Resolve the target <th> element.
    var targetTh = dayHeaders[colIndex];
    if (!targetTh) {
        console.error('removeColumn: colIndex out of range', colIndex, dayHeaders.length);
        return;
    }

    // Pre-removal mapping approach: old index -> room name.
    var oldIndexToRoom = {};
    dayHeaders.forEach(function(th, i) {
        oldIndexToRoom[i] = extractRoomFromDayHeader(th, day);
    });

    // Step 4: Find the absolute column index in the full <thead><tr>.
    var headRow = table.querySelector('thead tr');
    var absColIndex = Array.from(headRow.children).indexOf(targetTh);

    // Step 5: Remove all .activity-block elements in this column.
    var blocksToRemove = Array.from(
        container.querySelectorAll('.activity-block[data-day="' + day + '"][data-building="' + building + '"]')
    ).filter(function(b) {
        return parseInt(b.getAttribute('data-col-index'), 10) === colIndex;
    });
    blocksToRemove.forEach(function(b) {
        if (b.parentNode) {
            b.parentNode.removeChild(b);
        }
    });

    // Step 6: Remove the <th> from <thead>.
    headRow.removeChild(targetTh);

    // Step 7: Remove <td> at absColIndex from every <tbody><tr>.
    var bodyRows = table.querySelectorAll('tbody tr');
    bodyRows.forEach(function(row) {
        var cell = row.children[absColIndex];
        if (cell) row.removeChild(cell);
    });

    // Step 8: Recalculate data-col on remaining <td class="day-{day}"> cells.
    bodyRows.forEach(function(row) {
        var dayCells = Array.from(row.querySelectorAll('td.day-' + day));
        dayCells.forEach(function(td, idx) {
            td.setAttribute('data-col', idx);
        });
    });

    // After DOM removal, rebuild header metadata so remaining columns expose
    // consistent day-local data-col/data-room attributes.
    if (typeof refreshDayHeaderMetadata === 'function') {
        refreshDayHeaderMetadata(table, day);
    }

    // Step 9: Recalculate data-col-index on remaining blocks for this day.
    var updatedDayHeaders = Array.from(table.querySelectorAll('thead th.day-' + day));
    var survivingBlocks = container.querySelectorAll(
        '.activity-block[data-day="' + day + '"][data-building="' + building + '"]'
    );
    survivingBlocks.forEach(function(block) {
        var oldColIdx = parseInt(block.getAttribute('data-col-index'), 10);
        var room = oldIndexToRoom[oldColIdx] || '';
        var newIdx = -1;

        for (var i = 0; i < updatedDayHeaders.length; i++) {
            if (extractRoomFromDayHeader(updatedDayHeaders[i], day) === room) {
                newIdx = i;
                break;
            }
        }

        if (newIdx >= 0) {
            block.setAttribute('data-col-index', newIdx);
        } else {
            console.warn('removeColumn: could not remap block room', room, 'in day', day);
        }
    });

    // Step 10: No container width sync is needed: horizontal scroll lives inside the container.

    // Step 11: Call updateActivityPositions().
    if (typeof updateActivityPositions === 'function') {
        updateActivityPositions();
    }
}

function initColumnDeleteButtons() {
    _attachDeleteButtonsToExistingHeaders();

    if (window.__columnDeleteObserverInitialized) return;
    window.__columnDeleteObserverInitialized = true;

    // Watch for new headers/tables added anywhere in the document
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (!node || node.nodeType !== 1) return;

                // Direct TH node
                if (node.nodeName === 'TH' && !node.classList.contains('time-cell')) {
                    _attachDeleteButtonToHeader(node);
                    return;
                }

                // node itself IS the .schedule-grid (e.g. after full table replace)
                if (node.classList && node.classList.contains('schedule-grid')) {
                    node.querySelectorAll('thead th').forEach(function(th) {
                        if (!th.classList.contains('time-cell')) {
                            _attachDeleteButtonToHeader(th);
                        }
                    });
                    return;
                }

                // Any other subtree that contains headers
                if (node.querySelectorAll) {
                    node.querySelectorAll('.schedule-grid thead th').forEach(function(th) {
                        if (!th.classList.contains('time-cell')) {
                            _attachDeleteButtonToHeader(th);
                        }
                    });
                }
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
}

function initColumnAddButtons() {
    _attachAddButtonsToExistingHeaders();

    if (window.__columnAddObserverInitialized) return;
    window.__columnAddObserverInitialized = true;

    // Reuse the same MutationObserver strategy as initColumnDeleteButtons.
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (!node || node.nodeType !== 1) return;

                if (node.nodeName === 'TH' && !node.classList.contains('time-cell')) {
                    _attachAddButtonToHeader(node);
                    return;
                }

                if (node.classList && node.classList.contains('schedule-grid')) {
                    node.querySelectorAll('thead th').forEach(function(th) {
                        if (!th.classList.contains('time-cell')) {
                            _attachAddButtonToHeader(th);
                        }
                    });
                    return;
                }

                if (node.querySelectorAll) {
                    node.querySelectorAll('.schedule-grid thead th').forEach(function(th) {
                        if (!th.classList.contains('time-cell')) {
                            _attachAddButtonToHeader(th);
                        }
                    });
                }
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
}

function _attachAddButtonsToExistingHeaders() {
    document.querySelectorAll('.schedule-grid thead th').forEach(function(th) {
        if (!th.classList.contains('time-cell')) {
            _attachAddButtonToHeader(th);
        }
    });
}

function _attachDeleteButtonsToExistingHeaders() {
    document.querySelectorAll('.schedule-grid thead th').forEach(function(th) {
        if (!th.classList.contains('time-cell')) {
            _attachDeleteButtonToHeader(th);
        }
    });
}

function _attachDeleteButtonToHeader(th) {
    // Avoid double-attaching
    if (th.querySelector('.col-delete-btn')) return;

    var btn = document.createElement('button');
    btn.className = 'col-delete-btn';
    // Important: do NOT put "×" as a DOM text node inside <th>.
    // extractRoomFromDayHeader() parses headerElement.innerHTML and would include the button text.
    // Render the "×" via CSS ::before instead.
    btn.textContent = '';
    btn.title = 'Удалить колонку';

    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        _onDeleteColumnClick(th);
    });

    th.appendChild(btn);
}

function _attachAddButtonToHeader(th) {
    // Avoid double-attaching.
    if (th.querySelector('.col-add-btn')) return;

    var btn = document.createElement('button');
    btn.className = 'col-add-btn';
    // Do NOT put '+' as a DOM text node inside <th>.
    // extractRoomFromDayHeader() parses innerHTML and would include that text.
    // Render '+' via CSS ::before instead.
    btn.textContent = '';
    btn.title = 'Добавить колонку';

    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        // If any edit dialog is open, ignore the click.
        if (window.editDialogOpen) return;
        _onAddColumnClick(th);
    });

    th.appendChild(btn);
}

function _onAddColumnClick(th) {
    var container = th.closest('.schedule-container');
    if (!container) return;
    var building = container.getAttribute('data-building');

    var dayClass = Array.from(th.classList).find(function(cls) {
        return cls.startsWith('day-');
    });
    if (!dayClass) return;
    var day = dayClass.replace('day-', '');

    // openAddColumnDialog is defined in menu.js (Phase 8-05).
    // Guard with typeof check to degrade gracefully if menu.js is not loaded.
    if (typeof openAddColumnDialog === 'function') {
        openAddColumnDialog(building, day);
    } else {
        console.warn('_onAddColumnClick: openAddColumnDialog not available yet');
    }
}

function _onDeleteColumnClick(th) {
    // Determine building, day, colIndex from the <th>
    var container = th.closest('.schedule-container');
    if (!container) return;
    var building = container.getAttribute('data-building');

    // Find which day this <th> belongs to
    var dayClass = Array.from(th.classList).find(function(cls) {
        return cls.startsWith('day-');
    });
    if (!dayClass) return;
    var day = dayClass.replace('day-', '');

    // Find colIndex among th.day-{day} in this container
    var dayHeaders = Array.from(container.querySelectorAll('.schedule-grid thead th.day-' + day));
    // Prefer the logical local index stored on the header; DOM index alone is
    // more fragile once columns are dynamically inserted/removed.
    var colIndex = typeof getHeaderLocalColumnIndex === 'function'
        ? getHeaderLocalColumnIndex(th, dayHeaders.indexOf(th))
        : dayHeaders.indexOf(th);
    if (colIndex < 0) return;

    // Guard: last column
    if (dayHeaders.length <= 1) {
        alert('Невозможно удалить последнюю колонку дня ' + day);
        return;
    }

    var room = extractRoomFromDayHeader(th, day);
    var confirmed = confirm('Удалить колонку ' + day + ' ' + room + '? Все блоки в этой колонке будут удалены.');
    if (!confirmed) return;

    removeColumn(building, day, colIndex);
}

window.removeColumn = removeColumn;
window.initColumnDeleteButtons = initColumnDeleteButtons;
window.initColumnAddButtons = initColumnAddButtons;
