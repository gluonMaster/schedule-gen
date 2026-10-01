(function () {
  "use strict";

  var state = {
    query: "",
    isOpen: false,
    slot: null,
    root: null,
    openButton: null,
    panel: null,
    input: null,
    clearButton: null,
    closeButton: null,
    status: null,
    emptyState: null,
    observer: null,
    scheduleObserver: null,
    noticeMessage: "",
    noticeTimer: null,
    layoutRefreshPending: false,
    layoutRefreshFrame: 0,
    reapplyPending: false,
    compactRowsSearchActive: false,
    mutationSuppressionDepth: 0,
    lastMatchCount: 0,
  };

  var SEARCH_CLASS_NAMES = {
    hiddenBlock: "schedgen-search-hidden-block",
    tempBlock: "schedgen-search-show-temp-block",
    hiddenCol: "schedgen-search-hidden-col",
    tempCell: "schedgen-search-show-temp-cell",
    hiddenRow: "schedgen-search-hidden-row",
    hiddenBuilding: "schedgen-search-hidden-building",
    disabledToggle: "schedgen-search-disabled",
  };

  var SEARCH_MUTATION_ATTRS = [
    "data-day",
    "data-building",
    "data-col-index",
    "data-room",
    "data-start-time",
    "data-end-time",
    "data-start-row",
    "data-row-span",
    "data-lesson-type",
  ];

  function authUi() {
    return window.SchedGenAuthUI || null;
  }

  function getSearchSlot() {
    var ui = authUi();

    if (ui && typeof ui.getSearchSlot === "function") {
      return ui.getSearchSlot();
    }
    return document.getElementById("schedgen-nav-search-slot");
  }

  function syncShellOffsets() {
    var ui = authUi();

    if (ui && typeof ui.syncShellOffsets === "function") {
      ui.syncShellOffsets();
    }
  }

  function isEditModeActive() {
    var ui = authUi();

    return !!(ui && typeof ui.isEditMode === "function" && ui.isEditMode());
  }

  function disconnectObserver() {
    if (!state.observer) {
      return;
    }

    state.observer.disconnect();
    state.observer = null;
  }

  function ensureObserver() {
    if (state.observer || !document.body) {
      return;
    }

    state.observer = new MutationObserver(function () {
      if (mountSearchUi()) {
        disconnectObserver();
      }
    });
    state.observer.observe(document.body, { childList: true, subtree: true });
  }

  function disconnectScheduleObserver() {
    if (!state.scheduleObserver) {
      return;
    }

    state.scheduleObserver.disconnect();
    state.scheduleObserver = null;
  }

  function syncScheduleObserver() {
    if (!hasSearchTokens() || !document.body) {
      disconnectScheduleObserver();
      return;
    }
    if (state.scheduleObserver) {
      return;
    }

    state.scheduleObserver = new MutationObserver(function (mutations) {
      if (state.mutationSuppressionDepth > 0) {
        return;
      }
      if (!hasSearchTokens()) {
        disconnectScheduleObserver();
        return;
      }
      if (!mutations.some(isRelevantScheduleMutation)) {
        return;
      }

      queueSearchReapply();
    });
    state.scheduleObserver.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: SEARCH_MUTATION_ATTRS,
    });
  }

  function isRelevantScheduleMutation(mutation) {
    var i;

    if (!mutation) {
      return false;
    }

    if (
      mutation.type === "attributes" ||
      mutation.type === "characterData"
    ) {
      return isScheduleContentNode(mutation.target);
    }

    if (mutation.type !== "childList") {
      return false;
    }

    if (isScheduleContentNode(mutation.target)) {
      return true;
    }
    for (i = 0; i < mutation.addedNodes.length; i += 1) {
      if (isScheduleContentNode(mutation.addedNodes[i])) {
        return true;
      }
    }
    for (i = 0; i < mutation.removedNodes.length; i += 1) {
      if (isScheduleContentNode(mutation.removedNodes[i])) {
        return true;
      }
    }

    return false;
  }

  function isScheduleContentNode(node) {
    var element = node;

    if (!element) {
      return false;
    }
    if (element.nodeType === 3) {
      element = element.parentElement;
    }
    if (!element || !element.closest || isSearchOwnedNode(element)) {
      return false;
    }

    return !!element.closest(".schedule-container");
  }

  function isSearchOwnedNode(node) {
    var element = node;

    if (!element) {
      return false;
    }
    if (element.nodeType === 3) {
      element = element.parentElement;
    }
    if (!element) {
      return false;
    }

    return !!(
      (state.root && (element === state.root || state.root.contains(element))) ||
      (state.emptyState &&
        (element === state.emptyState || state.emptyState.contains(element)))
    );
  }

  function queueSearchReapply() {
    if (!hasSearchTokens()) {
      disconnectScheduleObserver();
      return;
    }
    if (state.reapplyPending) {
      return;
    }

    state.reapplyPending = true;
    window.requestAnimationFrame(function () {
      state.reapplyPending = false;
      reapplySearchIfNeeded();
    });
  }

  function reapplySearchIfNeeded() {
    if (!hasSearchTokens()) {
      disconnectScheduleObserver();
      return;
    }

    updateSearchResults();
  }

  function withMutationObserverSuppressed(callback) {
    state.mutationSuppressionDepth += 1;
    try {
      return typeof callback === "function" ? callback() : null;
    } finally {
      state.mutationSuppressionDepth = Math.max(
        0,
        state.mutationSuppressionDepth - 1
      );
    }
  }

  function createSearchUi() {
    var root = document.createElement("div");
    var openButton = document.createElement("button");
    var panel = document.createElement("div");
    var input = document.createElement("input");
    var clearButton = document.createElement("button");
    var closeButton = document.createElement("button");
    var status = document.createElement("span");

    root.className = "schedule-search-ui";
    root.setAttribute("data-search-ui-root", "true");

    openButton.type = "button";
    openButton.className = "schedule-search-open";
    openButton.textContent = "Поиск";
    openButton.setAttribute("aria-label", "Открыть поиск по расписанию");
    openButton.addEventListener("click", function () {
      openSearch();
    });

    panel.className = "schedule-search-panel";

    input.type = "search";
    input.className = "schedule-search-input";
    input.placeholder = "Учитель, предмет, кабинет, время...";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.setAttribute("aria-label", "Поиск по расписанию");
    input.addEventListener("input", function (event) {
      setNotice("");
      state.query = event.target.value || "";
      updateSearchResults();
    });
    input.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      if (hasSearchTokens()) {
        clearSearch();
        focusInput();
        return;
      }

      closeSearch();
    });

    clearButton.type = "button";
    clearButton.className = "schedule-search-clear";
    clearButton.textContent = "Очистить";
    clearButton.addEventListener("click", function () {
      setNotice("");
      clearSearch();
      focusInput();
    });

    closeButton.type = "button";
    closeButton.className = "schedule-search-close";
    closeButton.textContent = "×";
    closeButton.setAttribute("aria-label", "Закрыть поиск");
    closeButton.addEventListener("click", function () {
      closeSearch();
    });

    status.className = "schedule-search-status";
    status.setAttribute("aria-live", "polite");

    panel.appendChild(input);
    panel.appendChild(clearButton);
    panel.appendChild(closeButton);
    root.appendChild(openButton);
    root.appendChild(panel);
    root.appendChild(status);

    state.root = root;
    state.openButton = openButton;
    state.panel = panel;
    state.input = input;
    state.clearButton = clearButton;
    state.closeButton = closeButton;
    state.status = status;
  }

  function mountSearchUi() {
    var slot = getSearchSlot();

    if (!slot) {
      ensureObserver();
      return false;
    }

    state.slot = slot;

    if (!state.root) {
      createSearchUi();
    }

    if (!slot.contains(state.root)) {
      slot.textContent = "";
      slot.appendChild(state.root);
      syncShellOffsets();
    }

    syncUiState();
    disconnectObserver();
    return true;
  }

  function init() {
    mountSearchUi();
    ensureEmptyState();
    handleEditModeChange(isEditModeActive());
    return window.ScheduleSearch;
  }

  function openSearch() {
    if (isEditModeActive()) {
      setNotice("Поиск недоступен во время редактирования.");
      syncUiState();
      return false;
    }

    setNotice("");

    if (!state.isOpen) {
      state.isOpen = true;
      syncUiState();
    }

    focusInput();
    return true;
  }

  function closeSearch() {
    deactivateSearch({ closePanel: true });
  }

  function clearSearch() {
    deactivateSearch({ closePanel: false });
  }

  function hasSearchTokens() {
    return buildQueryTokens(state.query).length > 0;
  }

  function handleEditModeChange(enabled) {
    if (enabled) {
      if (state.isOpen || hasSearchTokens()) {
        deactivateSearch({ closePanel: true, flushLayout: true });
      }
      setNotice("Поиск недоступен во время редактирования.");
    }
    syncUiState();
  }

  function deactivateSearch(options) {
    var config = options || {};
    var hadSearchEffects = hasSearchTokens();
    var hadVisualState = state.isOpen || hadSearchEffects;

    disconnectScheduleObserver();
    state.query = "";
    if (config.closePanel) {
      state.isOpen = false;
    }
    if (!config.preserveNotice) {
      setNotice("");
    }
    withMutationObserverSuppressed(function () {
      removeSearchEffects();
    });
    state.lastMatchCount = 0;
    syncUiState();

    if (!hadSearchEffects || config.refreshLayout === false) {
      return hadVisualState;
    }
    if (config.flushLayout) {
      flushLayoutRefresh();
    } else {
      queueLayoutRefresh();
    }
    return true;
  }

  function prepareForSerialization(options) {
    return deactivateSearch({
      closePanel: true,
      flushLayout: !!(options && options.flushLayout),
      refreshLayout: !(options && options.refreshLayout === false),
    });
  }

  function prepareForEditMode() {
    return deactivateSearch({ closePanel: true, flushLayout: true });
  }

  function updateSearchResults() {
    var tokens;
    var matchCount;

    withMutationObserverSuppressed(function () {
      removeSearchEffects();
    });
    state.lastMatchCount = 0;

    tokens = buildQueryTokens(state.query);
    if (!tokens.length) {
      syncUiState();
      queueLayoutRefresh();
      return;
    }

    if (isEditModeActive()) {
      state.query = "";
      state.isOpen = false;
      setNotice("Поиск недоступен во время редактирования.");
      syncUiState();
      queueLayoutRefresh();
      return;
    }

    matchCount = withMutationObserverSuppressed(function () {
      return applySearchTokens(tokens);
    });
    state.lastMatchCount = matchCount;
    syncUiState();
    queueLayoutRefresh();
  }

  function applySearchTokens(tokens) {
    var matchedColumns = Object.create(null);
    var matchedBlocks = [];
    var sections = collectScheduleSections();
    var blocks = collectIndexedBlocks();

    blocks.forEach(function (entry) {
      if (matchesAllTokens(entry, tokens)) {
        matchedColumns[entry.columnKey] = true;
        matchedBlocks.push(entry);
        return;
      }

      entry.element.classList.add(SEARCH_CLASS_NAMES.hiddenBlock);
    });

    sections.forEach(function (section) {
      if (applyColumnFiltering(section, matchedColumns) > 0) {
        applyRowFiltering(section, matchedBlocks);
      }
    });
    applyMatchedBlockOverrides(matchedBlocks);

    if (!matchedBlocks.length) {
      showEmptyState();
    } else {
      hideEmptyState();
    }

    if (document.body) {
      document.body.classList.toggle("schedgen-search-active", true);
    }

    return matchedBlocks.length;
  }

  function collectIndexedBlocks() {
    return Array.from(document.querySelectorAll(".activity-block"))
      .filter(isBlockSearchIndexable)
      .map(buildBlockSearchEntry)
      .filter(function (entry) {
        return !!entry;
      });
  }

  function buildBlockSearchEntry(block) {
    var container = block.closest(".schedule-container");
    var table = container ? container.querySelector(".schedule-grid") : null;
    var day = (block.getAttribute("data-day") || "").trim();
    var building =
      (block.getAttribute("data-building") ||
        (container ? container.getAttribute("data-building") : "") ||
        "").trim();
    var colIndex = toInteger(block.getAttribute("data-col-index"), -1);
    var rows = resolveBlockRows(block);
    var room = resolveBlockRoom(block, table, day, colIndex);
    var timeRange = resolveBlockTimeRange(block);
    var searchText;

    if (!container || !table || !day || !building || colIndex < 0) {
      return null;
    }

    hydrateBlockRuntimeAttrs(block, room, timeRange, rows);
    searchText = buildBlockSearchText(block, building, day, room, timeRange);

    return {
      element: block,
      container: container,
      building: building,
      day: day,
      colIndex: colIndex,
      columnKey: buildColumnKey(building, day, colIndex),
      startRow: rows ? rows.startRow : -1,
      rowSpan: rows ? rows.rowSpan : -1,
      exact: normalizeExact(searchText),
      folded: normalizeFolded(searchText),
    };
  }

  function buildBlockSearchText(block, building, day, room, timeRange) {
    var textContent = block.textContent || "";
    var visibleText = extractBlockLines(block).join(" ");
    var rangeCompact = "";
    var rangeSpaced = "";
    var parts = [textContent];

    if (visibleText && visibleText !== textContent) {
      parts.push(visibleText);
    }
    if (building) {
      parts.push(building);
    }
    if (day) {
      parts.push(day);
    }
    if (room) {
      parts.push(room);
    }
    if (timeRange) {
      if (timeRange.start) {
        parts.push(timeRange.start);
      }
      if (timeRange.end) {
        parts.push(timeRange.end);
      }
      if (timeRange.start && timeRange.end) {
        rangeCompact = timeRange.start + "-" + timeRange.end;
        rangeSpaced = timeRange.start + " - " + timeRange.end;
        parts.push(rangeCompact);
        parts.push(rangeSpaced);
      }
    }

    return parts.join(" ");
  }

  function buildQueryTokens(query) {
    return normalizeExact(query)
      .split(" ")
      .filter(function (token) {
        return !!token;
      })
      .map(function (token) {
        return {
          exact: token,
          folded: normalizeFolded(token),
        };
      });
  }

  function matchesAllTokens(entry, tokens) {
    return tokens.every(function (token) {
      return (
        entry.exact.indexOf(token.exact) !== -1 ||
        entry.folded.indexOf(token.folded) !== -1
      );
    });
  }

  function normalizeExact(value) {
    var normalized = String(value || "");

    if (typeof normalized.normalize === "function") {
      normalized = normalized.normalize("NFKC");
    }

    return normalized
      .replace(/[\u00A0\u202F]/g, " ")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function normalizeFolded(value) {
    return normalizeExact(value)
      .replace(/ä/g, "a")
      .replace(/ö/g, "o")
      .replace(/ü/g, "u")
      .replace(/ß/g, "ss");
  }

  function extractBlockLines(block) {
    return (block.innerHTML || "")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<[^>]*>/g, "")
      .split("\n")
      .map(function (line) {
        return line.trim();
      })
      .filter(function (line) {
        return !!line;
      });
  }

  function resolveBlockRoom(block, table, day, colIndex) {
    var room = (block.getAttribute("data-room") || "").trim();

    if (room) {
      return room;
    }

    return resolveRoomName(table, day, colIndex);
  }

  function resolveRoomName(table, day, colIndex) {
    var header;

    if (!table || !day || colIndex < 0) {
      return "";
    }

    header = findHeaderByLocalColumn(table, day, colIndex);
    if (!header) {
      return "";
    }

    if (typeof window.extractRoomFromDayHeader === "function") {
      return window.extractRoomFromDayHeader(header, day).trim();
    }

    return (header.textContent || "").replace(day, "").trim();
  }

  function findHeaderByLocalColumn(table, day, colIndex) {
    var byAttr;
    var headers;

    byAttr = table.querySelector(
      'thead th.day-' + cssEscape(day) + '[data-col="' + String(colIndex) + '"]'
    );
    if (byAttr) {
      return byAttr;
    }

    headers = Array.from(table.querySelectorAll("thead th.day-" + cssEscape(day)));
    return headers[colIndex] || null;
  }

  function resolveBlockTimeRange(block) {
    var startTime = (block.getAttribute("data-start-time") || "").trim();
    var endTime = (block.getAttribute("data-end-time") || "").trim();
    var startMinutes;
    var endMinutes;
    var lines;
    var match;
    var i;

    if (startTime && endTime) {
      startMinutes = parseClockTime(startTime);
      endMinutes = parseClockTime(endTime);
      if (startMinutes >= 0 && endMinutes > startMinutes) {
        return { start: startTime, end: endTime };
      }
    }

    lines = extractBlockLines(block);
    for (i = lines.length - 1; i >= 0; i -= 1) {
      match = lines[i].match(/(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})/);
      if (!match) {
        continue;
      }

      startMinutes = parseClockTime(match[1]);
      endMinutes = parseClockTime(match[2]);
      if (startMinutes >= 0 && endMinutes > startMinutes) {
        return { start: match[1], end: match[2] };
      }
    }

    return resolveBlockTimeRangeFromRows(block);
  }

  function resolveBlockTimeRangeFromRows(block) {
    var startRow = toInteger(block.getAttribute("data-start-row"), -1);
    var rowSpan = toInteger(block.getAttribute("data-row-span"), -1);
    var gridStartValue = typeof gridStart !== "undefined" ? gridStart : 9 * 60;
    var interval = typeof timeInterval !== "undefined" ? timeInterval : 5;
    var startMinutes;
    var endMinutes;

    if (startRow < 0 || rowSpan <= 0) {
      return null;
    }

    startMinutes = gridStartValue + startRow * interval;
    endMinutes = gridStartValue + (startRow + rowSpan) * interval;
    return {
      start: formatClockTime(startMinutes),
      end: formatClockTime(endMinutes),
    };
  }

  function resolveBlockRows(block) {
    var startRow = toInteger(block.getAttribute("data-start-row"), -1);
    var rowSpan = toInteger(block.getAttribute("data-row-span"), -1);
    var gridStartValue = typeof gridStart !== "undefined" ? gridStart : 9 * 60;
    var interval = typeof timeInterval !== "undefined" ? timeInterval : 5;
    var lines;
    var match;
    var startMinutes;
    var endMinutes;
    var i;

    if (startRow >= 0 && rowSpan > 0) {
      return {
        startRow: startRow,
        rowSpan: rowSpan,
      };
    }

    lines = extractBlockLines(block);
    for (i = lines.length - 1; i >= 0; i -= 1) {
      match = lines[i].match(/(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})/);
      if (!match) {
        continue;
      }

      startMinutes = parseClockTime(match[1]);
      endMinutes = parseClockTime(match[2]);
      if (startMinutes < 0 || endMinutes <= startMinutes) {
        continue;
      }

      startRow = Math.floor((startMinutes - gridStartValue) / interval);
      rowSpan = Math.floor((endMinutes - startMinutes) / interval);
      if (startRow >= 0 && rowSpan > 0) {
        return {
          startRow: startRow,
          rowSpan: rowSpan,
        };
      }
    }

    return null;
  }

  function hydrateBlockRuntimeAttrs(block, room, timeRange, rows) {
    if (room && !block.getAttribute("data-room")) {
      block.setAttribute("data-room", room);
    }
    if (timeRange && timeRange.start && !block.getAttribute("data-start-time")) {
      block.setAttribute("data-start-time", timeRange.start);
    }
    if (timeRange && timeRange.end && !block.getAttribute("data-end-time")) {
      block.setAttribute("data-end-time", timeRange.end);
    }
    if (rows && !block.getAttribute("data-start-row")) {
      block.setAttribute("data-start-row", String(rows.startRow));
    }
    if (rows && !block.getAttribute("data-row-span")) {
      block.setAttribute("data-row-span", String(rows.rowSpan));
    }
  }

  function applyColumnFiltering(section, matchedColumns) {
    var table = section.table;
    var visibleColumnCount = 0;

    Array.from(table.querySelectorAll("thead th")).forEach(function (header) {
      var day = resolveHeaderDay(header);
      var colIndex;
      var columnKey;

      if (!day) {
        return;
      }

      colIndex = resolveHeaderLocalColumnIndex(table, header, day);
      if (colIndex < 0) {
        return;
      }

      columnKey = buildColumnKey(section.building, day, colIndex);
      if (matchedColumns[columnKey]) {
        visibleColumnCount += 1;
        if (isDayHidden(day, section.container)) {
          showColumnCellsForColumn(table, day, colIndex);
          header.classList.add(SEARCH_CLASS_NAMES.tempCell);
        }
        return;
      }

      header.classList.add(SEARCH_CLASS_NAMES.hiddenCol);
      hideBodyCellsForColumn(table, day, colIndex);
    });

    if (!visibleColumnCount) {
      hideBuildingSection(section);
      return 0;
    }

    showBuildingSection(section);
    return visibleColumnCount;
  }

  function resolveHeaderLocalColumnIndex(table, header, day) {
    var explicitIndex;
    var headers;

    explicitIndex = toInteger(header.getAttribute("data-col"), -1);
    if (explicitIndex >= 0) {
      return explicitIndex;
    }

    headers = Array.from(table.querySelectorAll("thead th.day-" + cssEscape(day)));
    return headers.indexOf(header);
  }

  function resolveHeaderDay(header) {
    var dayClass;

    if (!header || !header.classList) {
      return "";
    }

    dayClass = Array.from(header.classList).find(function (className) {
      return className.indexOf("day-") === 0;
    });

    return dayClass ? dayClass.substring(4) : "";
  }

  function hideBodyCellsForColumn(table, day, colIndex) {
    table
      .querySelectorAll(
        'tbody td.day-' + cssEscape(day) + '[data-col="' + String(colIndex) + '"]'
      )
      .forEach(function (cell) {
        cell.classList.add(SEARCH_CLASS_NAMES.hiddenCol);
      });
  }

  function showColumnCellsForColumn(table, day, colIndex) {
    table
      .querySelectorAll(
        'tbody td.day-' + cssEscape(day) + '[data-col="' + String(colIndex) + '"]'
      )
      .forEach(function (cell) {
        cell.classList.add(SEARCH_CLASS_NAMES.tempCell);
      });
  }

  function applyMatchedBlockOverrides(matchedBlocks) {
    matchedBlocks.forEach(function (entry) {
      if (!isDayHidden(entry.day, entry.container)) {
        return;
      }

      entry.element.classList.add(SEARCH_CLASS_NAMES.tempBlock);
    });
  }

  function applyRowFiltering(section, matchedBlocks) {
    var hasRowCoverage = false;
    var rowsToKeep = Object.create(null);
    var rowMap = collectTableRowMap(section.table);

    matchedBlocks.forEach(function (entry) {
      var row;
      var endRow;

      if (entry.container !== section.container) {
        return;
      }
      if (entry.startRow < 0 || entry.rowSpan <= 0) {
        return;
      }

      hasRowCoverage = true;
      for (row = entry.startRow; row < entry.startRow + entry.rowSpan; row += 1) {
        rowsToKeep[String(row)] = true;
      }

      endRow = entry.startRow + entry.rowSpan;
      if (rowMap[String(endRow)]) {
        rowsToKeep[String(endRow)] = true;
      }
    });

    if (!hasRowCoverage) {
      return;
    }

    Object.keys(rowMap).forEach(function (rowKey) {
      if (rowsToKeep[rowKey]) {
        return;
      }

      rowMap[rowKey].classList.add(SEARCH_CLASS_NAMES.hiddenRow);
    });
  }

  function collectTableRowMap(table) {
    var rowMap = Object.create(null);

    Array.from(table.querySelectorAll("tbody tr")).forEach(function (row) {
      var rowIndex = resolveTableRowIndex(row);

      if (rowIndex >= 0) {
        rowMap[String(rowIndex)] = row;
      }
    });

    return rowMap;
  }

  function resolveTableRowIndex(row) {
    var indexedCell = row ? row.querySelector("td[data-row]") : null;

    if (!indexedCell) {
      return -1;
    }

    return toInteger(indexedCell.getAttribute("data-row"), -1);
  }

  function collectScheduleSections() {
    return Array.from(document.querySelectorAll(".schedule-container"))
      .filter(isElementBaselineVisible)
      .map(function (container) {
        return {
          container: container,
          table: container.querySelector(".schedule-grid"),
          building: (container.getAttribute("data-building") || "").trim(),
          heading: findBuildingHeading(container),
        };
      })
      .filter(function (section) {
        return !!(section.table && section.building);
      });
  }

  function findBuildingHeading(container) {
    var node = container ? container.previousElementSibling : null;

    while (node) {
      if (node.tagName === "H2") {
        return node;
      }
      if (node.classList && node.classList.contains("schedule-container")) {
        break;
      }
      node = node.previousElementSibling;
    }

    return null;
  }

  function hideBuildingSection(section) {
    section.container.classList.add(SEARCH_CLASS_NAMES.hiddenBuilding);
    if (section.heading) {
      section.heading.classList.add(SEARCH_CLASS_NAMES.hiddenBuilding);
    }
  }

  function showBuildingSection(section) {
    section.container.classList.remove(SEARCH_CLASS_NAMES.hiddenBuilding);
    if (section.heading) {
      section.heading.classList.remove(SEARCH_CLASS_NAMES.hiddenBuilding);
    }
  }

  function removeSearchEffects() {
    document
      .querySelectorAll("." + SEARCH_CLASS_NAMES.hiddenBlock)
      .forEach(function (element) {
        element.classList.remove(SEARCH_CLASS_NAMES.hiddenBlock);
      });
    document
      .querySelectorAll("." + SEARCH_CLASS_NAMES.tempBlock)
      .forEach(function (element) {
        element.classList.remove(SEARCH_CLASS_NAMES.tempBlock);
      });
    document
      .querySelectorAll("." + SEARCH_CLASS_NAMES.hiddenCol)
      .forEach(function (element) {
        element.classList.remove(SEARCH_CLASS_NAMES.hiddenCol);
      });
    document
      .querySelectorAll("." + SEARCH_CLASS_NAMES.tempCell)
      .forEach(function (element) {
        element.classList.remove(SEARCH_CLASS_NAMES.tempCell);
      });
    document
      .querySelectorAll("." + SEARCH_CLASS_NAMES.hiddenRow)
      .forEach(function (element) {
        element.classList.remove(SEARCH_CLASS_NAMES.hiddenRow);
      });
    document
      .querySelectorAll("." + SEARCH_CLASS_NAMES.hiddenBuilding)
      .forEach(function (element) {
        element.classList.remove(SEARCH_CLASS_NAMES.hiddenBuilding);
      });

    hideEmptyState();

    if (document.body) {
      document.body.classList.remove("schedgen-search-active");
    }
  }

  function ensureEmptyState() {
    var anchor;

    if (state.emptyState && document.body && document.body.contains(state.emptyState)) {
      return state.emptyState;
    }

    state.emptyState = document.createElement("div");
    state.emptyState.id = "schedgen-search-empty-state";
    state.emptyState.className = "schedule-search-empty-state";
    state.emptyState.setAttribute("aria-live", "polite");
    state.emptyState.textContent = "Ничего не найдено";

    anchor = document.querySelector(".schedule-container");
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(state.emptyState, anchor);
    } else {
      document.body.appendChild(state.emptyState);
    }

    return state.emptyState;
  }

  function showEmptyState() {
    ensureEmptyState().classList.add("is-visible");
  }

  function hideEmptyState() {
    if (state.emptyState) {
      state.emptyState.classList.remove("is-visible");
    }
  }

  function focusInput() {
    if (!state.input || !state.isOpen) {
      return;
    }

    window.requestAnimationFrame(function () {
      if (!state.input || !state.isOpen) {
        return;
      }
      state.input.focus();
      state.input.select();
    });
  }

  function flushLayoutRefresh() {
    if (typeof window.updateActivityPositions !== "function") {
      return;
    }

    if (state.layoutRefreshFrame) {
      window.cancelAnimationFrame(state.layoutRefreshFrame);
      state.layoutRefreshFrame = 0;
    }
    state.layoutRefreshPending = false;
    window.updateActivityPositions();
  }

  function queueLayoutRefresh() {
    if (
      state.layoutRefreshPending ||
      typeof window.updateActivityPositions !== "function"
    ) {
      return;
    }

    state.layoutRefreshPending = true;
    state.layoutRefreshFrame = window.requestAnimationFrame(function () {
      state.layoutRefreshPending = false;
      state.layoutRefreshFrame = 0;
      window.updateActivityPositions();
    });
  }

  function notifyCompactRowsSearchState(active) {
    if (active === state.compactRowsSearchActive) {
      return;
    }

    state.compactRowsSearchActive = active;
    if (
      window.ScheduleCompactRows &&
      typeof window.ScheduleCompactRows.refresh === "function"
    ) {
      window.ScheduleCompactRows.refresh();
    }
  }

  function setNotice(message) {
    if (state.noticeTimer) {
      window.clearTimeout(state.noticeTimer);
    }

    state.noticeMessage = message || "";
    state.noticeTimer = state.noticeMessage
      ? window.setTimeout(function () {
          state.noticeMessage = "";
          state.noticeTimer = null;
          syncUiState();
        }, 3000)
      : null;
  }

  function getStatusText() {
    if (state.noticeMessage) {
      return state.noticeMessage;
    }
    if (hasSearchTokens()) {
      return state.lastMatchCount > 0
        ? "Совпадений: " + String(state.lastMatchCount)
        : "Ничего не найдено";
    }
    return "";
  }

  function syncUiState() {
    var active = hasSearchTokens();
    var statusText = getStatusText();

    if (state.input) {
      state.input.value = state.query;
      state.input.disabled = isEditModeActive();
    }
    if (state.root) {
      state.root.classList.toggle("is-open", state.isOpen);
      state.root.classList.toggle("is-active", active);
      state.root.classList.toggle("is-disabled", isEditModeActive());
      state.root.setAttribute("data-search-active", active ? "true" : "false");
    }
    if (state.slot) {
      state.slot.setAttribute("data-search-active", active ? "true" : "false");
    }
    if (state.openButton) {
      state.openButton.setAttribute("aria-expanded", state.isOpen ? "true" : "false");
    }
    if (state.clearButton) {
      state.clearButton.disabled = !active;
    }
    if (state.status) {
      state.status.textContent = statusText;
      state.status.classList.toggle("is-hidden", !statusText);
    }

    setDayToggleButtonsLocked(active);
    syncScheduleObserver();
    syncShellOffsets();
    notifyCompactRowsSearchState(active);
  }

  function setDayToggleButtonsLocked(locked) {
    document.querySelectorAll(".toggle-day-button").forEach(function (button) {
      button.disabled = !!locked;
      button.classList.toggle(SEARCH_CLASS_NAMES.disabledToggle, !!locked);
      button.setAttribute("aria-disabled", locked ? "true" : "false");
    });
  }

  function buildColumnKey(building, day, colIndex) {
    return [building || "", day || "", String(colIndex)].join("::");
  }

  function parseClockTime(value) {
    var match = String(value || "").trim().match(/^(\d{1,2}):(\d{2})$/);

    if (!match) {
      return -1;
    }

    return parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
  }

  function formatClockTime(totalMinutes) {
    var hours = Math.floor(totalMinutes / 60);
    var minutes = totalMinutes % 60;

    return String(hours).padStart(2, "0") + ":" + String(minutes).padStart(2, "0");
  }

  function toInteger(value, fallback) {
    var parsed = parseInt(value, 10);
    return isNaN(parsed) ? fallback : parsed;
  }

  function isBlockSearchIndexable(block) {
    var day;
    var container;

    if (!block) {
      return false;
    }
    if (isElementBaselineVisible(block)) {
      return true;
    }
    if (block.classList.contains("lesson-type-filter-hidden")) {
      return false;
    }

    day = (block.getAttribute("data-day") || "").trim();
    container = block.closest(".schedule-container");
    return !!(
      day &&
      container &&
      isDayHidden(day, container) &&
      isElementDisplayNone(block)
    );
  }

  function isDayHidden(day, container) {
    var button;
    var header;

    if (!day) {
      return false;
    }

    button = document.querySelector(
      '.toggle-day-button.active[data-day="' + cssEscape(day) + '"]'
    );
    if (button) {
      return true;
    }

    if (!container || !container.querySelector) {
      return false;
    }

    header = container.querySelector("thead th.day-" + cssEscape(day));
    return !!(header && isElementDisplayNone(header));
  }

  function isElementBaselineVisible(element) {
    var style;

    if (!element) {
      return false;
    }

    style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden";
  }

  function isElementDisplayNone(element) {
    if (!element) {
      return true;
    }

    return window.getComputedStyle(element).display === "none";
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(String(value || ""));
    }

    return String(value || "").replace(/["\\]/g, "\\$&");
  }

  window.ScheduleSearch = {
    init: init,
    clearSearch: clearSearch,
    isActive: hasSearchTokens,
    prepareForSerialization: prepareForSerialization,
    prepareForEditMode: prepareForEditMode,
    handleScheduleMutation: queueSearchReapply,
    handleEditModeChange: handleEditModeChange,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

(function () {
  "use strict";

  function shouldLoadRoomsScheduleFocus() {
    try {
      return new URLSearchParams(window.location.search || "").get("rooms_nav") === "1";
    } catch (error) {
      return false;
    }
  }

  function loadRoomsScheduleFocus() {
    var script;

    if (
      !shouldLoadRoomsScheduleFocus() ||
      window.__roomsScheduleFocusLoaded ||
      window.__roomsScheduleFocusLoading
    ) {
      return;
    }

    window.__roomsScheduleFocusLoading = true;
    script = document.createElement("script");
    script.src = "/static/rooms_schedule_focus.js?v=20260521_3";
    script.async = false;
    script.onload = function () {
      window.__roomsScheduleFocusLoading = false;
    };
    script.onerror = function () {
      window.__roomsScheduleFocusLoading = false;
      console.error("Failed to load rooms_schedule_focus.js");
    };
    document.head.appendChild(script);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadRoomsScheduleFocus);
  } else {
    loadRoomsScheduleFocus();
  }
})();
