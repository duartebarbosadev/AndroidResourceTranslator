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
        
        # Convert locale code to standard format
        standard_code = locale_code
       
        # Handle Android BCP 47 format (b+zh+CN or b+zh+Hans+CN)
        if locale_code.startswith("b+"):
            parts = locale_code[2:].split("+")
            language = parts[0]
            script = None
            region = None
           
            # Handle scripts like Hans/Hant in Chinese
            if len(parts) > 1 and parts[1] in ["Hans", "Hant"]:
                script = parts[1]
                region = parts[2] if len(parts) > 2 else None
            elif len(parts) > 1:
                region = parts[1]
           
            standard_code = language
            if script:
                standard_code += "_" + script
            if region:
                standard_code += "_" + region
           
        # Handle Android standard resource format (zh-rCN)
        elif "-r" in locale_code:
            parts = locale_code.split("-r")
            language = parts[0]
            region = parts[1] if len(parts) > 1 else None
            standard_code = language
            if region:
                standard_code += "_" + region
               
        # Handle regular dash format (en-US)
        elif "-" in locale_code and not locale_code.startswith("b+"):
            standard_code = locale_code.replace("-", "_")
       
        # Parse the locale using Babel
        locale = Locale.parse(standard_code)
       
        # Return the full display name in English
        return locale.get_display_name(locale='en')
       
    except Exception as e:
        # Log warning and return the original code if parsing fails
        logger.warning(f"Could not determine language name for locale '{locale_code}': {e}")
        return locale_code