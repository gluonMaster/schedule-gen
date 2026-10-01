// Модуль для адаптивного изменения цвета текста в блоках расписания

// Функция инициализации адаптивного цвета текста
function initAdaptiveTextColor() {
    // Применяем контрастный цвет текста к существующим блокам
    applyContrastTextColorToBlocks();
    
    // Наблюдаем за добавлением новых блоков
    setupBlockObserver();
}

// Функция для применения контрастного цвета текста ко всем блокам
function applyContrastTextColorToBlocks() {
    var blocks = document.querySelectorAll('.activity-block');
    blocks.forEach(function(block) {
        applyContrastTextColorToBlock(block);
    });
    
    console.log(`Применен контрастный цвет текста к ${blocks.length} блокам`);
}

// Функция для применения контрастного цвета текста к одному блоку
function applyContrastTextColorToBlock(block) {
    // Получаем цвет фона блока
    var backgroundColor = getComputedStyle(block).backgroundColor;
    
    // Если фон не задан или прозрачный, используем цвет по умолчанию
    if (!backgroundColor || backgroundColor === 'transparent' || backgroundColor === 'rgba(0, 0, 0, 0)') {
        backgroundColor = block.style.backgroundColor || '#FFFBD3'; // Желтый цвет по умолчанию
    }
    
    // Получаем контрастный цвет текста
    var textColor = getContrastTextColor(backgroundColor);
    
    // Применяем цвет текста к блоку
    block.style.color = textColor;
    
    // Добавляем класс для текстовой тени в зависимости от цвета текста
    if (textColor === '#FFFFFF') {
        // Для белого текста добавляем темную тень
        block.style.textShadow = '0 0 1px rgba(0, 0, 0, 0.7)';
    } else {
        // Для черного текста добавляем светлую тень
        block.style.textShadow = '0 0 1px rgba(255, 255, 255, 0.7)';
    }
}

// Настраиваем наблюдатель за добавлением новых блоков
function setupBlockObserver() {
    // Создаем наблюдатель за изменениями в DOM
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            // Проверяем, добавлены ли новые узлы
            if (mutation.type === 'childList' && mutation.addedNodes.length) {
                mutation.addedNodes.forEach(function(node) {
                    // Если добавлен элемент с классом activity-block
                    if (node.nodeType === 1 && node.classList && node.classList.contains('activity-block')) {
                        applyContrastTextColorToBlock(node);
                    }
                    // Или проверяем вложенные элементы, если это контейнер
                    else if (node.nodeType === 1 && node.querySelectorAll) {
                        var newBlocks = node.querySelectorAll('.activity-block');
                        newBlocks.forEach(applyContrastTextColorToBlock);
                    }
                });
            }
        });
    });
    
    // Начинаем наблюдение за всем документом
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    console.log('Наблюдатель за новыми блоками инициализирован');
    
    // Также обновляем цвет текста при изменении стиля блока
    document.addEventListener('DOMAttrModified', function(e) {
        var target = e.target;
        if (target.classList && target.classList.contains('activity-block') && 
            e.attrName === 'style' && e.newValue.includes('background-color')) {
            applyContrastTextColorToBlock(target);
        }
    }, false);
    
    // Для браузеров, не поддерживающих DOMAttrModified
    document.body.addEventListener('click', function(e) {
        // Проверяем, был ли клик внутри или рядом с блоком активности
        var block = e.target.closest('.activity-block');
        if (block) {
            // Немного задерживаем, чтобы дать время другим обработчикам изменить стиль
            setTimeout(function() {
                applyContrastTextColorToBlock(block);
            }, 100);
        }
    });
}

// Функция для обновления цвета текста при изменении фона блока
function updateTextColorAfterBackgroundChange(block) {
    // Ждем небольшую задержку, чтобы дать браузеру время применить новый цвет фона
    setTimeout(function() {
        applyContrastTextColorToBlock(block);
    }, 10);
}

// Экспортируем функции для использования в других модулях
window.initAdaptiveTextColor = initAdaptiveTextColor;
window.applyContrastTextColorToBlock = applyContrastTextColorToBlock;
window.updateTextColorAfterBackgroundChange = updateTextColorAfterBackgroundChange;