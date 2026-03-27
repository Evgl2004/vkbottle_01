"""Интеграционные тесты для веб-маршрутов."""

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from unittest.mock import AsyncMock, patch

from app.web.routes import setup_routes


class TestWebRoutes(AioHTTPTestCase):
    """Тестирование веб-маршрутов с использованием aiohttp.test_utils."""

    async def get_application(self):
        """Создаёт тестовое приложение aiohttp."""
        app = web.Application()
        setup_routes(app)
        return app

    @unittest_run_loop
    async def test_health_check(self):
        """Эндпоинт /health должен возвращать статус ok."""
        resp = await self.client.request("GET", "/health")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"status": "ok"}

    @unittest_run_loop
    @patch("app.web.routes.validate_state_token")
    @patch("app.web.routes.verify_phone_from_mini_app")
    async def test_phone_verify_success(self, mock_verify, mock_validate):
        """Успешное подтверждение телефона."""
        mock_validate.return_value = None  # state_token не используется
        mock_verify.return_value = (True, "Телефон успешно подтверждён")

        payload = {
            "phone": "+79991234567",
            "vk_user_id": 123456789,
            "signature": {"vk_user_id": "123456789", "sign": "valid"},
        }
        resp = await self.client.request(
            "POST",
            "/api/v1/phone/verify",
            json=payload,
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "успешно" in data["message"].lower()

    @unittest_run_loop
    @patch("app.web.routes.validate_state_token")
    async def test_phone_verify_missing_fields(self, mock_validate):
        """Отсутствие обязательных полей приводит к ошибке 400."""
        mock_validate.return_value = None
        payload = {"phone": "+79991234567"}  # нет vk_user_id
        resp = await self.client.request(
            "POST",
            "/api/v1/phone/verify",
            json=payload,
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert "missing" in data["error"].lower()

    @unittest_run_loop
    async def test_phone_verify_invalid_json(self):
        """Невалидный JSON приводит к ошибке 400."""
        resp = await self.client.request(
            "POST",
            "/api/v1/phone/verify",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert "invalid json" in data["error"].lower()

    @unittest_run_loop
    @patch("app.web.routes.validate_state_token")
    @patch("app.web.routes.verify_phone_from_mini_app")
    async def test_phone_verify_with_state_token(self, mock_verify, mock_validate):
        """Успешное подтверждение с валидным state_token."""
        mock_validate.return_value = 123456789  # user_id из токена
        mock_verify.return_value = (True, "Телефон успешно подтверждён")

        payload = {
            "phone": "+79991234567",
            "vk_user_id": 123456789,
            "state_token": "valid-token",
            "signature": {"vk_user_id": "123456789", "sign": "valid"},
        }
        resp = await self.client.request(
            "POST",
            "/api/v1/phone/verify",
            json=payload,
        )
        assert resp.status == 200
        mock_validate.assert_called_once_with("valid-token")
        mock_verify.assert_called_once()

    @unittest_run_loop
    @patch("app.web.routes.validate_state_token")
    async def test_phone_verify_invalid_state_token(self, mock_validate):
        """Невалидный state_token приводит к ошибке 400."""
        mock_validate.return_value = None

        payload = {
            "phone": "+79991234567",
            "vk_user_id": 123456789,
            "state_token": "invalid-token",
            "signature": {},
        }
        resp = await self.client.request(
            "POST",
            "/api/v1/phone/verify",
            json=payload,
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert "invalid or expired" in data["error"].lower()

    @unittest_run_loop
    @patch("app.web.routes.validate_state_token")
    async def test_phone_verify_state_token_user_mismatch(self, mock_validate):
        """Несоответствие user_id из state_token и vk_user_id приводит к ошибке."""
        mock_validate.return_value = 999999999  # другой user_id

        payload = {
            "phone": "+79991234567",
            "vk_user_id": 123456789,
            "state_token": "valid-token",
            "signature": {},
        }
        resp = await self.client.request(
            "POST",
            "/api/v1/phone/verify",
            json=payload,
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert "user mismatch" in data["error"].lower()

    @unittest_run_loop
    @patch("app.web.routes.validate_state_token")
    @patch("app.web.routes.verify_phone_from_mini_app")
    async def test_phone_verify_failure(self, mock_verify, mock_validate):
        """Ошибка проверки телефона возвращает 400."""
        mock_validate.return_value = None
        mock_verify.return_value = (False, "Невалидная подпись")

        payload = {
            "phone": "+79991234567",
            "vk_user_id": 123456789,
            "signature": {},
        }
        resp = await self.client.request(
            "POST",
            "/api/v1/phone/verify",
            json=payload,
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert data["error"] == "Невалидная подпись"