import os
import sys
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import logging

#!/usr/bin/env python3
"""
Tests for AndroidResourceTranslator.py
"""
import xml.etree.ElementTree as ET

# Import the main module functions and classes to test
from AndroidResourceTranslator import (
    configure_logging,
    detect_language_from_path,
    AndroidResourceFile,
    AndroidModule,
    find_resource_files,
    update_xml_file,
    translate_text,
    translate_plural_text,
    auto_translate_resources,
    check_missing_translations,
    create_translation_report
)

class TestLanguageDetection(unittest.TestCase):
    """Tests for language detection functionality"""
    
    def test_detect_language_default(self):
        """Test detection of default language"""
        path = Path("fake/path/values/strings.xml")
        self.assertEqual(detect_language_from_path(path), "default")
        
    def test_detect_language_simple(self):
        """Test detection of simple language codes"""
        path = Path("fake/path/values-es/strings.xml")
        self.assertEqual(detect_language_from_path(path), "es")
        
    def test_detect_language_complex(self):
        """Test detection of complex language codes"""
        path = Path("fake/path/values-zh-rCN/strings.xml")
        self.assertEqual(detect_language_from_path(path), "zh-rCN")
        
    def test_detect_language_bcp47(self):
        """Test detection of BCP47 language tags"""
        path = Path("fake/path/values-b+sr+Latn/strings.xml")
        self.assertEqual(detect_language_from_path(path), "b+sr+Latn")


class TestAndroidResourceFile(unittest.TestCase):
    """Tests for AndroidResourceFile class"""
    
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        
        # Create a test XML file
        self.xml_content = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="hello">Hello World</string>
    <string name="app_name">TestApp</string>
    <string name="non_translatable" translatable="false">DONT_TRANSLATE</string>
    <plurals name="plural_test">
        <item quantity="one">%d item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>
"""
        self.xml_path = Path(self.temp_dir.name) / "strings.xml"
        with open(self.xml_path, "w", encoding="utf-8") as f:
            f.write(self.xml_content)
            
    def test_parse_file(self):
        """Test parsing of XML file"""
        resource = AndroidResourceFile(self.xml_path, "en")
        
        # Check basic properties
        self.assertEqual(resource.language, "en")
        self.assertEqual(resource.path, self.xml_path)
        self.assertFalse(resource.modified)
        
        # Check parsed content
        self.assertEqual(len(resource.strings), 2)  # non_translatable should be skipped
        self.assertEqual(resource.strings["hello"], "Hello World")
        self.assertEqual(resource.strings["app_name"], "TestApp")
        self.assertNotIn("non_translatable", resource.strings)
        
        # Check plurals
        self.assertEqual(len(resource.plurals), 1)
        self.assertIn("plural_test", resource.plurals)
        self.assertEqual(resource.plurals["plural_test"]["one"], "%d item")
        self.assertEqual(resource.plurals["plural_test"]["other"], "%d items")
        
    def test_summary(self):
        """Test summary generation"""
        resource = AndroidResourceFile(self.xml_path)
        summary = resource.summary()
        self.assertEqual(summary["strings"], 2)
        self.assertEqual(summary["plurals"], 1)


class TestAndroidModule(unittest.TestCase):
    """Tests for AndroidModule class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.module = AndroidModule("test_module", "test_id")
        self.resource1 = mock.MagicMock(spec=AndroidResourceFile)
        self.resource1.path = Path("fake/path1.xml")
        self.resource1.summary.return_value = {"strings": 5, "plurals": 2}
        
        self.resource2 = mock.MagicMock(spec=AndroidResourceFile)
        self.resource2.path = Path("fake/path2.xml") 
        self.resource2.summary.return_value = {"strings": 3, "plurals": 1}
    
    def test_init(self):
        """Test initialization of AndroidModule"""
        self.assertEqual(self.module.name, "test_module")
        self.assertEqual(self.module.identifier, "test_id")
        self.assertEqual(len(self.module.language_resources), 0)
    
    def test_add_resource(self):
        """Test adding resources to module"""
        self.module.add_resource("en", self.resource1)
        self.module.add_resource("fr", self.resource2)
        self.module.add_resource("en", self.resource2)
        
        self.assertEqual(len(self.module.language_resources), 2)
        self.assertEqual(len(self.module.language_resources["en"]), 2)
        self.assertEqual(len(self.module.language_resources["fr"]), 1)
    
    def test_print_resources(self):
        """Test print_resources method with logging capture"""
        self.module.add_resource("en", self.resource1)
        self.module.add_resource("fr", self.resource2)
        
        # Capture logging output
        with self.assertLogs(level='INFO') as cm:
            self.module.print_resources()
            
        # Verify log output contains expected information
        self.assertTrue(any("test_module" in line for line in cm.output))
        self.assertTrue(any("test_id" in line for line in cm.output))
        self.assertTrue(any("[en]" in line for line in cm.output))
        self.assertTrue(any("[fr]" in line for line in cm.output))


