FROM python:3.13-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    alsa-utils \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем директории и устанавливаем права
RUN mkdir -p /app/session /app/logs \
    && chmod 777 /app/session /app/logs

# Устанавливаем рабочую директорию
WORKDIR /

# Копируем все файлы в контейнер
COPY . .

# Обновляем pip и устанавливаем зависимости
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Указываем переменные окружения
ENV PYTHONUNBUFFERED=1

# Устанавливаем права на выполнение скрипта
RUN chmod +x scrap_bot.py

# Запускаем бота
CMD ["python", "scrap_bot.py"]