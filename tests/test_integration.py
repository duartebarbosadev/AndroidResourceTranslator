import os
import sys
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import logging
from unittest.mock import patch

"""
Integration tests for AndroidResourceTranslator focusing on how components work together.
Tests how different modules interact and perform end-to-end functionality.
"""
import xml.etree.ElementTree as ET

# Import the main module functions and classes to test
from AndroidResourceTranslator import (
    configure_logging,
    AndroidModule,
    translate_text,
    translate_plural_text,
    auto_translate_resources,
    create_translation_report
)
@mock.patch('AndroidResourceTranslator.call_openai')
class TestTranslation(unittest.TestCase):
    """Tests for translation functionality with mocked OpenAI calls"""
    
    def test_translate_text(self, mock_call_openai):
        """Test translating a simple string"""
        mock_call_openai.return_value = "Hola Mundo"
        
        result = translate_text(
            "Hello World",
            "es",
            "fake_api_key",
            "gpt-4o-mini",
            "Test project context"
        )
        
        self.assertEqual(result, "Hola Mundo")
        mock_call_openai.assert_called_once()
        
        # Verify that API was called with correct parameters
        args = mock_call_openai.call_args
        self.assertIn("Hello World", args[0][0])  # Check prompt contains source text
        self.assertIn("es", args[0][0])  # Check prompt contains target language
        self.assertIn("es", args[0][1])  # Check system message contains target language
        self.assertIn("Test project context", args[0][1])  # Check system message contains project context
        self.assertEqual(args[0][2], "fake_api_key")  # Check correct API key
        self.assertEqual(args[0][3], "gpt-4o-mini")  # Check correct model
    
    def test_translate_plural_text(self, mock_call_openai):
        """Test translating plural text"""
        mock_call_openai.return_value = '{"one": "1 día", "other": "%d días"}'
        
        source_plural = {"one": "1 day", "other": "%d days"}
        result = translate_plural_text(
            source_plural,
            "es",
            "fake_api_key",
            "gpt-4o-mini",
            "Test project context"
        )
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["one"], "1 día")
        self.assertEqual(result["other"], "%d días")
        mock_call_openai.assert_called_once()

@mock.patch('AndroidResourceTranslator.translate_text')
@mock.patch('AndroidResourceTranslator.translate_plural_text')
@mock.patch('AndroidResourceTranslator.update_xml_file')
class TestAutoTranslation(unittest.TestCase):
    """Test the auto_translate_resources function - integration test not covered elsewhere"""
    
    def setUp(self):
        """Set up test modules for auto translation testing"""
        # Create a test module with default and es languages
        self.module = AndroidModule("test_module", "test_id")
        
        # Default language resources
        self.default_resource = mock.MagicMock()
        self.default_resource.strings = {
            "hello": "Hello World",
            "goodbye": "Goodbye"
        }
        self.default_resource.plurals = {
            "days": {"one": "%d day", "other": "%d days"}
        }
        self.default_resource.modified = False
        
        # Spanish language resources with missing translations
        self.es_resource = mock.MagicMock()
        self.es_resource.strings = {
            "hello": "Hola Mundo"
            # "goodbye" is missing
        }
        self.es_resource.plurals = {}  # All plurals missing
        self.es_resource.modified = False
        
        # Add resources to module
        self.module.add_resource("default", self.default_resource)
        self.module.add_resource("es", self.es_resource)
        
        # Build modules dict
        self.modules = {"test_id": self.module}
    
    def test_auto_translate(self, mock_update_xml, mock_translate_plural, mock_translate_text):
        """Test auto translation of missing resources - an important integration test"""
        # Set up mocks
        mock_translate_text.return_value = "Adiós"
        mock_translate_plural.return_value = {"one": "%d día", "other": "%d días"}
        
        result = auto_translate_resources(
            self.modules,
            "fake_api_key",
            "gpt-4o-mini",
            "Test project",
            False  # no validation
        )
        
        # Check that translate_text was called for the missing string
        mock_translate_text.assert_called_once_with(
            "Goodbye", target_language="es", api_key="fake_api_key",
            model="gpt-4o-mini", project_context="Test project"
        )
        
        # Check that translate_plural_text was called for the missing plural
        mock_translate_plural.assert_called_once()
        self.assertEqual(mock_translate_plural.call_args[0][0], {"one": "%d day", "other": "%d days"})
        
        # Check that update_xml_file was called to save changes
        mock_update_xml.assert_called_once_with(self.es_resource)
        
        # Check that the resource was updated with translations
        self.assertEqual(self.es_resource.strings["goodbye"], "Adiós")
        self.assertEqual(self.es_resource.plurals["days"], {"one": "%d día", "other": "%d días"})
        
        # Check that the resource was marked as modified
        self.assertTrue(self.es_resource.modified)
        
        # Check the translation log contains the expected entries
        self.assertIn("test_module", result)
        self.assertIn("es", result["test_module"])
        self.assertIn("strings", result["test_module"]["es"])
        self.assertIn("plurals", result["test_module"]["es"])
        self.assertEqual(len(result["test_module"]["es"]["strings"]), 1)
        self.assertEqual(len(result["test_module"]["es"]["plurals"]), 1)


class TestTranslationReport(unittest.TestCase):
    """Tests for the translation report generation - not covered in test_report.py"""
    
    def test_create_translation_report_empty(self):
        """Test creating a translation report with no translations"""
        report = create_translation_report({})
        self.assertIn("# Translation Report", report)
        self.assertIn("No translations were performed", report)
        
    def test_create_translation_report_full(self):
        """Test creating a comprehensive translation report"""
        # Create a comprehensive translation log
        translation_log = {
            "module1": {
                "es": {
                    "strings": [
                        {"key": "hello", "source": "Hello", "translation": "Hola"},
                        {"key": "goodbye", "source": "Goodbye", "translation": "Adiós"}
                    ],
                    "plurals": [
                        {
                            "plural_name": "days", 
                            "translations": {"one": "1 día", "other": "%d días"}
                        }
                    ]
                },
                "fr": {
                    "strings": [
                        {"key": "hello", "source": "Hello", "translation": "Bonjour"}
                    ],
                    "plurals": []
                }
            },
            "module2": {
                "de": {
                    "strings": [],
                    "plurals": [
                        {
                            "plural_name": "items", 
                            "translations": {"one": "1 Element", "other": "%d Elemente"}
                        }
                    ]
                }
            }
        }
        
        report = create_translation_report(translation_log)
        
        # Check for main sections
        self.assertIn("# Translation Report", report)
        self.assertIn("## Module: module1", report)
        self.assertIn("## Module: module2", report)
        
        # Check for language sections
        self.assertIn("### Language: es", report)
        self.assertIn("### Language: fr", report)
        self.assertIn("### Language: de", report)
        
        # Check for strings table in es language
        self.assertIn("| Key | Source Text | Translated Text |", report)
        self.assertIn("| hello | Hello | Hola |", report)
        self.assertIn("| goodbye | Goodbye | Adiós |", report)
        
        # Check for plurals table in es language
        self.assertIn("#### Plural Resources", report)
        self.assertIn("**days**", report)
        self.assertIn("| one | 1 día |", report)
        self.assertIn("| other | %d días |", report)
        
        # Check for strings in fr language
        self.assertIn("| hello | Hello | Bonjour |", report)
        
        # Check for plurals in de language
        self.assertIn("**items**", report)
        self.assertIn("| one | 1 Element |", report)
        self.assertIn("| other | %d Elemente |", report)


if __name__ == "__main__":
    unittest.main()
