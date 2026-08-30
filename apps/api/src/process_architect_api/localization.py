import re


SUPPORTED_LOCALES = ("ru", "en", "es")
DEFAULT_LOCALE = "ru"
LOCALE_PATTERN = re.compile(r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$")


def normalize_locale(locale: str) -> str:
    value = locale.strip().replace("_", "-")
    if not LOCALE_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid BCP 47 locale: {locale}.")
    parts = value.split("-")
    normalized = [parts[0].lower()]
    normalized.extend(part.upper() if len(part) == 2 else part.title() for part in parts[1:])
    return "-".join(normalized)
