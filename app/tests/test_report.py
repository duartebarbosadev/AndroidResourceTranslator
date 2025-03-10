#!/usr/bin/env python3
"""
Tests for translation reporting functionality in AndroidResourceTranslator.

This module tests the generation of reports for missing translations
and completed translation operations.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import logging

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    create_translation_report,
    check_missing_translations,
    AndroidResourceFile,
    AndroidModule
)


class TestReporting(unittest.TestCase):
    """Tests for translation reporting functionality."""
    
    def test_create_translation_report_empty(self):
        """Test creating an empty translation report."""
        report = create_translation_report({})
        
        # Verify report contains header and empty notification
        self.assertIn("# Translation Report", report)
        self.assertIn("No translations were performed", report)
    
    def test_create_translation_report_with_data(self):
        """Test generating Markdown report from translation log."""
        # Sample translation log that would be returned from auto_translate_resources
        translation_log = {
            "test_module": {
                "es": {
                    "strings": [
                        {
                            "key": "hello",
                            "source": "Hello World",
                            "translation": "Hola Mundo"
                        },
                        {
                            "key": "goodbye",
                            "source": "Goodbye",
                            "translation": "Adiós"
                        }
                    ],
                    "plurals": [
                        {
                            "plural_name": "days",
                            "translations": {"one": "%d día", "other": "%d días"}
                        }
                    ]
                },
                "fr": {
                    "strings": [
                        {
                            "key": "hello",
                            "source": "Hello World",
                            "translation": "Bonjour le monde"
                        }
                    ],
                    "plurals": []
                }
            }
        }
        
        report = create_translation_report(translation_log)
        
        # Verify report structure and content
        self.assertIn("# Translation Report", report)
        self.assertIn("## Module: test_module", report)
        
        # Check Spanish section
        self.assertIn("### Language: es", report)
        self.assertIn("| Key | Source Text | Translated Text |", report)
        self.assertIn("| hello | Hello World | Hola Mundo |", report)
        self.assertIn("| goodbye | Goodbye | Adiós |", report)
        self.assertIn("**days**", report)
        self.assertIn("| one | %d día |", report)
        self.assertIn("| other | %d días |", report)
        
        # Check French section
        self.assertIn("### Language: fr", report)
        self.assertIn("| hello | Hello World | Bonjour le monde |", report)
    
    @patch('AndroidResourceTranslator.AndroidResourceFile.parse_file')
    def test_check_missing_translations_none_missing(self, mock_parse_file):
        """Test checking for missing translations when all are present."""
        # Create test modules with complete translations
        modules = {}
        module = AndroidModule("test_module")
        
        # Default resource with strings and plurals
        default_res = AndroidResourceFile(Path("dummy/path"), "default")
        default_res.strings = {"hello": "Hello", "goodbye": "Goodbye"}
        default_res.plurals = {"days": {"one": "%d day", "other": "%d days"}}
        
        # Spanish resource with complete translations
        es_res = AndroidResourceFile(Path("dummy/path"), "es")
        es_res.strings = {"hello": "Hola", "goodbye": "Adiós"}
        es_res.plurals = {"days": {"one": "%d día", "other": "%d días"}}
        
        # Add resources to module
        module.language_resources["default"] = [default_res]
        module.language_resources["es"] = [es_res]
        modules["test_module"] = module
        
        # Run with logging capture
        with self.assertLogs(level='INFO') as cm:
            missing_report = check_missing_translations(modules)
        
        # Verify log output
        log_output = '\n'.join(cm.output)
        self.assertIn("All translations are complete", log_output)
        
        # Verify empty missing report
        self.assertEqual(missing_report, {})
    
    @patch('AndroidResourceTranslator.AndroidResourceFile.parse_file')    
    def test_check_missing_translations_with_missing(self, mock_parse_file):
        """Test identifying missing translations in modules."""
        # Create test modules with missing translations
        modules = {}
        module = AndroidModule("test_module")
        
        # Default resource with all strings and plurals
        default_res = AndroidResourceFile(Path("dummy/path"), "default")
        default_res.strings = {"hello": "Hello", "welcome": "Welcome", "cancel": "Cancel"}
        default_res.plurals = {
            "days": {"one": "%d day", "other": "%d days"},
            "items": {"one": "%d item", "other": "%d items"}
        }
        
        # Spanish resource with missing translations
        es_res = AndroidResourceFile(Path("dummy/path"), "es")
        es_res.strings = {"hello": "Hola"}  # missing "welcome" and "cancel"
        es_res.plurals = {
            "days": {"one": "%d día", "other": "%d días"}
        }  # missing "items" plural
        
        # Add resources to module
        module.language_resources["default"] = [default_res]
        module.language_resources["es"] = [es_res]
        modules["test_module"] = module
        
        # Run with logging capture
        with self.assertLogs(level='INFO') as cm:
            missing_report = check_missing_translations(modules)
        
        # Check log output
        log_output = '\n'.join(cm.output)
        self.assertIn("has missing translations", log_output)
        self.assertIn("welcome", log_output)
        self.assertIn("cancel", log_output)
        self.assertIn("items", log_output)
        
        # Verify missing report structure
        self.assertIn("test_module", missing_report)
        self.assertIn("es", missing_report["test_module"])
        self.assertEqual(sorted(missing_report["test_module"]["es"]["strings"]), ["cancel", "welcome"])
        self.assertIn("items", missing_report["test_module"]["es"]["plurals"])


if __name__ == "__main__":
    unittest.main()