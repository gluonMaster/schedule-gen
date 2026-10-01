// Модуль для отслеживания новых блоков и применения к ним обработчиков удаления

// Функция инициализации наблюдателя за блоками
function initDeleteBlocksObserver() {
    // Создаем обработчик для новых блоков
    var observer = null;
    
    // Получаем статус режима удаления
    function isDeleteModeActive() {
        var deleteButton = document.getElementById('delete-block-button');
        return deleteButton && deleteButton.classList.contains('active');
    }
    
    // Функция для добавления обработчика удаления новому блоку
    function addDeleteHandlerToBlock(block) {
        if (isDeleteModeActive()) {
            // Добавляем обработчик клика для удаления
            block.addEventListener('click', handleBlockDelete);
            
            // Добавляем атрибут title для подсказки
            block.setAttribute('data-original-title', block.getAttribute('title') || '');
            block.setAttribute('title', 'Нажмите, чтобы удалить блок');
        }
    }
    
    // Обработчик удаления блока (дублируем для новых блоков)
    function handleBlockDelete(e) {
        if (!isDeleteModeActive()) return;
        
        // Предотвращаем всплытие события
        e.preventDefault();
        e.stopPropagation();
        
        // Получаем блок, на который кликнули
        var block = e.currentTarget;
        
        // Получаем информацию о блоке для уведомления
        var building = BuildingService.determineBuildingForBlock(block) || "Неизвестно";
        var day = block.getAttribute('data-day');
        var subject = '';
        var teacher = '';
        var time = '';
        
        // Извлекаем информацию из содержимого блока
        var subjectElement = block.querySelector('strong');
        if (subjectElement) {
            subject = subjectElement.textContent || '';
        }
        
        var parts = block.innerHTML.split('<br>');
        if (parts.length > 1) teacher = parts[1].trim();
        if (parts.length > 4) time = parts[4].trim();
        
        // Запрашиваем подтверждение удаления
        var confirmMessage = `Вы действительно хотите удалить занятие?\n\nЗдание: ${building}\nДень: ${day}\nПредмет: ${subject}\nПреподаватель: ${teacher}\nВремя: ${time}`;
        
        if (confirm(confirmMessage)) {
            // Удаляем блок
            block.parentNode.removeChild(block);
            
            // Создаем уведомление об успешном удалении
            showNotification(`Занятие удалено: ${subject} (${time})`, 'success');
        }
    }
    
    // Функция удалена - используем BuildingService.determineBuildingForBlock()
    
    // Функция для отображения уведомления (дублируем для автономности)
    function showNotification(message, type = 'info') {
        // Создаем элемент уведомления
        var notification = document.createElement('div');
        notification.className = 'notification ' + type;
        notification.textContent = message;
        
        // Добавляем стили для уведомления, если их еще нет
        if (!document.getElementById('notification-styles')) {
            var notificationStyles = document.createElement('style');
            notificationStyles.id = 'notification-styles';
            notificationStyles.textContent = `
                .notification {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    padding: 15px 25px;
                    border-radius: 4px;
                    font-weight: bold;
                    color: white;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                    z-index: 9999;
                    animation: fadeIn 0.3s ease, fadeOut 0.3s ease 2.7s;
                    max-width: 350px;
                }
                .notification.info {
                    background-color: #2196F3;
                }
                .notification.success {
                    background-color: #4CAF50;
                }
                .notification.warning {
                    background-color: #FF9800;
                }
                .notification.error {
                    background-color: #F44336;
                }
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                @keyframes fadeOut {
                    from { opacity: 1; transform: translateY(0); }
                    to { opacity: 0; transform: translateY(-10px); }
                }
            `;
            document.head.appendChild(notificationStyles);
        }
        
        // Добавляем уведомление в DOM
        document.body.appendChild(notification);
        
        // Удаляем уведомление через 3 секунды
        setTimeout(function() {
            if (notification.parentNode) {
                document.body.removeChild(notification);
            }
        }, 3000);
    }
    
    // Инициализация наблюдателя за добавлением новых блоков
    function initObserver() {
        // Определение конфигурации наблюдателя
        var config = { childList: true, subtree: true };
        
        // Создание экземпляра наблюдателя
        observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    // Проверяем каждый добавленный узел
                    mutation.addedNodes.forEach(function(node) {
                        // Проверяем, является ли узел элементом и имеет ли класс activity-block
                        if (node.nodeType === 1 && node.classList && node.classList.contains('activity-block')) {
                            addDeleteHandlerToBlock(node);
                        }
                        // Если это контейнер, проверяем его детей
                        else if (node.nodeType === 1 && node.querySelectorAll) {
                            var newBlocks = node.querySelectorAll('.activity-block');
                            newBlocks.forEach(addDeleteHandlerToBlock);
                        }
                    });
                }
            });
        });
        
        // Начинаем наблюдение за всем документом
        observer.observe(document.body, config);
        
        // Для тестирования
        console.log('Наблюдатель за новыми блоками инициализирован');
    }
    
    // Инициализируем наблюдатель
    initObserver();
    
    // Возвращаем функцию для остановки наблюдения
    return function stopObserver() {
        if (observer) {
            observer.disconnect();
            observer = null;
            console.log('Наблюдатель за новыми блоками остановлен');
        }
    };
}

// Экспортируем функцию инициализации
window.initDeleteBlocksObserver = initDeleteBlocksObserver;