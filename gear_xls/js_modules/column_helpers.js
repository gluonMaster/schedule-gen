// Column helpers shared by add/remove/move flows across buildings.

if (typeof window.daysOrder === "undefined") {
    window.daysOrder = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
}

function getScheduleTable(rootOrTable) {
    if (!rootOrTable) {
        return null;
    }
    if (rootOrTable.classList && rootOrTable.classList.contains("schedule-grid")) {
        return rootOrTable;
    }
    return rootOrTable.querySelector ? rootOrTable.querySelector(".schedule-grid") : null;
}

function normalizeRoomForBuilding(room, building) {
    var normalizedRoom = (room || "").trim();
    var prefix = "";

    if (!normalizedRoom) {
        return "";
    }

    if (building === "Villa") {
        prefix = "V";
    } else if (building === "Kolibri") {
        prefix = "K";
    }

    if (
        prefix &&
        normalizedRoom.length > prefix.length &&
        normalizedRoom.slice(0, prefix.length).toUpperCase() === prefix
    ) {
        return normalizedRoom.slice(prefix.length).trim();
    }

    return normalizedRoom;
}

function getHeaderLocalColumnIndex(headerElement, fallbackIndex) {
    var parsed = headerElement ? parseInt(headerElement.getAttribute("data-col"), 10) : NaN;
    return isNaN(parsed) ? fallbackIndex : parsed;
}

function setDayHeaderMetadata(headerElement, day, colIndex, room) {
    if (!headerElement) {
        return;
    }

    // Headers need the same logical coordinates as tbody cells/blocks so
    // runtime operations can safely recalculate columns after DOM edits.
    headerElement.setAttribute("data-day", day || "");
    if (typeof colIndex === "number" && colIndex >= 0) {
        headerElement.setAttribute("data-col", String(colIndex));
    } else {
        headerElement.removeAttribute("data-col");
    }
    headerElement.setAttribute("data-room", (room || "").trim());
}

function refreshDayHeaderMetadata(rootOrTable, day) {
    var table = getScheduleTable(rootOrTable);
    if (!table || !day) {
        return;
    }

    // Rebuild metadata from the actual header order after add/remove column.
    Array.from(table.querySelectorAll("thead th.day-" + day)).forEach(function (header, index) {
        setDayHeaderMetadata(header, day, index, parseRoomFromDayHeaderMarkup(header, day));
    });
}

function parseRoomFromDayHeaderMarkup(headerElement, day) {
    var dayLabel;
    var headerParts;
    var headerText;

    if (!headerElement) {
        return "";
    }

    // We intentionally parse markup here instead of cached data-room so
    // refreshDayHeaderMetadata() can reconstruct metadata from legacy headers.
    dayLabel = headerElement.getAttribute("data-day") || day || "";
    headerParts = (headerElement.innerHTML || "").split(/<br\s*\/?>/i);
    if (headerParts.length > 1) {
        return headerParts[1].replace(/<[^>]*>/g, "").trim();
    }

    headerText = headerElement.textContent.trim();
    return headerText.replace(dayLabel, "").trim();
}

function extractRoomFromDayHeader(headerElement, day) {
    var dataRoom;

    if (!headerElement) {
        return "";
    }

    dataRoom = headerElement.getAttribute("data-room");
    if (dataRoom !== null) {
        return dataRoom.trim();
    }

    return parseRoomFromDayHeaderMarkup(headerElement, day);
}

function findMatchingColumnInBuilding(day, room, building) {
    var normalizedRoom = normalizeRoomForBuilding(room, building);
    var container;
    var dayHeaders;
    var bestColIndex = -1;

    if (!normalizedRoom) {
        return -1;
    }

    container = BuildingService.findScheduleContainerForBuilding(building);
    if (!container) {
        console.error(`Container not found for building ${building}`);
        return -1;
    }

    // Normalize header metadata first so lookups work for both regenerated
    // HTML and columns inserted earlier in the current editing session.
    refreshDayHeaderMetadata(container, day);
    dayHeaders = container.querySelectorAll(`.schedule-grid th.day-${day}`);

    console.log(
        `Searching column for room ${normalizedRoom} in building ${building} on ${day}`
    );
    console.log(`Found ${dayHeaders.length} headers`);

    for (var i = 0; i < dayHeaders.length; i++) {
        var headerText = dayHeaders[i].textContent.trim();
        var roomPart = extractRoomFromDayHeader(dayHeaders[i], day);
        console.log(`Header ${i}: "${headerText}"`);

        if (roomPart === normalizedRoom) {
            bestColIndex = getHeaderLocalColumnIndex(dayHeaders[i], i);
            console.log(`Exact room match found in column ${bestColIndex}`);
            break;
        }
    }

    if (bestColIndex === -1) {
        console.log(
            `No column found for room ${normalizedRoom} in day ${day} / building ${building}`
        );
    }

    return bestColIndex;
}

