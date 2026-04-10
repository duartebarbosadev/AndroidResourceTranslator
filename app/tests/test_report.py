#!/usr/bin/env python3
"""
Tests for translation reporting functionality in AndroidResourceTranslator.

This module tests the generation of reports for missing translations
and completed translation operations.
"""

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    create_translation_report,
    check_missing_translations,
    AndroidResourceFile,
    AndroidModule,
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
                            "translation": "Hola Mundo",
                        },
                        {"key": "goodbye", "source": "Goodbye", "translation": "Adiós"},
                    ],
                    "plurals": [
                        {
                            "plural_name": "days",
                            "translations": {"one": "%d día", "other": "%d días"},
                        }
                    ],
                },
                "fr": {
                    "strings": [
                        {
                            "key": "hello",
                            "source": "Hello World",
                            "translation": "Bonjour le monde",
                        }
                    ],
                    "plurals": [],
                },
            }
        }

        report = create_translation_report(translation_log)

        # Verify report structure and content
        self.assertIn("# Translation Report", report)
        self.assertIn("## Module: test_module", report)

        # Check Spanish section
        self.assertIn("### Language: Spanish", report)
        self.assertIn("| Key | Source Text | Translated Text |", report)
        self.assertIn("| hello | Hello World | Hola Mundo |", report)
        self.assertIn("| goodbye | Goodbye | Adiós |", report)
        self.assertIn("**days**", report)
        self.assertIn("| one | %d día |", report)
        self.assertIn("| other | %d días |", report)

        # Check French section
        self.assertIn("### Language: French", report)
        self.assertIn("| hello | Hello World | Bonjour le monde |", report)

    def test_create_translation_report_distinguishes_duplicate_module_names(self):
        """Duplicate short names should render as separate module sections."""
        translation_log = {
            "/repo/featureA/common": {
                "_module_name": "common",
                "es": {
                    "strings": [
                        {
                            "key": "hello",
                            "source": "Hello",
                            "translation": "Hola",
                        }
                    ],
                    "plurals": [],
                },
            },
            "/repo/featureB/common": {
                "_module_name": "common",
                "fr": {
                    "strings": [
                        {
                            "key": "hello",
                            "source": "Hello",
                            "translation": "Bonjour",
                        }
                    ],
                    "plurals": [],
                },
            },
        }

        report = create_translation_report(translation_log)

        self.assertIn("## Module: common (/repo/featureA/common)", report)
        self.assertIn("## Module: common (/repo/featureB/common)", report)
        self.assertIn("| hello | Hello | Hola |", report)
        self.assertIn("| hello | Hello | Bonjour |", report)

    @patch("AndroidResourceTranslator.AndroidResourceFile.parse_file")
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
        with self.assertLogs(level="INFO") as cm:
            missing_report = check_missing_translations(modules)

        # Verify log output
        log_output = "\n".join(cm.output)
        self.assertIn("All translations are complete", log_output)

        # Verify empty missing report
        self.assertEqual(missing_report, {})

    @patch("AndroidResourceTranslator.AndroidResourceFile.parse_file")
    def test_check_missing_translations_with_missing(self, mock_parse_file):
        """Test identifying missing translations in modules."""
        # Create test modules with missing translations
        modules = {}
        module = AndroidModule("test_module")

        # Default resource with all strings and plurals
        default_res = AndroidResourceFile(Path("dummy/path"), "default")
        default_res.strings = {
            "hello": "Hello",
            "welcome": "Welcome",
            "cancel": "Cancel",
        }
        default_res.plurals = {
            "days": {"one": "%d day", "other": "%d days"},
            "items": {"one": "%d item", "other": "%d items"},
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
        with self.assertLogs(level="INFO") as cm:
            missing_report = check_missing_translations(modules)

        # Check log output
        log_output = "\n".join(cm.output)
        self.assertIn("has missing translations", log_output)
        self.assertIn("welcome", log_output)
        self.assertIn("cancel", log_output)
        self.assertIn("items", log_output)

        # Verify missing report structure
        self.assertIn("test_module", missing_report)
        self.assertIn("es", missing_report["test_module"])
        self.assertEqual(
            sorted(missing_report["test_module"]["es"]["strings"]),
            ["cancel", "welcome"],
        )
        self.assertIn("items", missing_report["test_module"]["es"]["plurals"])

    @patch("AndroidResourceTranslator.AndroidResourceFile.parse_file")
    def test_check_missing_translations_keeps_duplicate_module_names_separate(
        self, mock_parse_file
    ):
        """Missing-report state should be keyed by unique module identifier."""
        modules = {}

        module_a = AndroidModule("common", identifier="/repo/featureA/common")
        default_a = AndroidResourceFile(Path("dummy/path"), "default")
        default_a.strings = {"hello": "Hello"}
        default_a.plurals = {}
        es_a = AndroidResourceFile(Path("dummy/path"), "es")
        es_a.strings = {}
        es_a.plurals = {}
        module_a.language_resources["default"] = [default_a]
        module_a.language_resources["es"] = [es_a]
        modules[module_a.identifier] = module_a

        module_b = AndroidModule("common", identifier="/repo/featureB/common")
        default_b = AndroidResourceFile(Path("dummy/path"), "default")
        default_b.strings = {"bye": "Goodbye"}
        default_b.plurals = {}
        fr_b = AndroidResourceFile(Path("dummy/path"), "fr")
        fr_b.strings = {}
        fr_b.plurals = {}
        module_b.language_resources["default"] = [default_b]
        module_b.language_resources["fr"] = [fr_b]
        modules[module_b.identifier] = module_b

        missing_report = check_missing_translations(modules)

        self.assertIn("/repo/featureA/common", missing_report)
        self.assertIn("/repo/featureB/common", missing_report)
        self.assertEqual(missing_report["/repo/featureA/common"]["_module_name"], "common")
        self.assertEqual(missing_report["/repo/featureB/common"]["_module_name"], "common")
        self.assertEqual(
            missing_report["/repo/featureA/common"]["es"]["strings"], ["hello"]
        )
        self.assertEqual(
            missing_report["/repo/featureB/common"]["fr"]["strings"], ["bye"]
        )


if __name__ == "__main__":
    unittest.main()
