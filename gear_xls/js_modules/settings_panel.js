// Модуль панели настроек компенсации

// Обновленная функция применения настроек компенсации
function applyCompensationSettings() {
    // Сохраняем предыдущие значения 
    window.previousCompensationFactor = window.compensationFactor;
    window.previousCompensationExponent = window.compensationExponent;
    
    // Получаем новые значения из ползунков
    var newSettings = {
        compensationFactor: parseFloat(document.getElementById('comp-factor').value),
        compensationExponent: parseFloat(document.getElementById('comp-exponent').value)
    };
    
    // Обновляем глобальные переменные
    window.compensationFactor = newSettings.compensationFactor;
    window.compensationExponent = newSettings.compensationExponent;
    
    // Сохраняем настройки в localStorage
    saveSettings(newSettings);
    
    // Обновляем позиции всех блоков, используя новые параметры компенсации
    updateActivityPositions();
    
    // Уведомляем пользователя
    alert('Настройки компенсации применены!');
}

// Обновленная функция инициализации настроек компенсации
function initCompensationSettings() {
    // Значения по умолчанию
    var defaultSettings = {
        compensationFactor: 0.4,
        compensationExponent: 1.02
    };
    
    // Получаем сохраненные настройки или используем значения по умолчанию
    var settings = loadSettings() || defaultSettings;
    
    // Обновляем глобальные переменные
    window.compensationFactor = settings.compensationFactor;
    window.compensationExponent = settings.compensationExponent;
    window.previousCompensationFactor = settings.compensationFactor;
    window.previousCompensationExponent = settings.compensationExponent;
    
    // Проверяем, существует ли уже панель настроек
    var existingPanel = document.querySelector('.settings-panel');
    
    if (!existingPanel) {
        // Создаем HTML панели настроек только если её нет
        var settingsHTML = `
            <div class="settings-panel">
                <div class="settings-toggle">⚙️</div>
                <div class="settings-content">
                    <h3>Настройки отображения</h3>
                    <div class="setting-row">
                        <label for="comp-factor">Коэффициент компенсации: <span id="comp-factor-value">${settings.compensationFactor}</span></label>
                        <input type="range" id="comp-factor" min="0" max="1" step="0.05" value="${settings.compensationFactor}">
                    </div>
                    <div class="setting-row">
                        <label for="comp-exponent">Показатель нелинейности: <span id="comp-exponent-value">${settings.compensationExponent}</span></label>
                        <input type="range" id="comp-exponent" min="0.8" max="1.5" step="0.01" value="${settings.compensationExponent}">
                    </div>
                    <div class="setting-buttons">
                        <button id="apply-settings">Применить</button>
                        <button id="reset-settings">Сбросить</button>
                    </div>
                    <div class="settings-info">
                        Настройки помогают корректно отображать блоки в вашем браузере.
                        <br>Изменяйте значения и нажимайте "Применить" для проверки.
                    </div>
                </div>
            </div>
        `;
        
        // Создаем и добавляем стили (только при создании новой панели)
        var styleElement = document.createElement('style');
        styleElement.textContent = `
            .settings-panel {
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 999;
                font-family: Arial, sans-serif;
            }
            .settings-toggle {
                width: 40px;
                height: 40px;
                background-color: white;
                border-radius: 50%;
                display: flex;
                justify-content: center;
                align-items: center;
                cursor: pointer;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                font-size: 20px;
            }
            .settings-content {
                position: absolute;
                bottom: 50px;
                right: 0;
                width: 300px;
                background-color: white;
                border-radius: 8px;
                padding: 15px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                display: none;
            }
            .settings-content h3 {
                margin-top: 0;
                margin-bottom: 15px;
                font-size: 16px;
                color: #333;
                border-bottom: 1px solid #eee;
                padding-bottom: 8px;
            }
            .setting-row {
                margin-bottom: 15px;
            }
            .setting-row label {
                display: block;
                margin-bottom: 5px;
                font-size: 14px;
            }
            .setting-row input {
                width: 100%;
            }
            .setting-buttons {
                display: flex;
                margin-top: 15px;
        }
        .setting-buttons button {
            padding: 8px 12px;
            border: none;
            border-radius: 4px;
            background-color: #4CAF50;
            color: white;
            cursor: pointer;
            font-size: 14px;
        }
        .setting-buttons button:hover {
            opacity: 0.9;
        }
        .setting-buttons button#reset-settings {
            background-color: #f1f1f1;
            color: #333;
        }
        .settings-info {
            margin-top: 15px;
            font-size: 12px;
            color: #666;
            font-style: italic;
            line-height: 1.4;
        }
        .settings-open .settings-content {
            display: block;
        }
        `;
        document.head.appendChild(styleElement);
        
        // Создаем панель настроек (только если её нет)
        var settingsElement = document.createElement('div');
        settingsElement.innerHTML = settingsHTML;
        document.body.appendChild(settingsElement);
    }
    
    // Получаем элементы (независимо от того, создали мы их или они уже существовали)
    var settingsPanel = document.querySelector('.settings-panel');
    var settingsToggle = document.querySelector('.settings-toggle');
    var compFactorInput = document.getElementById('comp-factor');
    var compExponentInput = document.getElementById('comp-exponent');
    var compFactorValue = document.getElementById('comp-factor-value');
    var compExponentValue = document.getElementById('comp-exponent-value');
    var applyButton = document.getElementById('apply-settings');
    var resetButton = document.getElementById('reset-settings');
    
    // Обновляем значения в уже существующих элементах
    if (compFactorInput) compFactorInput.value = settings.compensationFactor;
    if (compExponentInput) compExponentInput.value = settings.compensationExponent;
    if (compFactorValue) compFactorValue.textContent = settings.compensationFactor;
    if (compExponentValue) compExponentValue.textContent = settings.compensationExponent;
    
    // Очищаем старые обработчики событий путем клонирования элементов
    if (settingsToggle) {
        var newSettingsToggle = settingsToggle.cloneNode(true);
        settingsToggle.parentNode.replaceChild(newSettingsToggle, settingsToggle);
        settingsToggle = newSettingsToggle;
    }
    
    if (applyButton) {
        var newApplyButton = applyButton.cloneNode(true);
        applyButton.parentNode.replaceChild(newApplyButton, applyButton);
        applyButton = newApplyButton;
    }
    
    if (resetButton) {
        var newResetButton = resetButton.cloneNode(true);
        resetButton.parentNode.replaceChild(newResetButton, resetButton);
        resetButton = newResetButton;
    }
    
    if (compFactorInput) {
        var newCompFactorInput = compFactorInput.cloneNode(true);
        compFactorInput.parentNode.replaceChild(newCompFactorInput, compFactorInput);
        compFactorInput = newCompFactorInput;
    }
    
    if (compExponentInput) {
        var newCompExponentInput = compExponentInput.cloneNode(true);
        compExponentInput.parentNode.replaceChild(newCompExponentInput, compExponentInput);
        compExponentInput = newCompExponentInput;
    }
    
    // Привязываем обработчики событий заново
    if (settingsToggle && settingsPanel) {
        settingsToggle.addEventListener('click', function() {
            settingsPanel.classList.toggle('settings-open');
        });
    }
    
    if (compFactorInput && compFactorValue) {
        compFactorInput.addEventListener('input', function() {
            compFactorValue.textContent = this.value;
        });
    }
    
    if (compExponentInput && compExponentValue) {
        compExponentInput.addEventListener('input', function() {
            compExponentValue.textContent = this.value;
        });
    }
    
    if (applyButton) {
        applyButton.addEventListener('click', applyCompensationSettings);
    }
    
    if (resetButton) {
        resetButton.addEventListener('click', function() {
            // Сбрасываем к значениям по умолчанию
            if (compFactorInput) compFactorInput.value = defaultSettings.compensationFactor;
            if (compExponentInput) compExponentInput.value = defaultSettings.compensationExponent;
            if (compFactorValue) compFactorValue.textContent = defaultSettings.compensationFactor;
            if (compExponentValue) compExponentValue.textContent = defaultSettings.compensationExponent;
            
            // Сохраняем предыдущие значения перед обновлением
            window.previousCompensationFactor = window.compensationFactor;
            window.previousCompensationExponent = window.compensationExponent;
            
            // Применяем значения по умолчанию
            window.compensationFactor = defaultSettings.compensationFactor;
            window.compensationExponent = defaultSettings.compensationExponent;
            
            // Сохраняем настройки по умолчанию
            saveSettings(defaultSettings);
            
            // Обновляем позиции всех блоков
            resetCompensation();
            updateActivityPositions();
            
            // Уведомляем пользователя
            alert('Настройки сброшены к значениям по умолчанию!');
        });
    }
}