from babel import Locale

import logging

logger = logging.getLogger(__name__)


def get_language_name(locale_code: str) -> str:
    """
    Get language name from various locale code formats using Babel.
    Handles Android resource qualifiers (standard and BCP 47).

    Args:
        locale_code: A string representing a locale code in various formats:
                    - Language code (e.g., 'en', 'zh')
                    - Language with country (e.g., 'en-US', 'zh-CN')
                    - Android standard qualifier (e.g., 'en-rUS', 'zh-rCN')
                    - Android BCP 47 qualifier (e.g., 'b+en+US', 'b+zh+CN')
                    - With script info (e.g., 'b+zh+Hans+CN')

    Returns:
        A string with the display name of the language in English, including region if available.
        Returns the original locale_code if parsing fails.
    """
    try:
        # If locale_code is 'default', return Default (English)
        if locale_code == "default":
            return "Default (English)"

        # Normalize the locale code using regex
        import re

        normalized_code = re.sub(r"^b\+", "", locale_code)
        normalized_code = re.sub(r"-r", "_", normalized_code)
        normalized_code = re.sub(r"-", "_", normalized_code)
        normalized_code = re.sub(r"\+", "_", normalized_code)

        # Parse the locale using Babel
        locale = Locale.parse(normalized_code)
        # Return the full display name in English
        return locale.get_display_name(locale="en")

    except Exception as e:
        # Log warning and return the original code if parsing fails
        logger.warning(
            f"Could not determine language name for locale '{locale_code}': {e}"
        )
        return locale_code
