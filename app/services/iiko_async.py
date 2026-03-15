"""Асинхронный клиент работы с iiko Cloud API.

Клиент инкапсулирует:
1. получение и обновление access token;
2. запрос клиента по телефону;
3. создание/обновление клиента;
4. выпуск карты и подключение программы лояльности.

Модуль оставлен максимально близким к логике референса, но адаптирован
к текущему проекту и конфигурации.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings


class AsyncIikoApi:
    """Асинхронный адаптер iiko API."""

    def __init__(self, api_key: str, organization_id: str, base_url: Optional[str] = None) -> None:
        self.api_key = api_key
        self.organization_id = organization_id
        self.base_url = (base_url or settings.iiko_base_url).rstrip("/")

        self.token: Optional[str] = None
        self.token_expire_time: Optional[datetime] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Возвращает живую HTTP-сессию (создаёт при первом вызове)."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Корректно закрывает HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _is_token_valid(self) -> bool:
        """Проверяет, что токен существует и ещё не истёк."""
        return bool(self.token and self.token_expire_time and datetime.now() < self.token_expire_time)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    )
    async def _get_token(self) -> Optional[str]:
        """Получает токен доступа.

        Особенности:
        - использует lock, чтобы параллельные корутины не гонялись за токеном;
        - повторяет запрос на сетевых ошибках;
        - хранит токен в памяти и обновляет чуть раньше истечения (запас 1 минута).
        """

        async with self._lock:
            if await self._is_token_valid():
                return self.token

            session = await self._get_session()
            payload = {"apiLogin": self.api_key}

            async with session.post(
                f"{self.base_url}/access_token",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                self.token = data.get("token")
                self.token_expire_time = datetime.now() + timedelta(minutes=14)
                logger.info("Получен новый токен iiko")
                return self.token

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Приводит телефон к виду `+7XXXXXXXXXX` (или +<digits> для иных стран)."""

        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits.startswith("7"):
            return f"+{digits}"
        if digits.startswith("8") and len(digits) == 11:
            return f"+7{digits[1:]}"
        if len(digits) == 10:
            return f"+7{digits}"
        return f"+{digits}"

    async def get_customer_info(self, phone: str) -> Optional[Dict[str, Any]]:
        """Возвращает данные клиента iiko по номеру телефона."""

        token = await self._get_token()
        if not token:
            return None

        session = await self._get_session()
        payload = {
            "phone": self._normalize_phone(phone),
            "type": "phone",
            "organizationId": self.organization_id,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            async with session.post(
                f"{self.base_url}/loyalty/iiko/customer/info",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._extract_customer_info(data)
                if response.status in (400, 404):
                    return None

                logger.error("Ошибка iiko customer/info: статус {}", response.status)
                return None
        except aiohttp.ClientError as error:
            logger.error("Сетевая ошибка customer/info: {}", error)
            return None

    async def register_customer(
        self,
        phone: str,
        name: str = "",
        surname: str = "",
        birth_date: Optional[str] = None,
        sex: Optional[int] = None,
        email: str = "",
        consent_status: int = 0,
        should_receive_promo: bool = True,
        should_receive_loyalty: bool = True,
        customer_id: Optional[str] = None,
    ) -> Tuple[Optional[str], str]:
        """Создает или обновляет клиента iiko."""

        token = await self._get_token()
        if not token:
            return None, "Не удалось получить токен iiko."

        payload: Dict[str, Any] = {
            "phone": self._normalize_phone(phone),
            "name": name,
            "shouldReceivePromoActionsInfo": should_receive_promo,
            "shouldReceiveLoyaltyInfo": should_receive_loyalty,
            "consentStatus": consent_status,
            "organizationId": self.organization_id,
        }
        if surname:
            payload["surName"] = surname
        if birth_date:
            payload["birthday"] = birth_date
        if sex is not None:
            payload["sex"] = sex
        if email:
            payload["email"] = email
        if customer_id:
            payload["id"] = customer_id

        session = await self._get_session()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            async with session.post(
                f"{self.base_url}/loyalty/iiko/customer/create_or_update",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("id"), "Клиент iiko успешно сохранён."

                body = await response.text()
                return None, f"Ошибка iiko create_or_update: {body}"
        except aiohttp.ClientError as error:
            return None, f"Сетевая ошибка iiko create_or_update: {error}"

    async def add_card(self, customer_id: str, card_number: str) -> Tuple[bool, str]:
        """Добавляет карту клиенту iiko."""

        token = await self._get_token()
        if not token:
            return False, "Не удалось получить токен iiko."

        session = await self._get_session()
        payload = {
            "customerId": customer_id,
            "cardNumber": card_number,
            "cardTrack": card_number,
            "organizationId": self.organization_id,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            async with session.post(
                f"{self.base_url}/loyalty/iiko/customer/card/add",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    return True, "Карта успешно добавлена."
                return False, await response.text()
        except aiohttp.ClientError as error:
            return False, f"Сетевая ошибка add_card: {error}"

    async def get_loyalty_programs(self) -> List[Dict[str, Any]]:
        """Возвращает список программ лояльности iiko."""

        token = await self._get_token()
        if not token:
            return []

        session = await self._get_session()
        payload = {
            "withoutMarketingCampaigns": True,
            "organizationId": self.organization_id,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            async with session.post(
                f"{self.base_url}/loyalty/iiko/program",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    return []
                data = await response.json()
                return data.get("programs") or data.get("Programs") or []
        except aiohttp.ClientError:
            return []

    async def add_customer_to_program(
        self,
        customer_id: str,
        program_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Подключает клиента к программе лояльности.

        Если `program_id` не передан, выбирается первая доступная программа.
        """

        if not program_id:
            programs = await self.get_loyalty_programs()
            if not programs:
                return False, "Не удалось получить программы лояльности."
            target = programs[0]
            program_id = target.get("id")
            if not program_id:
                return False, "Не удалось определить ID программы лояльности."

        token = await self._get_token()
        if not token:
            return False, "Не удалось получить токен iiko."

        session = await self._get_session()
        payload = {
            "customerId": customer_id,
            "organizationId": self.organization_id,
            "programId": program_id,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            async with session.post(
                f"{self.base_url}/loyalty/iiko/customer/program/add",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    return True, "Программа лояльности подключена."
                return False, await response.text()
        except aiohttp.ClientError as error:
            return False, f"Сетевая ошибка add_customer_to_program: {error}"

    def _extract_customer_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Преобразует ответ iiko в более удобный формат для приложения."""

        result = {
            "customer_id": data.get("id"),
            "name": f"{data.get('surname', '')} {data.get('name', '')}".strip(),
            "phone": data.get("phone", ""),
            "balance": 0,
            "program_name": "",
            "cards": [],
        }

        wallets = data.get("walletBalances") or []
        if wallets:
            target = wallets[0]
            result["balance"] = target.get("balance", 0)
            result["program_name"] = (
                target.get("name") or target.get("programName") or target.get("walletName") or ""
            ).strip()

        cards = data.get("cards") or []
        for card in cards:
            info = {"number": card.get("number", ""), "valid_to": card.get("validToDate", "")}
            if info["valid_to"]:
                try:
                    parsed = datetime.strptime(info["valid_to"], "%Y-%m-%d %H:%M:%S.%f")
                    info["valid_to"] = parsed.strftime("%d.%m.%Y")
                except ValueError:
                    pass
            result["cards"].append(info)

        return result
