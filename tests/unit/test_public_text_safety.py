"""Shared plain-text policy for public bios and descriptions."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_contracts.owner import OwnerExternalProductCreateRequest, OwnerPresentationUpdateRequest
from ai_stp_contracts.public_profile import ProfileFields
from ai_stp_contracts.reports import CountryRequest, ServiceRequest
from ai_stp_contracts.text_safety import validate_public_text


def test_public_text_accepts_unicode_letters_and_digits() -> None:
    profile = ProfileFields(display_name="Алиса 2", bio="Создаю ИИ-сервисы 24/7.")
    presentation = OwnerPresentationUpdateRequest(bio="Компонент для Python 3.", media=[])
    component = ComponentPassportPatch(description="Компонент для Python 3.")
    service = OwnerExternalProductCreateRequest(
        name="Сервис 2",
        primary_url="https://example.com",
        description="Платформа для команд.",
        country_codes=[],
    )
    request = ServiceRequest(
        name="Сервис 2",
        primary_url="https://example.com",
        description_ru="Описание 2.",
        description_en="Service for teams.",
        source_url="https://example.com/source",
        country_codes=[],
    )
    country = CountryRequest(code="RU", name_ru="Россия", name_en="Russia")

    assert profile.bio == "Создаю ИИ-сервисы 24/7."
    assert presentation.bio == "Компонент для Python 3."
    assert component.description == "Компонент для Python 3."
    assert service.description == "Платформа для команд."
    assert request.description_en == "Service for teams."
    assert country.name_ru == "Россия"


def test_public_text_normalizes_unicode_and_newlines() -> None:
    assert validate_public_text("Cafe\u0301\r\nbio") == "Café\nbio"


@pytest.mark.parametrize(
    "value",
    ["Ребёнок", "небесный", "serviceable", "еб"],  # noqa: RUF001
)
def test_public_text_does_not_match_word_fragments(value: str) -> None:
    assert validate_public_text(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "Offer software services.",
        "Available for hire.",
        "Open source commission system.",
        "Paid content strategy.",
        "Предлагаю услуги для команд.",
    ],
)
def test_public_text_accepts_nonsexual_service_language(value: str) -> None:
    assert validate_public_text(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "hello — world",
        "hello 🚀",
        "hello\u200bworld",
        "porn site",
        "порнография",
        "секс",
        "nsfw",
        "xxx",
        "пиздец",
        "ебать",
        "блядь",
        "сука",
        "fuck",
        "bitch",
        "sexual services",
        "only fans",
        "онлифанс",
        "убью тебя",
        "насилие",
        "нацист",
        "фашизм",
        "война",
        "military attack",
    ],
)
def test_public_text_rejects_typography_invisible_characters_and_prohibited_content(
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        ProfileFields(bio=value)


def test_public_text_rejects_markup_and_blank_descriptions() -> None:
    with pytest.raises(ValidationError):
        OwnerPresentationUpdateRequest(bio="**bold**", media=[])
    with pytest.raises(ValidationError):
        ComponentPassportPatch(description="**bold**")
    with pytest.raises(ValidationError):
        OwnerExternalProductCreateRequest(
            name="Service",
            primary_url="https://example.com",
            description="   ",
        )


def test_public_text_rejects_invalid_utf8_surrogates() -> None:
    with pytest.raises(ValueError, match="valid UTF-8"):
        validate_public_text("\ud800")
