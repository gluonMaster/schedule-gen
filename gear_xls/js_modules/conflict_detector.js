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
        return window.readBlockContentLines(blockElement);
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

    function localCalculationDate() {
        var now = new Date();
        return now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
    }

    function parseDates(value) {
        if (Array.isArray(value)) return value.slice();
        if (!value) return [];
        try {
            var dates = JSON.parse(value);
            return Array.isArray(dates) ? dates : ['invalid'];
        } catch (error) {
            return ['invalid']; // Invalid dated data must not become weekly.
        }
    }

    function activeDates(block, calculationDate) {
        var days = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
        return block.dates.filter(function(value) {
            if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value < calculationDate) return false;
            var parsed = new Date(value + 'T12:00:00');
            if (isNaN(parsed.getTime()) || parsed.getDate() !== Number(value.slice(8, 10)) ||
                parsed.getMonth() + 1 !== Number(value.slice(5, 7))) return false;
            return !block.day || days[parsed.getDay()] === block.day;
        });
    }

    function calendarOverlap(block1, block2, calculationDate) {
        if (block1.lessonType !== 'rental' && block2.lessonType !== 'rental') return true;
        if (block1.dates.length && block2.dates.length) {
            var dates2 = activeDates(block2, calculationDate);
            return activeDates(block1, calculationDate).some(function(value) { return dates2.indexOf(value) !== -1; });
        }
        if (block1.dates.length || block2.dates.length) {
            var dated = block1.dates.length ? block1 : block2;
            var weekly = block1.dates.length ? block2 : block1;
            var days = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
            return activeDates(dated, calculationDate).some(function(value) {
                return !weekly.day || days[new Date(value + 'T12:00:00').getDay()] === weekly.day;
            });
        }
        return true;
    }

    function parseRecord(record) {
        var lessonType = normalizeLessonType(record.lesson_type);
        var parsed = typeof parseTimeRange === 'function' ? parseTimeRange(record.start_time + '-' + record.end_time) : null;
        var building = normalizeText(record.building);
        return {
            day: record.day || '', building: building, subject: record.subject || '',
            teacher: record.teacher || '', students: record.students || '',
            room: normalizeRoomForBuilding(record.room || '', building), lessonType: lessonType,
            groupMarkers: lessonType === 'group' ? extractGroupMarkers(record.students) : [],
            dates: parseDates(lessonType === 'rental' ? (record.rental_dates || record.rental_dates_json) :
                (lessonType === 'trial' ? (record.trial_dates || record.trial_dates_json) : [])),
            timeRange: record.start_time + '-' + record.end_time,
            startMinutes: parsed ? parsed.startMinutes : null, endMinutes: parsed ? parsed.endMinutes : null
        };
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
            room: normalizeRoomForBuilding(room, building),
            lessonType: lessonType,
            dates: parseDates(lessonType === 'rental' ? blockElement.getAttribute('data-rental-dates') :
                (lessonType === 'trial' ? blockElement.getAttribute('data-trial-dates') : [])),
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

        var teachingPair = block1.lessonType !== 'rental' && block2.lessonType !== 'rental';
        if (teachingPair && block1.teacher && block1.teacher === block2.teacher) {
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
            teachingPair &&
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

    function findConflicts(scheduleData, calculationDate) {
        if (typeof checkTimeOverlap !== 'function') {
            return [];
        }

        var parsedBlocks = Array.isArray(scheduleData) ? scheduleData.map(parseRecord) : getVisibleBlocks().map(parseBlock);
        calculationDate = calculationDate || localCalculationDate();
        var conflicts = [];

        for (var i = 0; i < parsedBlocks.length; i++) {
            for (var j = i + 1; j < parsedBlocks.length; j++) {
                var block1 = parsedBlocks[i];
                var block2 = parsedBlocks[j];

                if (!block1.day || !block2.day || block1.day !== block2.day) {
                    continue;
                }

                if (!calendarOverlap(block1, block2, calculationDate)) continue;

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

    function hasConflicts(scheduleData, calculationDate) {
        return findConflicts(scheduleData, calculationDate).length > 0;
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

    function getConflictSummary(scheduleData, calculationDate) {
        var conflicts = findConflicts(scheduleData, calculationDate);
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
        getCalculationDate: localCalculationDate,
        findConflicts: function(scheduleData, calculationDate) {
            return findConflicts(scheduleData, calculationDate);
        },
        highlightConflicts: function() {
            return highlightConflicts();
        },
        hasConflicts: function(scheduleData, calculationDate) {
            return hasConflicts(scheduleData, calculationDate);
        },
        getConflictSummary: function(scheduleData, calculationDate) {
            return getConflictSummary(scheduleData, calculationDate);
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
