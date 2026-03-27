"""Unit-тесты для сервиса работы с VK Mini App."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.services.mini_app import (
    generate_mini_app_link,
    create_state_token,
    validate_state_token,
    notify_bot_phone_verified,
    verify_phone_from_mini_app,
)


class TestGenerateMiniAppLink:
    """Тестирование генерации ссылки на Mini App."""

    @patch("app.services.mini_app.settings")
    def test_with_app_id_and_user_id(self, mock_settings):
        """Генерация ссылки с заданным app_id и user_id."""
        mock_settings.vk_mini_app_id = 123456
        mock_settings.vk_mini_app_url = "https://vk.com/app"
        link = generate_mini_app_link(user_id=789)
        assert link.startswith("https://vk.com/app123456?")
        assert "vk_user_id=789" in link
        assert "state_token" not in link

    @patch("app.services.mini_app.settings")
    def test_with_state_token(self, mock_settings):
        """Генерация ссылки с переданным state_token."""
        mock_settings.vk_mini_app_id = 123456
        mock_settings.vk_mini_app_url = "https://vk.com/app"
        link = generate_mini_app_link(user_id=789, state_token="abc123")
        assert "state_token=abc123" in link

    @patch("app.services.mini_app.settings")
    def test_with_custom_url(self, mock_settings):
        """Генерация ссылки с кастомным URL."""
        mock_settings.vk_mini_app_id = 123456
        mock_settings.vk_mini_app_url = "https://myapp.example.com"
        link = generate_mini_app_link(user_id=789)
        assert link.startswith("https://myapp.example.com?")
        assert "vk_user_id=789" in link

    @patch("app.services.mini_app.settings")
    def test_missing_app_id(self, mock_settings):
        """Если app_id не задан, возвращается пустая строка."""
        mock_settings.vk_mini_app_id = None
        mock_settings.vk_mini_app_url = "https://vk.com/app"
        link = generate_mini_app_link(user_id=789)
        assert link == ""


class TestCreateStateToken:
    """Тестирование создания state_token."""

    @pytest.mark.asyncio
    @patch("app.services.mini_app.uuid")
    @patch("app.services.state_dispenser.get_redis_client")
    async def test_create_token(self, mock_get_redis, mock_uuid):
        """Токен создаётся и сохраняется в Redis."""
        mock_uuid.uuid4.return_value = "test-uuid"
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        token = await create_state_token(user_id=123, ttl_seconds=300)
        assert token == "test-uuid"
        # Проверяем, что redis.setex был вызван с правильными аргументами
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "mini_app:state_token:test-uuid"
        assert call_args[0][1] == 300
        # Проверяем, что в данных есть user_id
        import json
        data = json.loads(call_args[0][2])
        assert data["user_id"] == 123
        assert "created_at" in data


class TestValidateStateToken:
    """Тестирование валидации state_token."""

    @pytest.mark.asyncio
    @patch("app.services.state_dispenser.get_redis_client")
    async def test_valid_token(self, mock_get_redis):
        """Валидный токен возвращает user_id и удаляется из Redis."""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = '{"user_id": 123, "created_at": "2023-01-01T00:00:00Z"}'
        user_id = await validate_state_token("valid-token")
        assert user_id == 123
        mock_redis.get.assert_called_once_with("mini_app:state_token:valid-token")
        mock_redis.delete.assert_called_once_with("mini_app:state_token:valid-token")

    @pytest.mark.asyncio
    @patch("app.services.state_dispenser.get_redis_client")
    async def test_expired_token(self, mock_get_redis):
        """Истёкший токен возвращает None."""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = None
        user_id = await validate_state_token("expired-token")
        assert user_id is None
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.state_dispenser.get_redis_client")
    async def test_invalid_json(self, mock_get_redis):
        """Некорректные данные в Redis возвращают None."""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = "invalid json"
        user_id = await validate_state_token("bad-token")
        assert user_id is None
        mock_redis.delete.assert_called_once_with("mini_app:state_token:bad-token")

    @pytest.mark.asyncio
    @patch("app.services.state_dispenser.get_redis_client")
    async def test_missing_user_id(self, mock_get_redis):
        """Если в данных нет user_id, возвращается None."""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = '{"created_at": "2023-01-01T00:00:00Z"}'
        user_id = await validate_state_token("no-user-token")
        assert user_id is None
        mock_redis.delete.assert_called_once_with("mini_app:state_token:no-user-token")


class TestNotifyBotPhoneVerified:
    """Тестирование уведомления бота о подтверждении телефона."""

    @pytest.mark.asyncio
    @patch("app.services.state_dispenser.get_redis_client")
    async def test_set_flag(self, mock_get_redis):
        """Флаг устанавливается в Redis с TTL."""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        await notify_bot_phone_verified(user_id=123, ttl_seconds=60)
        mock_redis.setex.assert_called_once_with("phone_verified:123", 60, "1")


class TestVerifyPhoneFromMiniApp:
    """Тестирование проверки телефона из Mini App."""

    @pytest.mark.asyncio
    @patch("app.services.mini_app.verify_mini_app_request")
    @patch("app.services.mini_app.db")
    @patch("app.utils.validation.validate_phone")
    @patch("app.utils.validation.normalize_phone")
    @patch("app.services.mini_app.notify_bot_phone_verified")
    async def test_success(
        self,
        mock_notify,
        mock_normalize,
        mock_validate,
        mock_db,
        mock_verify,
    ):
        """Успешное подтверждение телефона."""
        mock_verify.return_value = True
        mock_validate.return_value = (True, "")
        mock_normalize.return_value = "+79991234567"
        mock_user = MagicMock()
        mock_user.phone_verified_at = None
        # db.get_user должен быть асинхронным
        mock_db.get_user = AsyncMock(return_value=mock_user)
        mock_db.update_user = AsyncMock()
        mock_notify.return_value = None

        success, message = await verify_phone_from_mini_app(
            phone="+79991234567",
            vk_user_id=123,
            signature_params={"vk_user_id": "123", "sign": "valid"},
        )
        assert success is True
        assert "успешно" in message.lower()
        mock_db.update_user.assert_called_once()
        # Проверяем, что notify_bot_phone_verified был вызван
        mock_notify.assert_called_once_with(123)

    @pytest.mark.asyncio
    @patch("app.services.mini_app.verify_mini_app_request")
    async def test_invalid_signature(self, mock_verify):
        """Невалидная подпись приводит к ошибке."""
        mock_verify.return_value = False
        success, message = await verify_phone_from_mini_app(
            phone="+79991234567",
            vk_user_id=123,
            signature_params={},
        )
        assert success is False
        assert "подпись" in message.lower()

    @pytest.mark.asyncio
    @patch("app.services.mini_app.verify_mini_app_request")
    async def test_user_id_mismatch(self, mock_verify):
        """Несоответствие vk_user_id приводит к ошибке."""
        mock_verify.return_value = True
        success, message = await verify_phone_from_mini_app(
            phone="+79991234567",
            vk_user_id=123,
            signature_params={"vk_user_id": "456", "sign": "valid"},
        )
        assert success is False
        assert "идентификатора" in message.lower()

    @pytest.mark.asyncio
    @patch("app.services.mini_app.verify_mini_app_request")
    @patch("app.utils.validation.validate_phone")
    async def test_invalid_phone(self, mock_validate, mock_verify):
        """Невалидный номер телефона приводит к ошибке."""
        mock_verify.return_value = True
        mock_validate.return_value = (False, "Некорректный номер")
        success, message = await verify_phone_from_mini_app(
            phone="invalid",
            vk_user_id=123,
            signature_params={"vk_user_id": "123", "sign": "valid"},
        )
        assert success is False
        assert "некорректный" in message.lower()

    @pytest.mark.asyncio
    @patch("app.services.mini_app.verify_mini_app_request")
    @patch("app.services.mini_app.db")
    @patch("app.utils.validation.validate_phone")
    @patch("app.utils.validation.normalize_phone")
    async def test_already_verified(self, mock_normalize, mock_validate, mock_db, mock_verify):
        """Если телефон уже подтверждён, возвращается успех с соответствующим сообщением."""
        mock_verify.return_value = True
        mock_validate.return_value = (True, "")
        mock_normalize.return_value = "+79991234567"
        mock_user = MagicMock()
        mock_user.phone_verified_at = datetime.now(timezone.utc)
        # db.get_user должен быть асинхронным
        mock_db.get_user = AsyncMock(return_value=mock_user)

        success, message = await verify_phone_from_mini_app(
            phone="+79991234567",
            vk_user_id=123,
            signature_params={"vk_user_id": "123", "sign": "valid"},
        )
        assert success is True
        assert "уже" in message.lower()
        # Обновление БД не должно вызываться
        mock_db.update_user.assert_not_called()