class TestResourceFileDiscovery(unittest.TestCase):
    """Tests for resource file discovery functionality"""
    
    def setUp(self):
        """Create a mock directory structure for testing"""
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.test_root = Path(self.temp_dir.name)
        
        # Create directory structure
        # app/src/main/res/values/strings.xml
        # app/src/main/res/values-es/strings.xml
        # app/src/main/res/values-fr/strings.xml
        # lib/src/main/res/values/strings.xml
        
        # App module
        app_path = self.test_root / "app" / "src" / "main" / "res"
        (app_path / "values").mkdir(parents=True)
        (app_path / "values-es").mkdir()
        (app_path / "values-fr").mkdir()
        
        # Lib module
        lib_path = self.test_root / "lib" / "src" / "main" / "res"
        (lib_path / "values").mkdir(parents=True)
        
        # Create strings.xml files
        self.create_xml_file(app_path / "values" / "strings.xml")
        self.create_xml_file(app_path / "values-es" / "strings.xml")
        self.create_xml_file(app_path / "values-fr" / "strings.xml")
        self.create_xml_file(lib_path / "values" / "strings.xml")
        
        # Create a build directory that should be ignored
        build_path = self.test_root / "app" / "build" / "generated" / "res" / "values"
        build_path.mkdir(parents=True)
        self.create_xml_file(build_path / "strings.xml")
    
    def create_xml_file(self, path):
        """Helper to create a simple strings.xml file"""
        content = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="test">Test</string>
</resources>
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    
    def test_find_resource_files(self):
        """Test finding resource files"""
        modules = find_resource_files(str(self.test_root), ["build"])
        
        # Should find two modules (app and lib)
        self.assertEqual(len(modules), 2)
        
        # Find module keys
        app_key = None
        lib_key = None
        for key, module in modules.items():
            if module.name == "main" and "app" in key:
                app_key = key
            elif module.name == "main" and "lib" in key:
                lib_key = key
        
        self.assertIsNotNone(app_key)
        self.assertIsNotNone(lib_key)
        
        # App module should have 3 language resources (default, es, fr)
        self.assertEqual(len(modules[app_key].language_resources), 3)
        self.assertIn("default", modules[app_key].language_resources)
        self.assertIn("es", modules[app_key].language_resources)
        self.assertIn("fr", modules[app_key].language_resources)
        
        # Lib module should have 1 language resource (default)
        self.assertEqual(len(modules[lib_key].language_resources), 1)
        self.assertIn("default", modules[lib_key].language_resources)
        
    def test_ignore_folders(self):
        """Test that ignore_folders works properly"""
        # Without ignoring build folder, we would find the build/generated resources
        modules_with_build = find_resource_files(str(self.test_root), [])
        
        # With ignoring build folder, we shouldn't find those resources
        modules_without_build = find_resource_files(str(self.test_root), ["build"])
        
        # We should have fewer resources when ignoring build folder
        app_resources_with_build = sum(len(resources) for module in modules_with_build.values()
                                       for resources in module.language_resources.values())
        app_resources_without_build = sum(len(resources) for module in modules_without_build.values()
                                         for resources in module.language_resources.values())
        
        self.assertGreater(app_resources_with_build, app_resources_without_build)


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
    
    def test_translate_plural_text_invalid_response(self, mock_call_openai):
        """Test handling invalid JSON responses"""
        mock_call_openai.return_value = "Invalid JSON response"
        
        source_plural = {"one": "1 day", "other": "%d days"}
        result = translate_plural_text(
            source_plural,
            "es",
            "fake_api_key",
            "gpt-4o-mini",
            "Test project context"
        )
        
        # Should fallback to a simple dict with "other" key
        self.assertIsInstance(result, dict)
        self.assertEqual(result["other"], "Invalid JSON response")


@mock.patch('AndroidResourceTranslator.translate_text')
@mock.patch('AndroidResourceTranslator.translate_plural_text')
@mock.patch('AndroidResourceTranslator.update_xml_file')
class TestAutoTranslation(unittest.TestCase):
    """Test the auto_translate_resources function"""
    
    def setUp(self):
        """Set up test modules for auto translation testing"""
        # Create a test module with default and es languages
        self.module = AndroidModule("test_module", "test_id")
        
        # Default language resources
        self.default_resource = AndroidResourceFile(Path("fake/default.xml"), "default")
        self.default_resource.strings = {
            "hello": "Hello World",
            "goodbye": "Goodbye"
        }
        self.default_resource.plurals = {
            "days": {"one": "%d day", "other": "%d days"}
        }
        
        # Spanish language resources with missing translations
        self.es_resource = AndroidResourceFile(Path("fake/es.xml"), "es")
        self.es_resource.strings = {
            "hello": "Hola Mundo"
            # "goodbye" is missing
        }
        self.es_resource.plurals = {}  # All plurals missing
        
        # Add resources to module
        self.module.add_resource("default", self.default_resource)
        self.module.add_resource("es", self.es_resource)
        
        # Build modules dict
        self.modules = {"test_id": self.module}
    
    def test_auto_translate(self, mock_update_xml, mock_translate_plural, mock_translate_text):
        """Test auto translation of missing resources"""
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


