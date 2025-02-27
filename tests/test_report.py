import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import logging

# Add parent directory to path so we can import the main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    create_translation_report,
    check_missing_translations,
    AndroidResourceFile,
    AndroidModule
)

class TestReporting(unittest.TestCase):
    def test_create_translation_report(self):
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
                        }
                    ],
                    "plurals": [
                        {
                            "plural_name": "days",
                            "translations": {"one": "%d día", "other": "%d días"}
                        }
                    ]
                }
            }
        }
        
        report = create_translation_report(translation_log)
        
        # Verify report content
        self.assertIn("# Translation Report", report)
        self.assertIn("## Module: test_module", report)
        self.assertIn("### Language: es", report)
        self.assertIn("hello", report)
        self.assertIn("Hello World", report)
        self.assertIn("Hola Mundo", report)
        self.assertIn("days", report)
        self.assertIn("%d día", report)
    
    def test_check_missing_translations(self):
        """Test identifying missing translations in modules."""
        # Create test modules with missing translations
        modules = {}
        module = AndroidModule("test_module")
        
        # Default resource with all strings and plurals
        default_res = AndroidResourceFile(Path("dummy/path"), "default")
        default_res.strings = {"hello": "Hello", "welcome": "Welcome"}
        default_res.plurals = {"days": {"one": "%d day", "other": "%d days"}}
        
        # Spanish resource with missing translations
        es_res = AndroidResourceFile(Path("dummy/path"), "es")
        es_res.strings = {"hello": "Hola"}  # missing "welcome"
        es_res.plurals = {}  # missing all plurals
        
        # Add resources to module
        module.language_resources["default"] = [default_res]
        module.language_resources["es"] = [es_res]
        modules["test_module"] = module
        
        # Run with logging capture
        with self.assertLogs(level='INFO') as cm:
            check_missing_translations(modules)
        
        # Check log output
        log_output = '\n'.join(cm.output)
        self.assertIn("welcome", log_output)
        self.assertIn("days", log_output)

if __name__ == "__main__":
    unittest.main()