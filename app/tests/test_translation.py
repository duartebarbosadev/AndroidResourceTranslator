#!/usr/bin/env python3
"""
Tests for translation functionality in AndroidResourceTranslator.

This module tests the text translation and OpenAI integration features including:
- Single string translation
- Plural string translation
- Auto-translation of resources
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    auto_translate_resources,
    AndroidModule,
    escape_apostrophes,
    escape_percent,
    escape_double_quotes,
    escape_at_symbol,
    escape_special_chars,
)
from llm_provider import LLMConfig, LLMProvider


class TestSpecialCharacterEscaping(unittest.TestCase):
    """Tests for the special character escaping functionality."""

    def test_escape_apostrophes(self):
        """Test that apostrophes are properly escaped."""
        test_cases = [
            # Format: (input, expected output)
            ("No apostrophes here", "No apostrophes here"),
            ("Apostrophe's need escaping", "Apostrophe\\'s need escaping"),
            (
                "Multiple apostrophes' in one's text",
                "Multiple apostrophes\\' in one\\'s text",
            ),
            (
                "Already escaped apostrophe \\'s fine",
                "Already escaped apostrophe \\'s fine",
            ),
            (
                "Mixed escaping: one's and one\\'s",
                "Mixed escaping: one\\'s and one\\'s",
            ),
            ("", ""),  # Empty string
            (None, None),  # None value
            ("Special ' chars ' everywhere '", "Special \\' chars \\' everywhere \\'"),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_apostrophes(input_text)
                self.assertEqual(result, expected)

    def test_escape_percent(self):
        """Test that percent signs are properly escaped."""
        test_cases = [
            # Format: (input, expected output)
            ("No percent signs here", "No percent signs here"),
            ("15% discount", "15\\% discount"),
            ("Multiple % percent % signs", "Multiple \\% percent \\% signs"),
            (
                "Already escaped percent \\% is fine",
                "Already escaped percent \\% is fine",
            ),
            ("Mixed escaping: 10% and 20\\%", "Mixed escaping: 10\\% and 20\\%"),
            ("", ""),  # Empty string
            (None, None),  # None value
            # Format specifiers should not be escaped
            ("String with %s format specifier", "String with %s format specifier"),
            ("Int with %d format specifier", "Int with %d format specifier"),
            (
                "Indexed with %1$s format specifier",
                "Indexed with %1$s format specifier",
            ),
            # Mix of format specifiers and regular percent signs
            ("Mix of %s and % signs", "Mix of %s and \\% signs"),
            ("Pattern 100% %d complete", "Pattern 100\\% %d complete"),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_percent(input_text)
                self.assertEqual(result, expected)

    def test_escape_double_quotes(self):
        """Test that double quotes are properly escaped."""
        test_cases = [
            # Format: (input, expected output)
            ("No double quotes here", "No double quotes here"),
            ('Text with "quotes"', 'Text with \\"quotes\\"'),
            ('Multiple "double" "quotes"', 'Multiple \\"double\\" \\"quotes\\"'),
            (
                'Already escaped \\"quotes\\" are fine',
                'Already escaped \\"quotes\\" are fine',
            ),
            (
                'Mixed escaping: "quote" and \\"quote\\"',
                'Mixed escaping: \\"quote\\" and \\"quote\\"',
            ),
            ("", ""),  # Empty string
            (None, None),  # None value
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_double_quotes(input_text)
                self.assertEqual(result, expected)

    def test_escape_at_symbol(self):
        """Test that at symbols are properly escaped."""
        test_cases = [
            # Format: (input, expected output)
            ("No at symbols here", "No at symbols here"),
            ("Email: user@example.com", "Email: user\\@example.com"),
            ("Multiple @ symbols @ here", "Multiple \\@ symbols \\@ here"),
            ("Already escaped \\@symbol is fine", "Already escaped \\@symbol is fine"),
            (
                "Mixed escaping: @symbol and \\@symbol",
                "Mixed escaping: \\@symbol and \\@symbol",
            ),
            ("", ""),  # Empty string
            (None, None),  # None value
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_at_symbol(input_text)
                self.assertEqual(result, expected)

    def test_escape_special_chars(self):
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
            (
                'Mixed "quote", apostrophe\'s, 25% and user@example.com',
                'Mixed \\"quote\\", apostrophe\\\'s, 25\\% and user\\@example.com',
            ),
            # Test that format specifiers are preserved
            ("Format %s and %d with %1$s escape", "Format %s and %d with %1$s escape"),
            # Test with already escaped characters
            ("Pre-escaped \\'s and \\% and \\@", "Pre-escaped \\'s and \\% and \\@"),
            # Test with complex mix of escaped and unescaped
            (
                "Mixed: \"quote\" and \\\"quote\\\", 'single' and \\'single\\', 10% and \\%",
                "Mixed: \\\"quote\\\" and \\\"quote\\\", \\'single\\' and \\'single\\', 10\\% and \\%",
            ),
            ("", ""),  # Empty string
            (None, None),  # None value
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_special_chars(input_text)
                self.assertEqual(result, expected)

    def test_escape_special_chars_preserves_html_markup(self):
        """Ensure escaping preserves inline HTML markup and attributes."""
        simple_html = 'Visit our <a href="https://test.com">website</a> for more info'
        self.assertEqual(escape_special_chars(simple_html), simple_html)

        complex_html = "Don't miss our <a href='https://test.com'>sale</a> at 50% off"
        expected_complex = (
            'Don\\\'t miss our <a href="https://test.com">sale</a> at 50\\% off'
        )
        self.assertEqual(escape_special_chars(complex_html), expected_complex)


class TestAutoTranslation(unittest.TestCase):
    """Tests for the auto-translation workflow."""

    def setUp(self):
        """Set up test modules with default and target languages."""
        # Create a test module
        self.module = AndroidModule("test_module", "test_id")

        # Default language resources
        self.default_resource = MagicMock()
        self.default_resource.strings = {"hello": "Hello World", "goodbye": "Goodbye"}
        self.default_resource.plurals = {"days": {"one": "%d day", "other": "%d days"}}
        self.default_resource.modified = False

        # Spanish language resources with missing translations
        self.es_resource = MagicMock()
        self.es_resource.strings = {
            "hello": "Hola Mundo"  # "goodbye" is missing
        }
        self.es_resource.plurals = {}  # All plurals missing
        self.es_resource.modified = False

        # Add resources to module
        self.module.add_resource("default", self.default_resource)
        self.module.add_resource("es", self.es_resource)

        # Build modules dict
        self.modules = {"test_id": self.module}

    @patch("AndroidResourceTranslator.translate_plurals_batch_with_llm")
    @patch("AndroidResourceTranslator.translate_strings_batch_with_llm")
    @patch("AndroidResourceTranslator.update_xml_file")
    def test_auto_translate(
        self,
        mock_update_xml,
        mock_translate_strings_batch,
        mock_translate_plurals_batch,
    ):
        """Test complete auto-translation workflow."""
        # Configure mocks
        mock_translate_strings_batch.return_value = {"goodbye": "Adiós"}
        mock_translate_plurals_batch.return_value = {
            "days": {"one": "%d día", "other": "%d días"}
        }

        # Create LLMConfig
        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        # Execute auto translation
        result = auto_translate_resources(
            self.modules,
            llm_config=llm_config,
            project_context="Test project",
        )

        # Verify translation calls
        mock_translate_strings_batch.assert_called_once()
        strings_payload = (
            mock_translate_strings_batch.call_args.kwargs.get("strings_dict")
            or mock_translate_strings_batch.call_args.args[0]
        )
        self.assertEqual(strings_payload, {"goodbye": "Goodbye"})

        mock_translate_plurals_batch.assert_called_once()
        plurals_payload = (
            mock_translate_plurals_batch.call_args.kwargs.get("plurals_dict")
            or mock_translate_plurals_batch.call_args.args[0]
        )
        self.assertEqual(
            plurals_payload, {"days": {"one": "%d day", "other": "%d days"}}
        )

        # Verify file updates
        mock_update_xml.assert_called_once_with(self.es_resource)

        # Verify resource updates
        self.assertEqual(self.es_resource.strings["goodbye"], "Adiós")
        self.assertEqual(
            self.es_resource.plurals["days"], {"one": "%d día", "other": "%d días"}
        )

        # Verify resource was marked modified
        self.assertTrue(self.es_resource.modified)

        # Verify translation log structure
        self.assertIn("test_module", result)
        self.assertIn("es", result["test_module"])
        self.assertIn("strings", result["test_module"]["es"])
        self.assertIn("plurals", result["test_module"]["es"])


if __name__ == "__main__":
    unittest.main()
