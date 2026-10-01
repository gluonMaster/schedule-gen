(function () {
  "use strict";

  var lockVersion = null;
  var heartbeatTimer = null;
  var pollingTimer = null;
  var currentLockHolder = null;
  var sessionExpiredHandled = false;

  function authUi() {
    return window.SchedGenAuthUI;
  }

  function baseSyncUi() {
    return window.SchedGenBaseSyncUI || null;
  }

  function currentRole() {
    return authUi().currentRole();
  }

  function currentUser() {
    return authUi().currentUser();
  }

  function isEditableRole() {
    return authUi().isEditableRole(currentRole());
  }

  function init() {
    if (!authUi()) {
      return;
    }

    ensureLockBanner();
    syncLockBannerMetrics();
    refreshLockStatus();
    stopPolling();
    pollingTimer = window.setInterval(pollStatus, 30000);

    window.addEventListener("beforeunload", function () {
      if (lockVersion === null || !navigator.sendBeacon) {
        return;
      }

      navigator.sendBeacon(
        "/api/lock/release",
        JSON.stringify({ version: lockVersion })
      );
    });
  }

  function ensureLockBanner() {
    var banner;
    var nav;
    var firstContainer;

    addStyleOnce(
      "schedgen-lock-banner-style",
      [
        "#schedgen-lock-banner {",
        "  display: none !important;",
        "  height: 0 !important;",
        "  margin: 0 !important;",
        "  padding: 0 !important;",
        "}",
      ].join("\n")
    );

    if (document.getElementById("schedgen-lock-banner")) {
      return;
    }

    banner = document.createElement("div");
    banner.id = "schedgen-lock-banner";
    nav = document.getElementById("schedgen-nav");
    firstContainer = document.querySelector(".schedule-container");

    if (nav && nav.parentNode) {
      if (firstContainer && firstContainer.parentNode === nav.parentNode) {
        nav.parentNode.insertBefore(banner, firstContainer);
      } else {
        nav.insertAdjacentElement("afterend", banner);
      }
      return;
    }

    if (firstContainer && firstContainer.parentNode) {
      firstContainer.parentNode.insertBefore(banner, firstContainer);
      return;
    }

    document.body.appendChild(banner);
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

  function renderNavLockState(options) {
    if (!authUi() || typeof authUi().setNavEditorState !== "function") {
      return;
    }

    authUi().setNavEditorState(options || null);
  }

  function isRestorePayload(data) {
    return !!(
      data &&
      (data.code === "RESTORE_IN_PROGRESS" ||
        data.restore_in_progress ||
        data.active ||
        data.recovery_required)
    );
  }

  function clearLocalLockStateForRestore() {
    closeOpenDialogs();
    stopHeartbeat();
    lockVersion = null;
    currentLockHolder = null;
    if (authUi() && typeof authUi().setEditMode === "function") {
      authUi().setEditMode(false);
    }
    renderNavLockState({
      mode: "view",
      message: "Восстановление...",
      buttons: [],
    });
    syncLockBannerMetrics();
  }

  function handleRestoreInProgress(data) {
    clearLocalLockStateForRestore();
    if (
      window.SchedGenBackupUI &&
      typeof window.SchedGenBackupUI.handleRestoreInProgress === "function"
    ) {
      window.SchedGenBackupUI.handleRestoreInProgress(data || {});
    }
  }

  function refreshLockStatus() {
    apiRequest("/api/lock/status").then(function (result) {
      if (result) {
        updateLockBanner(result.data);
      }
    });
  }

  function pollStatus() {
    apiRequest("/api/status").then(function (result) {
      if (result && result.data && result.data.lock) {
        if (isRestorePayload(result.data.restore)) {
          handleRestoreInProgress(result.data.restore);
          return;
        }
        updateLockBanner(result.data.lock);
        if (
          baseSyncUi() &&
          typeof baseSyncUi().handleBaseRevision === "function"
        ) {
          baseSyncUi().handleBaseRevision(result.data.base_revision);
        }
        if (
          window.SchedGenIndividualUI &&
          typeof window.SchedGenIndividualUI.handleIndividualRevision === "function"
        ) {
          window.SchedGenIndividualUI.handleIndividualRevision(
            result.data.individual_revision
          );
        }
      }
    });
  }

  function updateLockBanner(lockState) {
    var holder;
    var role;
    var navState;

    ensureLockBanner();
    if (!lockState) {
      return;
    }

    holder = lockState.holder || null;
    role = currentRole();
    currentLockHolder = holder;

    if (
      holder === currentUser() &&
      typeof lockState.version !== "undefined" &&
      lockState.version !== null
    ) {
      lockVersion = lockState.version;
      authUi().setEditMode(true);
      if (heartbeatTimer === null) {
        startHeartbeat();
      }
    } else if (holder !== currentUser()) {
      stopHeartbeat();
      lockVersion = null;
      authUi().setEditMode(false);
    }

    navState = { mode: "view", message: "", buttons: [] };

    if (holder === null) {
      navState.mode = "view";
      navState.message = "Режим просмотра";
      if (isEditableRole()) {
        navState.buttons.push({
          label: "Начать редактирование",
          onClick: acquireLock,
        });
      }
      renderNavLockState(navState);
      syncLockBannerMetrics();
      return;
    }

    if (holder === currentUser()) {
      navState.mode = "self";
      navState.message = "Режим редактирования: вы";
      navState.buttons.push({
        label: "Завершить редактирование",
        onClick: releaseLock,
      });
      renderNavLockState(navState);
      syncLockBannerMetrics();
      return;
    }

    navState.mode = "other";
    navState.message =
      "Редактирует: " +
      holder +
      (lockState.acquired_at
        ? " (" + formatLockTime(lockState.acquired_at) + ")"
        : "");

    if (role === "admin") {
      navState.buttons.push({
        label: "Снять блокировку",
        onClick: forceReleaseLock,
      });
    }

    renderNavLockState(navState);
    syncLockBannerMetrics();
  }

  function acquireLock() {
    if (baseSyncUi() && typeof baseSyncUi().canStartEditing === "function") {
      if (!baseSyncUi().canStartEditing()) {
        return;
      }
    }

    apiRequest("/api/lock/acquire", "POST", {}).then(function (result) {
      var now;

      if (!result) {
        return;
      }

      if (!result.data.ok) {
        window.alert(
          "Расписание сейчас редактирует другой пользователь."
        );
        refreshLockStatus();
        return;
      }

      now = new Date().toISOString();
      lockVersion = result.data.version;
      authUi().setEditMode(true);
      startHeartbeat();
      updateLockBanner({
        holder: currentUser(),
        version: result.data.version,
        acquired_at: now,
        last_heartbeat: now,
      });
    });
  }

  function releaseLock() {
    if (lockVersion === null) {
      closeOpenDialogs();
      authUi().setEditMode(false);
      refreshLockStatus();
      return;
    }

    apiRequest("/api/lock/release", "POST", { version: lockVersion }).then(
      function () {
        closeOpenDialogs();
        stopHeartbeat();
        lockVersion = null;
        authUi().setEditMode(false);
        refreshLockStatus();
      }
    );
  }

  function forceReleaseLock() {
    if (
      !currentLockHolder ||
      !window.confirm(
        "Принудительно снять блокировку у " + currentLockHolder + "?"
      )
    ) {
      return;
    }

    apiRequest("/api/lock", "DELETE").then(function (result) {
      if (result) {
        refreshLockStatus();
      }
    });
  }

  function sendHeartbeat() {
    if (lockVersion === null) {
      return;
    }

    apiRequest("/api/lock/heartbeat", "POST", { version: lockVersion }).then(
      function (result) {
        if (!result || result.data.ok) {
          return;
        }

        if (result.data.reason === "force_released") {
          handleForceRelease();
          return;
        }

        if (result.data.reason === "lock_expired") {
          window.alert(
            "Ваша сессия редактирования истекла из-за долгого отсутствия активности. Сохранённые изменения не потеряны."
          );
          closeOpenDialogs();
          stopHeartbeat();
          lockVersion = null;
          authUi().setEditMode(false);
          refreshLockStatus();
          return;
        }

        if (result.data.reason === "not_holder") {
          closeOpenDialogs();
          stopHeartbeat();
          lockVersion = null;
          authUi().setEditMode(false);
          refreshLockStatus();
        }
      }
    );
  }

  function handleForceRelease() {
    window.alert(
      "Администратор завершил вашу сессию редактирования. Незавершённые изменения в открытом диалоге будут потеряны."
    );
    closeOpenDialogs();
    stopHeartbeat();
    lockVersion = null;
    authUi().setEditMode(false);
    refreshLockStatus();
  }

  function closeOpenDialogs() {
    var readonlyOverlay = document.getElementById("readonly-block-overlay");

    if (typeof window.closeEditDialog === "function") {
      window.closeEditDialog();
    } else if (typeof window.closeDialog === "function") {
      window.closeDialog();
    }

    document.querySelectorAll(".dialog-overlay").forEach(function (overlay) {
      var button = overlay.querySelector(
        "#cancel-edit, #cancel-create, button[type='button']"
      );

      if (button) {
        button.click();
      } else if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
    });

    if (readonlyOverlay) {
      readonlyOverlay.remove();
    }

    document.body.style.overflow = "";
    window.editDialogOpen = false;
  }

  function handleSessionExpired() {
    if (sessionExpiredHandled) {
      return;
    }

    sessionExpiredHandled = true;
    stopHeartbeat();
    stopPolling();
    authUi().setEditMode(false);
    closeOpenDialogs();
    window.alert("Сессия истекла. Войдите снова.");
    window.location.href = "/login";
  }

  function apiRequest(url, method, payload) {
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
          handleSessionExpired();
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

          if (data && data.code === "RESTORE_IN_PROGRESS") {
            handleRestoreInProgress(data);
            return null;
          }

          return { response: response, data: data };
        });
      })
      .catch(function (error) {
        console.error("Lock API request failed:", error);
        return null;
      });
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = window.setInterval(sendHeartbeat, 60000);
  }

  function stopHeartbeat() {
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  function stopPolling() {
    if (pollingTimer !== null) {
      window.clearInterval(pollingTimer);
      pollingTimer = null;
    }
  }

  function syncLockBannerMetrics() {
    var banner = document.getElementById("schedgen-lock-banner");
    var height = banner ? banner.offsetHeight : 0;

    document.documentElement.style.setProperty(
      "--schedgen-lock-banner-height",
      height + "px"
    );
  }

  function formatLockTime(value) {
    var date = new Date(value);

    if (isNaN(date.getTime())) {
      return "с " + value;
    }

    return "с " + date.toLocaleString("ru-RU");
  }

  window.handleSessionExpired = handleSessionExpired;
  window.SchedGenLockUI = {
    clearLocalLockStateForRestore: clearLocalLockStateForRestore,
    closeOpenDialogs: closeOpenDialogs,
    handleSessionExpired: handleSessionExpired,
    refreshLockStatus: refreshLockStatus,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
