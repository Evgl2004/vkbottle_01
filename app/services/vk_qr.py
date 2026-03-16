"""Сервис генерации и отправки QR-кодов виртуальных карт в сообщения VK.

Назначение модуля:
1. Сформировать PNG-изображение QR-кода по номеру виртуальной карты.
2. Загрузить изображение через VK API (`photos.getMessagesUploadServer`).
3. Сохранить загруженную фотографию (`photos.saveMessagesPhoto`).
4. Отправить пользователю сообщение с attachment вида `photo<owner_id>_<id>`.

Почему вынесено в отдельный сервис:
- один и тот же сценарий используется в нескольких потоках (регистрация, меню);
- централизованно логируются все этапы (генерация, upload, save, send);
- в случае ошибки можно дать единый fallback и быстро диагностировать причину.
"""

from __future__ import annotations

from typing import Any, Optional

import aiohttp
import qrcode
from loguru import logger
from vkbottle.bot import Message


def mask_card_number(card_number: str) -> str:
    """Возвращает безопасное представление номера карты для логов.

    Пример:
    - `79991234567_20260316` -> `79***16`
    """

    value = (card_number or "").strip()
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _extract_field(source: Any, field: str) -> Any:
    """Безопасно извлекает поле из dict/объекта модели VK API."""

    if isinstance(source, dict):
        return source.get(field)
    return getattr(source, field, None)


def _build_photo_attachment(photo: Any) -> Optional[str]:
    """Формирует attachment-строку VK из объекта фотографии."""

    owner_id = _extract_field(photo, "owner_id")
    photo_id = _extract_field(photo, "id")
    access_key = _extract_field(photo, "access_key")

    if owner_id is None or photo_id is None:
        return None

    attachment = f"photo{owner_id}_{photo_id}"
    if access_key:
        attachment += f"_{access_key}"
    return attachment


def generate_qr_png_bytes(card_number: str) -> bytes:
    """Генерирует PNG-байты QR-кода по номеру карты."""

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=2,
    )
    qr.add_data(card_number)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    # Объект изображения PIL совместим с методом `save`.
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def send_card_qr(
    message: Message,
    card_number: str,
    *,
    title: str = "QR-код виртуальной карты",
) -> bool:
    """Генерирует и отправляет QR-картинку карты в текущий диалог.

    Возвращает:
    - `True`, если картинка успешно отправлена;
    - `False`, если на любом этапе произошла ошибка.
    """

    user_id = int(message.from_id)
    peer_id = int(message.peer_id)
    safe_card = mask_card_number(card_number)

    if not card_number:
        logger.warning(
            "Пропуск генерации QR: пустой номер карты (user_id={}, peer_id={})",
            user_id,
            peer_id,
        )
        return False

    logger.debug(
        "Старт отправки QR-кода карты (user_id={}, peer_id={}, card={})",
        user_id,
        peer_id,
        safe_card,
    )

    try:
        image_bytes = generate_qr_png_bytes(card_number)
        logger.debug(
            "QR-код сгенерирован (user_id={}, size={} bytes, card={})",
            user_id,
            len(image_bytes),
            safe_card,
        )

        upload_info = await message.ctx_api.photos.get_messages_upload_server(peer_id=peer_id)
        upload_url = _extract_field(upload_info, "upload_url")
        if not upload_url:
            logger.error(
                "VK не вернул upload_url для QR (user_id={}, peer_id={}, card={})",
                user_id,
                peer_id,
                safe_card,
            )
            return False

        form = aiohttp.FormData()
        form.add_field(
            "photo",
            image_bytes,
            filename="virtual_card_qr.png",
            content_type="image/png",
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                upload_url,
                data=form,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                raw_body = await response.text()
                if response.status != 200:
                    logger.error(
                        "Ошибка загрузки QR в VK upload-server: status={}, body='{}', user_id={}, card={}",
                        response.status,
                        raw_body[:800],
                        user_id,
                        safe_card,
                    )
                    return False

                upload_result = await response.json(content_type=None)

        photo_value = upload_result.get("photo")
        server_value = upload_result.get("server")
        hash_value = upload_result.get("hash")
        if not photo_value or server_value is None or not hash_value:
            logger.error(
                "Некорректный ответ upload-server при отправке QR: {} (user_id={}, card={})",
                upload_result,
                user_id,
                safe_card,
            )
            return False

        saved_photos = await message.ctx_api.photos.save_messages_photo(
            photo=photo_value,
            server=server_value,
            hash=hash_value,
        )
        if not saved_photos:
            logger.error(
                "VK не сохранил photo после upload (user_id={}, card={})",
                user_id,
                safe_card,
            )
            return False

        attachment = _build_photo_attachment(saved_photos[0])
        if not attachment:
            logger.error(
                "Не удалось собрать attachment для QR (user_id={}, card={}, photo={})",
                user_id,
                safe_card,
                saved_photos[0],
            )
            return False

        # По UX-требованию подпись отправляется отдельным сообщением,
        # а само изображение QR уходит без caption для максимальной площади отображения.
        await message.answer(
            "\n".join(
                [
                    title,
                    f"Номер карты: {card_number}",
                ]
            )
        )
        await message.answer(attachment=attachment)

        logger.info(
            "QR-код карты отправлен успешно (user_id={}, peer_id={}, card={})",
            user_id,
            peer_id,
            safe_card,
        )
        return True
    except Exception:
        logger.exception(
            "Непредвиденная ошибка при отправке QR (user_id={}, peer_id={}, card={})",
            user_id,
            peer_id,
            safe_card,
        )
        return False
