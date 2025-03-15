#!/usr/bin/env python3
"""
Standalone tests for the character escaping functions.
This script doesn't require any external dependencies.
"""
import re
import sys

# Import the escape functions directly
def escape_apostrophes(text: str) -> str:
    """Ensure apostrophes in the text are properly escaped for Android resource files."""
    if not text:
        return text
    return re.sub(r"(?<!\\)'", r"\'", text)

def escape_percent(text: str) -> str:
    """Ensure percent signs in the text are properly escaped for Android resource files."""
    if not text:
        return text
    return re.sub(r'(?<!\\)%(?![0-9]?[$]?[sd])', r'\\%', text)

def escape_double_quotes(text: str) -> str:
    """Ensure double quotes in the text are properly escaped for Android resource files."""
    if not text:
        return text
    return re.sub(r'(?<!\\)"', r'\\"', text)

def escape_at_symbol(text: str) -> str:
    """Ensure at symbols in the text are properly escaped for Android resource files."""
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

def run_tests():
    """Run tests for all escape functions."""
    test_escape_apostrophes()
    test_escape_percent()
    test_escape_double_quotes()
    test_escape_at_symbol()
    test_escape_special_chars()
    print("All tests passed!")

def test_escape_apostrophes():
    """Test that apostrophes are properly escaped."""
    test_cases = [
        # Format: (input, expected output)
        ("No apostrophes here", "No apostrophes here"),
        ("Apostrophe's need escaping", "Apostrophe\\'s need escaping"),
        ("Multiple apostrophes' in one's text", "Multiple apostrophes\\' in one\\'s text"),
        ("Already escaped apostrophe \\'s fine", "Already escaped apostrophe \\'s fine"),
        ("Mixed escaping: one's and one\\'s", "Mixed escaping: one\\'s and one\\'s"),
        ("", ""),  # Empty string
        (None, None),  # None value
        ("Special ' chars ' everywhere '", "Special \\' chars \\' everywhere \\'"),
    ]
    
    for input_text, expected in test_cases:
        result = escape_apostrophes(input_text)
        assert result == expected, f"Failed on '{input_text}': got '{result}', expected '{expected}'"
    print("✅ escape_apostrophes tests passed")

def test_escape_percent():
    """Test that percent signs are properly escaped."""
    test_cases = [
        # Format: (input, expected output)
        ("No percent signs here", "No percent signs here"),
        ("15% discount", "15\\% discount"),
        ("Multiple % percent % signs", "Multiple \\% percent \\% signs"),
        ("Already escaped percent \\% is fine", "Already escaped percent \\% is fine"),
        ("Mixed escaping: 10% and 20\\%", "Mixed escaping: 10\\% and 20\\%"),
        ("", ""),  # Empty string
        (None, None),  # None value
        # Format specifiers should not be escaped
        ("String with %s format specifier", "String with %s format specifier"),
        ("Int with %d format specifier", "Int with %d format specifier"),
        ("Indexed with %1$s format specifier", "Indexed with %1$s format specifier"),
        # Mix of format specifiers and regular percent signs
        ("Mix of %s and % signs", "Mix of %s and \\% signs"),
        ("Pattern 100% %d complete", "Pattern 100\\% %d complete"),
    ]
    
    for input_text, expected in test_cases:
        result = escape_percent(input_text)
        assert result == expected, f"Failed on '{input_text}': got '{result}', expected '{expected}'"
    print("✅ escape_percent tests passed")

def test_escape_double_quotes():
    """Test that double quotes are properly escaped."""
    test_cases = [
        # Format: (input, expected output)
        ('No double quotes here', 'No double quotes here'),
        ('Text with "quotes"', 'Text with \\"quotes\\"'),
        ('Multiple "double" "quotes"', 'Multiple \\"double\\" \\"quotes\\"'),
        ('Already escaped \\"quotes\\" are fine', 'Already escaped \\"quotes\\" are fine'),
        ('Mixed escaping: "quote" and \\"quote\\"', 'Mixed escaping: \\"quote\\" and \\"quote\\"'),
        ("", ""),  # Empty string
        (None, None),  # None value
    ]
    
    for input_text, expected in test_cases:
        result = escape_double_quotes(input_text)
        assert result == expected, f"Failed on '{input_text}': got '{result}', expected '{expected}'"
    print("✅ escape_double_quotes tests passed")

def test_escape_at_symbol():
    """Test that at symbols are properly escaped."""
    test_cases = [
        # Format: (input, expected output)
        ("No at symbols here", "No at symbols here"),
        ("Email: user@example.com", "Email: user\\@example.com"),
        ("Multiple @ symbols @ here", "Multiple \\@ symbols \\@ here"),
        ("Already escaped \\@symbol is fine", "Already escaped \\@symbol is fine"),
        ("Mixed escaping: @symbol and \\@symbol", "Mixed escaping: \\@symbol and \\@symbol"),
        ("", ""),  # Empty string
        (None, None),  # None value
    ]
    
    for input_text, expected in test_cases:
        result = escape_at_symbol(input_text)
        assert result == expected, f"Failed on '{input_text}': got '{result}', expected '{expected}'"
    print("✅ escape_at_symbol tests passed")

def test_escape_special_chars():
    """Test that all special characters are properly escaped in a single pass."""
    test_cases = [
        # Format: (input, expected output)
        ("Normal text", "Normal text"),
        # Test with individual special characters
        ("Text with apostrophe's", "Text with apostrophe\\'s"),
        ("Text with percent 50%", "Text with percent 50\\%"),
        ('Text with "quotes"', 'Text with \\"quotes\\"'),
        ("Text with @symbol", "Text with \\@symbol"),
        # Test with multiple different special characters
        ('Mixed "quote", apostrophe\'s, 25% and user@example.com',
         'Mixed \\"quote\\", apostrophe\\\'s, 25\\% and user\\@example.com'),
        # Test that format specifiers are preserved
        ("Format %s and %d with %1$s escape", "Format %s and %d with %1$s escape"),
        # Test with already escaped characters
        ("Pre-escaped \\'s and \\% and \\@", "Pre-escaped \\'s and \\% and \\@"),
        # Test with complex mix of escaped and unescaped
        ('Mixed: "quote" and \\"quote\\", \'single\' and \\\'single\\\', 10% and \\%',
         'Mixed: \\"quote\\" and \\"quote\\", \\\'single\\\' and \\\'single\\\', 10\\% and \\%'),
        ("", ""),  # Empty string
        (None, None),  # None value
    ]
    
    for input_text, expected in test_cases:
        result = escape_special_chars(input_text)
        assert result == expected, f"Failed on '{input_text}': got '{result}', expected '{expected}'"
    print("✅ escape_special_chars tests passed")

if __name__ == "__main__":
    run_tests()