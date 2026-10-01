// Основной модуль с базовыми функциями расписания

function refreshCompactRowsAfterUiChange() {
    if (window.ScheduleCompactRows && typeof window.ScheduleCompactRows.refresh === 'function') {
        window.ScheduleCompactRows.refresh();
    } else if (typeof window.updateActivityPositions === 'function') {
        window.updateActivityPositions();
    }
}

// Функция переключения видимости дня
window.toggleDay = function(btn, dayCode) {
    var hidden;
    document.querySelectorAll('.schedule-container').forEach(function(container) {
        var cells = container.querySelectorAll('th.day-' + dayCode);
        cells.forEach(function(cell) {
            cell.style.display = (cell.style.display === 'none') ? '' : 'none';
        });
        
        var dataCells = container.querySelectorAll('td.day-' + dayCode);
        dataCells.forEach(function(cell) {
            cell.style.display = (cell.style.display === 'none') ? '' : 'none';
        });
        
        var acts = container.querySelectorAll('.activity-block[data-day="' + dayCode + '"]');
        acts.forEach(function(act) {
            act.style.display = (act.style.display === 'none') ? 'flex' : 'none';
        });
        
        if (cells.length > 0) {
            hidden = (cells[0].style.display === 'none');
        }
    });
    
    if (hidden) {
        btn.classList.add("active");
    } else {
        btn.classList.remove("active");
    }
    
    refreshCompactRowsAfterUiChange();
};
