import re

DEFAULT_COUNTRY_CODE = '254'


def normalize_phone(value):
    """Return the number in international format (+254712345678), or None if blank.

    A leading 0 is read as a Kenyan local number (0712345678 -> +254712345678). Other numbers
    must be given with a country code, with or without the leading +.
    """
    if not value:
        return None
    number = re.sub(r'[\s\-().]', '', str(value))
    if not number:
        return None
    if number.startswith('+'):
        return number
    if number.startswith('00'):
        return '+' + number[2:]
    if number.startswith('0'):
        return '+' + DEFAULT_COUNTRY_CODE + number[1:]
    return '+' + number
