import os
import sys
import unittest
from pathlib import Path
import tempfile

# Add parent directory to path so we can import the main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import AndroidResourceFile, update_xml_file

class TestXmlFormatting(unittest.TestCase):
    
    def test_preserve_indentation(self):
        """Test that the original indentation style is preserved"""
        # Create a temp file with specific indentation (2 spaces)
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "strings.xml"
            original_content = """<?xml version="1.0" encoding="utf-8"?>
<resources>
  <string name="existing">Existing String</string>
  <plurals name="existing_plural">
    <item quantity="one">1 item</item>
    <item quantity="other">%d items</item>
  </plurals>
</resources>"""
            with open(xml_path, "w") as f:
                f.write(original_content)
            
            # Create resource with new string
            resource = AndroidResourceFile(xml_path)
            resource.strings["existing"] = "Existing String"
            resource.strings["new_string"] = "New String"
            resource.modified = True
            
            # Update the file
            update_xml_file(resource)
            
            # Read updated file
            with open(xml_path) as f:
                updated_content = f.read()
            
            # Check that original 2-space indentation is preserved
            self.assertIn('  <string name="new_string">New String</string>', updated_content)
    
    def test_preserve_xml_declaration(self):
        """Test that the XML declaration is preserved correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "strings.xml"
            
            # Create a file with a specific XML declaration format
            original_content = """<?xml version='1.0' encoding='utf-8'?>
<resources>
    <string name="test">Test</string>
</resources>"""
            with open(xml_path, "w") as f:
                f.write(original_content)
            
            # Create resource with new string
            resource = AndroidResourceFile(xml_path)
            resource.strings["test"] = "Test"
            resource.strings["new_string"] = "New String"
            resource.modified = True
            
            # Update the file
            update_xml_file(resource)
            
            # Check that the standardized XML declaration is used
            with open(xml_path) as f:
                updated_content = f.read()
            
            # The XML declaration should be standardized to double quotes
            self.assertTrue(updated_content.startswith('<?xml version="1.0" encoding="utf-8"?>'))
    
    def test_handle_empty_file(self):
        """Test handling of an empty or malformed XML file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "strings.xml"
            
            # Create an empty file
            with open(xml_path, "w") as f:
                f.write("")
            
            # Create resource with new strings
            resource = AndroidResourceFile(xml_path)
            # The parse should fail, but update should handle it gracefully
            resource.strings["test"] = "Test"
            resource.modified = True
            
            # This shouldn't raise an exception
            update_xml_file(resource)

if __name__ == "__main__":
    unittest.main()
