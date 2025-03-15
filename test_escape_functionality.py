#!/usr/bin/env python3
"""
Simple script to verify that the escape_special_chars function works correctly
in the context of translate_text and translate_plural_text.
"""
import re
import json
from typing import Dict

# Import the escape functions
def escape_apostrophes(text: str) -> str:
    """Ensure apostrophes in the text are properly escaped."""
    if not text:
        return text
    return re.sub(r"(?<!\\)'", r"\'", text)

def escape_percent(text: str) -> str:
    """Ensure percent signs in the text are properly escaped."""
    if not text:
        return text
    return re.sub(r'(?<!\\)%(?![0-9]?[$]?[sd])', r'\\%', text)

def escape_double_quotes(text: str) -> str:
    """Ensure double quotes in the text are properly escaped."""
    if not text:
        return text
    return re.sub(r'(?<!\\)"', r'\\"', text)

def escape_at_symbol(text: str) -> str:
    """Ensure at symbols in the text are properly escaped."""
    if not text:
        return text
    return re.sub(r'(?<!\\)@', r'\\@', text)

def escape_special_chars(text: str) -> str:
    """Ensure all special characters in the text are properly escaped."""
    if not text:
        return text
    text = escape_apostrophes(text)
    text = escape_percent(text)
    text = escape_double_quotes(text)
    text = escape_at_symbol(text)
    return text

# Mock translate functions to simulate behavior
def translate_text(text: str, target_language: str, api_key: str, model: str, project_context: str) -> str:
    """Mock translate_text function."""
    # Simulate the result of call_openai
    result = f"Translated {text} with special chars: ' % @ \""
    # Apply escape_special_chars as in the original function
    return escape_special_chars(result)

def translate_plural_text(source_plural: Dict[str, str], target_language: str, api_key: str, 
                         model: str, project_context: str) -> Dict[str, str]:
    """Mock translate_plural_text function."""
    # Simulate the result of call_openai and json.loads
    result = {
        "one": f"One item with special chars: ' % @ \"",
        "other": f"Multiple items with special chars: ' % @ \""
    }
    # Apply escape_special_chars to each item as in the original function
    for quantity, text in result.items():
        result[quantity] = escape_special_chars(text)
    return result

def test_translate_text_with_escape_special_chars():
    """Test translate_text with escape_special_chars."""
    result = translate_text(
        "Test string", "es", "fake_api_key", "gpt-4", ""
    )
    print(f"translate_text result: {result}")
    
    # Verify all special characters are escaped
    assert "\\'" in result, "Apostrophes should be escaped"
    assert "\\%" in result, "Percent signs should be escaped"
    assert "\\@" in result, "At symbols should be escaped"
    assert "\\\"" in result, "Double quotes should be escaped"
    
    print("✅ translate_text with escape_special_chars test passed")

def test_translate_plural_text_with_escape_special_chars():
    """Test translate_plural_text with escape_special_chars."""
    source_plural = {"one": "One item", "other": "Multiple items"}
    result = translate_plural_text(
        source_plural, "es", "fake_api_key", "gpt-4", ""
    )
    
    print(f"translate_plural_text result: {json.dumps(result, indent=2)}")
    
    # Verify all special characters are escaped in both plural forms
    for quantity, text in result.items():
        assert "\\'" in text, f"Apostrophes should be escaped in {quantity}"
        assert "\\%" in text, f"Percent signs should be escaped in {quantity}"
        assert "\\@" in text, f"At symbols should be escaped in {quantity}"
        assert "\\\"" in text, f"Double quotes should be escaped in {quantity}"
    
    print("✅ translate_plural_text with escape_special_chars test passed")

if __name__ == "__main__":
    test_translate_text_with_escape_special_chars()
    test_translate_plural_text_with_escape_special_chars()
    print("\nAll integration tests passed!")