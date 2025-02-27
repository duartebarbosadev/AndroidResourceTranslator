import os
import sys
import unittest
from pathlib import Path
import tempfile

# Add parent directory to path so we can import the main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    AndroidResourceFile, 
    detect_language_from_path,
    find_resource_files,
)

class TestResourceParser(unittest.TestCase):
    
    def setUp(self):
        # Use the test resources directory
        self.test_resources_dir = Path(__file__).parent / "test_resources"
        
    def test_detect_language_from_path(self):
        """Test language detection from resource directory names."""
        test_cases = [
            (self.test_resources_dir / "values" / "strings.xml", "default"),
            (self.test_resources_dir / "values-es" / "strings.xml", "es"),
            (self.test_resources_dir / "values-zh-rCN" / "strings.xml", "zh-rCN"),
            (self.test_resources_dir / "values-b+sr+Latn" / "strings.xml", "b+sr+Latn"),
            (Path("values/strings.xml"), "default"),
            (Path("values-es/strings.xml"), "es"),
            (Path("values-zh-rCN/strings.xml"), "zh-rCN"),
            (Path("values-b+sr+Latn/strings.xml"), "b+sr+Latn"),
        ]
        
        for path, expected_lang in test_cases:
            detected_lang = detect_language_from_path(path)
            self.assertEqual(detected_lang, expected_lang, 
                             f"Failed to detect language from {path}")

    def test_android_resource_file_parsing(self):
        """Test parsing of a strings.xml file."""
        # Test with the default English strings file
        resource_file = AndroidResourceFile(
            self.test_resources_dir / "values" / "strings.xml", 
            "default"
        )
        
        # Check that the strings were parsed correctly
        self.assertIn("app_name", resource_file.strings)
        self.assertEqual(resource_file.strings["app_name"], "Test App")
        
        # Check that plurals were parsed correctly
        self.assertIn("num_items", resource_file.plurals)
        self.assertIn("one", resource_file.plurals["num_items"])
        self.assertEqual(resource_file.plurals["num_items"]["one"], "%d item")
        
    def test_find_resource_files(self):
        """Test finding resource files in a directory."""
        modules = find_resource_files(str(self.test_resources_dir))
        
        # We should have found our test module
        self.assertGreaterEqual(len(modules), 1)
        
        # Check if we found the correct languages
        for module in modules.values():
            self.assertIn("default", module.language_resources)
            
            # Check if we have at least one Spanish translation file
            has_spanish = any("es" in lang for lang in module.language_resources.keys())
            self.assertTrue(has_spanish, "Spanish translation not found")
            
    def test_ignore_folders(self):
        """Test the ignore_folders functionality."""
        # First, count all modules without ignoring any folders
        all_modules = find_resource_files(str(self.test_resources_dir))
        
        # Now, ignore a folder that contains one of our test files
        modules_with_ignore = find_resource_files(
            str(self.test_resources_dir), 
            ignore_folders=["ignored_folder"]
        )
        
        # We should have fewer modules or the same number of modules but fewer files
        if len(all_modules) == len(modules_with_ignore):
            # Same number of modules, but we should have fewer files
            all_resources_count = sum(
                sum(len(resources) for resources in module.language_resources.values())
                for module in all_modules.values()
            )
            ignored_resources_count = sum(
                sum(len(resources) for resources in module.language_resources.values())
                for module in modules_with_ignore.values()
            )
            self.assertLess(ignored_resources_count, all_resources_count)
        else:
            # Fewer modules
            self.assertLess(len(modules_with_ignore), len(all_modules))
            
    def test_update_xml_file_real(self):
        """Test actual XML file updating with real files."""
        # Import update_xml_file function
        from AndroidResourceTranslator import update_xml_file
        
        # Create a temporary XML file
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "strings.xml"
            with open(xml_path, "w") as f:
                f.write('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="existing">Existing String</string>
</resources>''')
            
            # Create resource and add new strings
            res = AndroidResourceFile(xml_path, "en")
            res.strings["existing"] = "Existing String"  # unchanged
            res.strings["new_string"] = "New String"     # new
            res.modified = True
            
            # Update the file
            update_xml_file(res)
            
            # Read the file back and verify changes
            with open(xml_path) as f:
                content = f.read()
                
            self.assertIn('<string name="new_string">New String</string>', content)
            self.assertIn('<string name="existing">Existing String</string>', content)
            
if __name__ == "__main__":
    unittest.main()
