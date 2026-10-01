(function () {
  "use strict";

  if (window.__roomsScheduleFocusLoaded) {
    return;
  }
  window.__roomsScheduleFocusLoaded = true;

  var DAY_FALLBACK = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  var HIGHLIGHT_CLASS = "rooms-schedule-focus-cell";
  var HEADER_CLASS = "rooms-schedule-focus-header";
  var NOTICE_ID = "rooms-schedule-focus-notice";
  var READY_TIMEOUT_MS = 8000;
  var EDIT_TIMEOUT_MS = 5000;
  var EDIT_MODE_POLL_MS = 500;
  var activeFocus = null;
  var focusObserver = null;
  var editModePoll = 0;
  var clearTriggersBound = false;

  function parseNavigationTarget() {
    var params = new URLSearchParams(window.location.search || "");

    if (params.get("rooms_nav") !== "1") {
      return null;
    }

    return {
      building: (params.get("rooms_building") || "").trim(),
      room: (params.get("rooms_room") || "").trim(),
      day: (params.get("rooms_day") || "").trim(),
      start: (params.get("rooms_start") || "").trim(),
      end: (params.get("rooms_end") || "").trim(),
    };
  }

  function isValidTarget(target) {
    return !!(
      target &&
      target.building &&
      target.room &&
      target.day &&
      parseClockTime(target.start) >= 0 &&
      parseClockTime(target.end) > parseClockTime(target.start)
    );
  }

  function parseClockTime(value) {
    var match = String(value || "").match(/^(\d{1,2}):(\d{2})$/);

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

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(String(value || ""));
    }
    return String(value || "").replace(/["\\]/g, "\\$&");
  }

  function getDaysOrder() {
    return Array.isArray(window.daysOrder) && window.daysOrder.length
      ? window.daysOrder.slice()
      : DAY_FALLBACK.slice();
  }

  function getGridStart() {
    if (typeof window.gridStart === "number") {
      return window.gridStart;
    }
    if (typeof gridStart !== "undefined" && typeof gridStart === "number") {
      return gridStart;
    }
    return 9 * 60;
  }

  function getTimeInterval() {
    if (typeof window.timeInterval === "number") {
      return window.timeInterval;
    }
    if (typeof timeInterval !== "undefined" && typeof timeInterval === "number") {
      return timeInterval;
    }
    return 5;
  }

  function authUi() {
    return window.SchedGenAuthUI || null;
  }

  function waitForReady(startedAt) {
    startedAt = startedAt || Date.now();

    return new Promise(function(resolve, reject) {
      function tick() {
        if (
          authUi() &&
          window.SchedGenLockUI &&
          typeof window.addColumnIfMissing === "function" &&
          typeof window.toggleDay === "function" &&
          typeof window.updateActivityPositions === "function" &&
          document.querySelector(".schedule-container")
        ) {
          resolve();
          return;
        }

        if (Date.now() - startedAt > READY_TIMEOUT_MS) {
          reject(new Error("Интерфейс расписания не успел загрузиться."));
          return;
        }
        window.setTimeout(tick, 100);
      }

      tick();
    });
  }

  function waitForEditMode(startedAt) {
    startedAt = startedAt || Date.now();

    return new Promise(function(resolve, reject) {
      function tick() {
        var ui = authUi();

        if (ui && typeof ui.isEditMode === "function" && ui.isEditMode()) {
          resolve();
          return;
        }

        if (Date.now() - startedAt > EDIT_TIMEOUT_MS) {
          reject(new Error("Не удалось включить режим редактирования. Возможно, сессия редактирования уже занята другим пользователем."));
          return;
        }
        window.setTimeout(tick, 150);
      }

      if (
        window.SchedGenLockUI &&
        typeof window.SchedGenLockUI.refreshLockStatus === "function"
      ) {
        window.SchedGenLockUI.refreshLockStatus();
      }
      tick();
    });
  }

  function ensureStyle() {
    var style;

    if (document.getElementById("rooms-schedule-focus-style")) {
      return;
    }

    style = document.createElement("style");
    style.id = "rooms-schedule-focus-style";
    style.textContent = [
      "." + HIGHLIGHT_CLASS + " {",
      "  background: #fff3cd !important;",
      "  outline: 2px solid #f59e0b;",
      "  outline-offset: -2px;",
      "}",
      "." + HEADER_CLASS + " {",
      "  box-shadow: inset 0 0 0 3px #f59e0b;",
      "}",
      "#" + NOTICE_ID + " {",
      "  position: fixed;",
      "  right: 16px;",
      "  bottom: 16px;",
      "  z-index: 10000;",
      "  max-width: 420px;",
      "  padding: 12px 14px;",
      "  border: 1px solid #a8d5b5;",
      "  border-radius: 6px;",
      "  background: #f3fff6;",
      "  color: #1f6f35;",
      "  font: 13px/1.35 sans-serif;",
      "  box-shadow: 0 6px 20px rgba(0,0,0,.16);",
      "}",
      "#" + NOTICE_ID + ".error {",
      "  border-color: #f0b4b4;",
      "  background: #fff5f5;",
      "  color: #8a1f1f;",
      "}",
    ].join("\n");
    document.head.appendChild(style);
  }

  function showNotice(message, type) {
    var notice = document.getElementById(NOTICE_ID);

    ensureStyle();
    if (!notice) {
      notice = document.createElement("div");
      notice.id = NOTICE_ID;
      document.body.appendChild(notice);
    }
    notice.className = type || "";
    notice.textContent = message;
  }

  function hideNotice() {
    var notice = document.getElementById(NOTICE_ID);

    if (notice && notice.parentNode) {
      notice.parentNode.removeChild(notice);
    }
  }

  function ensureOnlyTargetDayVisible(targetDay) {
    getDaysOrder().forEach(function(day) {
      var button = document.querySelector(
        '.toggle-day-button[data-day="' + cssEscape(day) + '"]'
      );
      var isHidden;

      if (!button) {
        return;
      }

      isHidden = button.classList.contains("active");
      if (day === targetDay && isHidden) {
        window.toggleDay(button, day);
      } else if (day !== targetDay && !isHidden) {
        window.toggleDay(button, day);
      }
    });
  }

  function requestColumnPermission(target) {
    return fetch("/api/columns", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        building: target.building,
        day: target.day,
        room: target.room,
      }),
    }).then(function(response) {
      if (response.status === 401) {
        window.location.href = "/login";
        throw new Error("Сессия истекла. Нужно войти снова.");
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

        if (!response.ok || !data.ok) {
          if (data.code === "NO_LOCK") {
            throw new Error("Режим редактирования недоступен. Вернитесь к поиску аудиторий и попробуйте еще раз.");
          }
          throw new Error(data.error || "Не удалось подготовить колонку аудитории.");
        }
        return data;
      });
    });
  }

  function findContainer(building) {
    if (
      window.BuildingService &&
      typeof window.BuildingService.findScheduleContainerForBuilding === "function"
    ) {
      return window.BuildingService.findScheduleContainerForBuilding(building);
    }
    return document.querySelector(
      '.schedule-container[data-building="' + cssEscape(building) + '"]'
    );
  }

  function findTargetHeader(container, day, colIndex) {
    var headers = Array.prototype.slice.call(
      container.querySelectorAll(".schedule-grid thead th.day-" + cssEscape(day))
    );

    return headers.find(function(header, index) {
      if (typeof window.getHeaderLocalColumnIndex === "function") {
        return window.getHeaderLocalColumnIndex(header, index) === colIndex;
      }
      return index === colIndex;
    });
  }

  function clearPreviousHighlight() {
    document.querySelectorAll("." + HIGHLIGHT_CLASS).forEach(function(cell) {
      cell.classList.remove(HIGHLIGHT_CLASS);
    });
    document.querySelectorAll("." + HEADER_CLASS).forEach(function(header) {
      header.classList.remove(HEADER_CLASS);
    });
  }

  function clearFocus(options) {
    var config = options || {};

    clearPreviousHighlight();
    disconnectFocusObserver();
    stopEditModeWatcher();
    activeFocus = null;
    if (config.keepNotice !== true) {
      hideNotice();
    }
    if (typeof window.updateActivityPositions === "function") {
      window.updateActivityPositions();
    }
    if (
      window.ScheduleCompactRows &&
      typeof window.ScheduleCompactRows.refresh === "function"
    ) {
      window.ScheduleCompactRows.refresh();
    }
  }

  function bindClearTriggers() {
    if (clearTriggersBound) {
      return;
    }

    clearTriggersBound = true;
    document.addEventListener("keydown", function(event) {
      if (event.key === "Escape" && activeFocus) {
        clearFocus();
      }
    }, true);
    document.addEventListener("click", function(event) {
      var target = event.target;

      if (
        activeFocus &&
        target &&
        target.closest &&
        target.closest(".toggle-day-button")
      ) {
        clearFocus();
      }
    }, true);
    document.addEventListener("schedgen:edit-mode-change", function(event) {
      if (activeFocus && event.detail && event.detail.enabled === false) {
        clearFocus();
      }
    });
  }

  function startEditModeWatcher() {
    stopEditModeWatcher();
    editModePoll = window.setInterval(function() {
      var ui = authUi();

      if (
        activeFocus &&
        ui &&
        typeof ui.isEditMode === "function" &&
        !ui.isEditMode()
      ) {
        clearFocus();
      }
    }, EDIT_MODE_POLL_MS);
  }

  function stopEditModeWatcher() {
    if (editModePoll) {
      window.clearInterval(editModePoll);
      editModePoll = 0;
    }
  }

  function disconnectFocusObserver() {
    if (focusObserver) {
      focusObserver.disconnect();
      focusObserver = null;
    }
  }

  function normalizeRoomName(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function getBlockTimeRange(block) {
    var start = block.getAttribute("data-start-time") || "";
    var end = block.getAttribute("data-end-time") || "";
    var startMinutes = parseClockTime(start);
    var endMinutes = parseClockTime(end);
    var startRow;
    var rowSpan;
    var gridStartValue;
    var interval;

    if (startMinutes >= 0 && endMinutes > startMinutes) {
      return {
        start: startMinutes,
        end: endMinutes,
      };
    }

    startRow = toInteger(block.getAttribute("data-start-row"), -1);
    rowSpan = toInteger(block.getAttribute("data-row-span"), -1);
    if (startRow < 0 || rowSpan <= 0) {
      return null;
    }

    gridStartValue = getGridStart();
    interval = getTimeInterval();
    startMinutes = gridStartValue + startRow * interval;
    endMinutes = gridStartValue + (startRow + rowSpan) * interval;
    return {
      start: startMinutes,
      end: endMinutes,
    };
  }

  function blockMatchesActiveFocus(block) {
    var target;
    var container;
    var building;
    var day;
    var room;
    var colIndex;
    var range;
    var targetStart;
    var targetEnd;

    if (!activeFocus || !block || !block.matches || !block.matches(".activity-block")) {
      return false;
    }

    target = activeFocus.target;
    container = block.closest(".schedule-container");
    building =
      (block.getAttribute("data-building") ||
        (container ? container.getAttribute("data-building") : "") ||
        "").trim();
    day = (block.getAttribute("data-day") || "").trim();
    room = normalizeRoomName(block.getAttribute("data-room") || "");
    colIndex = toInteger(block.getAttribute("data-col-index"), -1);

    if (building !== target.building || day !== target.day) {
      return false;
    }
    if (
      colIndex !== activeFocus.colIndex &&
      room !== normalizeRoomName(target.room)
    ) {
      return false;
    }

    range = getBlockTimeRange(block);
    if (!range) {
      return false;
    }

    targetStart = parseClockTime(target.start);
    targetEnd = parseClockTime(target.end);
    return range.start < targetEnd && range.end > targetStart;
  }

  function collectActivityBlocks(node) {
    var blocks = [];
    var element = node;

    if (!element || element.nodeType !== 1) {
      return blocks;
    }
    if (element.matches && element.matches(".activity-block")) {
      blocks.push(element);
    }
    if (element.querySelectorAll) {
      element.querySelectorAll(".activity-block").forEach(function(block) {
        blocks.push(block);
      });
    }
    return blocks;
  }

  function mutationContainsCompletedBlock(mutation) {
    var blocks = [];

    if (!mutation) {
      return false;
    }
    if (mutation.type === "attributes") {
      blocks = collectActivityBlocks(mutation.target);
    } else if (mutation.type === "childList") {
      mutation.addedNodes.forEach(function(node) {
        blocks = blocks.concat(collectActivityBlocks(node));
      });
    }

    return blocks.some(blockMatchesActiveFocus);
  }

  function startCompletionObserver(container) {
    disconnectFocusObserver();
    if (!container || !document.body) {
      return;
    }

    focusObserver = new MutationObserver(function(mutations) {
      if (!activeFocus) {
        return;
      }
      if (mutations.some(mutationContainsCompletedBlock)) {
        clearFocus();
      }
    });
    focusObserver.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: [
        "data-building",
        "data-day",
        "data-col-index",
        "data-room",
        "data-start-time",
        "data-end-time",
        "data-start-row",
        "data-row-span",
      ],
    });
  }

  function activateFocus(target, container, colIndex) {
    activeFocus = {
      target: target,
      container: container,
      colIndex: colIndex,
    };
    bindClearTriggers();
    startCompletionObserver(container);
    startEditModeWatcher();
  }

  function highlightTarget(container, target, colIndex) {
    var gridStartValue = getGridStart();
    var interval = getTimeInterval();
    var startMinutes = parseClockTime(target.start);
    var endMinutes = parseClockTime(target.end);
    var startRow = Math.max(0, Math.floor((startMinutes - gridStartValue) / interval));
    var endRow = Math.max(startRow + 1, Math.ceil((endMinutes - gridStartValue) / interval));
    var targetCell;
    var header;
    var row;

    clearFocus({ keepNotice: true });

    for (row = startRow; row < endRow; row += 1) {
      var cell = container.querySelector(
        "td.day-" +
          cssEscape(target.day) +
          '[data-row="' +
          String(row) +
          '"][data-col="' +
          String(colIndex) +
          '"]'
      );

      if (cell) {
        cell.classList.add(HIGHLIGHT_CLASS);
        if (!targetCell) {
          targetCell = cell;
        }
      }
    }

    header = findTargetHeader(container, target.day, colIndex);
    if (header) {
      header.classList.add(HEADER_CLASS);
    }

    if (typeof window.updateActivityPositions === "function") {
      window.updateActivityPositions();
    }
    if (
      window.ScheduleCompactRows &&
      typeof window.ScheduleCompactRows.refresh === "function"
    ) {
      window.ScheduleCompactRows.refresh();
    }

    if (targetCell) {
      window.setTimeout(function() {
        targetCell.scrollIntoView({ block: "center", inline: "center" });
        window.setTimeout(function() {
          window.scrollBy(0, -100);
        }, 50);
      }, 100);
    }

    return !!targetCell;
  }

  function prepareSchedulePlace(target) {
    var container;
    var colIndex;

    ensureOnlyTargetDayVisible(target.day);
    return requestColumnPermission(target)
      .then(function() {
        colIndex = window.addColumnIfMissing(target.day, target.room, target.building);
        if (colIndex < 0) {
          throw new Error("Не удалось найти или добавить колонку аудитории.");
        }
        if (typeof window.updateActivityPositions === "function") {
          window.updateActivityPositions();
        }
        container = findContainer(target.building);
        if (!container) {
          throw new Error("Не найдено здание " + target.building + " в расписании.");
        }
        if (!highlightTarget(container, target, colIndex)) {
          throw new Error("Колонка найдена, но нужная ячейка времени не найдена.");
        }
        activateFocus(target, container, colIndex);
        showNotice(
          "Место подготовлено: " +
            target.building +
            ", " +
            target.room +
            ", " +
            target.day +
            " " +
            target.start +
            " - " +
            target.end +
            ". Режим редактирования активен.",
          ""
        );
      });
  }

  function run() {
    var target = parseNavigationTarget();

    if (!target) {
      return;
    }
    if (!isValidTarget(target)) {
      showNotice("Некорректные параметры перехода из поиска аудиторий.", "error");
      return;
    }

    waitForReady()
      .then(function() {
        return waitForEditMode();
      })
      .then(function() {
        return prepareSchedulePlace(target);
      })
      .catch(function(error) {
        showNotice(error.message || "Не удалось подготовить место в расписании.", "error");
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

  window.RoomsScheduleFocus = {
    clear: clearFocus,
  };
})();