class TestReporting(unittest.TestCase):
    """Tests for reporting functions"""
    
    def setUp(self):
        """Set up test modules for reporting tests"""
        # Create a test module with default and two language resources
        self.module = AndroidModule("test_module", "test_id")
        
        # Default language resources
        self.default_resource = AndroidResourceFile(Path("fake/default.xml"), "default")
        self.default_resource.strings = {
            "hello": "Hello",
            "goodbye": "Goodbye",
            "welcome": "Welcome"
        }
        self.default_resource.plurals = {
            "days": {"one": "%d day", "other": "%d days"}
        }
        
        # Spanish language - missing some translations
        self.es_resource = AndroidResourceFile(Path("fake/es.xml"), "es")
        self.es_resource.strings = {
            "hello": "Hola",
            # "goodbye" and "welcome" missing
        }
        self.es_resource.plurals = {}  # All plurals missing
        
        # French language - complete translations
        self.fr_resource = AndroidResourceFile(Path("fake/fr.xml"), "fr")
        self.fr_resource.strings = {
            "hello": "Bonjour",
            "goodbye": "Au revoir",
            "welcome": "Bienvenue"
        }
        self.fr_resource.plurals = {
            "days": {"one": "%d jour", "other": "%d jours"}
        }
        
        # Add resources to module
        self.module.add_resource("default", self.default_resource)
        self.module.add_resource("es", self.es_resource)
        self.module.add_resource("fr", self.fr_resource)
        
        # Build modules dict
        self.modules = {"test_id": self.module}
        
    def test_check_missing_translations(self):
        """Test check_missing_translations with missing translations"""
        # Capture log output
        with self.assertLogs(level='INFO') as cm:
            check_missing_translations(self.modules)
        
        # Verify log contains info about missing translations for Spanish
        log_output = '\n'.join(cm.output)
        self.assertIn("Missing Translations Report", log_output)
        self.assertIn("test_module", log_output)
        self.assertIn("[es]", log_output)
        self.assertIn("goodbye", log_output)
        self.assertIn("welcome", log_output)
        self.assertIn("days", log_output)
        
        # French should not be reported as missing translations
        self.assertNotIn("[fr]", log_output)
    
    def test_create_translation_report(self):
        """Test creating a translation report"""
        # Create sample translation log
        translation_log = {
            "test_module": {
                "es": {
                    "strings": [
                        {
                            "key": "goodbye",
                            "source": "Goodbye",
                            "translation": "Adiós"
                        },
                        {
                            "key": "welcome",
                            "source": "Welcome",
                            "translation": "Bienvenido"
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
        
        # Check report formatting
        self.assertIn("# Translation Report", report)
        self.assertIn("## Module: test_module", report)
        self.assertIn("### Language: es", report)
        self.assertIn("goodbye", report)
        self.assertIn("Goodbye", report)
        self.assertIn("Adiós", report)
        self.assertIn("welcome", report)
        self.assertIn("Welcome", report)
        self.assertIn("Bienvenido", report)
        self.assertIn("days", report)
        self.assertIn("%d día", report)
        self.assertIn("%d días", report)


class TestUpdateXmlFile(unittest.TestCase):
    """Test XML file updating functionality"""
    
    def setUp(self):
        """Create a temporary XML file for testing"""
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        
        self.xml_path = Path(self.temp_dir.name) / "strings.xml"
        self.xml_content = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="existing">Existing String</string>
    <plurals name="existing_plural">
        <item quantity="one">1 item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>
"""
        with open(self.xml_path, "w", encoding="utf-8") as f:
            f.write(self.xml_content)
    
    def test_update_xml_file(self):
        """Test updating XML file with new strings and plurals"""
        # Create a resource with new strings and plurals
        resource = AndroidResourceFile(self.xml_path)
        resource.strings = {
            "existing": "Existing String",  # Unchanged
            "new_string": "New String"      # New
        }
        resource.plurals = {
            "existing_plural": {
                "one": "1 item",
                "other": "%d items"
            },
            "new_plural": {
                "one": "1 new item",
                "other": "%d new items"
            }
        }
        resource.modified = True
        
        # Update the XML file
        update_xml_file(resource)
        
        # Read the updated file
        with open(self.xml_path, "r", encoding="utf-8") as f:
            updated_content = f.read()
        
        # Check that the original content is preserved
        self.assertIn('<string name="existing">Existing String</string>', updated_content)
        self.assertIn('<item quantity="one">1 item</item>', updated_content)
        self.assertIn('<item quantity="other">%d items</item>', updated_content)
        
        # Check that new elements were added
        self.assertIn('<string name="new_string">New String</string>', updated_content)
        self.assertIn('<plurals name="new_plural">', updated_content)
        self.assertIn('<item quantity="one">1 new item</item>', updated_content)
        self.assertIn('<item quantity="other">%d new items</item>', updated_content)
        
        # Check that XML declaration is properly formatted
        self.assertIn('<?xml version="1.0" encoding="utf-8"?>', updated_content)
        
        # Check that the resource is not marked as modified anymore
        self.assertFalse(resource.modified)


if __name__ == "__main__":
    unittest.main()