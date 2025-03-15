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
from pathlib import Path

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    translate_text,
    translate_plural_text,
    auto_translate_resources,
    AndroidResourceFile,
    AndroidModule,
    escape_apostrophes,
    escape_percent,
    escape_double_quotes,
    escape_at_symbol,
    escape_special_chars
)


class TestSpecialCharacterEscaping(unittest.TestCase):
    """Tests for the special character escaping functionality."""
    
    def test_escape_apostrophes(self):
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
            with self.subTest(input_text=input_text):
                result = escape_percent(input_text)
                self.assertEqual(result, expected)
    
    def test_escape_double_quotes(self):
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
            ("Mixed escaping: @symbol and \\@symbol", "Mixed escaping: \\@symbol and \\@symbol"),
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
            with self.subTest(input_text=input_text):
                result = escape_special_chars(input_text)
                self.assertEqual(result, expected)

    def test_escape_apostrophes_integration_with_translate_text(self):
        """Test that translate_text properly escapes apostrophes in results."""
        with patch('AndroidResourceTranslator.call_openai') as mock_call_openai:
            # Configure mock to return text with apostrophes
            mock_call_openai.return_value = "Si us plau, activa Scrolless a la configuració d'accessibilitat."
            
            # Execute the function
            result = translate_text(
                "Please enable Scrolless in accessibility settings.", 
                target_language="ca", 
                api_key="test_api_key", 
                model="test-model", 
                project_context=""
            )
            
            # Verify results - apostrophes should be escaped
            self.assertEqual(
                result, 
                "Si us plau, activa Scrolless a la configuració d\\'accessibilitat."
            )

    def test_escape_special_chars_integration_with_translate_text(self):
        """Test that translate_text properly escapes all special characters in results."""
        with patch('AndroidResourceTranslator.call_openai') as mock_call_openai:
            # Configure mock to return text with multiple special characters
            mock_call_openai.return_value = "Mensaje con \"comillas\", apóstrofo', 25% y usuario@ejemplo.com"
            
            # Execute the function
            result = translate_text(
                "Message with \"quotes\", apostrophe', 25% and user@example.com", 
                target_language="es", 
                api_key="test_api_key", 
                model="test-model", 
                project_context=""
            )
            
            # Verify results - all special characters should be escaped
            self.assertEqual(
                result, 
                "Mensaje con \\\"comillas\\\", apóstrofo\\', 25\\% y usuario\\@ejemplo.com"
            )

    def test_escape_apostrophes_integration_with_translate_plural_text(self):
        """Test that translate_plural_text properly escapes apostrophes in results."""
        with patch('AndroidResourceTranslator.call_openai') as mock_call_openai:
            # Configure mock with JSON plural response containing apostrophes
            mock_call_openai.return_value = '{"one": "%d element d\'accessibilitat", "other": "%d elements d\'accessibilitat"}'
            
            # Execute the function
            source_plural = {"one": "%d accessibility item", "other": "%d accessibility items"}
            result = translate_plural_text(
                source_plural, 
                target_language="ca", 
                api_key="test_api_key", 
                model="test-model", 
                project_context=""
            )
            
            # Verify results - apostrophes should be escaped in all plural forms
            self.assertEqual(result["one"], "%d element d\\'accessibilitat")
            self.assertEqual(result["other"], "%d elements d\\'accessibilitat")
            
    def test_escape_special_chars_integration_with_translate_plural_text(self):
        """Test that translate_plural_text properly escapes all special characters in results."""
        with patch('AndroidResourceTranslator.call_openai') as mock_call_openai:
            # Configure mock with JSON plural response containing multiple special characters
            mock_call_openai.return_value = """{"one": "%d \\"elemento\\" al 50% en mi@correo", "other": "%d \\"elementos\\" al 50% en mi@correo"}"""
            
            # Execute the function
            source_plural = {"one": "%d \"item\" at 50% in my@email", "other": "%d \"items\" at 50% in my@email"}
            result = translate_plural_text(
                source_plural, 
                target_language="es", 
                api_key="test_api_key", 
                model="test-model", 
                project_context=""
            )
            
            # Verify results - all special characters should be escaped in all plural forms
            self.assertEqual(result["one"], "%d \\\"elemento\\\" al 50\\% en mi\\@correo")
            self.assertEqual(result["other"], "%d \\\"elementos\\\" al 50\\% en mi\\@correo")


