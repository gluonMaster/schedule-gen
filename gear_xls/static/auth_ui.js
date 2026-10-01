(function () {
  "use strict";

  var HIDE_SELECTORS = {
    viewer: [
      "#menuButton",
      "#menuDropdown",
      "#exportToExcel",
      "#create-block-button",
      "#toggle-add-mode",
      "#delete-block-button",
      ".col-add-btn",
      ".col-delete-btn",
    ],
    organizer: [
      "#exportToExcel",
      "#menuItemNewSchedule",
    ],
    editor: ["#exportToExcel"],
  };

  var EDIT_SELECTORS = [
    "#create-block-button",
    "#toggle-add-mode",
    "#delete-block-button",
    ".col-add-btn",
    ".col-delete-btn",
  ];

  var isEditMode = false;
  var allowUnsafeNavigation = false;

  function currentRole() {
    return window.USER_ROLE || "viewer";
  }

  function baseSyncUi() {
    return window.SchedGenBaseSyncUI || null;
  }

  function currentUser() {
    return window.CURRENT_USER || "";
  }

  function isEditableRole(role) {
    return role === "admin" || role === "editor" || role === "organizer";
  }

  function canEditNow(role) {
    return isEditableRole(role) && isEditMode;
  }

  function getBlockLessonType(block) {
    return block ? block.getAttribute("data-lesson-type") || "group" : "group";
  }

  function canMutateBlock(role, block) {
    var lessonType = getBlockLessonType(block);

    if (role === "admin") {
      return true;
    }
    if (role === "editor") {
      return lessonType !== "group";
    }
    if (role === "organizer") {
      return lessonType === "trial";
    }
    return false;
  }

  function stopEvent(event) {
    if (!event) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") {
      event.stopImmediatePropagation();
    }
  }

  function getBlockedMutationMessage(role, lessonType, action) {
    if (role === "organizer") {
      return action === "delete"
        ? "Организатор может удалять только trial-занятия."
        : "Организатор может изменять только trial-занятия.";
    }
    if (role === "editor" && lessonType === "group") {
      return action === "delete"
        ? "Недостаточно прав для удаления групповых занятий."
        : "Групповые занятия доступны только для просмотра.";
    }
    return "Недостаточно прав для этого действия.";
  }

  function cancelUnauthorizedResize(event) {
    if (typeof handleResizeMouseUp === "function" && window.isResizing) {
      try {
        handleResizeMouseUp(event || {});
      } catch (error) {
        console.warn("Failed to cancel protected resize:", error);
      }
    }
  }

  function init() {
    injectNav();
    ensureBaseStyles();
    syncShellOffsets();
    ensureDomObserver();
    attachNavigationGuards();
    applyRoleRestrictions(currentRole());
    syncShellOffsets();
    ensureResizeHandler();
  }

  function injectNav() {
    var roleLabels;
    var nav;
    var editorTools;
    var statusPanel;
    var statusText;
    var statusActions;
    var searchSlot;
    var form;
    var logoutButton;

    if (!document.body || document.getElementById("schedgen-nav")) {
      return;
    }

    roleLabels = {
      admin: "администратор",
      editor: "редактор",
      organizer: "организатор",
      viewer: "наблюдатель",
    };

    nav = createElement("nav", "schedgen-nav");
    nav.id = "schedgen-nav";
    // Keep editor controls and search in one stable zone so lock-state updates
    // can rerender buttons without destroying the search mount point.
    editorTools = createElement("div", "nav-editor-tools");
    editorTools.id = "schedgen-nav-editor-tools";
    statusPanel = createElement("div", "nav-lock-controls");
    statusPanel.id = "schedgen-nav-lock-controls";
    statusText = createElement("span", "nav-lock-status");
    statusText.id = "schedgen-nav-lock-status";
    statusActions = createElement("span", "nav-lock-actions");
    statusActions.id = "schedgen-nav-lock-actions";
    // Search UI is mounted by a separate module into this dedicated slot.
    searchSlot = createElement("div", "nav-search-slot");
    searchSlot.id = "schedgen-nav-search-slot";
    searchSlot.setAttribute("data-ui-slot", "schedule-search");
    statusPanel.appendChild(statusText);
    statusPanel.appendChild(statusActions);
    editorTools.appendChild(statusPanel);
    editorTools.appendChild(searchSlot);
    nav.appendChild(createElement("span", "nav-brand", "Kolibri SchedGen"));
    nav.appendChild(createLink("/schedule", "Расписание"));
    nav.appendChild(createLink("/rooms", "Аудитории"));
    nav.appendChild(editorTools);
    nav.appendChild(
      createElement(
        "span",
        "nav-user",
        (window.DISPLAY_NAME || currentUser() || "Пользователь") +
          " (" +
          (roleLabels[currentRole()] || currentRole() || "пользователь") +
          ")"
      )
    );

    form = document.createElement("form");
    form.method = "post";
    form.action = "/logout";
    form.style.display = "inline";

    logoutButton = createElement("button", "nav-logout-btn", "Выйти");
    logoutButton.type = "submit";
    form.appendChild(logoutButton);
    nav.appendChild(form);

    document.body.insertBefore(nav, document.body.firstChild);
    document.body.classList.add("schedgen-nav-active");
  }

  function setNavEditorState(options) {
    var panel = document.getElementById("schedgen-nav-lock-controls");
    var status = document.getElementById("schedgen-nav-lock-status");
    var actions = document.getElementById("schedgen-nav-lock-actions");

    if (!panel || !status || !actions) {
      return;
    }

    panel.className = "nav-lock-controls";
    if (options && options.mode) {
      panel.classList.add("mode-" + options.mode);
    }

    status.textContent = (options && options.message) || "";
    actions.textContent = "";

    ((options && options.buttons) || []).forEach(function (buttonConfig) {
      var button = createElement(
        "button",
        "nav-lock-btn",
        buttonConfig.label || ""
      );

      button.type = "button";
      if (buttonConfig.kind) {
        button.classList.add(buttonConfig.kind);
      }
      button.addEventListener("click", buttonConfig.onClick);
      actions.appendChild(button);
    });

    panel.style.display =
      status.textContent || actions.childElementCount ? "flex" : "none";
    syncShellOffsets();
  }

  function syncShellOffsets() {
    var nav = document.getElementById("schedgen-nav");
    var stickyButtons = document.querySelector(".sticky-buttons");
    var navHeight = nav ? nav.offsetHeight : 44;
    var toolbarHeight = stickyButtons ? stickyButtons.offsetHeight : 0;

    if (!document.body) {
      return;
    }

    document.body.classList.add("schedgen-nav-active");
    document.documentElement.style.setProperty(
      "--schedgen-nav-height",
      navHeight + "px"
    );
    document.documentElement.style.setProperty(
      "--schedgen-toolbar-height",
      toolbarHeight + "px"
    );
    document.documentElement.style.setProperty(
      "--schedgen-banner-top",
      navHeight + toolbarHeight + "px"
    );
    document.body.style.paddingTop = navHeight + toolbarHeight + 4 + "px";
  }

  function ensureResizeHandler() {
    if (window.__schedgenShellResizeBound) {
      return;
    }

    window.__schedgenShellResizeBound = true;
    window.addEventListener("resize", syncShellOffsets);
  }

  function getSearchSlot() {
    // Expose a stable lookup so external UI modules do not depend on nav internals.
    return document.getElementById("schedgen-nav-search-slot");
  }

  function createElement(tag, className, text) {
    var element = document.createElement(tag);
    if (className) {
      element.className = className;
    }
    if (typeof text !== "undefined") {
      element.textContent = text;
    }
    return element;
  }

  function createLink(href, text) {
    var link = createElement("a", "nav-link", text);
    link.href = href;
    return link;
  }

  function addStyleOnce(id, cssText) {
    var style;

    if (document.getElementById(id)) {
      return;
    }

    style = document.createElement("style");
    style.id = id;
    style.textContent = cssText;
    document.head.appendChild(style);
  }

  function ensureBaseStyles() {
    addStyleOnce(
      "schedgen-auth-ui-style",
      [
        "body.schedgen-readonly .activity-block { pointer-events: none !important; }",
        "body.schedgen-readonly .drag-handle,",
        "body.schedgen-readonly [data-drag-handle] { pointer-events: none !important; }",
        'body.schedgen-readonly .activity-block[data-lesson-type="group"] { cursor: default !important; }',
        'body[data-user-role="organizer"] #exportToExcel { display: none !important; }',
      ].join("\n")
    );
  }

  function ensureDomObserver() {
    if (document.body.__authUiObserverAttached) {
      return;
    }

    document.body.__authUiObserverAttached = true;
    new MutationObserver(function () {
      syncShellOffsets();
      syncUiState(currentRole());
      if (currentRole() === "editor" || currentRole() === "organizer") {
        processGroupBlocks();
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  function applyRoleRestrictions(role) {
    if (role === "editor" || role === "organizer") {
      attachEditorEventGuards();
      processGroupBlocks();
    }
    syncUiState(role);
  }

  function syncUiState(role) {
    document.body.setAttribute("data-user-role", role || "viewer");
    toggleSelectors(HIDE_SELECTORS.viewer, role === "viewer");
    toggleSelectors(HIDE_SELECTORS.organizer, role === "organizer");
    toggleSelectors(HIDE_SELECTORS.editor, role === "editor");
    toggleSelectors(
      EDIT_SELECTORS,
      role === "viewer" || (isEditableRole(role) && !isEditMode)
    );

    document.body.classList.toggle(
      "schedgen-readonly",
      role === "viewer" || (isEditableRole(role) && !isEditMode)
    );

    if (!canEditNow(role)) {
      deactivateEditModes();
    }
  }

  function toggleSelectors(selectors, hidden) {
    selectors.forEach(function (selector) {
      document.querySelectorAll(selector).forEach(function (element) {
        element.style.display = hidden ? "none" : "";
      });
    });
  }

  function deactivateEditModes() {
    var addModeButton = document.getElementById("toggle-add-mode");
    var deleteButton = document.getElementById("delete-block-button");

    if (addModeButton && addModeButton.classList.contains("active")) {
      addModeButton.click();
    }
    if (deleteButton && deleteButton.classList.contains("active")) {
      deleteButton.click();
    }
  }

  function attachEditorEventGuards() {
    if (document.body.__editorGuardAttached) {
      return;
    }

    document.body.__editorGuardAttached = true;

    document.addEventListener(
      "mousedown",
      function (event) {
        var role = currentRole();
        var block = event.target.closest
          ? event.target.closest(".activity-block")
          : null;

        if (!block || !canEditNow(role) || canMutateBlock(role, block)) {
          return;
        }

        cancelUnauthorizedResize(event);
        stopEvent(event);
      },
      true
    );

    document.addEventListener(
      "click",
      function (event) {
        var role = currentRole();
        var block = event.target.closest
          ? event.target.closest(".activity-block")
          : null;
        var lessonType;

        if (
          !block ||
          !canEditNow(role) ||
          !document.body.classList.contains("delete-mode") ||
          canMutateBlock(role, block)
        ) {
          return;
        }

        lessonType = getBlockLessonType(block);
        stopEvent(event);
        alert(getBlockedMutationMessage(role, lessonType, "delete"));
      },
      true
    );

    document.addEventListener(
      "dblclick",
      function (event) {
        var role = currentRole();
        var block = event.target.closest
          ? event.target.closest(".activity-block")
          : null;
        var lessonType;

        if (!block || !canEditNow(role) || canMutateBlock(role, block)) {
          return;
        }

        lessonType = getBlockLessonType(block);
        stopEvent(event);
        if (lessonType === "group") {
          showReadOnlyBlockInfo(block);
          return;
        }
        alert(getBlockedMutationMessage(role, lessonType, "edit"));
      },
      true
    );
  }

  function processGroupBlocks() {
    document
      .querySelectorAll('.activity-block[data-lesson-type="group"]')
      .forEach(function (block) {
        block.setAttribute("draggable", "false");
        block.style.cursor =
          canEditNow(currentRole()) && !canMutateBlock(currentRole(), block)
            ? "default"
            : "";
        block
          .querySelectorAll(".drag-handle,[data-drag-handle]")
          .forEach(function (handle) {
            handle.style.pointerEvents = "none";
          });
      });
  }

  function attachNavigationGuards() {
    if (document.body.__authUiNavigationGuardsAttached) {
      return;
    }

    document.body.__authUiNavigationGuardsAttached = true;

    document.addEventListener(
      "click",
      function (event) {
        var link = event.target.closest ? event.target.closest("#schedgen-nav a[href]") : null;

        if (!link || allowUnsafeNavigation || !shouldGuardNavigation(link.href)) {
          return;
        }

        event.preventDefault();
        confirmNavigationAway(function () {
          allowAndContinue(function () {
            window.location.href = link.href;
          });
        });
      },
      true
    );

    document.addEventListener(
      "submit",
      function (event) {
        var form = event.target;

        if (
          !form ||
          allowUnsafeNavigation ||
          !form.action ||
          !/\/logout(?:\?|$)/.test(form.action)
        ) {
          return;
        }

        event.preventDefault();
        confirmNavigationAway(function () {
          allowAndContinue(function () {
            form.submit();
          });
        });
      },
      true
    );

    window.addEventListener("beforeunload", function (event) {
      if (allowUnsafeNavigation || !hasUnpublishedChanges()) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    });
  }

  function shouldGuardNavigation(href) {
    var url;

    if (!href || !hasUnpublishedChanges()) {
      return false;
    }
    try {
      url = new URL(href, window.location.href);
    } catch (error) {
      return false;
    }
    if (url.origin !== window.location.origin) {
      return false;
    }
    return url.pathname !== window.location.pathname || url.search !== window.location.search;
  }

  function hasUnpublishedChanges() {
    return !!(
      baseSyncUi() &&
      typeof baseSyncUi().hasUnpublishedGroupChanges === "function" &&
      baseSyncUi().hasUnpublishedGroupChanges()
    );
  }

  function refreshCompactRowsAfterEditModeChange() {
    if (
      window.ScheduleCompactRows &&
      typeof window.ScheduleCompactRows.refresh === "function"
    ) {
      window.ScheduleCompactRows.refresh();
    } else if (typeof window.updateActivityPositions === "function") {
      window.updateActivityPositions();
    }
  }

  function confirmNavigationAway(continueAction) {
    var baseUi = baseSyncUi();

    if (!hasUnpublishedChanges()) {
      continueAction();
      return;
    }

    if (
      window.confirm(
        "Есть неопубликованные изменения группового расписания. Нажмите OK, чтобы опубликовать их сейчас."
      )
    ) {
      if (!baseUi || typeof baseUi.publishScheduleForNavigation !== "function") {
        return;
      }
      Promise.resolve(baseUi.publishScheduleForNavigation()).then(function (published) {
        if (published) {
          continueAction();
        }
      });
      return;
    }

    if (
      window.confirm(
        "Перейти без публикации? Неопубликованные изменения будут потеряны."
      )
    ) {
      continueAction();
    }
  }

  function allowAndContinue(callback) {
    allowUnsafeNavigation = true;
    callback();
    window.setTimeout(function () {
      allowUnsafeNavigation = false;
    }, 1000);
  }

  function setEditMode(enabled) {
    var previousEditMode = isEditMode;

    if (
      enabled &&
      window.ScheduleSearch &&
      typeof window.ScheduleSearch.prepareForEditMode === "function"
    ) {
      window.ScheduleSearch.prepareForEditMode();
    }

    isEditMode = !!enabled;
    syncUiState(currentRole());
    if (
      window.ScheduleSearch &&
      typeof window.ScheduleSearch.handleEditModeChange === "function"
    ) {
      window.ScheduleSearch.handleEditModeChange(isEditMode);
    }
    if (isEditMode !== previousEditMode) {
      refreshCompactRowsAfterEditModeChange();
      document.dispatchEvent(
        new CustomEvent("schedgen:edit-mode-change", {
          detail: { enabled: isEditMode },
        })
      );
    }
  }

  function getBlockInfo(blockElement) {
    var parts = blockElement.innerHTML.split("<br>").map(function (part) {
      return part.replace(/<[^>]+>/g, "").trim();
    });

    return {
      subject: parts[0] || blockElement.dataset.subject || "Не указано",
      teacher: parts[1] || blockElement.dataset.teacher || "Не указано",
      students:
        parts[2] ||
        blockElement.dataset.students ||
        blockElement.dataset.group ||
        "Не указано",
      room: parts[3] || blockElement.dataset.room || "Не указано",
      time:
        parts[4] || blockElement.dataset.time || blockElement.textContent.trim(),
    };
  }

  function showReadOnlyBlockInfo(blockElement) {
    var oldOverlay = document.getElementById("readonly-block-overlay");
    var info;
    var overlay;
    var modal;
    var closeButton;

    if (oldOverlay) {
      oldOverlay.remove();
    }

    info = getBlockInfo(blockElement);
    overlay = document.createElement("div");
    overlay.id = "readonly-block-overlay";
    overlay.style.cssText =
      "position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex;" +
      " align-items: center; justify-content: center; z-index: 10001;";

    modal = document.createElement("div");
    modal.style.cssText =
      "background: #fff; border-radius: 8px; padding: 20px; max-width: 420px;" +
      " width: 90%; box-shadow: 0 8px 24px rgba(0,0,0,.25); font-family: sans-serif;";

    modal.innerHTML =
      "<h3 style=\"margin:0 0 12px\">Информация о занятии</h3>" +
      "<p><strong>Предмет:</strong> " +
      escapeHtml(info.subject) +
      "</p>" +
      "<p><strong>Группа/ученики:</strong> " +
      escapeHtml(info.students) +
      "</p>" +
      "<p><strong>Преподаватель:</strong> " +
      escapeHtml(info.teacher) +
      "</p>" +
      "<p><strong>Кабинет:</strong> " +
      escapeHtml(info.room) +
      "</p>" +
      "<p><strong>Время:</strong> " +
      escapeHtml(info.time) +
      "</p>";

    closeButton = createElement("button", null, "Закрыть");
    closeButton.type = "button";
    closeButton.style.cssText =
      "margin-top: 8px; padding: 8px 14px; border: none; border-radius: 4px;" +
      " background: #1a73e8; color: #fff; cursor: pointer;";
    closeButton.addEventListener("click", function () {
      overlay.remove();
    });

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        overlay.remove();
      }
    });

    modal.appendChild(closeButton);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  window.SchedGenAuthUI = {
    init: init,
    currentRole: currentRole,
    currentUser: currentUser,
    isEditableRole: isEditableRole,
    canMutateBlock: canMutateBlock,
    getBlockLessonType: getBlockLessonType,
    isEditMode: function () {
      return isEditMode;
    },
    setEditMode: setEditMode,
    setNavEditorState: setNavEditorState,
    getSearchSlot: getSearchSlot,
    syncShellOffsets: syncShellOffsets,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
