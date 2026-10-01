// Модуль для обнаружения конфликтов расписания

var ConflictDetector = (function() {
    'use strict';

    function ensureStyles() {
        if (document.getElementById('conflict-detector-styles')) {
            return;
        }

        var style = document.createElement('style');
        style.id = 'conflict-detector-styles';
        style.textContent = `
            .activity-block.conflict-block {
                outline: 2px solid #e53935 !important;
                box-shadow: 0 0 0 3px rgba(229, 57, 53, 0.35) !important;
            }
        `;
        document.head.appendChild(style);
    }

    function normalizeBlockLines(blockElement) {
        var blockContent = blockElement.innerHTML || '';
        return blockContent
            .replace(/<br\s*\/?\s*>/gi, '\n')
            .replace(/<[^>]*>/g, '')
            .split('\n')
            .map(function(line) {
                return line.trim();
            })
            .filter(function(line) {
                return !!line;
            });
    }

    function minutesToLabel(totalMinutes) {
        if (typeof totalMinutes !== 'number' || totalMinutes < 0) {
            return '';
        }

        var hours = Math.floor(totalMinutes / 60);
        var minutes = totalMinutes % 60;
        return String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0');
    }

    function normalizeText(value) {
        return String(value || '').replace(/\s+/g, ' ').trim();
    }

    function normalizeLessonType(value) {
        var lessonType = normalizeText(value).toLowerCase();
        return lessonType || 'group';
    }

    function extractGroupMarkers(students) {
        var normalized = normalizeText(students);
        var markers = [];

        if (!normalized) {
            return markers;
        }

        normalized.split(/\s+/).forEach(function(part) {
            if (!/\d/.test(part)) {
                return;
            }

            if (part.indexOf('+') !== -1) {
                part.split('+').forEach(function(groupPart) {
                    groupPart = normalizeText(groupPart);
                    if (groupPart) {
                        markers.push(groupPart);
                    }
                });
                return;
            }

            markers.push(part);
        });

        return markers.length ? markers : [normalized];
    }

    function findSharedGroupMarker(block1, block2) {
        var markers1;
        var markers2;

        if (block1.lessonType !== 'group' || block2.lessonType !== 'group') {
            return '';
        }

        markers1 = block1.groupMarkers || [];
        markers2 = block2.groupMarkers || [];

        for (var i = 0; i < markers1.length; i++) {
            if (markers2.indexOf(markers1[i]) !== -1) {
                return markers1[i];
            }
        }

        return '';
    }

    function parseBlock(blockElement) {
        var lines = normalizeBlockLines(blockElement);
        var day = blockElement.getAttribute('data-day') || '';
        var building = blockElement.getAttribute('data-building') || '';
        var subject = lines[0] || '';
        var teacher = lines[1] || '';
        var students = lines[2] || '';
        var room = lines[3] || '';
        var timeRange = lines[4] || '';
        var lessonType = normalizeLessonType(blockElement.getAttribute('data-lesson-type'));
        var parsedTime = null;

        if (typeof parseTimeRange === 'function' && timeRange) {
            parsedTime = parseTimeRange(timeRange.replace(/\s+/g, ''));
        }

        return {
            element: blockElement,
            day: day,
            building: building,
            subject: subject,
            teacher: teacher,
            students: students,
            room: room,
            lessonType: lessonType,
            groupMarkers: lessonType === 'group' ? extractGroupMarkers(students) : [],
            timeRange: timeRange,
            startMinutes: parsedTime ? parsedTime.startMinutes : null,
            endMinutes: parsedTime ? parsedTime.endMinutes : null
        };
    }

    function getVisibleBlocks() {
        return Array.from(document.querySelectorAll('.activity-block')).filter(function(block) {
            return window.getComputedStyle(block).display !== 'none';
        });
    }

    function detectConflictType(block1, block2) {
        var sharedGroupMarker;

        if (block1.teacher && block1.teacher === block2.teacher) {
            return {
                type: 'teacher',
                label: block1.teacher
            };
        }

        if (block1.room && block1.room === block2.room && block1.building === block2.building) {
            return {
                type: 'room',
                label: block1.room + (block1.building ? ' (' + block1.building + ')' : '')
            };
        }

        sharedGroupMarker = findSharedGroupMarker(block1, block2);
        if (sharedGroupMarker) {
            return {
                type: 'group',
                label: sharedGroupMarker
            };
        }

        if (
            block1.lessonType !== 'group' &&
            block2.lessonType !== 'group' &&
            block1.students &&
            block1.students === block2.students
        ) {
            return {
                type: 'student',
                label: block1.students
            };
        }

        return null;
    }

    function findConflicts() {
        if (typeof checkTimeOverlap !== 'function') {
            return [];
        }

        var parsedBlocks = getVisibleBlocks().map(parseBlock);
        var conflicts = [];

        for (var i = 0; i < parsedBlocks.length; i++) {
            for (var j = i + 1; j < parsedBlocks.length; j++) {
                var block1 = parsedBlocks[i];
                var block2 = parsedBlocks[j];

                if (!block1.day || !block2.day || block1.day !== block2.day) {
                    continue;
                }

                if (
                    block1.startMinutes === null ||
                    block1.endMinutes === null ||
                    block2.startMinutes === null ||
                    block2.endMinutes === null
                ) {
                    continue;
                }

                if (!checkTimeOverlap(block1.startMinutes, block1.endMinutes, block2.startMinutes, block2.endMinutes)) {
                    continue;
                }

                var conflictType = detectConflictType(block1, block2);
                if (!conflictType) {
                    continue;
                }

                conflicts.push({
                    block1: block1,
                    block2: block2,
                    type: conflictType.type,
                    label: conflictType.label
                });
            }
        }

        return conflicts;
    }

    function highlightConflicts() {
        var allBlocks = document.querySelectorAll('.activity-block');
        allBlocks.forEach(function(block) {
            block.classList.remove('conflict-block');
        });

        var conflicts = findConflicts();
        conflicts.forEach(function(conflict) {
            conflict.block1.element.classList.add('conflict-block');
            conflict.block2.element.classList.add('conflict-block');
        });

        return conflicts.length;
    }

    function hasConflicts() {
        return findConflicts().length > 0;
    }

    function getConflictLabel(conflict) {
        if (conflict.label) {
            return conflict.label;
        }
        return conflict.block1.students || '';
    }

    function getConflictTimeLabel(conflict) {
        var start = Math.max(conflict.block1.startMinutes, conflict.block2.startMinutes);
        var end = Math.min(conflict.block1.endMinutes, conflict.block2.endMinutes);

        if (start >= 0 && end > start) {
            return minutesToLabel(start) + '-' + minutesToLabel(end);
        }

        return conflict.block1.timeRange || conflict.block2.timeRange || '';
    }

    function getConflictSummary() {
        var conflicts = findConflicts();
        if (!conflicts.length) {
            return 'Конфликты не обнаружены.';
        }

        var limit = 5;
        var lines = ['Обнаружено ' + conflicts.length + ' конфликт(ов):'];
        var shown = conflicts.slice(0, limit);

        shown.forEach(function(conflict) {
            var label = getConflictLabel(conflict);
            var day = conflict.block1.day || '';
            var timeLabel = getConflictTimeLabel(conflict);
            var subject1 = conflict.block1.subject || 'Без предмета';
            var subject2 = conflict.block2.subject || 'Без предмета';

            lines.push('• ' + label + ': ' + day + ' ' + timeLabel + ' (' + subject1 + ' / ' + subject2 + ')');
        });

        if (conflicts.length > limit) {
            lines.push('...и ещё ' + (conflicts.length - limit) + ' конфликт(ов)');
        }

        return lines.join('\n');
    }

    ensureStyles();

    return {
        findConflicts: function() {
            return findConflicts();
        },
        highlightConflicts: function() {
            return highlightConflicts();
        },
        hasConflicts: function() {
            return hasConflicts();
        },
        getConflictSummary: function() {
            return getConflictSummary();
        }
    };
})();

window.ConflictDetector = ConflictDetector;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        ConflictDetector.highlightConflicts();
    });
} else {
    window.setTimeout(function() {
        ConflictDetector.highlightConflicts();
    }, 0);
}
