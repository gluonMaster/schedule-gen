// Module: block_content_sync.js
// Single-responsibility: synchronise block innerHTML from positional data attributes.
// Depends on: column_helpers.js (extractRoomFromDayHeader), global vars gridStart, timeInterval.

function syncBlockContent(block) {
    var day      = block.getAttribute('data-day');
    var colIndex = parseInt(block.getAttribute('data-col-index'), 10);
    var startRow = parseInt(block.getAttribute('data-start-row'), 10);
    var rowSpan  = parseInt(block.getAttribute('data-row-span'), 10);

    var parts = block.innerHTML.split(/<br\s*\/?>/i);
    while (parts.length < 5) {
        parts.push('');
    }
    var subject  = parts[0] !== undefined ? parts[0] : '';
    var teacher  = parts[1] !== undefined ? parts[1] : '';
    var students = parts[2] !== undefined ? parts[2] : '';
    var oldRoom  = parts[3] !== undefined ? parts[3] : '';
    var oldTime  = parts[4] !== undefined ? parts[4] : '';

    var newRoom = oldRoom; // default: keep existing
    var container = block.closest('.schedule-container');
    if (container) {
        var table = container.querySelector('.schedule-grid');
        if (table) {
            var dayHeaders = Array.from(table.querySelectorAll('th.day-' + day));
            if (!isNaN(colIndex) && colIndex >= 0 && colIndex < dayHeaders.length) {
                if (typeof extractRoomFromDayHeader === 'function') {
                    newRoom = extractRoomFromDayHeader(dayHeaders[colIndex], day);
                } else {
                    console.warn('syncBlockContent: extractRoomFromDayHeader is not available. Keeping old room text.');
                }
            } else {
                console.warn(
                    'syncBlockContent: colIndex ' + colIndex +
                    ' out of range (' + dayHeaders.length +
                    ' visible headers for day ' + day +
                    '). Keeping old room text.'
                );
            }
        } else {
            console.warn('syncBlockContent: schedule grid table not found. Keeping old room text.');
        }
    } else {
        console.warn('syncBlockContent: schedule container not found. Keeping old room text.');
    }

    var newTimeStr = oldTime; // default: keep existing
    if (!isNaN(startRow) && !isNaN(rowSpan) && rowSpan > 0) {
        var gStart    = (typeof gridStart !== 'undefined') ? gridStart : 9 * 60;
        var tInterval = (typeof timeInterval !== 'undefined') ? timeInterval : 5;
        var startMins = gStart + startRow * tInterval;
        var endMins   = gStart + (startRow + rowSpan) * tInterval;
        var startH = Math.floor(startMins / 60);
        var startM = startMins % 60;
        var endH   = Math.floor(endMins / 60);
        var endM   = endMins % 60;
        var pad = function(n) { return String(n).padStart(2, '0'); };
        newTimeStr = pad(startH) + ':' + pad(startM) + '-' + pad(endH) + ':' + pad(endM);
    } else {
        console.warn(
            'syncBlockContent: invalid startRow=' + startRow +
            ' or rowSpan=' + rowSpan +
            '. Keeping old time text.'
        );
    }

    var newHTML = subject + '<br>' + teacher + '<br>' + students + '<br>' + newRoom + '<br>' + newTimeStr;

    // Restore trial dates line for trial blocks
    if (block.getAttribute('data-lesson-type') === 'trial') {
        var rawDates = block.getAttribute('data-trial-dates');
        if (rawDates) {
            try {
                var trialDates = JSON.parse(rawDates);
                if (Array.isArray(trialDates) && trialDates.length > 0) {
                    var displayDates = trialDates.map(function(d) {
                        var parts = d.split('-');
                        return parts.length === 3 ? parts[2] + '.' + parts[1] + '.' + parts[0] : d;
                    }).join(', ');
                    newHTML += '<br>\uD83D\uDCC5 ' + displayDates;
                }
            } catch (e) { /* ignore parse errors */ }
        }
    }

    block.innerHTML = newHTML;
    if (container && container.getAttribute('data-building')) {
        block.setAttribute('data-building', container.getAttribute('data-building'));
    }
    if (newRoom) {
        block.setAttribute('data-room', newRoom);
    }
    if (newTimeStr && newTimeStr.indexOf('-') !== -1) {
        block.setAttribute('data-start-time', newTimeStr.split('-')[0] || '');
        block.setAttribute('data-end-time', newTimeStr.split('-')[1] || '');
    }

    if (block.getAttribute('data-lesson-type') === 'trial' && window.TrialUI) {
        var dates = [];
        try {
            dates = JSON.parse(block.getAttribute('data-trial-dates') || '[]');
        } catch (e) {}
        window.TrialUI.applyTrialExpiredStyle(block, window.TrialUI.isTrialExpired(dates));
    }

    // Update lesson type attribute and re-apply active filter
    if (typeof updateBlockLessonType === 'function') {
        updateBlockLessonType(block);
    }
    if (block.getAttribute('data-lesson-type') === 'group' && typeof window.normalizeGroupBlockRuntimeState === 'function') {
        window.normalizeGroupBlockRuntimeState(block);
    }
    if (typeof reapplyLessonTypeFilter === 'function') {
        reapplyLessonTypeFilter();
    }

    return {
        room:      newRoom,
        startTime: newTimeStr.split('-')[0] || '',
        endTime:   newTimeStr.split('-')[1] || ''
    };
}

window.syncBlockContent = syncBlockContent;
