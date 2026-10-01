// Module: block_resize.js
// Vertical resize of .activity-block elements by dragging the bottom edge.
// Depends on: block_content_sync.js (syncBlockContent),
//             services/drag_drop_service.js (DragDropService.setPreventDrag, isDragging),
//             position.js (updateActivityPositions),
//             global vars: gridCellHeight, borderWidth, gridStart, timeInterval.

var isResizing     = false; // true while a resize drag is active
var resizingBlock  = null;  // reference to the block being resized
var resizeStartY   = 0;     // clientY at mousedown
var resizeOrigSpan = 0;     // data-row-span value at mousedown
var resizeStartRow = 0;     // data-start-row value at mousedown (read-only during resize)
var RESIZE_ZONE_PX = 6;     // pixels from bottom edge that trigger resize mode
var compactRowsResizePaused = false;

function pauseCompactRowsForResize() {
    if (
        !compactRowsResizePaused &&
        window.ScheduleCompactRows &&
        typeof window.ScheduleCompactRows.pauseForInteraction === 'function'
    ) {
        window.ScheduleCompactRows.pauseForInteraction('resize');
        compactRowsResizePaused = true;
    }
}

function resumeCompactRowsAfterResize(refresh) {
    if (
        compactRowsResizePaused &&
        window.ScheduleCompactRows &&
        typeof window.ScheduleCompactRows.resumeAfterInteraction === 'function'
    ) {
        window.ScheduleCompactRows.resumeAfterInteraction('resize', { refresh: !!refresh });
    }
    compactRowsResizePaused = false;
}

function getResizeAuthUi() {
    return window.SchedGenAuthUI || null;
}

function getResizeRole() {
    return window.USER_ROLE || 'viewer';
}

function getResizeLessonType(block) {
    return block ? (block.getAttribute('data-lesson-type') || 'group') : 'group';
}

function canResizeBlock(block) {
    var authUi = getResizeAuthUi();
    var role = getResizeRole();
    var lessonType = getResizeLessonType(block);

    if (authUi && typeof authUi.isEditMode === 'function' && !authUi.isEditMode()) {
        return false;
    }
    if (authUi && typeof authUi.canMutateBlock === 'function') {
        return authUi.canMutateBlock(role, block);
    }
    if (role === 'admin') return true;
    if (role === 'editor') return lessonType !== 'group';
    if (role === 'organizer') return lessonType === 'trial';
    return false;
}

Object.defineProperty(window, 'isResizing', {
    get: function() { return isResizing; },
    configurable: true
});

function getBlockMaxRow(block) {
    var container = block.closest('.schedule-container');
    if (!container) return 999;
    var table = container.querySelector('.schedule-grid');
    if (!table) return 999;
    var cells = table.querySelectorAll('td[data-row]');
    var maxRow = 0;
    cells.forEach(function(cell) {
        var r = parseInt(cell.getAttribute('data-row'), 10);
        if (!isNaN(r) && r > maxRow) maxRow = r;
    });
    return maxRow + 1; // +1: allowed to span to end of last row
}

function isInResizeZone(block, clientY) {
    var rect = block.getBoundingClientRect();
    return clientY >= rect.bottom - RESIZE_ZONE_PX && clientY <= rect.bottom + 2;
}

function performResize(e) {
    var deltaY = e.clientY - resizeStartY;
    var gCellH = (typeof gridCellHeight !== 'undefined') ? gridCellHeight : 20;
    var bWidth = (typeof borderWidth !== 'undefined') ? borderWidth : 1;
    var deltaRows = Math.round(deltaY / (gCellH + bWidth));
    var newSpan = resizeOrigSpan + deltaRows;
    var maxRow = getBlockMaxRow(resizingBlock);

    // Clamp: minimum 1 row; maximum: startRow + span <= maxRow
    if (newSpan < 1) newSpan = 1;
    if (resizeStartRow + newSpan > maxRow) newSpan = maxRow - resizeStartRow;
    if (newSpan < 1) newSpan = 1;

    resizingBlock.setAttribute('data-row-span', newSpan);

    if (typeof updateActivityPositions === 'function') {
        updateActivityPositions();
    }
}

