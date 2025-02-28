import unittest
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add the parent directory to the Python path so we can import the module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from AndroidResourceTranslator import (
    find_resource_files, 
    AndroidModule,
    AndroidResourceFile, 
    detect_language_from_path,
    update_xml_file,
)

class TestFindResourceFiles(unittest.TestCase):
    
    def setUp(self):
        # Create a temporary directory for each test
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        # Clean up after each test
        shutil.rmtree(self.temp_dir)
    
    def create_strings_xml(self, path, content="<resources>\n    <string name=\"test\">Test</string>\n</resources>"):
        """Helper method to create a strings.xml file with specified content"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def create_gitignore(self, content):
        """Helper method to create a .gitignore file"""
        with open(os.path.join(self.temp_dir, '.gitignore'), 'w') as f:
            f.write(content)
    
    def test_empty_directory(self):
        """Test that an empty directory returns no modules"""
        modules = find_resource_files(self.temp_dir)
        self.assertEqual(len(modules), 0, "Empty directory should return no modules")
    
    def test_simple_structure(self):
        """Test finding resources in a simple Android structure"""
        # Create module structure: module1/src/main/res/values/strings.xml
        module_path = os.path.join(self.temp_dir, "module1", "src", "main", "res", "values")
        file_path = os.path.join(module_path, "strings.xml")
        self.create_strings_xml(file_path)
        
        modules = find_resource_files(self.temp_dir)
        
        self.assertEqual(len(modules), 1, "Should find one module")
        module_key = list(modules.keys())[0]
        self.assertEqual(modules[module_key].name, "module1", "Module name should be 'module1'")
        self.assertIn("default", modules[module_key].language_resources, "Should contain default language")
    
    def test_multiple_languages(self):
        """Test finding resources for multiple languages"""
        # Create default and es language resources
        base_path = os.path.join(self.temp_dir, "module1", "src", "main", "res")
        self.create_strings_xml(os.path.join(base_path, "values", "strings.xml"))
        self.create_strings_xml(os.path.join(base_path, "values-es", "strings.xml"))
        self.create_strings_xml(os.path.join(base_path, "values-fr", "strings.xml"))
        
        modules = find_resource_files(self.temp_dir)
        
        self.assertEqual(len(modules), 1, "Should find one module")
        module = list(modules.values())[0]
        self.assertEqual(len(module.language_resources), 3, "Should find resources for 3 languages")
        self.assertIn("default", module.language_resources)
        self.assertIn("es", module.language_resources)
        self.assertIn("fr", module.language_resources)
    
    def test_multiple_modules(self):
        """Test finding resources across multiple modules"""
        # Create two modules
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module1", "src", "main", "res", "values", "strings.xml"))
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module2", "src", "main", "res", "values", "strings.xml"))
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module2", "src", "main", "res", "values-es", "strings.xml"))
        
        modules = find_resource_files(self.temp_dir)
        
        self.assertEqual(len(modules), 2, "Should find two modules")
        module_names = {module.name for module in modules.values()}
        self.assertEqual(module_names, {"module1", "module2"})
    
    def test_ignore_folders(self):
        """Test that ignored folders are skipped"""
        # Create a normal module and one in an 'ignore_me' folder
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module1", "src", "main", "res", "values", "strings.xml"))
        self.create_strings_xml(os.path.join(
            self.temp_dir, "ignore_me", "module2", "src", "main", "res", "values", "strings.xml"))
        
        # Find resources with ignored folder
        modules = find_resource_files(self.temp_dir, ignore_folders=["ignore_me"])
        
        self.assertEqual(len(modules), 1, "Should find only one module")
        self.assertEqual(list(modules.values())[0].name, "module1", "Should only find module1")
    
    def test_gitignore_patterns(self):
        """Test that files matching gitignore patterns are skipped"""
        # Create .gitignore file with pattern
        self.create_gitignore("module2/\n*.bak")
        
        # Create a normal module and one that should be ignored
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module1", "src", "main", "res", "values", "strings.xml"))
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module2", "src", "main", "res", "values", "strings.xml"))
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module3.bak", "src", "main", "res", "values", "strings.xml"))
        
        # Find resources - should respect gitignore patterns
        modules = find_resource_files(self.temp_dir)
        
        self.assertEqual(len(modules), 1, "Should find only one module")
        self.assertEqual(list(modules.values())[0].name, "module1", "Should only find module1")
    
    def test_non_values_directories(self):
        """Test that resources outside of values* directories are ignored"""
        # Create a valid resource
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module1", "src", "main", "res", "values", "strings.xml"))
        
        # Create an invalid resource in a drawable directory
        self.create_strings_xml(os.path.join(
            self.temp_dir, "module1", "src", "main", "res", "drawable", "strings.xml"))
        
        modules = find_resource_files(self.temp_dir)
        module = list(modules.values())[0]
        
        # Should only find the resource in the values directory
        self.assertEqual(len(module.language_resources["default"]), 1)
        self.assertEqual(
            module.language_resources["default"][0].path.parent.name, 
            "values", 
            "Should only find resources in values directory"
        )
    
    def test_deeply_nested_structure(self):
        """Test finding resources in a deeply nested structure"""
        # Create a deeper structure than the standard Android structure
        deep_path = os.path.join(
            self.temp_dir, "parent", "subdir", "module1", "src", "main", "res", "values")
        self.create_strings_xml(os.path.join(deep_path, "strings.xml"))
        
        modules = find_resource_files(self.temp_dir)
        
        self.assertEqual(len(modules), 1, "Should find one module")
        self.assertEqual(list(modules.values())[0].name, "module1", "Should correctly identify module name")
    
    # --- Additional Tests from the "I don't like" file ---
    
    def test_detect_language_from_path(self):
        """Test language detection from resource directory names."""
        test_cases = [
            (Path(self.temp_dir) / "module1" / "src" / "main" / "res" / "values" / "strings.xml", "default"),
            (Path(self.temp_dir) / "module1" / "src" / "main" / "res" / "values-es" / "strings.xml", "es"),
            (Path(self.temp_dir) / "module1" / "src" / "main" / "res" / "values-zh-rCN" / "strings.xml", "zh-rCN"),
            (Path(self.temp_dir) / "module1" / "src" / "main" / "res" / "values-b+sr+Latn" / "strings.xml", "b+sr+Latn"),
        ]
        for path, expected_lang in test_cases:
            detected_lang = detect_language_from_path(path)
            self.assertEqual(detected_lang, expected_lang,
                             f"Failed to detect language from {path}")
    
    def test_android_resource_file_parsing(self):
        """Test parsing of a strings.xml file for strings and plurals."""
        xml_path = os.path.join(self.temp_dir, "module1", "src", "main", "res", "values", "strings.xml")
        content = """<resources>
    <string name="app_name">Test App</string>
    <plurals name="num_items">
        <item quantity="one">%d item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>"""
        self.create_strings_xml(xml_path, content=content)
        
        resource_file = AndroidResourceFile(Path(xml_path), "default")
        
        self.assertIn("app_name", resource_file.strings)
        self.assertEqual(resource_file.strings["app_name"], "Test App")
        self.assertIn("num_items", resource_file.plurals)
        self.assertIn("one", resource_file.plurals["num_items"])
        self.assertEqual(resource_file.plurals["num_items"]["one"], "%d item")
    
    def test_update_xml_file_real(self):
        """Test updating an XML file with new string entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = Path(tmp_dir) / "strings.xml"
            original_content = '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="existing">Existing String</string>
