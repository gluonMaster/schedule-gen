(function () {
    "use strict";

    var COMPACT_ROW_PADDING = 3;
    var COMPACT_EMPTY_MINUTES = 60;
    var COMPACT_HIDDEN_ROW_CLASS = "schedgen-compact-hidden-row";
    var COMPACT_EMPTY_NOTE_CLASS = "schedgen-compact-empty-note";
    var STYLE_ATTR = "data-schedgen-compact-rows-style";

    var initialized = false;
    var positionRaf = 0;
    var mutationObserver = null;
    var mutationRaf = 0;
    var interactionPauseCount = 0;
    var pendingRefresh = false;
    var pauseReasons = Object.create(null);
    var compactRangeByContainer = new WeakMap();
    var noteByContainer = new WeakMap();
    var OBSERVED_ACTIVITY_ATTRIBUTES = [
        "data-day",
        "data-building",
        "data-start-row",
        "data-row-span",
        "data-lesson-type",
        "data-col-index",
        "style"
    ];

    function injectCompactRowsStyle() {
        var style;

        if (document.querySelector("style[" + STYLE_ATTR + '="true"]')) {
            return;
        }

        style = document.createElement("style");
        style.setAttribute(STYLE_ATTR, "true");
        style.textContent = [
            "." + COMPACT_HIDDEN_ROW_CLASS + " { display: none !important; }",
            "." + COMPACT_EMPTY_NOTE_CLASS + " {",
            "  margin: 8px 0;",
            "  padding: 8px 10px;",
            "  font-size: 13px;",
            "  border-radius: 6px;",
            "  background: #fff8e1;",
            "  border: 1px solid #ffe082;",
            "  color: #5d4a00;",
            "}",
            "." + COMPACT_EMPTY_NOTE_CLASS + ".is-hidden { display: none !important; }"
        ].join("\n");

        document.head.appendChild(style);
    }

    function isSearchActive() {
        var search = window.ScheduleSearch;

        return !!(
            search &&
            typeof search.isActive === "function" &&
            search.isActive()
        );
    }

    function isEditModeActive() {
        var authUi = window.SchedGenAuthUI;

        return !!(
            authUi &&
            typeof authUi.isEditMode === "function" &&
            authUi.isEditMode()
        );
    }

    function isAddModeActive() {
        var addModeButton = document.getElementById("toggle-add-mode");

        return !!(addModeButton && addModeButton.classList.contains("active"));
    }

    function isCompactRowsSuspended() {
        return isSearchActive() || isEditModeActive() || isAddModeActive();
    }

    function hideAllEmptyNotes() {
        document
            .querySelectorAll("." + COMPACT_EMPTY_NOTE_CLASS)
            .forEach(function (note) {
                note.classList.add("is-hidden");
            });
    }

    function isActivityBlock(node) {
        return !!(
            node &&
            node.nodeType === 1 &&
            node.classList &&
            node.classList.contains("activity-block")
        );
    }

    function containsActivityBlock(node) {
        if (isActivityBlock(node)) {
            return true;
        }

        return !!(
            node &&
            node.nodeType === 1 &&
            typeof node.querySelector === "function" &&
            node.querySelector(".activity-block")
        );
    }

    function getInlineDisplayValue(styleText) {
        var match = String(styleText || "").match(/(?:^|;)\s*display\s*:\s*([^;]+)/i);
        return match ? match[1].trim().toLowerCase() : "";
    }

    function isRelevantActivityAttributeMutation(mutation) {
        if (!isActivityBlock(mutation.target)) {
            return false;
        }

        if (mutation.attributeName !== "style") {
            return OBSERVED_ACTIVITY_ATTRIBUTES.indexOf(mutation.attributeName) !== -1 &&
                mutation.oldValue !== mutation.target.getAttribute(mutation.attributeName);
        }

        return getInlineDisplayValue(mutation.oldValue) !== getInlineDisplayValue(mutation.target.getAttribute("style"));
    }

    function isRelevantActivityMutation(mutation) {
        var i;

        if (mutation.type === "attributes") {
            return isRelevantActivityAttributeMutation(mutation);
        }

        if (mutation.type !== "childList") {
            return false;
        }

        for (i = 0; i < mutation.addedNodes.length; i += 1) {
            if (containsActivityBlock(mutation.addedNodes[i])) {
                return true;
            }
        }
        for (i = 0; i < mutation.removedNodes.length; i += 1) {
            if (containsActivityBlock(mutation.removedNodes[i])) {
                return true;
            }
        }

        return false;
    }

    function scheduleRefreshFromMutation() {
        if (interactionPauseCount > 0) {
            pendingRefresh = true;
            return;
        }

        if (mutationRaf) {
            return;
        }

        mutationRaf = window.requestAnimationFrame(function () {
            mutationRaf = 0;
            refreshCompactRows();
        });
    }

    function handleObservedMutations(mutations) {
        if (!mutations.some(isRelevantActivityMutation)) {
            return;
        }

        scheduleRefreshFromMutation();
    }

    function ensureMutationObserver() {
        var target;

        if (mutationObserver || typeof window.MutationObserver !== "function") {
            return;
        }

        target = document.body || document.querySelector(".schedule-container");
        if (!target) {
            return;
        }

        mutationObserver = new MutationObserver(handleObservedMutations);
        mutationObserver.observe(target, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeOldValue: true,
            attributeFilter: OBSERVED_ACTIVITY_ATTRIBUTES
        });
    }

    function updatePositionsSoon() {
        if (positionRaf) {
            return;
        }

        positionRaf = window.requestAnimationFrame(function () {
            positionRaf = 0;
            if (typeof window.updateActivityPositions === "function") {
                window.updateActivityPositions();
            }
        });
    }

    function resetAllCompactRanges() {
        document
            .querySelectorAll(".schedule-container[data-building]")
            .forEach(function (container) {
                compactRangeByContainer.delete(container);
            });
    }

    function clearCompactRows(options) {
        var config = options || {};

        document
            .querySelectorAll("." + COMPACT_HIDDEN_ROW_CLASS)
            .forEach(function (row) {
                row.classList.remove(COMPACT_HIDDEN_ROW_CLASS);
            });

        hideAllEmptyNotes();

        if (!config.preserveRanges) {
            resetAllCompactRanges();
        }

        if (config.updatePositions) {
            updatePositionsSoon();
        }
    }

    function getBuildingName(container) {
        return container.getAttribute("data-building") || "unknown";
    }

    function getGlobalTimeInterval() {
        var value = null;

        if (typeof timeInterval !== "undefined") {
            value = Number(timeInterval);
        } else if (typeof window.timeInterval !== "undefined") {
            value = Number(window.timeInterval);
        }

        if (!isFinite(value) || value <= 0) {
            value = 5;
        }

        return value;
    }

    function collectRowMap(table) {
        var rowMap = new Map();
        var maxRow = null;

        if (!table) {
            return {
                rowMap: rowMap,
                maxRow: maxRow
            };
        }

        table.querySelectorAll("tbody tr").forEach(function (row) {
            var rowCell = row.querySelector("td[data-row]");
            var rowIndex;

            if (!rowCell) {
                return;
            }

            rowIndex = parseInt(rowCell.getAttribute("data-row"), 10);
            if (isNaN(rowIndex)) {
                return;
            }

            rowMap.set(rowIndex, row);
            if (maxRow === null || rowIndex > maxRow) {
                maxRow = rowIndex;
            }
        });

        return {
            rowMap: rowMap,
            maxRow: maxRow
        };
    }

    function getConfiguredDaysOrder() {
        var source = null;

        if (typeof daysOrder !== "undefined" && Array.isArray(daysOrder)) {
            source = daysOrder;
        } else if (Array.isArray(window.daysOrder)) {
            source = window.daysOrder;
        }

        return source ? source.slice() : [];
    }

    function pushUnique(list, value) {
        if (value && list.indexOf(value) === -1) {
            list.push(value);
        }
    }

    function collectDomDays(container, table) {
        var days = [];
        var root = table || container;

        getConfiguredDaysOrder().forEach(function (day) {
            pushUnique(days, day);
        });

        root.querySelectorAll("th[data-day], td[class*='day-']").forEach(function (cell) {
            var dataDay = cell.getAttribute("data-day");

            if (dataDay) {
                pushUnique(days, dataDay);
                return;
            }

            Array.prototype.forEach.call(cell.classList || [], function (className) {
                var match = className.match(/^day-(.+)$/);
                if (match) {
                    pushUnique(days, match[1]);
                }
            });
        });

        container.querySelectorAll(".activity-block[data-day]").forEach(function (block) {
            pushUnique(days, block.getAttribute("data-day"));
        });

        return days;
    }

    function hasActiveHiddenDayButton(day) {
        var hidden = false;

        document.querySelectorAll(".toggle-day-button.active").forEach(function (button) {
            if (button.getAttribute("data-day") === day) {
                hidden = true;
            }
        });

        return hidden;
    }

    function isElementDisplayed(element) {
        return window.getComputedStyle(element).display !== "none";
    }

    function areAllHidden(elements) {
        if (!elements.length) {
            return false;
        }

        return elements.every(function (element) {
            return !isElementDisplayed(element);
        });
    }

    function hasDisplayedElement(elements) {
        return elements.some(function (element) {
            return isElementDisplayed(element);
        });
    }

    function collectVisibleDays(container, table) {
        var days = collectDomDays(container, table);

        return days.filter(function (day) {
            var headers = Array.from(table.querySelectorAll("th.day-" + day));
            var cells = Array.from(table.querySelectorAll("td.day-" + day));

            if (hasActiveHiddenDayButton(day)) {
                return false;
            }
            if (!headers.length && !cells.length) {
                return false;
            }
            if (areAllHidden(headers)) {
                return false;
            }
            if (areAllHidden(cells)) {
                return false;
            }

            return hasDisplayedElement(headers) || hasDisplayedElement(cells);
        });
    }

    function isFiniteNumber(value) {
        return typeof value === "number" && isFinite(value);
    }

    function parseCoordinate(rawValue) {
        var value = parseInt(rawValue, 10);
        return isNaN(value) ? null : value;
    }

    function resolveBlockCoordinates(block, table) {
        var rawStart = block.getAttribute("data-start-row");
        var rawSpan = block.getAttribute("data-row-span");
        var startRow = parseCoordinate(rawStart);
        var rowSpan = parseCoordinate(rawSpan);
        var startMissing = rawStart === null || rawStart === "";
        var spanMissing = rawSpan === null || rawSpan === "";
        var derived;

        if (startMissing && typeof deriveStartRowFromBlock === "function") {
            derived = deriveStartRowFromBlock(block, table);
            startRow = parseCoordinate(derived);
        }

        if (spanMissing && typeof deriveRowSpanFromBlock === "function") {
            derived = deriveRowSpanFromBlock(block);
            rowSpan = parseCoordinate(derived);
        }

        return {
            startRow: startRow,
            rowSpan: rowSpan,
            startMissing: startMissing,
            spanMissing: spanMissing
        };
    }

    function validateBlockCoordinates(coords, maxRow) {
        var startRow = coords.startRow;
        var rowSpan = coords.rowSpan;
        var endRow;

        if (!isFiniteNumber(startRow)) {
            return "Invalid startRow";
        }
        if (!isFiniteNumber(rowSpan)) {
            return "Invalid rowSpan";
        }
        if (startRow < 0) {
            return "startRow below grid";
        }
        if (rowSpan <= 0) {
            return "rowSpan must be positive";
        }

        endRow = startRow + rowSpan;
        if (!isFiniteNumber(endRow) || endRow <= startRow) {
            return "Invalid endRow";
        }
        if (startRow > maxRow) {
            return "startRow beyond grid";
        }
        if (endRow > maxRow + 1) {
            return "endRow beyond grid";
        }

        return null;
    }

    function collectConsideredBlocks(container, table, visibleDays, maxRow) {
        var visibleDaySet = new Set(visibleDays);
        var result = {
            blocks: [],
            hasInvalidVisibleBlock: false,
            invalidBlock: null,
            invalidDay: null,
            reason: ""
        };

        container.querySelectorAll(".activity-block").forEach(function (block) {
            var day;
            var coords;
            var invalidReason;

            if (result.hasInvalidVisibleBlock) {
                return;
            }

            day = block.getAttribute("data-day");
            if (!visibleDaySet.has(day)) {
                return;
            }
            if (block.classList.contains("lesson-type-filter-hidden")) {
                return;
            }
            if (window.getComputedStyle(block).display === "none") {
                return;
            }

            coords = resolveBlockCoordinates(block, table);
            invalidReason = validateBlockCoordinates(coords, maxRow);
            if (invalidReason) {
                result.hasInvalidVisibleBlock = true;
                result.invalidBlock = block;
                result.invalidDay = day;
                result.reason = invalidReason;
                return;
            }

            result.blocks.push({
                block: block,
                day: day,
                startRow: coords.startRow,
                endRow: coords.startRow + coords.rowSpan
            });
        });

        return result;
    }

    function getContainerNote(container) {
        var note = noteByContainer.get(container);

        if (note && document.documentElement.contains(note)) {
            return note;
        }

        note = document.createElement("div");
        note.className = COMPACT_EMPTY_NOTE_CLASS + " is-hidden";
        note.setAttribute("role", "status");
        note.setAttribute("aria-live", "polite");

        container.parentNode.insertBefore(note, container);
        noteByContainer.set(container, note);

        return note;
    }

    function showEmptyNote(container, message) {
        var note = getContainerNote(container);

        note.textContent = message;
        note.classList.remove("is-hidden");
    }

    function hideEmptyNote(container) {
        var note = noteByContainer.get(container);

        if (note) {
            note.classList.add("is-hidden");
        }
    }

    function applyRange(container, rowMap, firstVisibleRow, lastVisibleRow) {
        rowMap.forEach(function (row, rowIndex) {
            row.classList.toggle(
                COMPACT_HIDDEN_ROW_CLASS,
                rowIndex < firstVisibleRow || rowIndex > lastVisibleRow
            );
        });
    }

    function getScrollContainer(container) {
        var current = container;

        while (current && current !== document.body && current !== document.documentElement) {
            var style = window.getComputedStyle(current);
            var overflowY = style.overflowY;

            if (
                (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") &&
                current.scrollHeight > current.clientHeight
            ) {
                return current;
            }

            current = current.parentElement;
        }

        return container;
    }

    function scrollContainerToCompactStartIfRangeChanged(container, firstVisibleRow, lastVisibleRow) {
        var previous = compactRangeByContainer.get(container);
        var changed = !previous ||
            previous.firstVisibleRow !== firstVisibleRow ||
            previous.lastVisibleRow !== lastVisibleRow;
        var scrollContainer;

        compactRangeByContainer.set(container, {
            firstVisibleRow: firstVisibleRow,
            lastVisibleRow: lastVisibleRow
        });

        if (!changed) {
            return;
        }

        scrollContainer = getScrollContainer(container);
        scrollContainer.scrollTop = 0;
    }

    function applyEmptyRange(container, rowMap, maxRow, message) {
        var emptyRowsToShow = Math.max(1, Math.ceil(COMPACT_EMPTY_MINUTES / getGlobalTimeInterval()));
        var firstVisibleRow = 0;
        var lastVisibleRow = Math.min(maxRow, emptyRowsToShow - 1);

        applyRange(container, rowMap, firstVisibleRow, lastVisibleRow);
        showEmptyNote(container, message);
        scrollContainerToCompactStartIfRangeChanged(container, firstVisibleRow, lastVisibleRow);
    }

    function failOpenContainer(container, reason, detail) {
        container
            .querySelectorAll("." + COMPACT_HIDDEN_ROW_CLASS)
            .forEach(function (row) {
                row.classList.remove(COMPACT_HIDDEN_ROW_CLASS);
            });
        hideEmptyNote(container);
        compactRangeByContainer.delete(container);

        if (window.console && typeof window.console.warn === "function") {
            window.console.warn("ScheduleCompactRows fail-open", {
                building: getBuildingName(container),
                day: detail && detail.day,
                block: detail && detail.block,
                reason: reason
            });
        }
    }

    function applyCompactRowsToContainer(container) {
        var table = container.querySelector(".schedule-grid");
        var rows = collectRowMap(table);
        var rowMap = rows.rowMap;
        var maxRow = rows.maxRow;
        var visibleDays;
        var result;
        var minStartRow;
        var maxEndRow;
        var firstVisibleRow;
        var lastVisibleRow;

        if (!table || !rowMap.size || maxRow === null) {
            failOpenContainer(container, "No row map");
            return;
        }

        visibleDays = collectVisibleDays(container, table);
        if (!visibleDays.length) {
            applyEmptyRange(
                container,
                rowMap,
                maxRow,
                "Все дни скрыты для здания " + getBuildingName(container) + "."
            );
            return;
        }

        result = collectConsideredBlocks(container, table, visibleDays, maxRow);
        if (result.hasInvalidVisibleBlock) {
            failOpenContainer(container, result.reason || "Invalid visible block coordinates", {
                day: result.invalidDay,
                block: result.invalidBlock
            });
            return;
        }

        if (!result.blocks.length) {
            applyEmptyRange(
                container,
                rowMap,
                maxRow,
                "Нет занятий для выбранных дней и текущего фильтра в здании " + getBuildingName(container) + "."
            );
            return;
        }

        minStartRow = Math.min.apply(null, result.blocks.map(function (block) {
            return block.startRow;
        }));
        maxEndRow = Math.max.apply(null, result.blocks.map(function (block) {
            return block.endRow;
        }));
        firstVisibleRow = Math.max(0, minStartRow - COMPACT_ROW_PADDING);
        lastVisibleRow = Math.min(maxRow, maxEndRow + COMPACT_ROW_PADDING - 1);

        applyRange(container, rowMap, firstVisibleRow, lastVisibleRow);
        hideEmptyNote(container);
        scrollContainerToCompactStartIfRangeChanged(container, firstVisibleRow, lastVisibleRow);
    }

    function refreshCompactRows(options) {
        var config = options || {};

        if (interactionPauseCount > 0 && !config.force) {
            pendingRefresh = true;
            return;
        }

        clearCompactRows({
            updatePositions: false,
            preserveRanges: true
        });

        if (isCompactRowsSuspended()) {
            hideAllEmptyNotes();
            resetAllCompactRanges();
            updatePositionsSoon();
            return;
        }

        document
            .querySelectorAll(".schedule-container[data-building]")
            .forEach(function (container) {
                applyCompactRowsToContainer(container);
            });

        updatePositionsSoon();
    }

    function pauseForInteraction(reason) {
        var key = reason || "interaction";

        pauseReasons[key] = (pauseReasons[key] || 0) + 1;
        interactionPauseCount += 1;

        return interactionPauseCount;
    }

    function resumeAfterInteraction(reason, options) {
        var key = reason || "interaction";
        var config = options || {};
        var shouldRefresh;

        if (pauseReasons[key] > 0) {
            pauseReasons[key] -= 1;
        }
        if (interactionPauseCount > 0) {
            interactionPauseCount -= 1;
        }

        if (config.refresh) {
            pendingRefresh = true;
        }

        if (interactionPauseCount > 0) {
            return interactionPauseCount;
        }

        shouldRefresh = pendingRefresh;
        pendingRefresh = false;

        if (shouldRefresh) {
            refreshCompactRows({ force: true });
        }

        return interactionPauseCount;
    }

    function initCompactRows() {
        injectCompactRowsStyle();
        ensureMutationObserver();

        if (!initialized) {
            initialized = true;
        }

        refreshCompactRows();
    }

    window.ScheduleCompactRows = {
        init: initCompactRows,
        refresh: refreshCompactRows,
        clear: clearCompactRows,
        isSuspended: isCompactRowsSuspended,
        pauseForInteraction: pauseForInteraction,
        resumeAfterInteraction: resumeAfterInteraction
    };
    window.initCompactRows = initCompactRows;
})();
