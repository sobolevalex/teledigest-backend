# 1. Создаем структуру директорий для FastAPI и папку для медиа
mkdir -p app/services/telegram_reader app/api app/models app/core media

# 2. Копируем исходный код старого проекта
cp -r ../telegram_reader/src/telegram_reader/* app/services/telegram_reader/

# 3. Копируем ключи, сессию и зависимости в корень
cp ../telegram_reader/config.json ../telegram_reader/.env ../telegram_reader/anon.session ../telegram_reader/requirements.txt .

# 4. Железобетонно защищаем секреты от попадания в GitHub (дописываем в .gitignore)
echo -e "\n# Секреты и локальные конфиги\n.env\nanon.session\nconfig.json\n\n# Виртуальное окружение и кэш\nvenv/\n.venv/\n__pycache__/\n*.pyc\n\n# Сгенерированные медиа\nmedia/\n" >> .gitignore

# 5. Создаем чистое виртуальное окружение
python3 -m venv venv

# Выводим сообщение об успехе
echo "✅ Проект успешно собран! Секреты спрятаны в .gitignore, venv создан."