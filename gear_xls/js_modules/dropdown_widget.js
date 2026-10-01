// Module: dropdown_widget.js
// Single responsibility: reusable autocomplete-dropdown widget for block dialogs.
// Depends on: CSS classes .autocomplete-dropdown, .autocomplete-dropdown-item (from html_styles.py).
// Depends on: .menu-modal-overlay / .menu-modal CSS for confirmation dialog.
// Does NOT depend on spiskiData directly — callers pass the items array.

function createAutocompleteInput(inputElement, items, options) {
    options = options || {};
    var allowCustom = (options.allowCustom !== false); // default true
    if (options.placeholder) {
        inputElement.placeholder = options.placeholder;
    }

    // Disable native browser history/autofill popups. We keep only the custom dropdown.
    inputElement.setAttribute('autocomplete', 'off');
    inputElement.autocomplete = 'off';
    inputElement.setAttribute('autocorrect', 'off');
    inputElement.setAttribute('autocapitalize', 'off');
    inputElement.setAttribute('spellcheck', 'false');
    inputElement.setAttribute('data-lpignore', 'true');
    if (inputElement.form) {
        inputElement.form.setAttribute('autocomplete', 'off');
    }

    // Ensure the parent has position:relative so the dropdown can be absolute-positioned below.
    var wrapper = inputElement.parentNode;
    if (wrapper && window.getComputedStyle(wrapper).position === 'static') {
        wrapper.style.position = 'relative';
    }

    var dropdownEl = null;
    var highlightedIndex = -1;
    var _blurPending = false;
    var _docClickHandler = null;

    function _isInputConnected() {
        if (!inputElement) return false;
        if (typeof inputElement.isConnected === 'boolean') return inputElement.isConnected;
        return document.body && document.body.contains(inputElement);
    }

    function _getFilteredItems() {
        var val = inputElement.value.toLowerCase();
        if (!val) return items.slice();
        return items.filter(function(it) {
            return it.toLowerCase().indexOf(val) !== -1;
        });
    }

    function _showDropdown() {
        _hideDropdown();
        var filtered = _getFilteredItems();
        if (filtered.length === 0) return;

        dropdownEl = document.createElement('div');
        dropdownEl.className = 'autocomplete-dropdown';
        var parent = inputElement.parentNode;
        if (parent) {
            var inputRect = inputElement.getBoundingClientRect();
            var parentRect = parent.getBoundingClientRect();
            dropdownEl.style.left = (inputRect.left - parentRect.left) + 'px';
            dropdownEl.style.top = (inputRect.bottom - parentRect.top) + 'px';
            dropdownEl.style.width = inputRect.width + 'px';
        }

        filtered.forEach(function(item, idx) {
            var div = document.createElement('div');
            div.className = 'autocomplete-dropdown-item';
            div.textContent = item;
            div.addEventListener('mousedown', function(e) {
                // Use mousedown (fires before blur) to capture click before focus is lost.
                e.preventDefault();
                inputElement.value = item;
                _hideDropdown();
                _blurPending = false;
            });
            div.addEventListener('mouseover', function() {
                _setHighlight(idx);
            });
            dropdownEl.appendChild(div);
        });

        // Position below the input: insert right after the input to avoid falling below hints/other elements.
        if (parent) {
            var nextEl = inputElement.nextElementSibling;
            if (nextEl) parent.insertBefore(dropdownEl, nextEl);
            else parent.appendChild(dropdownEl);
        }
        _setHighlight(-1);
    }

    function _hideDropdown() {
        if (dropdownEl && dropdownEl.parentNode) {
            dropdownEl.parentNode.removeChild(dropdownEl);
        }
        dropdownEl = null;
        highlightedIndex = -1;
    }

    function _setHighlight(idx) {
        if (!dropdownEl) return;
        var items2 = dropdownEl.querySelectorAll('.autocomplete-dropdown-item');
        items2.forEach(function(el) { el.classList.remove('highlighted'); });
        highlightedIndex = idx;
        if (idx >= 0 && idx < items2.length) {
            items2[idx].classList.add('highlighted');
            items2[idx].scrollIntoView({ block: 'nearest' });
        }
    }

    inputElement.addEventListener('focus', function() {
        _showDropdown();
    });

    inputElement.addEventListener('input', function() {
        _showDropdown();
    });

    inputElement.addEventListener('keydown', function(e) {
        if (!dropdownEl) {
            if (e.key === 'ArrowDown') { _showDropdown(); return; }
            return;
        }
        var itemEls = dropdownEl.querySelectorAll('.autocomplete-dropdown-item');
        var count = itemEls.length;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            _setHighlight(Math.min(highlightedIndex + 1, count - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            _setHighlight(Math.max(highlightedIndex - 1, -1));
        } else if (e.key === 'Enter') {
            if (highlightedIndex >= 0 && highlightedIndex < count) {
                e.preventDefault();
                inputElement.value = itemEls[highlightedIndex].textContent;
                _hideDropdown();
                _blurPending = false;
            }
        } else if (e.key === 'Escape') {
            _hideDropdown();
        }
    });

    inputElement.addEventListener('blur', function() {
        // Delay to allow mousedown on dropdown items to fire first.
        _blurPending = true;
        setTimeout(function() {
            if (!_blurPending) return;
            // If the dialog/input was removed from DOM (e.g. user cancelled),
            // do not show confirmation modals after close.
            if (!_isInputConnected()) {
                _blurPending = false;
                _hideDropdown();
                return;
            }
            _blurPending = false;
            _hideDropdown();
            _handleBlurConfirmation();
        }, 180);
    });

    // Close dropdown when clicking outside.
    _docClickHandler = function(e) {
        // Auto-cleanup: dialogs get removed often; avoid accumulating global handlers.
        if (!_isInputConnected()) {
            document.removeEventListener('click', _docClickHandler);
            _docClickHandler = null;
            return;
        }
        if (dropdownEl && !dropdownEl.contains(e.target) && e.target !== inputElement) {
            _hideDropdown();
        }
    };
    document.addEventListener('click', _docClickHandler);

    function _handleBlurConfirmation() {
        if (!allowCustom) return;
        var val = inputElement.value.trim();
        if (!val) return;

        // Check exact match (case-insensitive).
        var lowerVal = val.toLowerCase();
        var alreadyInList = items.some(function(it) {
            return it.toLowerCase() === lowerVal;
        });
        if (alreadyInList) return;

        // Show confirmation using existing showMenuConfirmModal pattern.
        // We need a version with custom button labels. Build a lightweight inline modal.
        _showAddConfirmModal(
            'Данное значение отсутствует в списке. Добавить введённое Вами значение как ещё один элемент списка?',
            'Да, добавить',
            'Нет',
            function() {
                // "Yes" — add to in-memory list.
                addItem(val);
                if (typeof options.onAddItem === 'function') options.onAddItem(val);
                // Persist to server so the value survives HTML regeneration.
                if (options.spiskiKey) {
                    _persistSpiskiToServer(options.spiskiKey, val);
                }
            },
            function() {
                // "No" — keep value in field, do nothing.
            }
        );
    }

    function _showAddConfirmModal(message, yesLabel, noLabel, onYes, onNo) {
        // Build an overlay identical in structure to .menu-modal-overlay / .menu-modal.
        var overlay = document.createElement('div');
        overlay.className = 'menu-modal-overlay open';
        overlay.innerHTML = [
            '<div class="menu-modal">',
            '  <p>' + message + '</p>',
            '  <button class="menu-modal-btn-yes">' + yesLabel + '</button>',
            '  <button class="menu-modal-btn-cancel">' + noLabel + '</button>',
            '</div>'
        ].join('');
        document.body.appendChild(overlay);

        function escHandler(e) {
            if (e.key === 'Escape') {
                _close();
            }
        }

        function _close() {
            document.removeEventListener('keydown', escHandler);
            if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        }

        overlay.querySelector('.menu-modal-btn-yes').addEventListener('click', function() {
            _close();
            if (typeof onYes === 'function') onYes();
        });
        overlay.querySelector('.menu-modal-btn-cancel').addEventListener('click', function() {
            _close();
            if (typeof onNo === 'function') onNo();
        });
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) _close();
        });

        document.addEventListener('keydown', escHandler);
    }

    function addItem(value) {
        var trimmed = (value || '').trim();
        if (!trimmed) return;
        // Push to the shared items array (mutates in-place so all widget instances sharing the same
        // array reference see the update immediately).
        var lowerTrimmed = trimmed.toLowerCase();
        var exists = items.some(function(it) { return it.toLowerCase() === lowerTrimmed; });
        if (!exists) {
            items.push(trimmed);
            sortStringListInPlace(items);
        }
    }

    function getItems() {
        return items;
    }

    return {
        input: inputElement,
        getItems: getItems,
        addItem: addItem
    };
}

