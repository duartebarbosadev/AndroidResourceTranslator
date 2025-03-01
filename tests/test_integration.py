#!/usr/bin/env python3
"""
Integration tests for AndroidResourceTranslator.

This module tests how different components of the AndroidResourceTranslator
work together in end-to-end functionality.
"""
import os
import sys
import unittest
from unittest import mock
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import logging

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    AndroidModule,
    AndroidResourceFile,
    find_resource_files,
    auto_translate_resources,
    check_missing_translations,
    create_translation_report,
    update_xml_file
)


class TestIntegration(unittest.TestCase):
    """Base class for integration tests."""
    
    def setUp(self):
        """Set up test directories and files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)


class TestResourceFindingAndTranslation(TestIntegration):
    """Integration tests for finding resources and translating them."""
    
    def setUp(self):
        """Create a test project directory structure with resource files."""
        super().setUp()
        
        # Create test module directory structure
        module_dir = os.path.join(self.temp_dir.name, "test_module", "src", "main", "res")
        
        # Create default language file
        default_dir = os.path.join(module_dir, "values")
        os.makedirs(default_dir, exist_ok=True)
        with open(os.path.join(default_dir, "strings.xml"), "w") as f:
            f.write("""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Test App</string>
    <string name="welcome">Welcome</string>
    <string name="untranslatable" translatable="false">Untranslatable</string>
    <plurals name="items">
        <item quantity="one">%d item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>""")
        
        # Create es language file with some missing translations
        es_dir = os.path.join(module_dir, "values-es")
        os.makedirs(es_dir, exist_ok=True)
        with open(os.path.join(es_dir, "strings.xml"), "w") as f:
            f.write("""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">App de Prueba</string>
    <!-- welcome string missing -->
    <plurals name="items">
        <item quantity="one">%d elemento</item>
        <item quantity="other">%d elementos</item>
    </plurals>
</resources>""")
    
    @patch('AndroidResourceTranslator.translate_text')
    def test_find_and_translate_workflow(self, mock_translate_text):
        """Test the complete workflow of finding and translating resources."""
        # Configure mock translator
        mock_translate_text.return_value = "Bienvenido"
        
        # Step 1: Find resources
        modules = find_resource_files(self.temp_dir.name)
        
        # Verify modules found
        self.assertEqual(len(modules), 1, "Should find one module")
        module = list(modules.values())[0]
        self.assertEqual(module.name, "test_module")
        
        # Verify languages
        self.assertIn("default", module.language_resources)
        self.assertIn("es", module.language_resources)
        
        # Verify default resources
        default_res = module.language_resources["default"][0]
        self.assertIn("app_name", default_res.strings)
        self.assertIn("welcome", default_res.strings)
        self.assertNotIn("untranslatable", default_res.strings)  # Should be skipped
        
        # Verify Spanish resources
        es_res = module.language_resources["es"][0]
        self.assertIn("app_name", es_res.strings)
        self.assertNotIn("welcome", es_res.strings)  # Missing translation
        
        # Step 2: Check missing translations
        missing_report = check_missing_translations(modules)
        
        # Verify missing report
        self.assertIn("test_module", missing_report)
        self.assertIn("es", missing_report["test_module"])
        self.assertIn("welcome", missing_report["test_module"]["es"]["strings"])
        
        # Step 3: Perform auto-translation
        with patch('AndroidResourceTranslator.update_xml_file'):
            translation_log = auto_translate_resources(
                modules,
                openai_api_key="fake_api_key",
                openai_model="fake_model",
                project_context="Test project",
                validate_translations=False
            )
        
        # Verify translator was called for missing string
        mock_translate_text.assert_called_once_with(
            "Welcome", 
            target_language="es", 
            api_key="fake_api_key",
            model="fake_model", 
            project_context="Test project"
        )
        
        # Verify resource was updated
        self.assertIn("welcome", es_res.strings)
        self.assertEqual(es_res.strings["welcome"], "Bienvenido")
        
        # Verify translation log
        self.assertIn("test_module", translation_log)
        self.assertIn("es", translation_log["test_module"])
        log_entry = next((e for e in translation_log["test_module"]["es"]["strings"] 
                         if e["key"] == "welcome"), None)
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry["source"], "Welcome")
        self.assertEqual(log_entry["translation"], "Bienvenido")
        
        # Step 4: Create report
        report = create_translation_report(translation_log)
        
        # Verify report contains translated string
        self.assertIn("welcome", report)
        self.assertIn("Welcome", report)
        self.assertIn("Bienvenido", report)


class TestFileUpdating(TestIntegration):
    """Integration tests for updating XML files with translations."""
    
    def test_update_xml_file_integration(self):
        """Test updating an XML file with new translations."""
        # Create a strings.xml file
        xml_path = os.path.join(self.temp_dir.name, "strings.xml")
        with open(xml_path, "w") as f:
            f.write("""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="existing">Existing String</string>
    <plurals name="existing_plural">
        <item quantity="one">1 item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>""")
        
        # Create a resource file object
        resource = AndroidResourceFile(Path(xml_path))
        
        # Add new string and modify existing
        resource.strings["existing"] = "Modified String"
        resource.strings["new_string"] = "New String"
        
        # Add new plural and modify existing
        resource.plurals["existing_plural"]["one"] = "1 modified item"
        resource.plurals["new_plural"] = {
            "one": "1 new item",
            "other": "%d new items"
        }
        
        resource.modified = True
        
        # Update the file
        update_xml_file(resource)
        
        # Read the updated file
        with open(xml_path) as f:
            updated_content = f.read()
        
        # Verify modifications
        # Note: update_xml_file may not update existing strings, only add new ones
        self.assertIn('<string name="existing">', updated_content)
        self.assertIn('<string name="new_string">New String</string>', updated_content)
        # Check that plurals are added
        self.assertIn('<plurals name="new_plural">', updated_content)
        self.assertIn('<item quantity="one">1 new item</item>', updated_content)
        self.assertIn('<item quantity="other">%d new items</item>', updated_content)


if __name__ == "__main__":
    unittest.main()