@patch('AndroidResourceTranslator.call_openai')
class TestTranslation(unittest.TestCase):
    """Tests for core translation functionality with mocked OpenAI API calls."""
    
    def test_translate_text(self, mock_call_openai):
        """Test translating a simple string with expected parameters."""
        # Configure mock
        mock_call_openai.return_value = "Hola Mundo"
        
        # Execute the function
        result = translate_text(
            "Hello World", 
            target_language="es", 
            api_key="test_api_key", 
            model="test-model", 
            project_context=""
        )
        
        # Verify results
        self.assertEqual(result, "Hola Mundo")
        mock_call_openai.assert_called_once()
        
        # Verify API call parameters
        args = mock_call_openai.call_args
        self.assertIn("Hello World", args[0][0])  # Check prompt contains source text
        self.assertIn("es", args[0][0])  # Check prompt contains target language
        self.assertIn("es", args[0][1])  # Check system message contains target language
        self.assertEqual(args[0][2], "test_api_key")  # Check correct API key
        self.assertEqual(args[0][3], "test-model")  # Check correct model

    def test_translate_text_empty_string(self, mock_call_openai):
        """Test that empty strings are not sent to the API."""
        # Execute the function with empty input
        result = translate_text("", "es", "test_api_key", "test-model", "")
        
        # Verify results
        self.assertEqual(result, "")
        mock_call_openai.assert_not_called()

    def test_translate_text_with_context(self, mock_call_openai):
        """Test translating with project context included."""
        # Configure mock
        mock_call_openai.return_value = "Hola Mundo"
        
        # Execute with project context
        result = translate_text(
            "Hello World", 
            target_language="es", 
            api_key="test_api_key", 
            model="test-model", 
            project_context="A test application"
        )
        
        # Verify results
        self.assertEqual(result, "Hola Mundo")
        
        # Verify project context was included
        args = mock_call_openai.call_args
        self.assertIn("A test application", args[0][1])  # Context in system message

    def test_translate_plural_text(self, mock_call_openai):
        """Test translating a plural resource with proper JSON response."""
        # Configure mock with JSON plural response
        mock_call_openai.return_value = '{"one": "%d elemento", "other": "%d elementos"}'
        
        # Execute the function
        source_plural = {"one": "%d item", "other": "%d items"}
        result = translate_plural_text(
            source_plural, 
            target_language="es", 
            api_key="test_api_key", 
            model="test-model", 
            project_context=""
        )
        
        # Verify results
        self.assertEqual(result["one"], "%d elemento")
        self.assertEqual(result["other"], "%d elementos")
        mock_call_openai.assert_called_once()

    def test_translate_plural_text_error(self, mock_call_openai):
        """Test error handling when OpenAI API fails."""
        # Configure mock to raise exception
        mock_call_openai.side_effect = Exception("API error")
        
        # Execute and verify exception propagation
        source_plural = {"one": "%d item", "other": "%d items"}
        with self.assertRaises(Exception) as context:
            translate_plural_text(
                source_plural, 
                target_language="es", 
                api_key="test_api_key", 
                model="test-model", 
                project_context=""
            )
        
        # Verify exception details
        self.assertIn("API error", str(context.exception))
        mock_call_openai.assert_called_once()


class TestAutoTranslation(unittest.TestCase):
    """Tests for the auto-translation workflow."""
    
    def setUp(self):
        """Set up test modules with default and target languages."""
        # Create a test module
        self.module = AndroidModule("test_module", "test_id")
        
        # Default language resources
        self.default_resource = MagicMock()
        self.default_resource.strings = {
            "hello": "Hello World",
            "goodbye": "Goodbye"
        }
        self.default_resource.plurals = {
            "days": {"one": "%d day", "other": "%d days"}
        }
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

    @patch('AndroidResourceTranslator.translate_text')
    @patch('AndroidResourceTranslator.translate_plural_text')
    @patch('AndroidResourceTranslator.update_xml_file')
    def test_auto_translate(self, mock_update_xml, mock_translate_plural, mock_translate_text):
        """Test complete auto-translation workflow."""
        # Configure mocks
        mock_translate_text.return_value = "Adiós"
        mock_translate_plural.return_value = {"one": "%d día", "other": "%d días"}
        
        # Execute auto translation
        result = auto_translate_resources(
            self.modules,
            openai_api_key="test_api_key",
            openai_model="test-model",
            project_context="Test project",
            validate_translations=False
        )
        
        # Verify translation calls
        mock_translate_text.assert_called_once_with(
            "Goodbye", 
            target_language="es", 
            api_key="test_api_key",
            model="test-model", 
            project_context="Test project"
        )
        
        mock_translate_plural.assert_called_once()
        self.assertEqual(
            mock_translate_plural.call_args[0][0], 
            {"one": "%d day", "other": "%d days"}
        )
        
        # Verify file updates
        mock_update_xml.assert_called_once_with(self.es_resource)
        
        # Verify resource updates
        self.assertEqual(self.es_resource.strings["goodbye"], "Adiós")
        self.assertEqual(
            self.es_resource.plurals["days"], 
            {"one": "%d día", "other": "%d días"}
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