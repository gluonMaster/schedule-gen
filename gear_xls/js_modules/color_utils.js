// Модуль для работы с цветами и их преобразованиями

// Функция для определения яркости цвета
function getColorBrightness(color) {
    // Извлекаем RGB значения из цвета
    var r, g, b;
    
    // Поддержка hex формата (#RRGGBB)
    if (color.startsWith('#')) {
        var hex = color.substring(1);
        r = parseInt(hex.substring(0, 2), 16);
        g = parseInt(hex.substring(2, 4), 16);
        b = parseInt(hex.substring(4, 6), 16);
    } 
    // Поддержка rgb(r, g, b) формата
    else if (color.startsWith('rgb')) {
        var rgbMatch = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[\d.]+)?\)/);
        if (rgbMatch) {
            r = parseInt(rgbMatch[1]);
            g = parseInt(rgbMatch[2]);
            b = parseInt(rgbMatch[3]);
        } else {
            // Если не удалось распарсить, используем значения по умолчанию
            r = 128;
            g = 128;
            b = 128;
        }
    }
    // По умолчанию (если формат неизвестен)
    else {
        r = 128;
        g = 128;
        b = 128;
    }
    
    // Используем формулу для определения относительной яркости
    // (0.299*R + 0.587*G + 0.114*B) / 255
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

// Функция для определения контрастного цвета текста
function getContrastTextColor(backgroundColor) {
    // Получаем яркость цвета фона
    var brightness = getColorBrightness(backgroundColor);
    
    // Порог яркости (от 0 до 1)
    // Значения выше порога считаются светлыми, ниже - темными
    var threshold = 0.55;
    
    // Для светлых фонов возвращаем темный текст, для темных - светлый
    return brightness > threshold ? '#000000' : '#FFFFFF';
}

// Функция для преобразования HEX в RGB
function hexToRgb(hex) {
    // Удаляем # если он присутствует
    hex = hex.replace(/^#/, '');
    
    // Извлекаем компоненты
    var bigint = parseInt(hex, 16);
    var r = (bigint >> 16) & 255;
    var g = (bigint >> 8) & 255;
    var b = bigint & 255;
    
    return { r, g, b };
}

// Функция для преобразования RGB в HEX
function rgbToHex(r, g, b) {
    return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}

// Функция для осветления или затемнения цвета
function adjustColor(color, amount) {
    var rgb = hexToRgb(color);
    
    rgb.r = Math.max(0, Math.min(255, rgb.r + amount));
    rgb.g = Math.max(0, Math.min(255, rgb.g + amount));
    rgb.b = Math.max(0, Math.min(255, rgb.b + amount));
    
    return rgbToHex(rgb.r, rgb.g, rgb.b);
}

// Экспортируем функции для использования в других модулях
window.getColorBrightness = getColorBrightness;
window.getContrastTextColor = getContrastTextColor;
window.hexToRgb = hexToRgb;
window.rgbToHex = rgbToHex;
window.adjustColor = adjustColor;