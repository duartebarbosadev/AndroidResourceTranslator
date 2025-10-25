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
    escape_double_quotes,
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

    def test_escape_special_chars(self):
        """Test that all special characters are properly escaped in a single pass."""
        test_cases = [
            # Format: (input, expected output)
            ("Normal text", "Normal text"),
            # Test with individual special characters
            ("Text with apostrophe's", "Text with apostrophe\\'s"),
            ('Text with "quotes"', 'Text with \\"quotes\\"'),
            ("Line with newline\nbreak", "Line with newline\\nbreak"),
            ("Already escaped \\n stays literal", "Already escaped \\n stays literal"),
            ("", ""),  # Empty string
            (None, None),  # None value
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_special_chars(input_text)
                self.assertEqual(result, expected)

    def test_escape_special_chars_aligns_backslashes_with_reference(self):
        """Ensure escaped sequences match the reference string."""
        source = "Progress: %d%% complete\\nKeep going!"
        translated = "Progreso: %d%% completo\\\\n¡Sigue!"
        expected = "Progreso: %d%% completo\\n¡Sigue!"
        self.assertEqual(
            escape_special_chars(translated, reference_text=source), expected
        )

        source_regex = "Regex guide:\\nUse \\\\d for digits\\nUse \\\\n for new line"
        translated_regex = "Guía regex:\\\\nUsa \\\\\\\\d para dígitos\\\\nUsa \\\\\\\\n para nueva línea"
        expected_regex = "Guía regex:\\nUsa \\\\d para dígitos\\nUsa \\\\n para nueva línea"
        self.assertEqual(
            escape_special_chars(translated_regex, reference_text=source_regex),
            expected_regex,
        )

    def test_escape_special_chars_preserves_html_markup(self):
        """Ensure escaping preserves inline HTML markup and attributes."""
        simple_html = 'Visit our <a href="https://test.com">website</a> for more info'
        self.assertEqual(escape_special_chars(simple_html), simple_html)

        complex_html = "Don't miss our <a href='https://test.com'>sale</a> at 50% off"
        expected_complex = (
            'Don\\\'t miss our <a href="https://test.com">sale</a> at 50% off'
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

        reference_examples = mock_translate_strings_batch.call_args.kwargs.get(
            "reference_examples"
        )
        self.assertIsNotNone(reference_examples)
        self.assertIn(
            {
                "key": "hello",
                "source": "Hello World",
                "existing_translation": "Hola Mundo",
            },
            reference_examples,
        )

        mock_translate_plurals_batch.assert_called_once()
        plurals_payload = (
            mock_translate_plurals_batch.call_args.kwargs.get("plurals_dict")
            or mock_translate_plurals_batch.call_args.args[0]
        )
        self.assertEqual(
            plurals_payload, {"days": {"one": "%d day", "other": "%d days"}}
        )
        self.assertIsNone(
            mock_translate_plurals_batch.call_args.kwargs.get("reference_examples")
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
