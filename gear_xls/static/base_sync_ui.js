(function () {
  "use strict";

  var _baseRevision = null;
  var _basePendingUpdate = false;
  var _blockNewEditsUntilSync = false;
  var _updateBannerTimer = null;
  var _toastTimer = null;
  var _publishedGroupSignature = null;
  var _basePendingDragStart = null;
  var _baseActiveDrag = null;
  var _basePendingResize = null;
  var _baseEditedBlock = null;
  var _baseCompactDragPaused = false;

  function authUi() {
    return window.SchedGenAuthUI || null;
  }

  function currentRole() {
    return window.USER_ROLE || "viewer";
  }

  function scheduleSearch() {
    return window.ScheduleSearch || null;
  }

  function prepareSearchForSerialization(options) {
    var search = scheduleSearch();

    if (!search || typeof search.prepareForSerialization !== "function") {
      return false;
    }
    return search.prepareForSerialization(options);
  }

  function notifySearchScheduleMutation() {
    var search = scheduleSearch();

    if (!search || typeof search.handleScheduleMutation !== "function") {
      return;
    }
    search.handleScheduleMutation();
  }

  function refreshCompactRowsAfterBaseMutation() {
    if (
      window.ScheduleCompactRows &&
      typeof window.ScheduleCompactRows.refresh === "function"
    ) {
      window.ScheduleCompactRows.refresh();
    } else if (typeof window.updateActivityPositions === "function") {
      window.updateActivityPositions();
    }
  }

  function pauseCompactRowsForBaseDrag() {
    if (
      !_baseCompactDragPaused &&
      window.ScheduleCompactRows &&
      typeof window.ScheduleCompactRows.pauseForInteraction === "function"
    ) {
      window.ScheduleCompactRows.pauseForInteraction("drag");
      _baseCompactDragPaused = true;
    }
  }

  function resumeCompactRowsAfterBaseDrag(refresh) {
    if (
      _baseCompactDragPaused &&
      window.ScheduleCompactRows &&
      typeof window.ScheduleCompactRows.resumeAfterInteraction === "function"
    ) {
      window.ScheduleCompactRows.resumeAfterInteraction("drag", { refresh: !!refresh });
    }
    _baseCompactDragPaused = false;
  }

  function reapplyLessonTypeFilterAfterBaseMutation() {
    if (typeof reapplyLessonTypeFilter === "function") {
      reapplyLessonTypeFilter();
      return;
    }
    refreshCompactRowsAfterBaseMutation();
  }

  function isInEditMode() {
    return !!(
      authUi() &&
      typeof authUi().isEditMode === "function" &&
      authUi().isEditMode() &&
      currentRole() === "admin"
    );
  }

  function ensureStyles() {
    addStyleOnce(
      "schedgen-base-sync-style",
      [
        "body.schedgen-sync-block .activity-block { pointer-events: none !important; }",
        "body.schedgen-sync-block .drag-handle,",
        "body.schedgen-sync-block [data-drag-handle] { pointer-events: none !important; }",
        "body.schedgen-sync-block #create-block-button,",
        "body.schedgen-sync-block #toggle-add-mode,",
        "body.schedgen-sync-block #delete-block-button,",
        "body.schedgen-sync-block .col-add-btn,",
        "body.schedgen-sync-block .col-delete-btn,",
        "body.schedgen-sync-block #menuItemAddColumn { display: none !important; }",
        "#schedgen-update-banner {",
        "  position: sticky;",
        "  top: calc(var(--schedgen-banner-top, 44px) + var(--schedgen-lock-banner-height, 40px));",
        "  z-index: 9050;",
        "  margin: 0;",
        "  padding: 8px 16px;",
        "  font: 13px/1.4 sans-serif;",
        "  color: #704214;",
        "  background: #ffe0a3;",
        "  border-bottom: 1px solid #e2b264;",
        "  display: none;",
        "}",
        "#schedgen-base-sync-toast {",
        "  position: fixed;",
        "  right: 20px;",
        "  bottom: 20px;",
        "  z-index: 10030;",
        "  max-width: 420px;",
        "  padding: 12px 16px;",
        "  border-radius: 8px;",
        "  color: #fff;",
        "  font: 13px/1.4 sans-serif;",
        "  box-shadow: 0 8px 20px rgba(0,0,0,.2);",
        "  display: none;",
        "}",
        ".activity-block.schedgen-publish-invalid {",
        "  outline: 3px solid #b3261e !important;",
        "  outline-offset: 2px;",
        "}",
      ].join("\n")
    );
  }

  function init() {
    ensureStyles();
    ensureDomObserver();
    attachBaseBlockInteractionHandlers();
    refreshBaseBlockInteractions(document);
    normalizeExistingGroupBlockRuntimeAttrs({ showAlert: false });
    setPublishedGroupBaseline();
    syncBlockUi();
  }

  function addStyleOnce(id, cssText) {
    var style;

    if (document.getElementById(id)) {
      return Promise.resolve(false);
    }
    style = document.createElement("style");
    style.id = id;
    style.textContent = cssText;
    document.head.appendChild(style);
  }

  function attachBaseBlockInteractionHandlers() {
    if (!document.body || document.body.__baseBlockInteractionHandlersAttached) {
      return;
    }
    document.body.__baseBlockInteractionHandlersAttached = true;

    document.addEventListener("submit", handleBaseEditSubmit, true);
    document.addEventListener("click", handleBaseEditCancel);
    document.addEventListener("mousedown", handleBaseResizeStart, true);
    document.addEventListener("mousemove", handleBaseDragMove, true);
    document.addEventListener("mouseup", handleBaseDragEnd, true);
    document.addEventListener("mouseup", handleBaseResizeEnd);
  }

  function ensureDomObserver() {
    if (!document.body || document.body.__baseSyncObserverAttached) {
      return;
    }
    document.body.__baseSyncObserverAttached = true;
    new MutationObserver(function () {
      refreshBaseBlockInteractions(document);
      updateDirtyState();
      syncBlockUi();
    }).observe(document.body, { childList: true, subtree: true, attributes: true });
  }

  function isGroupBlockElement(block) {
    var lessonType;

    if (!block) {
      return false;
    }

    lessonType = (block.getAttribute("data-lesson-type") || "").trim();
    if (lessonType) {
      return lessonType === "group";
    }

    // Legacy generated group blocks may still lack explicit lesson type.
    return !block.getAttribute("data-block-id");
  }

  function refreshBaseBlockInteractions(root) {
    var scope = root && root.querySelectorAll ? root : document;

    scope.querySelectorAll(".activity-block").forEach(function (block) {
      if (!isGroupBlockElement(block)) {
        return;
      }
      attachBaseBlockInteractions(block);
    });
  }

  function syncBlockUi() {
    document.body.classList.toggle(
      "schedgen-sync-block",
      _blockNewEditsUntilSync && !window.editDialogOpen
    );
    if (_blockNewEditsUntilSync && !window.editDialogOpen) {
      deactivateTransientModes();
    }
  }

  function setPublishedGroupBaseline(blocks) {
    _publishedGroupSignature = buildGroupSignature(blocks);
    updateDirtyState();
  }

  function hasUnpublishedGroupChanges() {
    if (currentRole() !== "admin") {
      return false;
    }
    return buildGroupSignature() !== (_publishedGroupSignature || "[]");
  }

  function updateDirtyState() {
    var hasChanges = hasUnpublishedGroupChanges();

    if (!document.body) {
      return hasChanges;
    }
    document.body.classList.toggle("schedgen-has-unpublished-changes", hasChanges);
    return hasChanges;
  }

  function deactivateTransientModes() {
    var addModeButton = document.getElementById("toggle-add-mode");
    var deleteButton = document.getElementById("delete-block-button");

    if (addModeButton && addModeButton.classList.contains("active")) {
      addModeButton.click();
    }
    if (deleteButton && deleteButton.classList.contains("active")) {
      deleteButton.click();
    }
  }

  function ensureBanner() {
    var banner = document.getElementById("schedgen-update-banner");
    var anchor;
    var container;

    if (banner) {
      return banner;
    }
    banner = document.createElement("div");
    banner.id = "schedgen-update-banner";
    anchor = document.getElementById("schedgen-lock-banner");
    container = document.querySelector(".schedule-container");

    if (anchor && anchor.parentNode) {
      anchor.insertAdjacentElement("afterend", banner);
    } else if (container && container.parentNode) {
      container.parentNode.insertBefore(banner, container);
    } else {
      document.body.appendChild(banner);
    }
    return banner;
  }

  function showUpdateBanner(message) {
    var banner = ensureBanner();

    banner.textContent = message;
    banner.style.display = "block";
    if (_updateBannerTimer) {
      window.clearTimeout(_updateBannerTimer);
    }
    _updateBannerTimer = window.setTimeout(function () {
      banner.style.display = "none";
      _updateBannerTimer = null;
    }, 10000);
  }

  function clearUpdateBanner() {
    var banner = document.getElementById("schedgen-update-banner");

    if (_updateBannerTimer) {
      window.clearTimeout(_updateBannerTimer);
      _updateBannerTimer = null;
    }
    if (banner) {
      banner.style.display = "none";
      banner.textContent = "";
    }
  }

  function showToast(message, type, duration) {
    var toast = document.getElementById("schedgen-base-sync-toast");

    if (!toast) {
      toast = document.createElement("div");
      toast.id = "schedgen-base-sync-toast";
      document.body.appendChild(toast);
    }
    if (_toastTimer) {
      window.clearTimeout(_toastTimer);
    }
    toast.textContent = message;
    toast.style.backgroundColor =
      type === "error" ? "#b3261e" : type === "warning" ? "#c57f00" : "#2e7d32";
    toast.style.display = "block";
    _toastTimer = window.setTimeout(function () {
      toast.style.display = "none";
      _toastTimer = null;
    }, duration || 3000);
  }

  function getHiddenDayButtons() {
    return Array.from(document.querySelectorAll(".toggle-day-button.active"));
  }

  function withHiddenDaysVisible(callback) {
    var hiddenButtons = getHiddenDayButtons();
    var result;

    if (hiddenButtons.length) {
      hiddenButtons.forEach(function (btn) {
        var dayCode = btn.getAttribute("data-day");
        if (dayCode && typeof window.toggleDay === "function") {
          window.toggleDay(btn, dayCode);
        }
      });
    }

    try {
      result = typeof callback === "function" ? callback() : null;
    } finally {
      hiddenButtons.forEach(function (btn) {
        var dayCode = btn.getAttribute("data-day");
        if (dayCode && typeof window.toggleDay === "function") {
          window.toggleDay(btn, dayCode);
        }
      });
    }

    return result;
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

    header = container.querySelector("th.day-" + day);
    return !!(header && window.getComputedStyle(header).display === "none");
  }

  function requestJson(url, method, payload) {
    var options = {
      method: method || "GET",
      headers: { Accept: "application/json" },
    };

    if (typeof payload !== "undefined") {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }

    return fetch(url, options)
      .then(function (response) {
        if (response.status === 401) {
          if (typeof window.handleSessionExpired === "function") {
            window.handleSessionExpired();
          }
          return null;
        }
        return response.text().then(function (text) {
          var data = {};
          if (text) {
            try {
              data = JSON.parse(text);
            } catch (error) {
              data = {};
            }
          }
          return { ok: response.ok, status: response.status, data: data };
        });
      })
      .catch(function (error) {
        console.error("Base sync request failed:", error);
        return null;
      });
  }

  function hasUnsafeLocalState() {
    var addModeButton = document.getElementById("toggle-add-mode");
    var inEditMode =
      authUi() &&
      typeof authUi().isEditMode === "function" &&
      authUi().isEditMode();

    return !!(
      inEditMode ||
      window.editDialogOpen ||
      window.draggedBlock ||
      window.isResizing ||
      document.body.classList.contains("delete-mode") ||
      (addModeButton && addModeButton.classList.contains("active"))
    );
  }

  function hasActiveEditLock() {
    return isInEditMode();
  }

  function hasUnstablePublishState() {
    var addModeButton = document.getElementById("toggle-add-mode");

    return !!(
      window.editDialogOpen ||
      window.draggedBlock ||
      _baseActiveDrag ||
      _basePendingDragStart ||
      window.isResizing ||
      _basePendingResize ||
      document.body.classList.contains("delete-mode") ||
      (addModeButton && addModeButton.classList.contains("active"))
    );
  }

  function ensureStablePublishState() {
    deactivateTransientModes();
    clearBasePendingDragStart();

    if (!hasUnstablePublishState()) {
      return true;
    }
    window.alert(
      "Завершите текущее действие редактирования перед публикацией: открытый диалог, drag, resize, add/delete mode."
    );
    return false;
  }

  function canStartEditing() {
    if (!_blockNewEditsUntilSync) {
      return true;
    }
    window.alert(
      "Базовое расписание обновлено на сервере. Обновите страницу перед началом редактирования."
    );
    return false;
  }

  function setBaseRevision(revision) {
    _baseRevision = revision || null;
    window.PUBLISHED_BASE_AVAILABLE = !!_baseRevision;
  }

  function handleBaseRevision(revision) {
    if (typeof revision === "undefined") {
      return;
    }
    if ((revision || null) !== _baseRevision) {
      _baseRevision = revision || null;
      _basePendingUpdate = true;
    }
    if (!_basePendingUpdate) {
      return;
    }
    if (!_baseRevision) {
      _basePendingUpdate = false;
      _blockNewEditsUntilSync = false;
      window.PUBLISHED_BASE_AVAILABLE = false;
      clearUpdateBanner();
      syncBlockUi();
      return;
    }
    if (!hasUnsafeLocalState()) {
      refreshBaseLayer();
      return;
    }
    _blockNewEditsUntilSync = true;
    showUpdateBanner(
      "Базовое расписание обновлено на сервере. Завершите текущую операцию и синхронизируйтесь."
    );
    syncBlockUi();
  }

  function refreshBaseLayer(preloaded) {
    if (preloaded) {
      applyBaseScheduleData(preloaded);
      if (typeof window.refreshIndividualLayer === "function") {
        return Promise.resolve(window.refreshIndividualLayer(preloaded)).then(
          function () {
            return preloaded;
          }
        );
      }
      return Promise.resolve(preloaded);
    }

    return requestJson("/api/schedule").then(function (result) {
      if (!result || !result.ok) {
        _blockNewEditsUntilSync = true;
        showUpdateBanner(
          "Не удалось синхронизировать базовое расписание. Повторите обновление страницы."
        );
        syncBlockUi();
        return null;
      }
      applyBaseScheduleData(result.data);
      if (typeof window.refreshIndividualLayer === "function") {
        return Promise.resolve(window.refreshIndividualLayer(result.data)).then(
          function () {
            return result.data;
          }
        );
      }
      return result.data;
    });
  }

  function applyBaseScheduleData(data) {
    var blocks;

    if (!data || (!("base_revision" in data) && !("published_base_available" in data))) {
      return data || null;
    }
    setBaseRevision(data.base_revision);
    if (data.published_base_available !== true) {
      _basePendingUpdate = false;
      _blockNewEditsUntilSync = false;
      clearUpdateBanner();
      syncBlockUi();
      return data;
    }

    blocks = Array.isArray(data.base) ? data.base : [];
    removeGroupBlocks();
    blocks.forEach(function (block) {
      renderBaseBlock(block, true);
    });
    reapplyLessonTypeFilterAfterBaseMutation();
    notifySearchScheduleMutation();

    _basePendingUpdate = false;
    _blockNewEditsUntilSync = false;
    setPublishedGroupBaseline(blocks);
    clearUpdateBanner();
    syncBlockUi();
    return data;
  }

  function preparePublishPreflight(options) {
    options = options || {};

    if (currentRole() !== "admin") {
      window.alert("Недостаточно прав для публикации расписания.");
      return false;
    }
    if (!hasActiveEditLock()) {
      window.alert("Чтобы опубликовать расписание, сначала нажмите «Начать редактирование».");
      return false;
    }
    if (_basePendingUpdate) {
      window.alert(
        "На сервере уже есть более новая версия базового расписания. Сначала синхронизируйтесь."
      );
      if (!hasUnsafeLocalState()) {
        refreshBaseLayer();
      }
      return false;
    }
    if (!ensureStablePublishState()) {
      return false;
    }
    if (!normalizeExistingGroupBlockRuntimeAttrs().ok) {
      return false;
    }
    if (!hasUnpublishedGroupChanges()) {
      if (options.showNoChangesAlert !== false) {
        window.alert("Нет изменений для публикации.");
      }
      return false;
    }
    return true;
  }

  function collectBlocksForPublish() {
    var blocks;
    var normalization;

    normalization = normalizeExistingGroupBlockRuntimeAttrs();
    if (!normalization.ok) {
      return null;
    }

    blocks = withHiddenDaysVisible(function () {
      return collectScheduleDataSafe();
    });
    if (!Array.isArray(blocks)) {
      window.alert("Функция сбора данных расписания недоступна.");
      return null;
    }
    if (buildGroupSignature(blocks) === (_publishedGroupSignature || "[]")) {
      window.alert("Нет изменений для публикации.");
      return null;
    }
    return blocks;
  }

  function handlePublishFailure(publishResult) {
    var data = (publishResult && publishResult.data) || {};
    var code = data.code || "";
    var error = data.error || "Не удалось опубликовать расписание.";

    if (publishResult && publishResult.status === 403 && code === "NO_LOCK") {
      if (window.SchedGenLockUI && typeof window.SchedGenLockUI.refreshLockStatus === "function") {
        window.SchedGenLockUI.refreshLockStatus();
      }
      return "Публикация невозможна без активного режима редактирования. Нажмите «Начать редактирование» и повторите.";
    }
    if (publishResult && publishResult.status === 409 && code === "BASE_REVISION_CONFLICT") {
      _basePendingUpdate = true;
      if (typeof data.current_base_revision !== "undefined") {
        _baseRevision = data.current_base_revision || null;
      }
      showUpdateBanner(
        "На сервере есть более новая версия базового расписания. Синхронизируйтесь перед публикацией."
      );
      syncBlockUi();
      return "На сервере есть более новая версия базового расписания. Сначала синхронизируйтесь.";
    }
    if (publishResult && publishResult.status === 400 && code === "EXPECTED_BASE_REVISION_REQUIRED") {
      return "Не удалось опубликовать расписание: клиент не передал ревизию базового расписания. Обновите страницу.";
    }
    return error;
  }

  function publishCollectedBlocks(blocks) {
    return requestJson("/api/schedule/publish", "POST", {
      blocks: blocks,
      expected_base_revision: _baseRevision,
    }).then(function (publishResult) {
      var error;

      if (!publishResult) {
        window.alert("Не удалось опубликовать расписание из-за ошибки сети.");
        return false;
      }
      if (!publishResult.ok || publishResult.data.ok === false) {
        error = handlePublishFailure(publishResult);
        window.alert(error);
        return false;
      }

      setBaseRevision(publishResult.data.base_revision || publishResult.data.published_at);
      _basePendingUpdate = false;
      _blockNewEditsUntilSync = false;
      setPublishedGroupBaseline(blocks);
      clearUpdateBanner();
      syncBlockUi();
      showToast(
        publishResult.data.changed === false
          ? "Изменений для публикации не найдено."
          : "Расписание опубликовано. Другие пользователи увидят обновление после следующего опроса/обновления страницы.",
        publishResult.data.changed === false ? "warning" : "success",
        5000
      );
      return true;
    });
  }

  function publishSchedule() {
    if (!preparePublishPreflight({ showNoChangesAlert: true })) {
      return;
    }
    if (
      !window.confirm(
        "Перед публикацией будет выполнена синхронизация индивидуальных занятий. Продолжить?"
      )
    ) {
      return;
    }

    prepareSearchForSerialization();

    requestJson("/api/individual_lessons").then(function (refreshResult) {
      if (!refreshResult || !refreshResult.ok) {
        window.alert(
          "Не удалось синхронизировать индивидуальные занятия перед публикацией. Публикация отменена."
        );
        return;
      }

      Promise.resolve(
        typeof window.refreshIndividualLayer === "function"
          ? window.refreshIndividualLayer(refreshResult.data)
          : refreshResult.data
      ).then(function () {
        var blocks;

        blocks = collectBlocksForPublish();
        if (!blocks) {
          return;
        }
        publishCollectedBlocks(blocks);
      });
    });
  }

  function collectScheduleDataSafe() {
    if (typeof collectScheduleData === "function") {
      try {
        return collectScheduleData({ includeHidden: true });
      } catch (error) {
        console.warn("collectScheduleData failed, falling back to DOM snapshot:", error);
      }
    }
    if (typeof window.collectScheduleData === "function") {
      try {
        return window.collectScheduleData({ includeHidden: true });
      } catch (error2) {
        console.warn("window.collectScheduleData failed, falling back to DOM snapshot:", error2);
      }
    }
    return buildScheduleSnapshotFromDom();
  }

  function publishScheduleForNavigation() {
    var blocks;

    if (!preparePublishPreflight({ showNoChangesAlert: true })) {
      return Promise.resolve(false);
    }

    prepareSearchForSerialization();

    return requestJson("/api/individual_lessons").then(function (refreshResult) {
      if (!refreshResult || !refreshResult.ok) {
        window.alert(
          "Не удалось синхронизировать индивидуальные занятия перед публикацией. Публикация отменена."
        );
        return false;
      }

      return Promise.resolve(
        typeof window.refreshIndividualLayer === "function"
          ? window.refreshIndividualLayer(refreshResult.data)
          : refreshResult.data
      ).then(function () {
        blocks = collectBlocksForPublish();
        if (!blocks) {
          return false;
        }
        return publishCollectedBlocks(blocks);
      });
    });
  }

  function buildScheduleSnapshotFromDom() {
    var scheduleData = [];

    document.querySelectorAll(".schedule-container").forEach(function (container) {
      var building = container.getAttribute("data-building") || "";
      var table = container.querySelector(".schedule-grid");

      if (!table) {
        return;
      }

      container.querySelectorAll(".activity-block").forEach(function (block) {
        var day;
        var colIndex;
        var roomName;
        var timeRange;
        var lines;

        day = block.getAttribute("data-day") || "";
        colIndex = toInteger(block.getAttribute("data-col-index"), -1);
        roomName = normalizeRoomName(
          resolveRoomName(table, day, colIndex) || block.getAttribute("data-room") || "",
          building
        );
        timeRange = resolveBlockTimeRange(block);
        lines = extractBlockLines(block);

        if (!building || !day || !roomName || !timeRange) {
          return;
        }

        scheduleData.push({
          subject: lines[0] || "",
          students: lines[2] || "",
          teacher: lines[1] || "",
          room: roomName,
          room_display: roomName,
          building: building,
          day: day,
          start_time: timeRange.start,
          end_time: timeRange.end,
          duration: timeRange.duration,
          color: window.getComputedStyle(block).backgroundColor || "",
          lesson_type: block.getAttribute("data-lesson-type") || "group",
        });
      });
    });

    return scheduleData;
  }

  function buildGroupSignature(blocks) {
    return JSON.stringify(
      normalizeBlocksForSignature(
        Array.isArray(blocks) ? blocks : buildScheduleSnapshotFromDom()
      )
    );
  }

  function normalizeBlocksForSignature(blocks) {
    return (blocks || [])
      .filter(function (block) {
        return block && block.lesson_type === "group";
      })
      .map(function (block) {
        return {
          building: String(block.building || "").trim(),
          day: String(block.day || "").trim(),
          room: String(block.room || block.room_display || "").trim(),
          start_time: String(block.start_time || "").trim(),
          end_time: String(block.end_time || "").trim(),
          subject: String(block.subject || "").trim(),
          teacher: String(block.teacher || "").trim(),
          students: String(block.students || "").trim(),
          lesson_type: "group",
          color: normalizeColorForSignature(block.color || ""),
        };
      })
      .sort(function (a, b) {
        return JSON.stringify(a).localeCompare(JSON.stringify(b));
      });
  }

  function normalizeColorForSignature(value) {
    var color = String(value || "").trim().toLowerCase();
    var rgbMatch;
    var toHex;

    if (!color) {
      return "";
    }
    if (color.charAt(0) === "#") {
      return color;
    }

    rgbMatch = color.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!rgbMatch) {
      return color;
    }
    toHex = function (part) {
      return parseInt(part, 10).toString(16).padStart(2, "0");
    };
    return "#" + toHex(rgbMatch[1]) + toHex(rgbMatch[2]) + toHex(rgbMatch[3]);
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

  function resolveRoomName(table, day, colIndex) {
    var headers;
    var headerText;

    if (!table || !day || colIndex < 0) {
      return "";
    }

    headers = table.querySelectorAll("th.day-" + day);
    if (headers.length <= colIndex) {
      return "";
    }

    headerText = (headers[colIndex].innerText || headers[colIndex].textContent || "").trim();
    return headerText.replace(day, "").trim();
  }

  function normalizeRoomName(room, building) {
    var normalizedRoom = (room || "").trim();

    if (typeof window.normalizeRoomForBuilding === "function") {
      return window.normalizeRoomForBuilding(normalizedRoom, building);
    }

    if (!normalizedRoom) {
      return "";
    }
    if (building === "Villa" && normalizedRoom.length > 1 && normalizedRoom.charAt(0).toUpperCase() === "V") {
      return normalizedRoom.slice(1).trim();
    }
    if (building === "Kolibri" && normalizedRoom.length > 1 && normalizedRoom.charAt(0).toUpperCase() === "K") {
      return normalizedRoom.slice(1).trim();
    }
    return normalizedRoom;
  }

  function resolveBlockTimeRange(block) {
    return (
      resolveBlockTimeRangeFromRows(block) ||
      resolveBlockTimeRangeFromText(block) ||
      resolveBlockTimeRangeFromAttrs(block)
    );
  }

  function resolveBlockTimeRangeFromAttrs(block) {
    var startTime = (block.getAttribute("data-start-time") || "").trim();
    var endTime = (block.getAttribute("data-end-time") || "").trim();
    var startMinutes = parseClockTime(startTime);
    var endMinutes = parseClockTime(endTime);

    if (startMinutes >= 0 && endMinutes > startMinutes) {
      return {
        start: formatClockTime(startMinutes),
        end: formatClockTime(endMinutes),
        duration: endMinutes - startMinutes,
      };
    }
    return null;
  }

  function resolveBlockTimeRangeFromText(block) {
    var lines;
    var timeMatch;
    var startMinutes;
    var endMinutes;
    var i;

    lines = extractBlockLines(block);
    for (i = lines.length - 1; i >= 0; i -= 1) {
      timeMatch = lines[i].match(/(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})/);
      if (!timeMatch) {
        continue;
      }
      startMinutes = parseClockTime(timeMatch[1]);
      endMinutes = parseClockTime(timeMatch[2]);
      if (startMinutes >= 0 && endMinutes > startMinutes) {
        return {
          start: formatClockTime(startMinutes),
          end: formatClockTime(endMinutes),
          duration: endMinutes - startMinutes,
        };
      }
    }
    return null;
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
      duration: endMinutes - startMinutes,
    };
  }

  function parseClockTime(value) {
    var match = String(value || "").trim().match(/^(\d{1,2}):(\d{2})$/);

    if (!match) {
      return -1;
    }

    return parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
  }

  function formatClockTime(minutes) {
    var hours = Math.floor(minutes / 60);
    var mins = minutes % 60;

    return String(hours).padStart(2, "0") + ":" + String(mins).padStart(2, "0");
  }

  function removeGroupBlocks() {
    document
      .querySelectorAll('.activity-block[data-lesson-type="group"]')
      .forEach(function (block) {
        if (block.parentNode) {
          block.parentNode.removeChild(block);
        }
      });
  }

  function renderBaseBlock(block, deferLayout) {
    var building = (block.building || "").trim();
    var day = (block.day || "").trim();
    var room = normalizeRoomName(block.room || block.room_display || "", building);
    var container = findScheduleContainer(building);
    var colIndex;
    var rows;
    var timeText;
    var element;

    if (!container || !building || !day || !room) {
      return null;
    }

    colIndex = resolveColumnIndex(building, day, room);
    if (colIndex < 0) {
      return null;
    }

    rows = resolveRows(block);
    timeText = (block.start_time || "") + "-" + (block.end_time || "");

    element = document.createElement("div");
    element.className = "activity-block activity-day-" + day;
    element.setAttribute("data-day", day);
    element.setAttribute("data-col-index", String(colIndex));
    element.setAttribute("data-building", building);
    element.setAttribute("data-lesson-type", "group");
    element.setAttribute("data-room", room);
    element.setAttribute("data-start-time", block.start_time || "");
    element.setAttribute("data-end-time", block.end_time || "");
    element.setAttribute("data-start-row", String(rows.start_row));
    element.setAttribute("data-row-span", String(rows.row_span));
    element.style.backgroundColor = block.color || "#FFFBD3";
    element.style.width = "100px";
    if (isDayHidden(day, container)) {
      element.style.display = "none";
    }

    if (typeof getContrastTextColor === "function") {
      element.style.color = getContrastTextColor(element.style.backgroundColor);
    }

    element.innerHTML = [
      "<strong>" + escapeHtml(block.subject || "") + "</strong>",
      escapeHtml(block.teacher || ""),
      escapeHtml(block.students || ""),
      escapeHtml(room),
      escapeHtml(timeText),
    ].join("<br>");
    container.appendChild(element);
    syncGroupBlockRuntimeAttrs(element);
    attachBaseBlockInteractions(element);
    if (!deferLayout) {
      reapplyLessonTypeFilterAfterBaseMutation();
    }
    return element;
  }

  function attachBaseBlockInteractions(block) {
    if (!block || block.__baseSyncInteractionsAttached) {
      return;
    }
    block.__baseSyncInteractionsAttached = true;

    block.addEventListener("mousedown", function (event) {
      handleBaseBlockMouseDown(block, event);
    });
    block.addEventListener("dblclick", function (event) {
      handleBaseBlockDoubleClick(block, event);
    });
  }

  function handleBaseBlockMouseDown(block, event) {
    var rect;
    var clientX;
    var clientY;

    if (!block || event.button !== 0 || !isInEditMode()) {
      return;
    }
    if ((block.getAttribute("data-lesson-type") || "group") !== "group") {
      return;
    }
    if (window.editDialogOpen || document.body.classList.contains("delete-mode")) {
      return;
    }

    rect = block.getBoundingClientRect();
    if (event.clientY >= rect.bottom - 8) {
      return;
    }

    clientX = event.clientX;
    clientY = event.clientY;
    clearBasePendingDragStart();
    _basePendingDragStart = {
      block: block,
      timer: window.setTimeout(function () {
        beginBaseDrag(block, clientX, clientY);
      }, 200),
    };
    event.preventDefault();
  }

  function handleBaseBlockDoubleClick(block, event) {
    if (!block || !isInEditMode()) {
      return;
    }
    clearBasePendingDragStart();
    cancelBaseDrag(block);
    event.preventDefault();
    event.stopPropagation();

    if (window.editDialogOpen) {
      return;
    }

    _baseEditedBlock = block;
    if (typeof window.openEditDialog === "function") {
      window.openEditDialog(
        block,
        block.style.left || "",
        block.style.top || "",
        block.getAttribute("data-building") || ""
      );
    }
  }

  function clearBasePendingDragStart() {
    if (_basePendingDragStart && _basePendingDragStart.timer) {
      clearTimeout(_basePendingDragStart.timer);
    }
    _basePendingDragStart = null;
  }

  function beginBaseDrag(block, clientX, clientY) {
    var rect;

    if (!block || !block.parentElement || !isInEditMode()) {
      clearBasePendingDragStart();
      return;
    }

    rect = block.getBoundingClientRect();
    _baseActiveDrag = {
      block: block,
      container: block.parentElement,
      offsetX: clientX - rect.left,
      offsetY: clientY - rect.top,
      initialLeft: parseFloat(block.style.left) || 0,
      initialTop: parseFloat(block.style.top) || 0,
      initialLeftStyle: block.style.left || "",
      initialTopStyle: block.style.top || "",
      initialDay: block.getAttribute("data-day"),
      initialColIndex: block.getAttribute("data-col-index"),
      initialStartRow: block.getAttribute("data-start-row"),
      initialClassName: block.className,
      moved: false,
    };
    clearBasePendingDragStart();
    pauseCompactRowsForBaseDrag();
    block.style.opacity = "0.7";
  }

  function handleBaseDragMove(event) {
    var drag = _baseActiveDrag;
    var containerRect;
    var newLeft;
    var newTop;
    var snapped;

    if (!drag || !drag.block || !drag.container || window.editDialogOpen) {
      return;
    }

    containerRect = drag.container.getBoundingClientRect();
    newLeft = event.clientX - containerRect.left - drag.offsetX + drag.container.scrollLeft;
    newTop = event.clientY - containerRect.top - drag.offsetY + drag.container.scrollTop;

    if (typeof GridSnapService !== "undefined" && GridSnapService) {
      snapped = GridSnapService.snapToGrid(newLeft, newTop, drag.block);
      newLeft = snapped.left;
      newTop = snapped.top;
    }

    drag.moved =
      drag.moved ||
      Math.abs(newLeft - drag.initialLeft) > 1 ||
      Math.abs(newTop - drag.initialTop) > 1;
    drag.block.style.left = newLeft + "px";
    drag.block.style.top = newTop + "px";
    event.preventDefault();
  }

  function handleBaseDragEnd(event) {
    var drag = _baseActiveDrag;

    if (!drag) {
      clearBasePendingDragStart();
      return;
    }

    _baseActiveDrag = null;
    try {
      drag.block.style.opacity = "1";
      if (!drag.moved) {
        return;
      }

      if (typeof BlockDropService !== "undefined" && BlockDropService) {
        BlockDropService.processBlockDrop(drag.block);
      } else if (typeof processBlockDrop === "function") {
        processBlockDrop(drag.block);
      }

      syncGroupBlockRuntimeAttrs(drag.block);
      event.preventDefault();
    } finally {
      resumeCompactRowsAfterBaseDrag(true);
    }
  }

  function cancelBaseDrag(block) {
    if (!_baseActiveDrag) {
      return;
    }
    if (block && _baseActiveDrag.block !== block) {
      return;
    }
    if (_baseActiveDrag.block) {
      restoreBaseDragSnapshot(_baseActiveDrag);
    }
    _baseActiveDrag = null;
    resumeCompactRowsAfterBaseDrag(true);
  }

  function restoreBaseDragSnapshot(drag) {
    if (!drag || !drag.block) {
      return;
    }
    drag.block.style.opacity = "1";
    drag.block.style.left = drag.initialLeftStyle || "";
    drag.block.style.top = drag.initialTopStyle || "";
    restoreAttribute(drag.block, "data-day", drag.initialDay);
    restoreAttribute(drag.block, "data-col-index", drag.initialColIndex);
    restoreAttribute(drag.block, "data-start-row", drag.initialStartRow);
    if (drag.initialClassName) {
      drag.block.className = drag.initialClassName;
    }
  }

  function restoreAttribute(element, name, value) {
    if (value === null || typeof value === "undefined") {
      element.removeAttribute(name);
      return;
    }
    element.setAttribute(name, value);
  }

  function handleBaseResizeStart(event) {
    var block =
      event.target && event.target.closest
        ? event.target.closest('.activity-block[data-lesson-type="group"]')
        : null;

    if (
      !block ||
      event.button !== 0 ||
      !isInEditMode() ||
      window.editDialogOpen ||
      document.body.classList.contains("delete-mode")
    ) {
      _basePendingResize = null;
      return;
    }
    if (!isInBaseResizeZone(block, event.clientY)) {
      _basePendingResize = null;
      return;
    }

    _basePendingResize = block;
  }

  function handleBaseResizeEnd() {
    if (!_basePendingResize) {
      return;
    }
    syncGroupBlockRuntimeAttrs(_basePendingResize);
    _basePendingResize = null;
  }

  function handleBaseEditSubmit(event) {
    var form = event.target;

    if (!form || form.id !== "edit-form" || !_baseEditedBlock) {
      return;
    }
    window.setTimeout(function () {
      syncGroupBlockRuntimeAttrs(_baseEditedBlock);
      _baseEditedBlock = null;
    }, 0);
  }

  function handleBaseEditCancel(event) {
    if (event.target && event.target.closest && event.target.closest("#cancel-edit")) {
      _baseEditedBlock = null;
    }
  }

  function isInBaseResizeZone(block, clientY) {
    var rect = block.getBoundingClientRect();
    return clientY >= rect.bottom - 6 && clientY <= rect.bottom + 2;
  }

  function syncGroupBlockRuntimeAttrs(block) {
    var container;
    var table;
    var building;
    var day;
    var colIndex;
    var lines;
    var room;
    var timeRange;
    var rows;
    var result;

    if (!block || !isGroupBlockElement(block)) {
      return { ok: true, skipped: true };
    }

    block.classList.remove("schedgen-publish-invalid");
    container = block.closest(".schedule-container");
    table = container ? container.querySelector(".schedule-grid") : null;
    building =
      (container && container.getAttribute("data-building")) ||
      block.getAttribute("data-building") ||
      "";
    day = block.getAttribute("data-day") || "";
    colIndex = toInteger(block.getAttribute("data-col-index"), -1);
    lines = extractBlockLines(block);
    room = normalizeRoomName(
      resolveRoomName(table, day, colIndex) || lines[3] || block.getAttribute("data-room") || "",
      building
    );
    timeRange = resolveBlockTimeRangeFromRows(block);

    if (!timeRange) {
      timeRange = resolveBlockTimeRangeFromText(block) || resolveBlockTimeRangeFromAttrs(block);
      rows = timeRange ? deriveRowsFromTimeRange(timeRange) : null;
      if (rows) {
        block.setAttribute("data-start-row", String(rows.start_row));
        block.setAttribute("data-row-span", String(rows.row_span));
      }
    }

    if (!container || !table) {
      return markInvalidGroupBlock(block, "Не найден контейнер или таблица расписания.");
    }
    if (!building || !day || colIndex < 0) {
      return markInvalidGroupBlock(block, "Не заполнены координаты блока.");
    }
    if (day === "So") {
      return markInvalidGroupBlock(block, "Воскресенье доступно только для trial-занятий.");
    }
    if (!room) {
      return markInvalidGroupBlock(block, "Не удалось определить кабинет блока.");
    }
    if (!timeRange) {
      return markInvalidGroupBlock(block, "Не удалось определить время блока.");
    }

    block.setAttribute("data-building", building);
    block.setAttribute("data-day", day);
    block.setAttribute("data-col-index", String(colIndex));
    block.setAttribute("data-lesson-type", "group");
    if (room) {
      block.setAttribute("data-room", room);
    }
    block.setAttribute("data-start-time", timeRange.start);
    block.setAttribute("data-end-time", timeRange.end);

    result = syncGroupBlockContentLines(block, lines, room, timeRange);
    if (!result.ok) {
      return result;
    }
    return { ok: true, block: block };
  }

  function normalizeExistingGroupBlockRuntimeAttrs(options) {
    var firstError = null;
    var count = 0;

    options = options || {};

    document
      .querySelectorAll(".activity-block")
      .forEach(function (block) {
        var result;

        if (!isGroupBlockElement(block)) {
          return;
        }
        count += 1;
        result = syncGroupBlockRuntimeAttrs(block);
        if (!result.ok && !firstError) {
          firstError = result;
        }
      });

    if (firstError) {
      if (options.showAlert !== false) {
        focusInvalidGroupBlock(firstError.block);
        window.alert(
          "Публикация остановлена: " +
            firstError.error +
            " Исправьте выделенный групповой блок через редактирование."
        );
      }
      return { ok: false, error: firstError.error, block: firstError.block, count: count };
    }
    return { ok: true, count: count };
  }

  function deriveRowsFromTimeRange(timeRange) {
    var startMinutes;
    var endMinutes;
    var gridStartValue = typeof gridStart !== "undefined" ? gridStart : 9 * 60;
    var interval = typeof timeInterval !== "undefined" ? timeInterval : 5;
    var startOffset;
    var duration;

    if (!timeRange) {
      return null;
    }
    startMinutes = parseClockTime(timeRange.start);
    endMinutes = parseClockTime(timeRange.end);
    duration = endMinutes - startMinutes;
    startOffset = startMinutes - gridStartValue;
    if (
      startMinutes < 0 ||
      endMinutes <= startMinutes ||
      startOffset < 0 ||
      startOffset % interval !== 0 ||
      duration % interval !== 0
    ) {
      return null;
    }
    return {
      start_row: startOffset / interval,
      row_span: duration / interval,
    };
  }

  function syncGroupBlockContentLines(block, lines, room, timeRange) {
    var subject = lines[0] || "";
    var teacher = lines[1] || "";
    var students = lines[2] || "";
    var timeText = timeRange.start + "-" + timeRange.end;

    if (!subject) {
      return markInvalidGroupBlock(block, "Не заполнен предмет группового блока.");
    }

    block.innerHTML = [
      "<strong>" + escapeHtml(subject) + "</strong>",
      escapeHtml(teacher),
      escapeHtml(students),
      escapeHtml(room),
      escapeHtml(timeText),
    ].join("<br>");
    return { ok: true };
  }

  function markInvalidGroupBlock(block, message) {
    if (block && block.classList) {
      block.classList.add("schedgen-publish-invalid");
    }
    return { ok: false, block: block, error: message };
  }

  function focusInvalidGroupBlock(block) {
    if (!block) {
      return;
    }
    try {
      block.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    } catch (error) {
      block.scrollIntoView();
    }
  }

  function findScheduleContainer(building) {
    if (typeof BuildingService !== "undefined") {
      return BuildingService.findScheduleContainerForBuilding(building);
    }
    return document.querySelector(
      '.schedule-container[data-building="' + cssEscape(building) + '"]'
    );
  }

  function resolveColumnIndex(building, day, room) {
    var colIndex =
      typeof findMatchingColumnInBuilding === "function"
        ? findMatchingColumnInBuilding(day, room, building)
        : -1;
    if (colIndex >= 0) {
      return colIndex;
    }
    if (typeof addColumnIfMissing === "function") {
      return addColumnIfMissing(day, room, building);
    }
    return -1;
  }

  function resolveRows(block) {
    var startRow = toInteger(block.start_row, -1);
    var rowSpan = toInteger(block.row_span, -1);
    var minutes;

    if (startRow >= 0 && rowSpan >= 1) {
      return { start_row: startRow, row_span: rowSpan };
    }
    minutes = parseTimeRange((block.start_time || "") + "-" + (block.end_time || ""));
    return {
      start_row: minutes ? minutes.start_row : 0,
      row_span: minutes ? minutes.row_span : 1,
    };
  }

  function parseTimeRange(value) {
    var match = (value || "").trim().match(/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/);
    var startMinutes;
    var endMinutes;
    var gridStartValue;
    var interval;

    if (!match) {
      return null;
    }
    startMinutes = parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
    endMinutes = parseInt(match[3], 10) * 60 + parseInt(match[4], 10);
    if (startMinutes >= endMinutes) {
      return null;
    }
    gridStartValue = typeof gridStart !== "undefined" ? gridStart : 9 * 60;
    interval = typeof timeInterval !== "undefined" ? timeInterval : 5;
    return {
      start_row: Math.floor((startMinutes - gridStartValue) / interval),
      row_span: Math.floor((endMinutes - startMinutes) / interval),
    };
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
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

  window.publishSchedule = publishSchedule;
  window.SchedGenBaseSyncUI = {
    canStartEditing: canStartEditing,
    hasUnsafeLocalState: hasUnsafeLocalState,
    hasUnpublishedGroupChanges: hasUnpublishedGroupChanges,
    hasPendingBaseUpdate: function () {
      return _basePendingUpdate;
    },
    isBaseSyncBlocked: function () {
      return _blockNewEditsUntilSync;
    },
    getBaseRevision: function () {
      return _baseRevision;
    },
    setBaseRevision: setBaseRevision,
    handleBaseRevision: handleBaseRevision,
    applyBaseScheduleData: applyBaseScheduleData,
    refreshBaseLayer: refreshBaseLayer,
    publishScheduleForNavigation: publishScheduleForNavigation,
    normalizeGroupBlockRuntimeState: syncGroupBlockRuntimeAttrs,
    normalizeAllGroupBlocks: normalizeExistingGroupBlockRuntimeAttrs,
  };
  window.normalizeGroupBlockRuntimeState = syncGroupBlockRuntimeAttrs;
  window.normalizeAllGroupBlocksRuntimeState = normalizeExistingGroupBlockRuntimeAttrs;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