</resources>'''
            with open(xml_path, "w", encoding='utf-8') as f:
                f.write(original_content)
            
            res = AndroidResourceFile(xml_path, "en")
            res.strings["existing"] = "Existing String"  # unchanged
            res.strings["new_string"] = "New String"       # new entry
            res.modified = True
            
            update_xml_file(res)
            
            with open(xml_path, encoding='utf-8') as f:
                updated_content = f.read()
            
            self.assertIn('<string name="new_string">New String</string>', updated_content)
            self.assertIn('<string name="existing">Existing String</string>', updated_content)
    
    def test_module_identifiers(self):
        """Test that modules are correctly assigned unique identifiers."""
        module1_path = os.path.join(self.temp_dir, "module1", "src", "main", "res", "values", "strings.xml")
        module2_path = os.path.join(self.temp_dir, "module2", "src", "main", "res", "values", "strings.xml")
        self.create_strings_xml(module1_path)
        self.create_strings_xml(module2_path)
        
        modules = find_resource_files(self.temp_dir)
        identifiers = {module.identifier for module in modules.values()}
        self.assertEqual(len(identifiers), len(modules),
                         "Module identifiers should be unique")
    
    def test_module_resource_counts(self):
        """Test that resource counts in each language do not exceed those in the default language."""
        base_path = os.path.join(self.temp_dir, "module1", "src", "main", "res")
        # Default resource with two strings and one plural
        default_content = """<resources>
    <string name="app_name">Test App</string>
    <string name="welcome">Welcome</string>
    <plurals name="num_items">
        <item quantity="one">%d item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>"""
        self.create_strings_xml(os.path.join(base_path, "values", "strings.xml"), content=default_content)
        
        # Spanish resource with one string and the same plural structure
        spanish_content = """<resources>
    <string name="app_name">Aplicación de prueba</string>
    <plurals name="num_items">
        <item quantity="one">%d artículo</item>
        <item quantity="other">%d artículos</item>
    </plurals>
</resources>"""
        self.create_strings_xml(os.path.join(base_path, "values-es", "strings.xml"), content=spanish_content)
        
        modules = find_resource_files(self.temp_dir)
        module = list(modules.values())[0]
        default_resources = module.language_resources.get("default", [])
        spanish_resources = module.language_resources.get("es", [])
        
        default_strings = sum(len(res.strings) for res in default_resources)
        default_plurals = sum(len(res.plurals) for res in default_resources)
        spanish_strings = sum(len(res.strings) for res in spanish_resources)
        spanish_plurals = sum(len(res.plurals) for res in spanish_resources)
        
        self.assertLessEqual(spanish_strings, default_strings,
                             "Spanish strings should not exceed default strings")
        self.assertLessEqual(spanish_plurals, default_plurals,
                             "Spanish plurals should not exceed default plurals")

if __name__ == '__main__':
    unittest.main()
