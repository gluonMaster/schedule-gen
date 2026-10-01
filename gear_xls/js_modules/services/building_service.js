// Единый сервис для работы со зданиями в расписании
// Заменяет дублированные функции в 8+ JavaScript файлах

/**
 * Сервис для работы со зданиями и их контейнерами расписания
 */
class BuildingService {
    
    /**
     * Определяет здание для указанного блока занятия.
     * Ищет родительский контейнер расписания и анализирует заголовок здания.
     * 
     * @param {HTMLElement} block - Элемент блока занятия
     * @returns {string} Название здания ('Villa', 'Kolibri' или 'Villa' по умолчанию)
     */
    static determineBuildingForBlock(block) {
        if (!block) {
            console.warn('BuildingService.determineBuildingForBlock: block is null or undefined');
            return "Villa"; // По умолчанию
        }
        
        // Находим родительский контейнер расписания
        var container = block.closest('.schedule-container');
        if (!container) {
            console.warn('BuildingService.determineBuildingForBlock: schedule-container not found for block');
            return "Villa"; // По умолчанию
        }
        
        // Ищем заголовок здания перед контейнером
        var element = container.previousElementSibling;
        while (element) {
            if (element.tagName === 'H2') {
                var headerText = element.textContent;
                if (headerText.includes('Villa')) return 'Villa';
                if (headerText.includes('Kolibri')) return 'Kolibri';
                break;
            }
            element = element.previousElementSibling;
        }
        
        return "Villa"; // По умолчанию, если не определено
    }
    
    /**
     * Находит контейнер расписания для указанного здания.
     * 
     * @param {string} buildingName - Название здания ('Villa' или 'Kolibri')
     * @returns {HTMLElement|null} Контейнер расписания или null если не найден
     */
    static findScheduleContainerForBuilding(buildingName) {
        if (!buildingName) {
            console.warn('BuildingService.findScheduleContainerForBuilding: buildingName is empty');
            return null;
        }
        
        var buildingHeaders = document.querySelectorAll('h2');
        
        for (var i = 0; i < buildingHeaders.length; i++) {
            var headerText = buildingHeaders[i].textContent;
            if (headerText.includes(buildingName)) {
                // Находим ближайший schedule-container после заголовка здания
                var scheduleContainer = buildingHeaders[i].nextElementSibling;
                while (scheduleContainer && !scheduleContainer.classList.contains('schedule-container')) {
                    scheduleContainer = scheduleContainer.nextElementSibling;
                }
                return scheduleContainer;
            }
        }
        
        console.warn(`BuildingService.findScheduleContainerForBuilding: container not found for building ${buildingName}`);
        return null;
    }
    
    /**
     * Возвращает список всех доступных зданий на странице.
     * 
     * @returns {string[]} Массив названий зданий
     */
    static getAvailableBuildings() {
        var buildings = [];
        var buildingHeaders = document.querySelectorAll('h2');
        
        for (var i = 0; i < buildingHeaders.length; i++) {
            var headerText = buildingHeaders[i].textContent;
            if (headerText.includes('Villa') && buildings.indexOf('Villa') === -1) {
                buildings.push('Villa');
            }
            if (headerText.includes('Kolibri') && buildings.indexOf('Kolibri') === -1) {
                buildings.push('Kolibri');
            }
        }
        
        // Если ничего не найдено, возвращаем стандартный набор
        if (buildings.length === 0) {
            buildings = ['Villa', 'Kolibri'];
        }
        
        return buildings;
    }
    
    /**
     * Проверяет существует ли здание на странице.
     * 
     * @param {string} buildingName - Название здания для проверки
     * @returns {boolean} true если здание существует, false иначе
     */
    static buildingExists(buildingName) {
        var availableBuildings = this.getAvailableBuildings();
        return availableBuildings.indexOf(buildingName) !== -1;
    }
    
    /**
     * Перемещает блок занятия в контейнер указанного здания.
     * 
     * @param {HTMLElement} block - Блок занятия для перемещения
     * @param {string} targetBuilding - Целевое здание
     * @returns {boolean} true если перемещение успешно, false иначе
     */
    static moveBlockToBuilding(block, targetBuilding) {
        if (!block || !targetBuilding) {
            console.error('BuildingService.moveBlockToBuilding: invalid parameters');
            return false;
        }
        
        // Проверяем что целевое здание существует
        if (!this.buildingExists(targetBuilding)) {
            console.error(`BuildingService.moveBlockToBuilding: building ${targetBuilding} does not exist`);
            return false;
        }
        
        // Находим контейнер целевого здания
        var targetContainer = this.findScheduleContainerForBuilding(targetBuilding);
        if (!targetContainer) {
            console.error(`BuildingService.moveBlockToBuilding: container not found for building ${targetBuilding}`);
            return false;
        }
        
        // Обновляем атрибут здания у блока
        block.setAttribute('data-building', targetBuilding);
        
        // Перемещаем блок в новый контейнер
        try {
            block.parentNode.removeChild(block);
            targetContainer.appendChild(block);
            console.log(`Block moved to building: ${targetBuilding}`);
            return true;
        } catch (error) {
            console.error('BuildingService.moveBlockToBuilding: error moving block:', error);
            return false;
        }
    }
    
    /**
     * Получает информацию о здании блока.
     * 
     * @param {HTMLElement} block - Блок занятия
     * @returns {Object} Объект с информацией о здании
     */
    static getBlockBuildingInfo(block) {
        var building = this.determineBuildingForBlock(block);
        var container = this.findScheduleContainerForBuilding(building);
        
        return {
            name: building,
            container: container,
            exists: this.buildingExists(building)
        };
    }
    
    /**
     * Валидирует название здания.
     * 
     * @param {string} buildingName - Название здания для валидации
     * @returns {boolean} true если название валидно, false иначе
     */
    static isValidBuildingName(buildingName) {
        if (!buildingName || typeof buildingName !== 'string') {
            return false;
        }
        
        var validBuildings = ['Villa', 'Kolibri'];
        return validBuildings.indexOf(buildingName) !== -1;
    }
    
    /**
     * Получает статистику по зданиям.
     * 
     * @returns {Object} Объект со статистикой: количество блоков по зданиям
     */
    static getBuildingStatistics() {
        var stats = {};
        var allBlocks = document.querySelectorAll('.activity-block');
        
        for (var i = 0; i < allBlocks.length; i++) {
            var block = allBlocks[i];
            var building = this.determineBuildingForBlock(block);
            
            if (!stats[building]) {
                stats[building] = 0;
            }
            stats[building]++;
        }
        
        return stats;
    }
}

// Экспортируем сервис в глобальную область видимости для использования в других модулях
window.BuildingService = BuildingService;

// Для отладки - выводим информацию о загрузке сервиса
console.log('BuildingService loaded successfully');

// Дополнительно экспортируем основные функции для обратной совместимости
window.determineBuildingForBlock = function(block) {
    console.warn('Deprecated: use BuildingService.determineBuildingForBlock() instead');
    return BuildingService.determineBuildingForBlock(block);
};

window.findScheduleContainerForBuilding = function(buildingName) {
    console.warn('Deprecated: use BuildingService.findScheduleContainerForBuilding() instead');
    return BuildingService.findScheduleContainerForBuilding(buildingName);
};