function updateBlockColumnForBuilding(block, room, building, day) {
    var colIndex;

    day = day || block.getAttribute("data-day");
    room = normalizeRoomForBuilding(room, building);
    colIndex = findMatchingColumnInBuilding(day, room, building);
    if (colIndex === -1) {
        console.warn(
            `Could not resolve room ${room} in building ${building}; falling back to first column`
        );
        colIndex = 0;
    }

    block.setAttribute("data-col-index", colIndex);
    return colIndex;
}

function formatDayRoomHeader(day, room, building) {
    room = normalizeRoomForBuilding(room, building);
    var container = BuildingService.findScheduleContainerForBuilding(building);
    var firstDayHeader;
    var headerText;
    var headerParts;
    var dayPart;

    if (!container) {
        console.warn(`Building container ${building} not found; using compact header format`);
        return day + room;
    }

    refreshDayHeaderMetadata(container, day);
    firstDayHeader = container.querySelector(`.schedule-grid th.day-${day}`);
    if (!firstDayHeader) {
        console.warn(`No headers found for ${day} in ${building}; using compact header format`);
        return day + room;
    }

    headerText = firstDayHeader.textContent.trim();
    console.log(`Inspecting header format: "${headerText}"`);

    headerParts = firstDayHeader.innerHTML.split("<br>");
    if (headerParts.length >= 2) {
        dayPart = headerParts[0].trim();
        if (headerText.includes(dayPart + " ")) {
            console.log(`Detected spaced format: "${day} ${room}"`);
            return day + " " + room;
        }
    }

    console.log(`Detected compact format: "${day}${room}"`);
    return day + room;
}

function roomSortKey(room) {
    var s = (room || "").trim();
    var parts;
    var floorPart;
    var roomPart;
    var floorOrder;
    var num;

    if (!s) {
        return [Infinity, 0, ""];
    }

    parts = s.split(".");
    if (parts.length === 2 && /^\d+$/.test(parts[1])) {
        floorPart = parts[0] || "";
        roomPart = parts[1] || "";

        if (/^k/i.test(floorPart) || floorPart === "\u041a" || floorPart === "\u043a") {
            floorOrder = -1;
        } else if (/^\d+$/.test(floorPart)) {
            floorOrder = parseInt(floorPart, 10);
        } else {
            floorOrder = Infinity;
        }

        num = parseInt(roomPart, 10);
        if (isNaN(num)) {
            num = 0;
        }
        return [floorOrder, num, s];
    }

    return [Infinity, 0, s];
}

function _compareRoomKeys(a, b) {
    var ka = roomSortKey(a);
    var kb = roomSortKey(b);

    if (ka[0] !== kb[0]) {
        if (ka[0] === Infinity) {
            return 1;
        }
        if (kb[0] === Infinity) {
            return -1;
        }
        return ka[0] - kb[0];
    }
    if (ka[1] !== kb[1]) {
        return ka[1] - kb[1];
    }
    return ka[2] < kb[2] ? -1 : ka[2] > kb[2] ? 1 : 0;
}

