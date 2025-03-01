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
    AndroidModule
)


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