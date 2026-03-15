"""Утилиты отображения пользовательского профиля на этапе регистрации."""

from __future__ import annotations

from app.database import db


def build_profile_review_text(user) -> str:
    """Формирует текст ревью анкеты.

    Функция вынесена отдельно, чтобы:
    - повторно использовать ее в регистрации и legacy-потоке;
    - обеспечивать единый формат представления данных.
    """

    gender_text = (
        "мужской"
        if user.gender == "male"
        else "женский"
        if user.gender == "female"
        else "не указан"
    )
    birth_text = user.birth_date.strftime("%d.%m.%Y") if user.birth_date else "не указана"

    return (
        "🧾 Проверьте введённые данные:\n\n"
        f"👤 Имя: {user.first_name_input or 'не указано'}\n"
        f"👥 Фамилия: {user.last_name_input or 'не указана'}\n"
        f"📱 Телефон: {user.phone_number or 'не указан'}\n"
        f"⚥ Пол: {gender_text}\n"
        f"🎂 Дата рождения: {birth_text}\n"
        f"📧 Email: {user.email or 'не указан'}\n\n"
        "Если всё верно, нажмите подтверждение. Если нужно изменить — выберите редактирование."
    )


async def get_profile_review_text(user_id: int) -> str:
    """Возвращает готовый текст ревью профиля по ID пользователя."""
    user = await db.get_user(user_id)
    if not user:
        return "❌ Не удалось загрузить анкету пользователя."
    return build_profile_review_text(user)