window.createAutocompleteInput = createAutocompleteInput;

function sortStringListInPlace(list) {
    if (!Array.isArray(list)) return;
    var collator = (typeof Intl !== 'undefined' && typeof Intl.Collator === 'function')
        ? new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
        : null;

    list.sort(function(a, b) {
        var sa = (a || '').toString();
        var sb = (b || '').toString();
        if (collator) return collator.compare(sa, sb);
        var la = sa.toLowerCase();
        var lb = sb.toLowerCase();
        if (la < lb) return -1;
        if (la > lb) return 1;
        return 0;
    });
}

// Shared helpers for building-specific room lists.
// Used by block_creation_dialog.js and editing_update.js (both load after dropdown_widget).
function getRoomListForBuilding(buildingName) {
    if (typeof spiskiData === 'undefined' || !spiskiData) return [];
    if (buildingName === 'Villa') return spiskiData.rooms_Villa || [];
    if (buildingName === 'Kolibri') return spiskiData.rooms_Kolibri || [];
    return spiskiData['rooms_' + buildingName] || [];
}

function addUniqueToList(list, value) {
    var v = (value || '').trim();
    if (!v) return;
    var lower = v.toLowerCase();
    var exists = list.some(function(it) { return (it || '').toLowerCase() === lower; });
    if (!exists) {
        list.push(v);
        sortStringListInPlace(list);
    }
}

function addRoomToBuildingList(buildingName, value) {
    var list = getRoomListForBuilding(buildingName);
    if (!Array.isArray(list)) return;
    addUniqueToList(list, value);
}

window.getRoomListForBuilding = getRoomListForBuilding;
window.sortStringListInPlace = sortStringListInPlace;
window.addUniqueToList = addUniqueToList;
window.addRoomToBuildingList = addRoomToBuildingList;

// Persist a new value to the server so it survives HTML regeneration.
// Fire-and-forget: does not block UI on network errors.
function _persistSpiskiToServer(spiskiKey, value) {
    if (!spiskiKey || !value) return;
    fetch('/api/spiski/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: spiskiKey, value: value })
    }).then(function(r) {
        if (!r.ok) console.warn('persistSpiskiToServer: server error', r.status);
    }).catch(function(err) {
        console.warn('persistSpiskiToServer: network error', err);
    });
}

window._persistSpiskiToServer = _persistSpiskiToServer;
