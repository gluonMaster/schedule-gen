(function () {
  "use strict";

  var _stylesInjected = false;
  var _allowedConvertRoles = ["admin", "editor", "organizer"];

  function injectTrialStyles() {
    var existing = document.getElementById("schedgen-trial-styles");
    if (existing) {
      _stylesInjected = true;
      return;
    }
    if (_stylesInjected) return;
    _stylesInjected = true;

    var style = document.createElement("style");
    style.id = "schedgen-trial-styles";
    style.textContent = [
      ".activity-block.lesson-type-trial,",
      '.activity-block[data-lesson-type="trial"] {',
      "  border: 2px solid #2e7d32 !important;",
      "  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.22), 0 0 0 1px rgba(46,125,50,0.22);",
      "  padding-top: 18px !important;",
      "  overflow: hidden;",
      "}",
      ".activity-block.lesson-type-trial::before,",
      '.activity-block[data-lesson-type="trial"]::before {',
      "  content: 'TRIAL';",
      "  position: absolute;",
      "  top: 4px;",
      "  right: 4px;",
      "  padding: 2px 6px;",
      "  border-radius: 999px;",
      "  background: #1b5e20;",
      "  color: #fff;",
      "  font-size: 10px;",
      "  font-weight: 700;",
      "  letter-spacing: 0.08em;",
      "  z-index: 2;",
      "  pointer-events: none;",
      "}",
      ".activity-block.lesson-type-trial strong,",
      '.activity-block[data-lesson-type="trial"] strong { display: block; width: 100%; margin-bottom: 2px; }',
      ".activity-block.trial-expired,",
      '.activity-block[data-lesson-type="trial"].trial-expired {',
      "  /* Keep grid positioning intact for expired trial blocks. */",
      "  position: absolute;",
      "}",
      ".trial-expired::after {",
      "  content: '';",
      "  position: absolute;",
      "  inset: 0;",
      "  background: repeating-linear-gradient(",
      "    135deg,",
      "    transparent, transparent 6px,",
      "    rgba(120,120,120,0.25) 6px,",
      "    rgba(120,120,120,0.25) 8px",
      "  );",
      "  pointer-events: none;",
      "  border-radius: inherit;",
      "  z-index: 1;",
      "}",
      ".trial-expired strong { text-decoration: line-through; opacity: 0.7; }",
      ".trial-dates-section { margin-top: 8px; }",
      ".trial-dates-section label { font-weight: bold; font-size: 0.9em; display: block; margin-bottom: 4px; }",
      ".trial-date-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; min-height: 24px; }",
      ".trial-date-chip { display: inline-flex; align-items: center; gap: 4px; background: #c8e6c9; border-radius: 12px; padding: 2px 8px; font-size: 0.85em; }",
      ".trial-date-chip .remove-date { background: none; border: none; cursor: pointer; font-size: 1em; line-height: 1; padding: 0; color: #555; }",
      ".trial-date-chip .remove-date:hover { color: #c00; }",
      ".trial-date-add-row { display: flex; gap: 6px; align-items: center; }",
      ".trial-date-add-row input[type=date] { flex: 1; }",
      ".convert-to-regular-btn { margin-top: 8px; width: 100%; background: #e8f5e9; border: 1px solid #81c784; color: #2e7d32; border-radius: 4px; padding: 6px 12px; cursor: pointer; font-size: 0.9em; }",
      ".convert-to-regular-btn:hover { background: #c8e6c9; }",
    ].join("\n");
    document.head.appendChild(style);
  }

  function isTrialExpired(trialDates) {
    if (!Array.isArray(trialDates) || trialDates.length === 0) return false;
    var now = new Date();
    var today = now.getFullYear() + "-"
      + String(now.getMonth() + 1).padStart(2, "0") + "-"
      + String(now.getDate()).padStart(2, "0");
    return trialDates.every(function (dateStr) {
      return typeof dateStr === "string" && dateStr < today;
    });
  }

  function applyTrialExpiredStyle(element, expired) {
    if (!element) return;
    element.classList.toggle("trial-expired", !!expired);
  }

  function preserveTrialBackground(element) {
    var inlineColor = element ? element.style.backgroundColor : "";

    if (!element || !inlineColor) return;
    element.style.setProperty("background", inlineColor, "important");
    element.style.setProperty("background-color", inlineColor, "important");
  }

  function readTrialDates(element) {
    var raw = element ? element.getAttribute("data-trial-dates") : "";
    if (!raw) return [];
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      return [];
    }
  }

  function refreshTrialBlockAppearance(element) {
    if (!element) return;
    if (
      (element.getAttribute("data-lesson-type") || "") !== "trial" &&
      !element.classList.contains("lesson-type-trial")
    ) {
      return;
    }
    preserveTrialBackground(element);
    applyTrialExpiredStyle(element, isTrialExpired(readTrialDates(element)));
  }

  function refreshTrialBlocks(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope
      .querySelectorAll('.activity-block[data-lesson-type="trial"], .activity-block.lesson-type-trial')
      .forEach(refreshTrialBlockAppearance);
  }

  function formatDateLabel(dateStr) {
    var parts = String(dateStr || "").split("-");
    return parts.length === 3 ? parts[2] + "." + parts[1] + "." + parts[0] : String(dateStr || "");
  }

  function addChip(chips, dateStr) {
    if (!dateStr || chips.querySelector('.trial-date-chip[data-date="' + dateStr + '"]')) return;

    var chip = document.createElement("span");
    var removeBtn = document.createElement("button");
    var label = formatDateLabel(dateStr);

    chip.className = "trial-date-chip";
    chip.setAttribute("data-date", dateStr);
    chip.appendChild(document.createTextNode(label + " "));

    removeBtn.type = "button";
    removeBtn.className = "remove-date";
    removeBtn.setAttribute("aria-label", "Удалить дату " + label);
    removeBtn.textContent = "✕";
    removeBtn.addEventListener("click", function () {
      chip.remove();
    });

    chip.appendChild(removeBtn);
    chips.appendChild(chip);
  }

  function buildTrialDatesSection(existingDates) {
    var dates = Array.isArray(existingDates) ? existingDates : [];
    var section = document.createElement("div");
    var label = document.createElement("label");
    var chips = document.createElement("div");
    var addRow = document.createElement("div");
    var dateInput = document.createElement("input");
    var addBtn = document.createElement("button");

    section.className = "trial-dates-section";
    label.textContent = "Даты занятия:";
    chips.className = "trial-date-chips";
    addRow.className = "trial-date-add-row";
    dateInput.type = "date";
    addBtn.type = "button";
    addBtn.textContent = "+ Добавить";

    function handleAdd() {
      if (!dateInput.value) return;
      addChip(chips, dateInput.value);
      dateInput.value = "";
    }

    addBtn.addEventListener("click", handleAdd);
    dateInput.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      event.preventDefault();
      handleAdd();
    });

    for (var i = 0; i < dates.length; i += 1) {
      addChip(chips, dates[i]);
    }

    addRow.appendChild(dateInput);
    addRow.appendChild(addBtn);
    section.appendChild(label);
    section.appendChild(chips);
    section.appendChild(addRow);
    return section;
  }

  function collectTrialDates(container) {
    if (!container) return [];
    var nodes = container.querySelectorAll(".trial-date-chip[data-date]");
    var dates = [];
    for (var i = 0; i < nodes.length; i += 1) {
      var dateStr = nodes[i].getAttribute("data-date");
      if (dateStr) dates.push(dateStr);
    }
    return dates;
  }

  function resetConvertButton(button) {
    button.disabled = false;
    button.textContent = "Сделать регулярным занятием";
  }

  function responseRequiresIndividualRefresh(data) {
    return !!(
      data &&
      (data.force_individual_refresh ||
        Number(data.individual_cleanup_removed || 0) > 0)
    );
  }

  function refreshIndividualLayerForCleanup(data) {
    if (
      responseRequiresIndividualRefresh(data) &&
      typeof window.refreshIndividualLayer === "function"
    ) {
      window.refreshIndividualLayer();
      return true;
    }
    return false;
  }

  function renderConvertButton(blockElement, role, container, onSuccess) {
    if (!blockElement || !container) return;
    if (_allowedConvertRoles.indexOf(role) === -1) return;
    if (blockElement.getAttribute("data-lesson-type") !== "trial") return;
    if (blockElement.getAttribute("data-day") === "So") return;

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "convert-to-regular-btn";
    btn.textContent = "Сделать регулярным занятием";

    btn.addEventListener("click", function () {
      var blockId = blockElement.getAttribute("data-block-id");
      if (!blockId) return;
      if (!window.confirm("Занятие станет постоянным. Trial-статус будет снят. Продолжить?")) return;

      btn.disabled = true;
      btn.textContent = "Сохранение...";

      fetch("/api/blocks/" + blockId + "/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          if (data && data.ok) {
            if (responseRequiresIndividualRefresh(data)) {
              if (typeof onSuccess === "function") {
                onSuccess(data.block, data);
              } else {
                refreshIndividualLayerForCleanup(data);
              }
              resetConvertButton(btn);
              return;
            }
            if (typeof onSuccess === "function") onSuccess(data.block, data);
            return;
          }
          alert("Ошибка: " + (data && data.error ? data.error : "неизвестная ошибка"));
          refreshIndividualLayerForCleanup(data);
          resetConvertButton(btn);
        })
        .catch(function (error) {
          alert("Сетевая ошибка: " + error.message);
          resetConvertButton(btn);
        });
    });

    container.appendChild(btn);
  }

  window.TrialUI = {
    injectTrialStyles: injectTrialStyles,
    isTrialExpired: isTrialExpired,
    applyTrialExpiredStyle: applyTrialExpiredStyle,
    refreshTrialBlockAppearance: refreshTrialBlockAppearance,
    refreshTrialBlocks: refreshTrialBlocks,
    buildTrialDatesSection: buildTrialDatesSection,
    collectTrialDates: collectTrialDates,
    renderConvertButton: renderConvertButton,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      injectTrialStyles();
      refreshTrialBlocks(document);
    });
  } else {
    injectTrialStyles();
    refreshTrialBlocks(document);
  }
})();
