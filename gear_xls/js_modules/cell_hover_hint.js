(function () {
    "use strict";

    var HINT_ID = "schedgen-cell-hover-hint";
    var STYLE_ID = "schedgen-cell-hover-hint-style";
    var HIDDEN_ROW_CLASS = "schedgen-compact-hidden-row";
    var initialized = false;
    var activeCell = null;

    var DAY_LABELS = {
        Mo: "Понедельник",
        Di: "Вторник",
        Mi: "Среда",
        Do: "Четверг",
        Fr: "Пятница",
        Sa: "Суббота",
        So: "Воскресенье"
    };

    function isEditModeActive() {
        var authUi = window.SchedGenAuthUI;

        return !!(
            authUi &&
            typeof authUi.isEditMode === "function" &&
            authUi.isEditMode()
        );
    }

    function isInteractionBusy() {
        return !!(
            window.editDialogOpen ||
            window.draggedBlock ||
            window.isResizing ||
            (document.body && document.body.classList.contains("delete-mode"))
        );
    }

    function injectStyle() {
        var style;

        if (document.getElementById(STYLE_ID)) {
            return;
        }

        style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = [
            "#" + HINT_ID + " {",
            "  position: fixed;",
            "  left: 0;",
            "  top: 0;",
            "  z-index: 12050;",
            "  max-width: 220px;",
            "  padding: 7px 9px;",
            "  border-radius: 6px;",
            "  background: rgba(24, 27, 38, 0.94);",
            "  color: #fff;",
            "  font: 12px/1.35 Arial, sans-serif;",
            "  white-space: pre-line;",
            "  box-shadow: 0 5px 16px rgba(0, 0, 0, 0.24);",
            "  pointer-events: none;",
            "  opacity: 0;",
            "  transform: translate3d(-9999px, -9999px, 0);",
            "  transition: opacity 80ms ease;",
            "}",
            "#" + HINT_ID + ".is-visible {",
            "  opacity: 1;",
            "}"
        ].join("\n");

        document.head.appendChild(style);
    }

    function getHintElement() {
        var hint = document.getElementById(HINT_ID);

        if (!hint) {
            hint = document.createElement("div");
            hint.id = HINT_ID;
            hint.setAttribute("role", "status");
            hint.setAttribute("aria-live", "polite");
            hint.setAttribute("aria-hidden", "true");
            document.body.appendChild(hint);
        }

        return hint;
    }

    function hideHint() {
        var hint = document.getElementById(HINT_ID);

        activeCell = null;
        if (!hint) {
            return;
        }
        hint.classList.remove("is-visible");
        hint.setAttribute("aria-hidden", "true");
        hint.style.transform = "translate3d(-9999px, -9999px, 0)";
    }

    function getDayFromCell(cell) {
        var classes = Array.prototype.slice.call(cell.classList || []);
        var dayClass = classes.find(function (className) {
            return className.indexOf("day-") === 0;
        });

        return dayClass ? dayClass.slice(4) : "";
    }

    function findHeader(table, day, colIndex) {
        var headers;
        var matchedHeader = null;

        if (!table || !day) {
            return null;
        }

        headers = Array.prototype.slice.call(
            table.querySelectorAll("thead th.day-" + day)
        );

        headers.forEach(function (header, index) {
            var headerCol = parseInt(header.getAttribute("data-col"), 10);

            if (index === colIndex && !matchedHeader) {
                matchedHeader = header;
            }
            if (headerCol === colIndex) {
                matchedHeader = header;
            }
        });

        return matchedHeader;
    }

    function textFromHeader(header) {
        return header ? (header.textContent || "").replace(/\s+/g, " ").trim() : "";
    }

    function roomFromHeader(header, day) {
        var dataRoom = header ? header.getAttribute("data-room") : "";
        var headerText;

        if (dataRoom) {
            return dataRoom.trim();
        }

        headerText = textFromHeader(header);
        if (!headerText) {
            return "";
        }

        if (day && headerText.indexOf(day) === 0) {
            return headerText.slice(day.length).trim();
        }

        return headerText;
    }

    function formatMinutes(totalMinutes) {
        var hours = Math.floor(totalMinutes / 60);
        var minutes = totalMinutes % 60;

        return (
            (hours < 10 ? "0" : "") +
            hours +
            ":" +
            (minutes < 10 ? "0" : "") +
            minutes
        );
    }

    function getCellTime(rowIndex) {
        var start = typeof gridStart === "number" ? gridStart : 9 * 60;
        var interval = typeof timeInterval === "number" ? timeInterval : 5;

        return formatMinutes(start + rowIndex * interval);
    }

    function buildHintText(cell) {
        var table = cell.closest(".schedule-grid");
        var container = cell.closest(".schedule-container");
        var day = getDayFromCell(cell);
        var colIndex = parseInt(cell.getAttribute("data-col"), 10);
        var rowIndex = parseInt(cell.getAttribute("data-row"), 10);
        var header = findHeader(table, day, colIndex);
        var room = roomFromHeader(header, day);
        var building = container ? container.getAttribute("data-building") || "" : "";
        var dayLabel = DAY_LABELS[day] ? DAY_LABELS[day] + " (" + day + ")" : day;

        if (!day || !isFinite(colIndex) || !isFinite(rowIndex)) {
            return "";
        }

        return [
            dayLabel,
            [building, room || "Кабинет не указан"].filter(Boolean).join(" · "),
            getCellTime(rowIndex)
        ].join("\n");
    }

    function getTargetCell(event) {
        var target = event && event.target;
        var cell;

        if (!target || typeof target.closest !== "function") {
            return null;
        }
        if (!isEditModeActive() || isInteractionBusy()) {
            return null;
        }
        if (target.closest(".activity-block") || target.closest(".edit-dialog")) {
            return null;
        }

        cell = target.closest(".schedule-grid td:not(.time-cell)");
        if (!cell || !cell.closest(".schedule-container")) {
            return null;
        }
        if (cell.closest("." + HIDDEN_ROW_CLASS)) {
            return null;
        }

        return cell;
    }

    function positionHint(hint, event) {
        var gap = 14;
        var margin = 8;
        var x = event.clientX + gap;
        var y = event.clientY + gap;
        var rect = hint.getBoundingClientRect();

        if (x + rect.width + margin > window.innerWidth) {
            x = event.clientX - rect.width - gap;
        }
        if (y + rect.height + margin > window.innerHeight) {
            y = event.clientY - rect.height - gap;
        }

        x = Math.max(margin, x);
        y = Math.max(margin, y);
        hint.style.transform =
            "translate3d(" + Math.round(x) + "px, " + Math.round(y) + "px, 0)";
    }

    function handlePointerMove(event) {
        var cell = getTargetCell(event);
        var hint;
        var text;

        if (!cell) {
            hideHint();
            return;
        }

        hint = getHintElement();
        if (cell !== activeCell) {
            text = buildHintText(cell);
            if (!text) {
                hideHint();
                return;
            }
            activeCell = cell;
            hint.textContent = text;
        }

        hint.classList.add("is-visible");
        hint.setAttribute("aria-hidden", "false");
        positionHint(hint, event);
    }

    function initCellHoverHint() {
        if (initialized) {
            return;
        }

        initialized = true;
        injectStyle();

        document.addEventListener("pointermove", handlePointerMove, true);
        document.addEventListener("pointerdown", hideHint, true);
        document.addEventListener("mouseleave", hideHint, true);
        document.addEventListener("scroll", hideHint, true);
    }

    window.initCellHoverHint = initCellHoverHint;
    window.ScheduleCellHoverHint = {
        hide: hideHint
    };
})();
