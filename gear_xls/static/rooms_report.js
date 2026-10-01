var _availData = null;
var _selectedBuilding = "";
var _selectedRoom = "";
var _selectedDays = [];
var _searchQuery = "";
var _requestedDurationMinutes = 0;
var _searchMode = "room";
var _requestedTimeFromMinutes = -1;
var _requestedTimeToMinutes = -1;
var _roomsNavigationBusy = false;

var DAY_ORDER = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
var BUILDING_ORDER = ["Villa", "Kolibri"];
var SLOT_MINUTES = 15;

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function parseTimeToMin(t) {
  var match = String(t || "").trim().match(/^(\d{1,2}):(\d{2})$/);
  var hour;
  var minute;

  if (!match) return -1;
  hour = parseInt(match[1], 10);
  minute = parseInt(match[2], 10);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return -1;
  return hour * 60 + minute;
}

function parseTimeInputValue(value) {
  var trimmed = String(value || "").trim();

  if (!trimmed) return -1;
  return parseTimeToMin(trimmed);
}

function formatMin(minutes) {
  return (
    (minutes < 600 ? "0" : "") +
    Math.floor(minutes / 60) +
    ":" +
    (minutes % 60 < 10 ? "0" : "") +
    (minutes % 60)
  );
}

function parseDurationMinutes(value) {
  var parsed = parseInt(String(value || "").trim(), 10);

  if (isNaN(parsed) || parsed <= 0) return 0;
  return parsed;
}

function formatDuration(minutes) {
  var hours = Math.floor(minutes / 60);
  var restMinutes = minutes % 60;
  var parts = [];

  if (hours) {
    parts.push(hours + " ч");
  }
  if (restMinutes) {
    parts.push(restMinutes + " мин");
  }
  if (!parts.length) {
    return "0 мин";
  }
  return parts.join(" ");
}

function makeWindow(startMin, endMin) {
  return {
    start: formatMin(startMin),
    end: formatMin(endMin),
    startMin: startMin,
    endMin: endMin,
    duration: endMin - startMin,
  };
}

function deriveFreeWindows(occupied, dayStart, dayEnd) {
  var sorted;
  var merged = [];
  var free = [];
  var cursor = dayStart;
  var i;

  if (!occupied.length) {
    return [makeWindow(dayStart, dayEnd)];
  }

  sorted = occupied.slice().sort(function(a, b) {
    return a.start - b.start;
  });

  for (i = 0; i < sorted.length; i += 1) {
    var start = Math.max(dayStart, sorted[i].start);
    var end = Math.min(dayEnd, sorted[i].end);

    if (start < 0 || end <= start) continue;
    if (merged.length && start <= merged[merged.length - 1].end) {
      merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, end);
    } else {
      merged.push({ start: start, end: end });
    }
  }

  if (!merged.length) {
    return [makeWindow(dayStart, dayEnd)];
  }

  for (i = 0; i < merged.length; i += 1) {
    if (cursor < merged[i].start) {
      free.push(makeWindow(cursor, merged[i].start));
    }
    cursor = Math.max(cursor, merged[i].end);
  }

  if (cursor < dayEnd) {
    free.push(makeWindow(cursor, dayEnd));
  }

  return free.filter(function(windowItem) {
    return windowItem.duration > 0;
  });
}

function showError(msg) {
  var tableWrap = document.getElementById("rooms-table-wrap");
  var report = document.getElementById("free-windows");

  if (tableWrap && !tableWrap.hidden) {
    tableWrap.innerHTML = '<p style="color:red;padding:12px">' + escapeHtml(msg) + "</p>";
  }
  if (report) {
    report.innerHTML = '<p style="color:red">' + escapeHtml(msg) + "</p>";
  }
  showNavigationStatus(msg, "error");
}

function initRoomsTableToggle() {
  var button = document.getElementById("btn-toggle-rooms-table");
  var tableWrap = document.getElementById("rooms-table-wrap");
  var controls = document.getElementById("rooms-controls");

  if (!tableWrap) return;
  if (!button && controls) {
    button = document.createElement("button");
    button.id = "btn-toggle-rooms-table";
    button.type = "button";
    controls.appendChild(button);
  }
  if (!button) return;

  tableWrap.hidden = true;
  button.setAttribute("aria-expanded", "false");
  button.textContent = "Показать таблицу занятости аудиторий";

  button.addEventListener("click", function() {
    var shouldShow = tableWrap.hidden;

    tableWrap.hidden = !shouldShow;
    button.setAttribute("aria-expanded", shouldShow ? "true" : "false");
    button.textContent = shouldShow
      ? "Скрыть таблицу занятости аудиторий"
      : "Показать таблицу занятости аудиторий";
  });
}