function handleResizeMouseMove(e) {
    // 1. If actively resizing, do resize logic
    if (isResizing && resizingBlock) {
        performResize(e);
        return;
    }

    // 2. If dragging (DragDropService is active), clear stale hover hint and do nothing
    if (typeof DragDropService !== 'undefined' && DragDropService.isDragging()) {
        document.querySelectorAll('.activity-block[data-resize-hover]').forEach(function(b) {
            b.removeAttribute('data-resize-hover');
        });
        return;
    }

    // 3. Update cursor hint on hovered block
    var target = e.target;
    var block = target.closest ? target.closest('.activity-block') : null;

    // Remove hint from all blocks
    document.querySelectorAll('.activity-block[data-resize-hover]').forEach(function(b) {
        if (b !== block) b.removeAttribute('data-resize-hover');
    });

    if (block && !window.editDialogOpen && canResizeBlock(block)) {
        if (isInResizeZone(block, e.clientY)) {
            block.setAttribute('data-resize-hover', '1');
        } else {
            block.removeAttribute('data-resize-hover');
        }
    }
}

function handleResizeMouseDown(e) {
    // Only left mouse button
    if (e.button !== 0) return;
    // Do not start resize if edit dialog is open
    if (window.editDialogOpen) return;

    var target = e.target;
    var block = target.closest ? target.closest('.activity-block') : null;
    if (!block) return;
    if (!canResizeBlock(block)) return;

    if (!isInResizeZone(block, e.clientY)) return;

    // Resize zone hit - start resize
    isResizing = true;
    resizingBlock = block;
    resizeStartY = e.clientY;
    resizeOrigSpan = parseInt(block.getAttribute('data-row-span'), 10) || 1;
    resizeStartRow = parseInt(block.getAttribute('data-start-row'), 10) || 0;
    pauseCompactRowsForResize();

    block.classList.add('resizing');

    // Prevent DragDropService from starting a drag on this mousedown
    if (typeof DragDropService !== 'undefined') {
        DragDropService.setPreventDrag(true);
    }

    e.stopPropagation();
    e.preventDefault();
}

function handleResizeMouseUp(e) {
    if (!isResizing || !resizingBlock) return;

    try {
        var finalSpan = parseInt(resizingBlock.getAttribute('data-row-span'), 10) || resizeOrigSpan;
        var spanChanged = (finalSpan !== resizeOrigSpan);

        // Finalize the new rowSpan (already set in performResize)
        resizingBlock.classList.remove('resizing');
        resizingBlock.removeAttribute('data-resize-hover');

        // Only update text and conflicts if the block was actually resized
        if (spanChanged) {
            if (typeof syncBlockContent === 'function') {
                syncBlockContent(resizingBlock);
            }
            if (resizingBlock.getAttribute('data-lesson-type') === 'group' && typeof window.normalizeGroupBlockRuntimeState === 'function') {
                window.normalizeGroupBlockRuntimeState(resizingBlock);
            }
            if (typeof ConflictDetector !== 'undefined') {
                ConflictDetector.highlightConflicts();
            }
        }
    } finally {
        // Re-enable drag
        if (typeof DragDropService !== 'undefined') {
            DragDropService.setPreventDrag(false);
        }

        isResizing = false;
        resizingBlock = null;
        resumeCompactRowsAfterResize(true);
    }
}

function initBlockResize() {
    document.addEventListener('mousemove', handleResizeMouseMove);
    document.addEventListener('mousedown', handleResizeMouseDown, true); // capture
    document.addEventListener('mouseup', handleResizeMouseUp);
    console.log('BlockResize initialized');
}

window.initBlockResize = initBlockResize;
