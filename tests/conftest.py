"""Конфигурация pytest для тестов проекта."""

import os
import sys

# Устанавливаем переменные окружения перед импортом модулей приложения
os.environ["VK_BOT_TOKEN"] = "test_token"
os.environ["VK_GROUP_ID"] = "0"
os.environ["VK_MINI_APP_ID"] = "123456"
os.environ["VK_MINI_APP_SECRET"] = "test_secret"
os.environ["VK_MINI_APP_URL"] = "https://vk.com/app"
os.environ["WEB_ENABLED"] = "false"
os.environ["WEB_HOST"] = "0.0.0.0"
os.environ["WEB_PORT"] = "8080"
os.environ["ADMIN_USER_IDS"] = ""
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_DB"] = "test_db"
os.environ["POSTGRES_USER"] = "test_user"
os.environ["POSTGRES_PASSWORD"] = "test_password"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["REDIS_DB"] = "0"
os.environ["REDIS_PASSWORD"] = ""
os.environ["IIKO_API_KEY"] = ""
os.environ["IIKO_ORG_ID"] = ""
os.environ["IIKO_BASE_URL"] = ""
os.environ["ENV"] = "test"
os.environ["LOG_LEVEL"] = "ERROR"
os.environ["LOG_SUPER_VERBOSE"] = "false"

# Теперь можно импортировать модули приложения
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))