function getNavigationStatusElement() {
  var status = document.getElementById("rooms-navigation-status");
  var controls = document.getElementById("rooms-controls");

  if (!status) {
    status = document.createElement("div");
    status.id = "rooms-navigation-status";
    status.hidden = true;
    if (controls && controls.parentNode) {
      controls.parentNode.insertBefore(status, controls.nextSibling);
    } else {
      document.body.insertBefore(status, document.body.firstChild);
    }
  }
  return status;
}

function clearNavigationStatus() {
  var status = getNavigationStatusElement();

  if (!status) return;
  status.hidden = true;
  status.className = "";
  status.textContent = "";
}

function showNavigationStatus(message, type, buttonOptions) {
  var status = getNavigationStatusElement();
  var button;

  if (!status) return;
  status.hidden = false;
  status.className = type || "";
  status.textContent = message;

  if (buttonOptions && buttonOptions.label && typeof buttonOptions.onClick === "function") {
    button = document.createElement("button");
    button.type = "button";
    button.textContent = buttonOptions.label;
    button.addEventListener("click", buttonOptions.onClick);
    status.appendChild(button);
  }
}

function isEditableRole() {
  return ["admin", "editor", "organizer"].indexOf(window.USER_ROLE || "") !== -1;
}

function setAvailableRoomLinksBusy(busy) {
  _roomsNavigationBusy = !!busy;
  Array.prototype.slice.call(document.querySelectorAll(".available-room-link")).forEach(function(button) {
    button.disabled = !!busy;
  });
}

function readNavigationTarget(button) {
  return {
    building: button.getAttribute("data-building") || "",
    room: button.getAttribute("data-room") || "",
    day: button.getAttribute("data-day") || "",
    start: button.getAttribute("data-start") || "",
    end: button.getAttribute("data-end") || "",
  };
}

function buildScheduleNavigationUrl(target) {
  var params = new URLSearchParams();

  params.set("rooms_nav", "1");
  params.set("rooms_building", target.building);
  params.set("rooms_room", target.room);
  params.set("rooms_day", target.day);
  params.set("rooms_start", target.start);
  params.set("rooms_end", target.end);
  return "/schedule?" + params.toString();
}

function navigateToScheduleTarget(target) {
  window.location.href = buildScheduleNavigationUrl(target);
}

function lockApiRequest(url, method) {
  return fetch(url, {
    method: method || "GET",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: method && method !== "GET" && method !== "DELETE" ? "{}" : undefined,
  }).then(function(response) {
    if (response.status === 401) {
      window.location.href = "/login";
      return null;
    }
    return response.text().then(function(text) {
      var data = {};

      if (text) {
        try {
          data = JSON.parse(text);
        } catch (error) {
          data = {};
        }
      }
      return { response: response, data: data };
    });
  });
}

function showLockUnavailable(target, data) {
  var holder = (data && data.holder) || "другой пользователь";
  var message = "Редактирование сейчас невозможно: расписание редактирует " + holder + ".";

  if ((window.USER_ROLE || "") !== "admin") {
    showNavigationStatus(message, "error");
    return;
  }

  showNavigationStatus(message, "error", {
    label: "Снять блокировку",
    onClick: function() {
      forceReleaseLockAndNavigate(target, holder);
    },
  });
}

function acquireLockAndNavigate(target) {
  if (!isEditableRole()) {
    showNavigationStatus("Для подготовки места в расписании нужен доступ к редактированию.", "error");
    return;
  }
  if (_roomsNavigationBusy) {
    return;
  }

  setAvailableRoomLinksBusy(true);
  showNavigationStatus("Проверяю доступ к редактированию...", "");

  lockApiRequest("/api/lock/acquire", "POST")
    .then(function(result) {
      var data;

      if (!result) return;
      data = result.data || {};
      if (data.ok || data.holder === window.CURRENT_USER) {
        navigateToScheduleTarget(target);
        return;
      }

      showLockUnavailable(target, data);
      setAvailableRoomLinksBusy(false);
    })
    .catch(function(error) {
      showNavigationStatus("Не удалось проверить доступ к редактированию: " + error.message, "error");
      setAvailableRoomLinksBusy(false);
    });
}

function forceReleaseLockAndNavigate(target, holder) {
  if (!window.confirm("Принудительно завершить сессию редактирования пользователя " + holder + "?")) {
    return;
  }

  setAvailableRoomLinksBusy(true);
  showNavigationStatus("Снимаю блокировку редактирования...", "");

  lockApiRequest("/api/lock", "DELETE")
    .then(function(result) {
      if (!result) return;
      if (!result.response.ok || !result.data || !result.data.ok) {
        showNavigationStatus("Не удалось снять блокировку редактирования.", "error");
        setAvailableRoomLinksBusy(false);
        return;
      }

      setAvailableRoomLinksBusy(false);
      acquireLockAndNavigate(target);
    })
    .catch(function(error) {
      showNavigationStatus("Не удалось снять блокировку: " + error.message, "error");
      setAvailableRoomLinksBusy(false);
    });
}