function addColumnIfMissing(day, room, building) {
    var normalizedRoom = normalizeRoomForBuilding(room, building);
    var container;
    var table;
    var dayHeaders;
    var insertionIndex;
    var newHeader;
    var thead;
    var insertPosition;
    var tbody;
    var rows;

    console.log(
        `Attempting to add column: day=${day}, room=${normalizedRoom}, building=${building}`
    );

    if (!normalizedRoom) {
        console.warn("Attempt to add a column with an empty room name");
        return -1;
    }

    container = BuildingService.findScheduleContainerForBuilding(building);
    if (!container) {
        console.error(`Container not found for building ${building}`);
        return -1;
    }

    table = container.querySelector(".schedule-grid");
    if (!table) {
        console.error(`Schedule table not found in building ${building}`);
        return -1;
    }

    refreshDayHeaderMetadata(table, day);
    dayHeaders = Array.from(table.querySelectorAll(`thead th.day-${day}`));
    console.log(`Found ${dayHeaders.length} headers for day ${day}`);

    for (var i = 0; i < dayHeaders.length; i++) {
        var headerText = dayHeaders[i].textContent.trim();
        var roomPart = extractRoomFromDayHeader(dayHeaders[i], day);
        console.log(`Checking existing header ${i}: "${headerText}"`);
        if (roomPart === normalizedRoom) {
            console.log(`Column for room ${normalizedRoom} already exists at index ${i}`);
            return getHeaderLocalColumnIndex(dayHeaders[i], i);
        }
    }

    console.log(`Creating new column for room ${normalizedRoom}`);

    insertionIndex = dayHeaders.length;
    for (var j = 0; j < dayHeaders.length; j++) {
        var existingRoom = extractRoomFromDayHeader(dayHeaders[j], day);
        if (_compareRoomKeys(normalizedRoom, existingRoom) < 0) {
            insertionIndex = j;
            break;
        }
    }

    newHeader = document.createElement("th");
    newHeader.className = "day-" + day;
    newHeader.innerHTML = day + "<br>" + normalizedRoom;
    setDayHeaderMetadata(newHeader, day, insertionIndex, normalizedRoom);

    thead = table.querySelector("thead tr");
    insertPosition = findInsertPositionInHeader(thead, day, insertionIndex);

    console.log(
        `Header insert position ${insertPosition} (of ${thead.children.length} total columns)`
    );

    if (insertPosition < thead.children.length) {
        thead.insertBefore(newHeader, thead.children[insertPosition]);
        console.log(`Inserted header before absolute column ${insertPosition}`);
    } else {
        thead.appendChild(newHeader);
        console.log("Appended header to the end of thead");
    }

    tbody = table.querySelector("tbody");
    rows = tbody.querySelectorAll("tr");

    console.log(`Adding tbody cells to ${rows.length} rows at absolute column ${insertPosition}`);

    for (var r = 0; r < rows.length; r++) {
        var newCell = document.createElement("td");
        newCell.className = "day-" + day;
        newCell.setAttribute("data-row", r);
        newCell.setAttribute("data-col", insertionIndex);

        if (insertPosition < rows[r].children.length) {
            rows[r].insertBefore(newCell, rows[r].children[insertPosition]);
        } else {
            rows[r].appendChild(newCell);
        }
    }

    // Every row keeps local day-relative data-col values; absolute table
    // indices are not stable once columns are inserted between days.
    for (var r2 = 0; r2 < rows.length; r2++) {
        var dayCells = Array.from(rows[r2].querySelectorAll("td.day-" + day));
        dayCells.forEach(function (td, idx) {
            td.setAttribute("data-col", idx);
        });
    }

    // Headers are renumbered after insertion so subsequent lookups can trust
    // data-col instead of recomputing from DOM position every time.
    refreshDayHeaderMetadata(table, day);

    console.log(`Updating data-col-index for existing blocks on ${day} in ${building}`);
    updateExistingBlocksColIndex(building, day, insertionIndex);

    console.log(`New column created for room ${normalizedRoom} at local index ${insertionIndex}`);
    return insertionIndex;
}

function findInsertPositionInHeader(headerRow, day, insertionIndex) {
    var position = 1;
    var daysOrder = window.daysOrder || ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

    for (var d = 0; d < daysOrder.length; d++) {
        if (daysOrder[d] === day) {
            position += insertionIndex;
            break;
        }

        position += headerRow.querySelectorAll(".day-" + daysOrder[d]).length;
    }

    return position;
}

function updateExistingBlocksColIndex(building, day, insertionIndex) {
    var container = BuildingService.findScheduleContainerForBuilding(building);
    var blocks;

    if (!container) {
        return;
    }

    blocks = container.querySelectorAll(
        `.activity-block[data-day="${day}"][data-building="${building}"]`
    );

    for (var i = 0; i < blocks.length; i++) {
        var block = blocks[i];
        var currentColIndex = parseInt(block.getAttribute("data-col-index"), 10);

        if (currentColIndex >= insertionIndex) {
            var newColIndex = currentColIndex + 1;
            block.setAttribute("data-col-index", newColIndex);
            console.log(
                `Updated block data-col-index from ${currentColIndex} to ${newColIndex}`
            );
        }
    }
}

window.extractRoomFromDayHeader = extractRoomFromDayHeader;
window.findMatchingColumnInBuilding = findMatchingColumnInBuilding;
window.updateBlockColumnForBuilding = updateBlockColumnForBuilding;
window.addColumnIfMissing = addColumnIfMissing;
window.formatDayRoomHeader = formatDayRoomHeader;
window.roomSortKey = roomSortKey;
window.getHeaderLocalColumnIndex = getHeaderLocalColumnIndex;
window.setDayHeaderMetadata = setDayHeaderMetadata;
window.refreshDayHeaderMetadata = refreshDayHeaderMetadata;
window.normalizeRoomForBuilding = normalizeRoomForBuilding;
