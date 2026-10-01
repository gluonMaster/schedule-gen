(function () {
  "use strict";

  var RESTORE_OVERLAY_TEXT =
    "Администратор выполняет восстановление базы расписания. Работа временно заблокирована. Вы сможете зайти после завершения восстановления.";
  var DIRTY_BACKUP_WARNING =
    "Есть неопубликованные изменения группового расписания. Резервная копия сохранит только опубликованное серверное состояние. Сначала опубликуйте расписание или продолжите без этих изменений.";
  var RESTORE_EDIT_MODE_MESSAGE =
    "Для восстановления сначала нажмите «Начать редактирование».";
  var STATUS_POLL_MS = 5000;

  var restorePollTimer = null;
  var knownRestoreGeneration = null;
  var restoreIsBlocking = false;
  var selfRestoreRunning = false;

  function authUi() {
    return window.SchedGenAuthUI || null;
  }

  function baseSyncUi() {
    return window.SchedGenBaseSyncUI || null;
  }

  function currentRole() {
    return window.USER_ROLE || "viewer";
  }

  function isAdmin() {
    return currentRole() === "admin";
  }

  function init() {
    if (!authUi()) {
      return;
    }

    ensureStyles();
    startRestorePolling();

    if (isAdmin()) {
      insertAdminMenuItems();
    }
  }

  function insertAdminMenuItems() {
    var dropdown = document.getElementById("menuDropdown");
    var separator;
    var createItem;
    var restoreItem;

    if (!dropdown || document.getElementById("schedgen-menu-backup-create")) {
      return;
    }

    separator = document.createElement("div");
    separator.id = "schedgen-menu-backup-separator";
    separator.className = "schedgen-menu-separator";

    createItem = createMenuItem(
      "schedgen-menu-backup-create",
      "Создать резервную копию",
      openCreateBackupModal
    );
    restoreItem = createMenuItem(
      "schedgen-menu-backup-restore",
      "Восстановить из резервной копии",
      openRestoreModal
    );

    dropdown.appendChild(separator);
    dropdown.appendChild(createItem);
    dropdown.appendChild(restoreItem);
  }

  function createMenuItem(id, label, handler) {
    var item = document.createElement("div");

    item.id = id;
    item.className = "menu-item";
    item.textContent = label;
    item.addEventListener("click", function (event) {
      event.stopPropagation();
      if (typeof window.closeMenu === "function") {
        window.closeMenu();
      }
      handler();
    });
    return item;
  }

  function openCreateBackupModal() {
    var modal = createModal("Создать резервную копию", "schedgen-backup-create-modal");
    var label = createElement("label", "schedgen-backup-field");
    var labelText = createElement("span", null, "Комментарий");
    var comment = document.createElement("textarea");
    var downloadLabel = createElement("label", "schedgen-backup-checkbox");
    var download = document.createElement("input");
    var createBackupButton = createButton("Создать backup", "primary", null);
    var cancelButton = createButton("Отмена", "secondary", modal.close);

    comment.maxLength = 500;
    comment.rows = 3;
    comment.placeholder = "Необязательно";
    label.appendChild(labelText);
    label.appendChild(comment);

    download.type = "checkbox";
    downloadLabel.appendChild(download);
    downloadLabel.appendChild(
      document.createTextNode("Скачать ZIP после создания")
    );

    createBackupButton.addEventListener("click", function () {
      runBackupCreateFlow(modal, comment.value, download.checked, createBackupButton);
    });

    modal.body.appendChild(label);
    modal.body.appendChild(downloadLabel);
    modal.footer.appendChild(cancelButton);
    modal.footer.appendChild(createBackupButton);
    document.body.appendChild(modal.overlay);
    comment.focus();
  }

  function runBackupCreateFlow(modal, comment, download, createButton) {
    var baseUi = baseSyncUi();
    var hasDirtyBase =
      baseUi &&
      typeof baseUi.hasUnpublishedGroupChanges === "function" &&
      baseUi.hasUnpublishedGroupChanges();

    modal.setStatus("");

    if (!hasDirtyBase) {
      createBackup(modal, comment, download, createButton);
      return;
    }

    showChoiceModal({
      title: "Неопубликованные изменения",
      message: DIRTY_BACKUP_WARNING,
      buttons: [
        { label: "Опубликовать и создать backup", value: "publish", kind: "primary" },
        {
          label: "Создать backup без неопубликованных изменений",
          value: "skip",
          kind: "secondary",
        },
        { label: "Отмена", value: null, kind: "secondary" },
      ],
    }).then(function (choice) {
      if (choice === "publish") {
        if (!baseUi || typeof baseUi.publishScheduleForNavigation !== "function") {
          modal.setStatus("Публикация расписания недоступна.", true);
          return;
        }
        setButtonBusy(createButton, true);
        Promise.resolve(baseUi.publishScheduleForNavigation())
          .then(function (published) {
            if (published) {
              createBackup(modal, comment, download, createButton);
              return;
            }
            modal.setStatus("Backup не создан: публикация не завершена.", true);
            setButtonBusy(createButton, false);
          })
          .catch(function (error) {
            console.error("Publish before backup failed:", error);
            modal.setStatus("Backup не создан: ошибка публикации.", true);
            setButtonBusy(createButton, false);
          });
        return;
      }

      if (choice === "skip") {
        createBackup(modal, comment, download, createButton);
      }
    });
  }

  function createBackup(modal, comment, download, createButton) {
    setButtonBusy(createButton, true);
    modal.setStatus("Создаётся резервная копия...");

    requestJson("/api/backups", {
      method: "POST",
      body: { comment: comment || "", download: !!download },
    }).then(function (result) {
      var backup;

      setButtonBusy(createButton, false);
      if (!result) {
        modal.setStatus("Не удалось создать backup.", true);
        return;
      }
      if (!result.response.ok || !result.data.ok) {
        modal.setStatus(errorMessage(result.data, "Не удалось создать backup."), true);
        return;
      }

      backup = result.data.backup || {};
      modal.setStatus("Резервная копия создана: " + (backup.filename || backup.id || ""));
      if (download && backup.download_url) {
        openDownload(backup.download_url);
      }
    });
  }

  function openRestoreModal() {
    var modal = createModal(
      "Восстановить из резервной копии",
      "schedgen-backup-restore-modal"
    );
    var state = {
      backups: [],
      selectedId: null,
      uploading: false,
      restoring: false,
    };
    var uploadRow = createElement("div", "schedgen-upload-row");
    var fileInput = document.createElement("input");
    var uploadButton = createButton("Загрузить ZIP", "secondary", null);
    var list = createElement("div", "schedgen-backup-list");
    var warning = createElement(
      "div",
      "schedgen-restore-warning",
      "Текущее состояние расписания будет заменено данными из выбранной резервной копии."
    );
    var acknowledgeLabel = createElement("label", "schedgen-backup-checkbox");
    var acknowledge = document.createElement("input");
    var restoreButton = createButton("Восстановить", "danger", null);
    var closeButton = createButton("Закрыть", "secondary", modal.close);

    fileInput.type = "file";
    fileInput.accept = ".zip,application/zip,application/x-zip-compressed";
    uploadButton.disabled = true;

    fileInput.addEventListener("change", function () {
      uploadButton.disabled = !fileInput.files || !fileInput.files.length || state.uploading;
    });

    uploadButton.addEventListener("click", function () {
      uploadBackupFile(modal, state, fileInput, uploadButton, list, updateRestoreButton);
    });

    acknowledge.type = "checkbox";
    acknowledge.addEventListener("change", updateRestoreButton);
    acknowledgeLabel.appendChild(acknowledge);
    acknowledgeLabel.appendChild(
      document.createTextNode("Я понимаю, что текущее состояние будет заменено")
    );

    restoreButton.disabled = true;
    restoreButton.addEventListener("click", function () {
      startRestore(modal, state, restoreButton, updateRestoreButton);
    });

    function updateRestoreButton() {
      var selected = getSelectedBackup(state);
      restoreButton.disabled = !(
        selected &&
        selected.valid &&
        acknowledge.checked &&
        !state.restoring
      );
    }

    uploadRow.appendChild(fileInput);
    uploadRow.appendChild(uploadButton);
    modal.body.appendChild(uploadRow);
    modal.body.appendChild(list);
    modal.body.appendChild(warning);
    modal.body.appendChild(acknowledgeLabel);
    modal.footer.appendChild(closeButton);
    modal.footer.appendChild(restoreButton);
    document.body.appendChild(modal.overlay);

    loadBackups(modal, state, list, null, updateRestoreButton);
  }

  function loadBackups(modal, state, list, selectedId, afterRender) {
    modal.setStatus("Загрузка списка backup...");
    list.textContent = "";
    list.appendChild(createElement("div", "schedgen-backup-empty", "Загрузка..."));

    requestJson("/api/backups", { method: "GET" }).then(function (result) {
      if (!result) {
        modal.setStatus("Не удалось загрузить список backup.", true);
        renderBackupList(state, list, afterRender);
        return;
      }
      if (!result.response.ok || !result.data.ok) {
        modal.setStatus(errorMessage(result.data, "Не удалось загрузить список backup."), true);
        renderBackupList(state, list, afterRender);
        return;
      }

      state.backups = Array.isArray(result.data.backups) ? result.data.backups : [];
      if (selectedId && findBackup(state.backups, selectedId)) {
        state.selectedId = selectedId;
      } else if (!findBackup(state.backups, state.selectedId)) {
        state.selectedId = null;
      }
      modal.setStatus("");
      renderBackupList(state, list, afterRender);
    });
  }

  function renderBackupList(state, list, afterRender) {
    list.textContent = "";

    if (!state.backups.length) {
      list.appendChild(
        createElement("div", "schedgen-backup-empty", "Серверных backup пока нет.")
      );
      if (typeof afterRender === "function") {
        afterRender();
      }
      return;
    }

    state.backups.forEach(function (backup) {
      var card = createElement(
        "div",
        "schedgen-backup-card" + (backup.valid ? "" : " invalid")
      );
      var header = createElement("label", "schedgen-backup-card-header");
      var radio = document.createElement("input");
      var title = createElement("span", "schedgen-backup-card-title");
      var meta = createElement("div", "schedgen-backup-card-meta");
      var comment;

      if (backup.id === state.selectedId) {
        card.classList.add("selected");
      }

      radio.type = "radio";
      radio.name = "schedgen-backup-selection";
      radio.disabled = !backup.valid;
      radio.checked = backup.id === state.selectedId;
      radio.addEventListener("change", function () {
        if (!backup.valid) {
          return;
        }
        state.selectedId = backup.id;
        renderBackupList(state, list, afterRender);
      });

      title.textContent = backup.filename || backup.id || "backup.zip";
      header.appendChild(radio);
      header.appendChild(title);
      card.appendChild(header);

      appendMeta(meta, "Дата", formatDate(backup.created_at || backup.uploaded_at));
      appendMeta(meta, "Автор", backupAuthor(backup));
      appendMeta(meta, "Тип", backupKindLabel(backup.backup_kind));
      appendMeta(meta, "Размер", formatSize(backup.size));
      appendMeta(meta, "Base revision", backup.base_revision || "—");
      appendMeta(meta, "Individual revision", backup.individual_revision || "—");
      appendMeta(
        meta,
        "Статус",
        backup.valid
          ? backup.project_root_matches === false
            ? "valid, другой project root"
            : "valid"
          : "invalid: " + (backup.invalid_reason || "ошибка проверки")
      );
      if (backup.uploaded_original_filename) {
        appendMeta(meta, "Исходный файл", backup.uploaded_original_filename);
      }
      card.appendChild(meta);

      if (backup.comment) {
        comment = createElement("div", "schedgen-backup-comment");
        comment.textContent = backup.comment;
        card.appendChild(comment);
      }

      if (backup.valid) {
        card.addEventListener("click", function (event) {
          if (event.target !== radio) {
            state.selectedId = backup.id;
            renderBackupList(state, list, afterRender);
          }
        });
      }

      list.appendChild(card);
    });

    if (typeof afterRender === "function") {
      afterRender();
    }
  }

  function appendMeta(container, label, value) {
    var row = createElement("div", "schedgen-backup-meta-row");
    var labelNode = createElement("span", "schedgen-backup-meta-label", label + ":");
    var valueNode = createElement("span", "schedgen-backup-meta-value", value || "—");

    row.appendChild(labelNode);
    row.appendChild(valueNode);
    container.appendChild(row);
  }

  function uploadBackupFile(modal, state, fileInput, uploadButton, list, afterRender) {
    var file = fileInput.files && fileInput.files[0];
    var formData;

    if (!file) {
      modal.setStatus("Выберите ZIP-файл.", true);
      return;
    }

    formData = new FormData();
    formData.append("file", file);
    state.uploading = true;
    uploadButton.disabled = true;
    modal.setStatus("Загрузка ZIP...");

    requestJson("/api/backups/upload", {
      method: "POST",
      formData: formData,
    }).then(function (result) {
      var backupId = null;

      state.uploading = false;
      uploadButton.disabled = !fileInput.files || !fileInput.files.length;

      if (!result) {
        modal.setStatus("Не удалось загрузить ZIP.", true);
        return;
      }
      if (!result.response.ok || !result.data.ok) {
        modal.setStatus(errorMessage(result.data, "Не удалось загрузить ZIP."), true);
        return;
      }

      backupId = result.data.backup && result.data.backup.id;
      modal.setStatus("ZIP загружен и сохранён как server backup.");
      fileInput.value = "";
      uploadButton.disabled = true;
      loadBackups(modal, state, list, backupId, afterRender);
    });
  }

  function startRestore(modal, state, restoreButton, updateRestoreButton) {
    var selected = getSelectedBackup(state);

    modal.setStatus("");
    if (!selected || !selected.valid) {
      modal.setStatus("Выберите valid backup.", true);
      return;
    }
    if (!authUi() || typeof authUi().isEditMode !== "function" || !authUi().isEditMode()) {
      modal.setStatus(RESTORE_EDIT_MODE_MESSAGE, true);
      return;
    }

    runRestoreRequest(modal, state, restoreButton, updateRestoreButton, false);
  }

  function runRestoreRequest(modal, state, restoreButton, updateRestoreButton, allowForeign) {
    var selected = getSelectedBackup(state);
    var url;

    if (!selected) {
      return;
    }

    state.restoring = true;
    selfRestoreRunning = true;
    restoreButton.disabled = true;
    showRestoreOverlay();
    modal.setStatus("Выполняется восстановление...");
    url = "/api/backups/" + encodeURIComponent(selected.id) + "/restore";

    requestJson(url, {
      method: "POST",
      body: {
        confirm: true,
        allow_foreign_project: allowForeign === true,
      },
    }).then(function (result) {
      state.restoring = false;
      updateRestoreButton();

      if (!result) {
        selfRestoreRunning = false;
        hideRestoreOverlayIfIdle();
        modal.setStatus("Не удалось выполнить restore.", true);
        return;
      }

      if (result.response.ok && result.data.ok) {
        modal.setStatus("Восстановление завершено. Страница будет обновлена.");
        showRestoreOverlay();
        window.setTimeout(function () {
          window.location.href = "/schedule";
        }, 700);
        return;
      }

      if (result.data && result.data.code === "PROJECT_ROOT_MISMATCH") {
        selfRestoreRunning = false;
        hideRestoreOverlayIfIdle();
        askProjectMismatchConfirmation().then(function (confirmed) {
          if (confirmed) {
            runRestoreRequest(modal, state, restoreButton, updateRestoreButton, true);
          } else {
            modal.setStatus("Restore отменён.");
          }
        });
        return;
      }

      if (result.data && result.data.code === "RESTORE_IN_PROGRESS") {
        handleRestoreInProgress(result.data);
        return;
      }

      selfRestoreRunning = false;
      hideRestoreOverlayIfIdle();
      modal.setStatus(errorMessage(result.data, "Не удалось выполнить restore."), true);
    });
  }

  function askProjectMismatchConfirmation() {
    return showChoiceModal({
      title: "Backup из другого проекта",
      message:
        "Project root резервной копии отличается от текущего проекта. Восстановить всё равно?",
      buttons: [
        { label: "Восстановить всё равно", value: true, kind: "danger" },
        { label: "Отмена", value: false, kind: "secondary" },
      ],
    });
  }

  function getSelectedBackup(state) {
    return findBackup(state.backups, state.selectedId);
  }

  function findBackup(backups, id) {
    if (!id) {
      return null;
    }
    for (var i = 0; i < backups.length; i += 1) {
      if (backups[i].id === id) {
        return backups[i];
      }
    }
    return null;
  }

  function startRestorePolling() {
    refreshRestoreStatus();
    if (restorePollTimer !== null) {
      return;
    }
    restorePollTimer = window.setInterval(refreshRestoreStatus, STATUS_POLL_MS);
  }

  function refreshRestoreStatus() {
    requestJson("/api/restore/status", { method: "GET", suppressRestoreHandling: true }).then(
      function (result) {
        if (!result || !result.data) {
          return;
        }
        handleRestoreStatus(result.data);
      }
    );
  }

  function handleRestoreStatus(data) {
    var blocking = isRestoreStatusBlocking(data);
    var generation = normalizeGeneration(data && data.generation);

    if (knownRestoreGeneration === null) {
      knownRestoreGeneration = generation;
    } else if (
      generation !== null &&
      generation !== knownRestoreGeneration &&
      !blocking &&
      !selfRestoreRunning
    ) {
      window.location.href = "/schedule";
      return;
    }

    if (generation !== null) {
      knownRestoreGeneration = generation;
    }

    if (blocking) {
      handleRestoreInProgress(data);
      return;
    }

    restoreIsBlocking = false;
    if (!selfRestoreRunning) {
      hideRestoreOverlay();
    }
  }

  function normalizeGeneration(value) {
    var generation = Number(value);
    return isNaN(generation) ? null : generation;
  }

  function isRestoreStatusBlocking(data) {
    return !!(
      data &&
      (data.restore_in_progress || data.active || data.recovery_required)
    );
  }

  function handleRestoreInProgress(data) {
    restoreIsBlocking = true;
    closeBackupModals();
    closeExternalDialogs();
    setEditModeFalse();
    showRestoreOverlay(data);
  }

  function showRestoreOverlay(data) {
    var overlay = document.getElementById("schedgen-restore-overlay");
    var message;

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "schedgen-restore-overlay";
      overlay.setAttribute("role", "alert");
      overlay.setAttribute("aria-live", "assertive");

      message = createElement("div", "schedgen-restore-overlay-card");
      message.appendChild(createElement("div", "schedgen-restore-spinner"));
      message.appendChild(
        createElement("div", "schedgen-restore-message", RESTORE_OVERLAY_TEXT)
      );
      overlay.appendChild(message);
      document.body.appendChild(overlay);
    }

    document.body.classList.add("schedgen-restore-blocked");
    if (data && data.recovery_required) {
      overlay
        .querySelector(".schedgen-restore-message")
        .textContent =
        data.recovery_message || data.message || RESTORE_OVERLAY_TEXT;
    } else {
      overlay.querySelector(".schedgen-restore-message").textContent =
        RESTORE_OVERLAY_TEXT;
    }
  }

  function hideRestoreOverlayIfIdle() {
    if (!restoreIsBlocking) {
      hideRestoreOverlay();
    }
  }

  function hideRestoreOverlay() {
    var overlay = document.getElementById("schedgen-restore-overlay");

    if (overlay && overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
    document.body.classList.remove("schedgen-restore-blocked");
  }

  function closeBackupModals() {
    document
      .querySelectorAll(".schedgen-backup-modal-overlay")
      .forEach(function (overlay) {
        if (overlay.parentNode) {
          overlay.parentNode.removeChild(overlay);
        }
      });
  }

  function closeExternalDialogs() {
    if (
      window.SchedGenLockUI &&
      typeof window.SchedGenLockUI.closeOpenDialogs === "function"
    ) {
      window.SchedGenLockUI.closeOpenDialogs();
    }
  }

  function setEditModeFalse() {
    if (authUi() && typeof authUi().setEditMode === "function") {
      authUi().setEditMode(false);
    }
  }

  function createModal(title, extraClass) {
    var overlay = createElement("div", "schedgen-backup-modal-overlay");
    var dialog = createElement(
      "div",
      "schedgen-backup-modal" + (extraClass ? " " + extraClass : "")
    );
    var header = createElement("div", "schedgen-backup-modal-header");
    var titleNode = createElement("h2", null, title);
    var closeButton = createButton("×", "icon", close);
    var body = createElement("div", "schedgen-backup-modal-body");
    var status = createElement("div", "schedgen-backup-status");
    var footer = createElement("div", "schedgen-backup-modal-footer");

    closeButton.setAttribute("aria-label", "Закрыть");
    header.appendChild(titleNode);
    header.appendChild(closeButton);
    body.appendChild(status);
    dialog.appendChild(header);
    dialog.appendChild(body);
    dialog.appendChild(footer);
    overlay.appendChild(dialog);

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        close();
      }
    });

    function close() {
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
    }

    function setStatus(message, isError) {
      status.textContent = message || "";
      status.classList.toggle("error", !!isError);
      status.style.display = message ? "block" : "none";
    }

    setStatus("");
    return {
      overlay: overlay,
      dialog: dialog,
      body: body,
      footer: footer,
      close: close,
      setStatus: setStatus,
    };
  }

  function showChoiceModal(options) {
    return new Promise(function (resolve) {
      var overlay = createElement("div", "schedgen-backup-modal-overlay");
      var dialog = createElement("div", "schedgen-backup-modal schedgen-choice-modal");
      var header = createElement("div", "schedgen-backup-modal-header");
      var body = createElement("div", "schedgen-backup-modal-body");
      var footer = createElement("div", "schedgen-backup-modal-footer");
      var settled = false;

      header.appendChild(createElement("h2", null, options.title || ""));
      body.appendChild(createElement("p", "schedgen-choice-message", options.message || ""));
      (options.buttons || []).forEach(function (buttonConfig) {
        var button = createButton(
          buttonConfig.label || "",
          buttonConfig.kind || "secondary",
          function () {
            settle(buttonConfig.value);
          }
        );
        footer.appendChild(button);
      });

      dialog.appendChild(header);
      dialog.appendChild(body);
      dialog.appendChild(footer);
      overlay.appendChild(dialog);
      document.body.appendChild(overlay);

      overlay.addEventListener("click", function (event) {
        if (event.target === overlay) {
          settle(null);
        }
      });

      function settle(value) {
        if (settled) {
          return;
        }
        settled = true;
        if (overlay.parentNode) {
          overlay.parentNode.removeChild(overlay);
        }
        resolve(value);
      }
    });
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

  function createButton(label, kind, onClick) {
    var button = document.createElement("button");

    button.type = "button";
    button.className = "schedgen-backup-btn" + (kind ? " " + kind : "");
    button.textContent = label;
    if (typeof onClick === "function") {
      button.addEventListener("click", onClick);
    }
    return button;
  }

  function setButtonBusy(button, busy) {
    if (!button) {
      return;
    }
    button.disabled = !!busy;
    button.classList.toggle("busy", !!busy);
  }

  function requestJson(url, options) {
    var fetchOptions = {
      method: (options && options.method) || "GET",
      headers: { Accept: "application/json" },
    };

    if (options && options.formData) {
      fetchOptions.body = options.formData;
    } else if (options && Object.prototype.hasOwnProperty.call(options, "body")) {
      fetchOptions.headers["Content-Type"] = "application/json";
      fetchOptions.body = JSON.stringify(options.body);
    }

    return fetch(url, fetchOptions)
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

          if (
            data &&
            data.code === "RESTORE_IN_PROGRESS" &&
            !(options && options.suppressRestoreHandling)
          ) {
            handleRestoreInProgress(data);
          }

          return { response: response, data: data };
        });
      })
      .catch(function (error) {
        console.error("Backup UI request failed:", error);
        return null;
      });
  }

  function errorMessage(data, fallback) {
    if (!data) {
      return fallback;
    }
    return data.error || data.message || fallback;
  }

  function openDownload(url) {
    var link;

    if (!url) {
      return;
    }

    link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function backupAuthor(backup) {
    if (backup.backup_kind === "uploaded") {
      return (
        backup.uploaded_by_display_name ||
        backup.uploaded_by ||
        backup.created_by_display_name ||
        backup.created_by ||
        "—"
      );
    }
    return backup.created_by_display_name || backup.created_by || "—";
  }

  function backupKindLabel(kind) {
    if (kind === "manual") {
      return "manual";
    }
    if (kind === "safety") {
      return "safety";
    }
    if (kind === "uploaded") {
      return "uploaded";
    }
    return kind || "—";
  }

  function formatDate(value) {
    var date;

    if (!value) {
      return "—";
    }
    date = new Date(value);
    if (isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString("ru-RU");
  }

  function formatSize(bytes) {
    var value = Number(bytes);

    if (!isFinite(value) || value < 0) {
      return "—";
    }
    if (value < 1024) {
      return value + " B";
    }
    if (value < 1024 * 1024) {
      return (value / 1024).toFixed(1) + " KB";
    }
    return (value / (1024 * 1024)).toFixed(1) + " MB";
  }

  function ensureStyles() {
    var style;

    if (document.getElementById("schedgen-backup-ui-style")) {
      return;
    }

    style = document.createElement("style");
    style.id = "schedgen-backup-ui-style";
    style.textContent = [
      ".schedgen-menu-separator { border-top: 1px solid #ddd; margin: 6px 0; }",
      ".schedgen-backup-modal-overlay {",
      "  position: fixed;",
      "  inset: 0;",
      "  z-index: 12000;",
      "  display: flex;",
      "  align-items: center;",
      "  justify-content: center;",
      "  padding: 16px;",
      "  background: rgba(32, 33, 36, .48);",
      "  font-family: Arial, sans-serif;",
      "}",
      ".schedgen-backup-modal {",
      "  width: min(680px, calc(100vw - 32px));",
      "  max-height: min(760px, calc(100vh - 32px));",
      "  overflow: auto;",
      "  background: #fff;",
      "  color: #202124;",
      "  border-radius: 8px;",
      "  box-shadow: 0 12px 32px rgba(0,0,0,.24);",
      "}",
      ".schedgen-choice-modal { width: min(560px, calc(100vw - 32px)); }",
      ".schedgen-backup-modal-header {",
      "  display: flex;",
      "  align-items: center;",
      "  justify-content: space-between;",
      "  gap: 12px;",
      "  padding: 14px 16px;",
      "  border-bottom: 1px solid #e5e7eb;",
      "}",
      ".schedgen-backup-modal-header h2 {",
      "  margin: 0;",
      "  font-size: 18px;",
      "  line-height: 1.25;",
      "  color: #202124;",
      "  text-align: left;",
      "}",
      ".schedgen-backup-modal-body { padding: 16px; }",
      ".schedgen-backup-modal-footer {",
      "  display: flex;",
      "  justify-content: flex-end;",
      "  gap: 8px;",
      "  padding: 12px 16px 16px;",
      "  border-top: 1px solid #e5e7eb;",
      "}",
      ".schedgen-backup-field { display: block; margin-bottom: 12px; font-size: 13px; }",
      ".schedgen-backup-field span { display: block; margin-bottom: 6px; font-weight: 600; }",
      ".schedgen-backup-field textarea {",
      "  width: 100%;",
      "  min-height: 76px;",
      "  padding: 8px;",
      "  border: 1px solid #cbd5e1;",
      "  border-radius: 6px;",
      "  resize: vertical;",
      "  font: 13px/1.4 Arial, sans-serif;",
      "}",
      ".schedgen-backup-checkbox {",
      "  display: flex;",
      "  align-items: center;",
      "  gap: 8px;",
      "  margin: 10px 0;",
      "  font-size: 13px;",
      "}",
      ".schedgen-backup-status {",
      "  display: none;",
      "  margin: 0 0 12px;",
      "  padding: 8px 10px;",
      "  border-radius: 6px;",
      "  background: #eef4ff;",
      "  color: #174ea6;",
      "  font-size: 13px;",
      "}",
      ".schedgen-backup-status.error { background: #fce8e6; color: #b3261e; }",
      ".schedgen-backup-btn {",
      "  border: 1px solid #cbd5e1;",
      "  border-radius: 6px;",
      "  padding: 8px 12px;",
      "  background: #fff;",
      "  color: #202124;",
      "  cursor: pointer;",
      "  font-size: 13px;",
      "  line-height: 1.2;",
      "}",
      ".schedgen-backup-btn.primary { border-color: #1a73e8; background: #1a73e8; color: #fff; }",
      ".schedgen-backup-btn.danger { border-color: #b3261e; background: #b3261e; color: #fff; }",
      ".schedgen-backup-btn.icon {",
      "  width: 30px;",
      "  height: 30px;",
      "  padding: 0;",
      "  font-size: 20px;",
      "  line-height: 1;",
      "}",
      ".schedgen-backup-btn:disabled { opacity: .55; cursor: default; }",
      ".schedgen-upload-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }",
      ".schedgen-upload-row input[type='file'] { max-width: 100%; font-size: 13px; }",
      ".schedgen-backup-list {",
      "  display: grid;",
      "  gap: 8px;",
      "  max-height: 360px;",
      "  overflow: auto;",
      "  border: 1px solid #e5e7eb;",
      "  border-radius: 8px;",
      "  padding: 8px;",
      "  background: #f8fafc;",
      "}",
      ".schedgen-backup-empty { padding: 10px; color: #5f6368; font-size: 13px; }",
      ".schedgen-backup-card {",
      "  border: 1px solid #d6dbe1;",
      "  border-radius: 6px;",
      "  padding: 10px;",
      "  background: #fff;",
      "  cursor: pointer;",
      "}",
      ".schedgen-backup-card.selected { border-color: #1a73e8; box-shadow: 0 0 0 1px #1a73e8 inset; }",
      ".schedgen-backup-card.invalid { opacity: .72; cursor: default; }",
      ".schedgen-backup-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }",
      ".schedgen-backup-card-title { font-weight: 600; overflow-wrap: anywhere; }",
      ".schedgen-backup-card-meta { display: grid; gap: 3px; font-size: 12px; color: #3c4043; }",
      ".schedgen-backup-meta-row { display: grid; grid-template-columns: 120px 1fr; gap: 6px; }",
      ".schedgen-backup-meta-label { color: #5f6368; }",
      ".schedgen-backup-meta-value { overflow-wrap: anywhere; }",
      ".schedgen-backup-comment {",
      "  margin-top: 8px;",
      "  padding: 8px;",
      "  border-radius: 6px;",
      "  background: #f1f3f4;",
      "  font-size: 12px;",
      "  overflow-wrap: anywhere;",
      "}",
      ".schedgen-restore-warning {",
      "  margin-top: 12px;",
      "  padding: 9px 10px;",
      "  border: 1px solid #f6c26b;",
      "  border-radius: 6px;",
      "  background: #fff7e6;",
      "  color: #704214;",
      "  font-size: 13px;",
      "}",
      ".schedgen-choice-message { margin: 0; font-size: 14px; line-height: 1.45; }",
      "#schedgen-restore-overlay {",
      "  position: fixed;",
      "  inset: 0;",
      "  z-index: 20000;",
      "  display: flex;",
      "  align-items: center;",
      "  justify-content: center;",
      "  padding: 20px;",
      "  background: rgba(32,33,36,.58);",
      "  font-family: Arial, sans-serif;",
      "  pointer-events: auto;",
      "}",
      ".schedgen-restore-overlay-card {",
      "  width: min(560px, calc(100vw - 32px));",
      "  border-radius: 8px;",
      "  background: #fff;",
      "  color: #202124;",
      "  padding: 24px;",
      "  box-shadow: 0 14px 36px rgba(0,0,0,.26);",
      "  display: flex;",
      "  gap: 16px;",
      "  align-items: center;",
      "}",
      ".schedgen-restore-message { font-size: 16px; line-height: 1.5; }",
      ".schedgen-restore-spinner {",
      "  width: 26px;",
      "  height: 26px;",
      "  flex: 0 0 auto;",
      "  border: 3px solid #dce3ea;",
      "  border-top-color: #1a73e8;",
      "  border-radius: 50%;",
      "  animation: schedgenRestoreSpin .9s linear infinite;",
      "}",
      "@keyframes schedgenRestoreSpin { to { transform: rotate(360deg); } }",
      "body.schedgen-restore-blocked { overflow: hidden; }",
      "body.schedgen-restore-blocked #schedgen-nav,",
      "body.schedgen-restore-blocked .sticky-buttons,",
      "body.schedgen-restore-blocked .schedule-container,",
      "body.schedgen-restore-blocked .activity-block { pointer-events: none !important; }",
      "@media (max-width: 640px) {",
      "  .schedgen-backup-modal-footer { flex-direction: column-reverse; }",
      "  .schedgen-backup-btn { width: 100%; }",
      "  .schedgen-backup-meta-row { grid-template-columns: 1fr; gap: 1px; }",
      "}",
    ].join("\n");
    document.head.appendChild(style);
  }

  window.SchedGenBackupUI = {
    handleRestoreInProgress: handleRestoreInProgress,
    refreshRestoreStatus: refreshRestoreStatus,
    isRestoreBlocking: function () {
      return restoreIsBlocking;
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