function initAvailableRoomNavigation() {
  var report = document.getElementById("free-windows");

  if (!report) return;

  report.addEventListener("click", function(event) {
    var button = event.target.closest ? event.target.closest(".available-room-link") : null;

    if (!button || !report.contains(button)) return;
    event.preventDefault();
    acquireLockAndNavigate(readNavigationTarget(button));
  });
}

function compareText(a, b) {
  return String(a || "").localeCompare(String(b || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function makeRoomSortKey(value) {
  var parts = String(value || "")
    .trim()
    .match(/\d+|\D+/g) || [];

  return parts.map(function(part) {
    if (/^\d+$/.test(part)) {
      return { kind: 0, numeric: parseInt(part, 10), text: "" };
    }
    return { kind: 1, numeric: 0, text: part.toLowerCase() };
  });
}

function compareRooms(a, b) {
  var keyA = makeRoomSortKey(a);
  var keyB = makeRoomSortKey(b);
  var maxLen = Math.max(keyA.length, keyB.length);
  var i;

  for (i = 0; i < maxLen; i += 1) {
    if (!keyA[i]) return -1;
    if (!keyB[i]) return 1;
    if (keyA[i].kind !== keyB[i].kind) {
      return keyA[i].kind - keyB[i].kind;
    }
    if (keyA[i].kind === 0 && keyA[i].numeric !== keyB[i].numeric) {
      return keyA[i].numeric - keyB[i].numeric;
    }
    if (keyA[i].kind === 1 && keyA[i].text !== keyB[i].text) {
      return keyA[i].text < keyB[i].text ? -1 : 1;
    }
  }

  return compareText(a, b);
}

function normalizeSearchText(value) {
  return String(value || "")
    .trim()
    .replace(/,/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function getConfiguredBuildingOrder(data) {
  var buildings = (data && data.buildings) || {};
  var rawOrder =
    Array.isArray(data && data.building_order) && data.building_order.length
      ? data.building_order.slice()
      : BUILDING_ORDER.slice();
  var seen = {};
  var ordered = [];

  rawOrder.forEach(function(building) {
    if (!building || seen[building] || !Object.prototype.hasOwnProperty.call(buildings, building)) {
      return;
    }
    seen[building] = true;
    ordered.push(building);
  });

  Object.keys(buildings)
    .sort(compareText)
    .forEach(function(building) {
      if (seen[building]) return;
      seen[building] = true;
      ordered.push(building);
    });

  return ordered;
}

function getBuildings(data) {
  return getConfiguredBuildingOrder(data);
}

function getRoomsForBuilding(data, building) {
  var buildings = (data && data.buildings) || {};

  if (building) {
    return (((buildings[building] || {}).rooms) || []).slice().sort(compareRooms);
  }

  var seen = {};
  var rooms = [];

  getBuildings(data).forEach(function(name) {
    (((buildings[name] || {}).rooms) || []).forEach(function(room) {
      var key = String(room || "").toLowerCase();

      if (!seen[key]) {
        seen[key] = true;
        rooms.push(room);
      }
    });
  });

  return rooms.sort(compareRooms);
}

function getOccupiedRoomsForBuilding(buildingData) {
  var seen = {};
  var rooms = [];

  Object.keys((buildingData && buildingData.days) || {}).forEach(function(day) {
    Object.keys((((buildingData || {}).days || {})[day]) || {}).forEach(function(room) {
      var key = String(room || "").toLowerCase();

      if (!seen[key]) {
        seen[key] = true;
        rooms.push(room);
      }
    });
  });

  return rooms.sort(compareRooms);
}

function getRoomCombos(data) {
  var seen = {};
  var combos = [];

  getBuildings(data).forEach(function(building) {
    (((data.buildings[building] || {}).rooms) || [])
      .slice()
      .sort(compareRooms)
      .forEach(function(room) {
        var key = building + "::" + room;

        if (seen[key]) return;
        seen[key] = true;
        combos.push({
          building: building,
          room: room,
          text: normalizeSearchText(room + " " + building),
        });
      });
  });

  return combos;
}

function getActiveDays() {
  return _selectedDays.length ? _selectedDays.slice() : DAY_ORDER.slice();
}

function shouldUseRoomFilter() {
  return _searchMode === "room" && !!_selectedRoom;
}

function getTargetsFromFilters(data) {
  var buildings = _selectedBuilding ? [_selectedBuilding] : getBuildings(data);
  var targets = [];

  buildings.forEach(function(building) {
    var buildingData = (data.buildings || {})[building];
    var rooms;

    if (!buildingData) return;
    rooms = (buildingData.rooms || []).slice();
    if (shouldUseRoomFilter()) {
      rooms = rooms.filter(function(room) {
        return room === _selectedRoom;
      });
    }
    rooms.sort(compareRooms).forEach(function(room) {
      targets.push({ building: building, room: room });
    });
  });

  return targets;
}

function filterWindowsByDuration(windows, requestedDuration) {
  if (!requestedDuration) {
    return windows.slice();
  }
  return windows.filter(function(windowItem) {
    return windowItem.duration >= requestedDuration;
  });
}

function formatWindowList(windows, includeDuration) {
  return windows
    .map(function(windowItem) {
      var label = windowItem.start + " - " + windowItem.end;
      if (includeDuration) {
        label += " (" + formatDuration(windowItem.duration) + ")";
      }
      return label;
    })
    .join(", ");
}

function applySearchStateFromInputs() {
  var searchBox = document.getElementById("search-box");
  var durationInput = document.getElementById("duration-minutes");
  var searchModeSelect = document.getElementById("search-mode");
  var timeFromInput = document.getElementById("time-from");
  var timeToInput = document.getElementById("time-to");

  _searchMode = searchModeSelect ? searchModeSelect.value : "room";
  _searchQuery = searchBox ? searchBox.value.trim() : "";
  _requestedDurationMinutes = durationInput
    ? parseDurationMinutes(durationInput.value)
    : 0;
  _requestedTimeFromMinutes = timeFromInput
    ? parseTimeInputValue(timeFromInput.value)
    : -1;
  _requestedTimeToMinutes = timeToInput
    ? parseTimeInputValue(timeToInput.value)
    : -1;
}

function setOptions(select, values, emptyLabel) {
  var parts = ['<option value="">' + escapeHtml(emptyLabel) + "</option>"];

  values.forEach(function(value) {
    parts.push('<option value="' + escapeHtml(value) + '">' + escapeHtml(value) + "</option>");
  });
  select.innerHTML = parts.join("");
}

function populateFilters(data) {
  var buildingSelect = document.getElementById("filter-building");
  var roomSelect = document.getElementById("filter-room");
  var buildings = getBuildings(data);

  if (_selectedBuilding && buildings.indexOf(_selectedBuilding) === -1) {
    _selectedBuilding = "";
    _selectedRoom = "";
  }

  setOptions(buildingSelect, buildings, "Все");
  buildingSelect.value = _selectedBuilding;

  function refillRooms() {
    var rooms = getRoomsForBuilding(data, _selectedBuilding);

    if (_selectedRoom && rooms.indexOf(_selectedRoom) === -1) {
      _selectedRoom = "";
    }

    setOptions(roomSelect, rooms, "Все");
    roomSelect.value = _selectedRoom;
  }

  refillRooms();

  buildingSelect.onchange = function() {
    _selectedBuilding = this.value;
    _selectedRoom = "";
    refillRooms();
    renderTable();
  };

  roomSelect.onchange = function() {
    _selectedRoom = this.value;
    renderTable();
  };
}

function populateAutocomplete(data) {
  var datalist = document.getElementById("room-suggestions");
  var items = getRoomCombos(data).map(function(item) {
    return item.room + " " + item.building;
  });

  datalist.innerHTML = items
    .map(function(item) {
      return '<option value="' + escapeHtml(item) + '"></option>';
    })
    .join("");
}

function toggleControlVisibility(wrapperId, visible) {
  var wrapper = document.getElementById(wrapperId);

  if (!wrapper) return;
  wrapper.hidden = !visible;
  Array.prototype.slice.call(wrapper.querySelectorAll("input, select")).forEach(function(control) {
    control.disabled = !visible;
  });
}

function syncSearchModeUI() {
  var searchButton = document.getElementById("btn-search");
  var searchBox = document.getElementById("search-box");

  toggleControlVisibility("filter-room-wrap", _searchMode === "room");
  toggleControlVisibility("search-box-wrap", _searchMode === "room");
  toggleControlVisibility("time-from-wrap", _searchMode === "available");
  toggleControlVisibility("time-to-wrap", _searchMode === "available");

  if (searchBox) {
    searchBox.placeholder = _searchMode === "room" ? "0.06 Kolibri ..." : "";
  }
  if (searchButton) {
    searchButton.textContent = _searchMode === "available" ? "Найти аудитории" : "Найти";
  }
}

function loadAvailability() {
  fetch("/api/rooms/availability")
    .then(function(r) {
      if (r.status === 401) {
        window.location.href = "/login";
        return null;
      }
      if (!r.ok) {
        showError("Ошибка загрузки данных: " + r.status);
        return null;
      }
      return r.json();
    })
    .then(function(data) {
      if (!data) return;
      _availData = data;
      populateFilters(data);
      populateAutocomplete(data);
      applySearchStateFromInputs();
      syncSearchModeUI();
      renderTable();
    })
    .catch(function(e) {
      showError("Сетевая ошибка: " + e.message);
    });
}

function buildColumns(data) {
  var activeBuildings;
  var activeDays;
  var columns = [];

  if (!data || !data.buildings) return [];

  activeBuildings = _selectedBuilding ? [_selectedBuilding] : getBuildings(data);
  activeDays = getActiveDays();

  activeBuildings.forEach(function(building) {
    var buildingData = data.buildings[building];
    var allRooms;
    var rooms;

    if (!buildingData) return;

    allRooms = (buildingData.rooms || []).slice();
    if (shouldUseRoomFilter()) {
      rooms = allRooms.filter(function(room) {
        return room === _selectedRoom;
      });
    } else {
      rooms = getOccupiedRoomsForBuilding(buildingData);
      if (!rooms.length) {
        rooms = allRooms;
      }
    }

    rooms.sort(compareRooms);
    activeDays.forEach(function(day) {
      rooms.forEach(function(room) {
        var daySlots = (((buildingData.days || {})[day] || {})[room]) || [];
        columns.push({
          building: building,
          day: day,
          room: room,
          slots: daySlots,
        });
      });
    });
  });

  return columns;
}

function buildSlotLookup(columns) {
  columns.forEach(function(column) {
    var lookup = {};

    (column.slots || []).forEach(function(slot) {
      var start = parseTimeToMin(slot.start);
      var end = parseTimeToMin(slot.end);
      var first = Math.ceil(start / SLOT_MINUTES) * SLOT_MINUTES;
      var t;

      if (start < 0 || end <= start) return;
      for (t = first; t < end; t += SLOT_MINUTES) {
        lookup[t] = slot;
      }
    });

    column.lookup = lookup;
  });
}

function renderTable() {
  var thead = document.getElementById("rooms-thead");
  var tbody = document.getElementById("rooms-tbody");
  var freeEl = document.getElementById("free-windows");
  var columns;
  var singleBuilding;
  var head;
  var gridStart;
  var gridEnd;
  var rows = [];
  var time;

  if (!_availData || !thead || !tbody) return;

  clearNavigationStatus();
  columns = buildColumns(_availData);
  buildSlotLookup(columns);

  if (!columns.length) {
    thead.innerHTML = "<tr><th>Время</th></tr>";
    tbody.innerHTML = '<tr><td>Нет данных для выбранных фильтров</td></tr>';
    if (freeEl) freeEl.innerHTML = "";
    renderFreeWindows();
    return;
  }

  singleBuilding = !!_selectedBuilding || getBuildings(_availData).length === 1;
  head = ["<tr><th>Время</th>"];

  columns.forEach(function(column) {
    var label = column.day + " " + column.room;

    if (!singleBuilding) label += " (" + column.building + ")";
    head.push("<th>" + escapeHtml(label) + "</th>");
  });
  head.push("</tr>");

  gridStart = parseTimeToMin(_availData.grid_start);
  gridEnd = parseTimeToMin(_availData.grid_end);

  for (time = gridStart; time < gridEnd; time += SLOT_MINUTES) {
    rows.push("<tr>");
    rows.push("<th>" + (time % 60 === 0 ? escapeHtml(formatMin(time)) : "") + "</th>");
    columns.forEach(function(column) {
      var slot = column.lookup[time] || null;
      var cls;
      var titleText;
      var text;

      if (!slot) {
        rows.push('<td class="slot-free"></td>');
        return;
      }

      cls = /^(individual|nachhilfe|trial)$/i.test(slot.lesson_type || "")
        ? "slot-busy-ind"
        : "slot-busy";
      titleText = [slot.subject || "", slot.students || ""].join(" ").trim();
      titleText = titleText
        ? titleText + " / " + (slot.teacher || "")
        : (slot.teacher || "");
      text = (slot.subject || "").slice(0, 10) || "*";

      rows.push(
        '<td class="' +
          cls +
          '" title="' +
          escapeHtml(titleText.trim()) +
          '">' +
          escapeHtml(text) +
          "</td>"
      );
    });
    rows.push("</tr>");
  }

  rows.push("<tr>");
  rows.push("<th>" + escapeHtml(formatMin(gridEnd)) + "</th>");
  columns.forEach(function() {
    rows.push('<td class="slot-free"></td>');
  });
  rows.push("</tr>");

  thead.innerHTML = head.join("");
  tbody.innerHTML = rows.join("");
  renderFreeWindows();
}

function resolveSearchTargets(data, query) {
  var lower = normalizeSearchText(query);
  var combos = getRoomCombos(data);
  var matches;

  if (!lower) return [];

  matches = combos.filter(function(item) {
    return item.text === lower;
  });

  if (!matches.length) {
    matches = combos.filter(function(item) {
      return normalizeSearchText(item.room) === lower;
    });
  }

  if (_selectedBuilding) {
    matches = matches.filter(function(item) {
      return item.building === _selectedBuilding;
    });
  }

  if (shouldUseRoomFilter()) {
    matches = matches.filter(function(item) {
      return item.room === _selectedRoom;
    });
  }

  return matches;
}

function getRequestedTimeRange(gridStart, gridEnd) {
  var dayStart = _requestedTimeFromMinutes >= 0
    ? Math.max(gridStart, _requestedTimeFromMinutes)
    : gridStart;
  var dayEnd = _requestedTimeToMinutes >= 0
    ? Math.min(gridEnd, _requestedTimeToMinutes)
    : gridEnd;

  if (dayEnd <= dayStart) {
    return {
      error: "Некорректный диапазон времени: время начала должно быть раньше времени окончания.",
    };
  }

  return {
    start: dayStart,
    end: dayEnd,
  };
}

function formatRangeSummary(range) {
  if (_requestedTimeFromMinutes >= 0 && _requestedTimeToMinutes >= 0) {
    return "время: " + formatMin(range.start) + " - " + formatMin(range.end);
  }
  if (_requestedTimeFromMinutes >= 0) {
    return "время: с " + formatMin(range.start);
  }
  if (_requestedTimeToMinutes >= 0) {
    return "время: до " + formatMin(range.end);
  }
  return "время: весь рабочий день";
}

function extractRoomFloor(room) {
  var value = String(room || "").trim();
  var dotIndex = value.indexOf(".");

  if (dotIndex > 0) {
    return value.slice(0, dotIndex);
  }
  return "__other__";
}

function formatFloorLabel(floor) {
  if (floor === "__other__") {
    return "Прочие";
  }
  return "Этаж " + floor;
}

function buildAvailableRoomWindowButton(windowEntry) {
  var label =
    windowEntry.day +
    ": " +
    windowEntry.start +
    " - " +
    windowEntry.end +
    " (" +
    formatDuration(windowEntry.duration) +
    ")";

  return (
    '<button type="button" class="available-room-link"' +
    ' data-building="' +
    escapeHtml(windowEntry.building) +
    '" data-room="' +
    escapeHtml(windowEntry.room) +
    '" data-day="' +
    escapeHtml(windowEntry.day) +
    '" data-start="' +
    escapeHtml(windowEntry.start) +
    '" data-end="' +
    escapeHtml(windowEntry.end) +
    '">' +
    escapeHtml(label) +
    "</button>"
  );
}

function renderSingleRoomReport(target) {
  var resolved = [];
  var activeDays;
  var requestedDuration;
  var gridStart;
  var gridEnd;
  var unique = {};
  var parts = [];
  var sectionsAdded = 0;

  activeDays = getActiveDays();
  requestedDuration = _requestedDurationMinutes;

  if (_searchQuery) {
    resolved = resolveSearchTargets(_availData, _searchQuery);
    if (!resolved.length) {
      target.innerHTML = "<p>Аудитория не найдена: " + escapeHtml(_searchQuery) + "</p>";
      return;
    }
  } else if (shouldUseRoomFilter()) {
    resolved = getTargetsFromFilters(_availData);
  } else {
    target.innerHTML = "";
    return;
  }

  gridStart = parseTimeToMin(_availData.grid_start);
  gridEnd = parseTimeToMin(_availData.grid_end);

  if (requestedDuration > 0) {
    parts.push(
      "<p>Показаны только окна, где помещается событие длительностью не менее " +
        escapeHtml(formatDuration(requestedDuration)) +
        ".</p>"
    );
  }

  resolved.forEach(function(item) {
    var key = item.building + "::" + item.room;
    var buildingData;
    var hasAnyOccupied = false;
    var fullyFreeText = "";
    var lines = [];

    if (unique[key]) return;
    unique[key] = true;

    buildingData = _availData.buildings[item.building] || { days: {} };

    activeDays.forEach(function(day) {
      var slots = (((buildingData.days || {})[day] || {})[item.room]) || [];
      var occupied = slots
        .map(function(slot) {
          return { start: parseTimeToMin(slot.start), end: parseTimeToMin(slot.end) };
        })
        .filter(function(slot) {
          return slot.start >= 0 && slot.end > slot.start;
        });
      var free = filterWindowsByDuration(
        deriveFreeWindows(occupied, gridStart, gridEnd),
        requestedDuration
      );
      var text = "нет свободного времени";

      if (occupied.length) {
        hasAnyOccupied = true;
      }
      if (!requestedDuration && !occupied.length) {
        text = "весь день";
      } else if (free.length) {
        text = formatWindowList(free, requestedDuration > 0);
      }

      if (requestedDuration > 0) {
        if (free.length) {
          lines.push("<li>" + escapeHtml(day + ": " + text) + "</li>");
        }
        return;
      }

      lines.push("<li>" + escapeHtml(day + ": " + text) + "</li>");
    });

    if (!requestedDuration && !hasAnyOccupied) {
      sectionsAdded += 1;
      if (activeDays.length === DAY_ORDER.length) {
        fullyFreeText =
          "Аудитория " +
          item.room +
          " (" +
          item.building +
          ") свободна во все рабочие дни.";
      } else if (activeDays.length > 1) {
        fullyFreeText =
          "Аудитория " +
          item.room +
          " (" +
          item.building +
          ") свободна во все выбранные дни.";
      } else {
        fullyFreeText =
          "Аудитория " +
          item.room +
          " (" +
          item.building +
          ") свободна в течение всего дня (" +
          activeDays[0] +
          ").";
      }
      parts.push("<p>" + escapeHtml(fullyFreeText) + "</p>");
      return;
    }

    if (!lines.length) {
      return;
    }

    sectionsAdded += 1;
    parts.push(
      "<h3>Аудитория " +
        escapeHtml(item.room) +
        " (" +
        escapeHtml(item.building) +
        ") - свободное время:</h3>"
    );
    parts.push("<ul>");
    parts.push(lines.join(""));
    parts.push("</ul>");
  });

  if (!sectionsAdded) {
    if (requestedDuration > 0) {
      target.innerHTML =
        "<p>Не найдено свободных окон длительностью не менее " +
        escapeHtml(formatDuration(requestedDuration)) +
        " для выбранной аудитории.</p>";
      return;
    }
    target.innerHTML = "";
    return;
  }

  target.innerHTML = parts.join("");
}

function renderAvailableRoomsReport(target) {
  var activeDays = getActiveDays();
  var requestedDuration = _requestedDurationMinutes;
  var gridStart = parseTimeToMin(_availData.grid_start);
  var gridEnd = parseTimeToMin(_availData.grid_end);
  var range = getRequestedTimeRange(gridStart, gridEnd);
  var targets;
  var summaryParts = [];
  var parts = [];
  var buildingSections = [];
  var buildingSectionByName = {};
  var resultsFound = 0;

  if (range.error) {
    target.innerHTML = "<p>" + escapeHtml(range.error) + "</p>";
    return;
  }

  if (!requestedDuration) {
    target.innerHTML = "<p>Укажите минимальную длительность для поиска свободных аудиторий.</p>";
    return;
  }

  targets = getTargetsFromFilters(_availData);
  if (!targets.length) {
    target.innerHTML = "<p>Не найдено доступных аудиторий.</p>";
    return;
  }

  if (_selectedBuilding) {
    summaryParts.push("здание: " + _selectedBuilding);
  } else {
    summaryParts.push("здания: все");
  }
  summaryParts.push("дни: " + activeDays.join(", "));
  summaryParts.push("длительность: от " + formatDuration(requestedDuration));
  summaryParts.push(formatRangeSummary(range));

  parts.push(
    '<div class="report-summary"><strong>Поиск свободных аудиторий.</strong> ' +
      escapeHtml(summaryParts.join("; ")) +
      ".</div>"
  );

  targets.forEach(function(item) {
    var buildingData = _availData.buildings[item.building] || { days: {} };
    var availableWindows = [];
    var buildingSection;
    var floorSection;
    var floorName;

    activeDays.forEach(function(day) {
      var slots = (((buildingData.days || {})[day] || {})[item.room]) || [];
      var occupied = slots
        .map(function(slot) {
          return { start: parseTimeToMin(slot.start), end: parseTimeToMin(slot.end) };
        })
        .filter(function(slot) {
          return slot.start >= 0 && slot.end > slot.start;
        });
      var free = filterWindowsByDuration(
        deriveFreeWindows(occupied, range.start, range.end),
        requestedDuration
      );

      if (!free.length) return;
      free.forEach(function(windowItem) {
        availableWindows.push({
          building: item.building,
          room: item.room,
          day: day,
          start: windowItem.start,
          end: windowItem.end,
          duration: windowItem.duration,
        });
      });
    });

    if (!availableWindows.length) {
      return;
    }

    resultsFound += 1;

    buildingSection = buildingSectionByName[item.building];
    if (!buildingSection) {
      buildingSection = {
        building: item.building,
        floors: [],
        floorLookup: {},
      };
      buildingSectionByName[item.building] = buildingSection;
      buildingSections.push(buildingSection);
    }

    floorName = extractRoomFloor(item.room);
    floorSection = buildingSection.floorLookup[floorName];
    if (!floorSection) {
      floorSection = {
        floor: floorName,
        rooms: [],
      };
      buildingSection.floorLookup[floorName] = floorSection;
      buildingSection.floors.push(floorSection);
    }

    floorSection.rooms.push({
      room: item.room,
      windows: availableWindows,
    });
  });

  if (!resultsFound) {
    target.innerHTML =
      parts.join("") +
      "<p>Не найдено доступных аудиторий для выбранных параметров.</p>";
    return;
  }

  buildingSections.forEach(function(buildingSection) {
    parts.push('<section class="available-report-building">');
    parts.push("<h3>" + escapeHtml(buildingSection.building) + "</h3>");

    buildingSection.floors.forEach(function(floorSection) {
      parts.push('<div class="available-report-floor">');
      parts.push("<h4>" + escapeHtml(formatFloorLabel(floorSection.floor)) + "</h4>");
      parts.push('<ul class="available-report-room-list">');
      floorSection.rooms.forEach(function(roomEntry) {
        parts.push('<li class="available-report-room">');
        parts.push('<span class="available-report-room-title">' + escapeHtml(roomEntry.room) + "</span> - ");
        parts.push('<ul class="available-report-window-list">');
        roomEntry.windows.forEach(function(windowEntry) {
          parts.push(
            '<li class="available-report-window-item">' +
              buildAvailableRoomWindowButton(windowEntry) +
              "</li>"
          );
        });
        parts.push("</ul>");
        parts.push("</li>");
      });
      parts.push("</ul>");
      parts.push("</div>");
    });

    parts.push("</section>");
  });

  target.innerHTML = parts.join("");
}

function renderFreeWindows() {
  var target = document.getElementById("free-windows");

  if (!_availData || !target) return;

  if (_searchMode === "available") {
    renderAvailableRoomsReport(target);
    return;
  }

  renderSingleRoomReport(target);
}

function ensureDayFilterControls() {
  var allBox = document.getElementById("d-all");
  var container = document.getElementById("day-filter-group");

  if (!container && allBox && allBox.parentNode) {
    container = allBox.parentNode.parentNode;
  }
  if (!container) return [];

  return DAY_ORDER.map(function(day) {
    var existing = document.getElementById("d-" + day);
    var wrapper;
    var input;
    var label;

    if (existing) return existing;

    wrapper = document.createElement("span");
    wrapper.className = "day-toggle";

    input = document.createElement("input");
    input.type = "checkbox";
    input.id = "d-" + day;

    label = document.createElement("label");
    label.setAttribute("for", input.id);
    label.textContent = day;

    wrapper.appendChild(input);
    wrapper.appendChild(label);
    container.appendChild(document.createTextNode(" "));
    container.appendChild(wrapper);

    return input;
  });
}

function _wireDayFilters() {
  var allBox = document.getElementById("d-all");
  var boxes = ensureDayFilterControls();

  if (!allBox || !boxes.length) return;

  allBox.onchange = function() {
    if (!this.checked) return;
    boxes.forEach(function(box) {
      box.checked = false;
    });
    _selectedDays = [];
    renderTable();
  };

  boxes.forEach(function(box, index) {
    box.onchange = function() {
      if (allBox.checked) allBox.checked = false;
      _selectedDays = boxes
        .map(function(item, idx) {
          return item.checked ? DAY_ORDER[idx] : null;
        })
        .filter(function(day) {
          return !!day;
        });
      if (!_selectedDays.length) {
        allBox.checked = true;
      }
      renderTable();
    };
  });
}

document.addEventListener("DOMContentLoaded", function() {
  var durationInput = document.getElementById("duration-minutes");
  var searchBox = document.getElementById("search-box");
  var searchModeSelect = document.getElementById("search-mode");
  var timeFromInput = document.getElementById("time-from");
  var timeToInput = document.getElementById("time-to");

  initRoomsTableToggle();
  initAvailableRoomNavigation();
  applySearchStateFromInputs();
  syncSearchModeUI();
  loadAvailability();

  document.getElementById("btn-search").addEventListener("click", function() {
    applySearchStateFromInputs();
    syncSearchModeUI();
    renderTable();
  });

  searchModeSelect.addEventListener("change", function() {
    applySearchStateFromInputs();
    syncSearchModeUI();
    renderTable();
  });

  searchBox.addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      applySearchStateFromInputs();
      renderTable();
    }
  });

  durationInput.addEventListener("input", function() {
    applySearchStateFromInputs();
    renderTable();
  });

  durationInput.addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      applySearchStateFromInputs();
      renderTable();
    }
  });

  [timeFromInput, timeToInput].forEach(function(input) {
    input.addEventListener("input", function() {
      applySearchStateFromInputs();
      renderTable();
    });
    input.addEventListener("keydown", function(e) {
      if (e.key === "Enter") {
        e.preventDefault();
        applySearchStateFromInputs();
        renderTable();
      }
    });
  });

  document.getElementById("btn-refresh").addEventListener("click", loadAvailability);
  _wireDayFilters();
});
