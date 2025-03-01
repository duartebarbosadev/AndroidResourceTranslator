#!/usr/bin/env python3
"""
Tests for XML formatting functionality in AndroidResourceTranslator.

This module tests the XML formatting and manipulation functions ensuring that
the original formatting is preserved and XML declaration standards are followed.
"""
import os
import sys
import unittest
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    AndroidResourceFile, 
    update_xml_file, 
    indent_xml
)


class TestXmlFormatting(unittest.TestCase):
    """Tests for XML formatting preservation and manipulation."""
    
    def test_preserve_indentation(self):
        """Test that the original indentation style is preserved."""
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
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(original_content)
            
            # Create resource with new string
            resource = AndroidResourceFile(xml_path)
            resource.strings["existing"] = "Existing String"
            resource.strings["new_string"] = "New String"
            resource.modified = True
            
            # Update the file
            update_xml_file(resource)
            
            # Read updated file
            with open(xml_path, encoding="utf-8") as f:
                updated_content = f.read()
            
            # Check that original 2-space indentation is preserved
            self.assertIn('  <string name="new_string">New String</string>', updated_content)
    
    def test_preserve_xml_declaration(self):
        """Test that the XML declaration is standardized correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "strings.xml"
            
            # Create a file with a non-standard XML declaration format using single quotes
            original_content = """<?xml version='1.0' encoding='utf-8'?>
<resources>
    <string name="test">Test</string>
</resources>"""
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(original_content)
            
            # Create resource with new string
            resource = AndroidResourceFile(xml_path)
            resource.strings["test"] = "Test"
            resource.strings["new_string"] = "New String"
            resource.modified = True
            
            # Update the file
            update_xml_file(resource)
            
            # Check that the standardized XML declaration is used
            with open(xml_path, encoding="utf-8") as f:
                updated_content = f.read()
            
            # The XML declaration should be standardized to double quotes
            self.assertTrue(updated_content.startswith('<?xml version="1.0" encoding="utf-8"?>'))
    
    def test_add_new_plural_resource(self):
        """Test adding a completely new plural resource to an XML file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "strings.xml"
            
            # Create initial file with no plurals
            original_content = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="test">Test</string>
</resources>"""
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(original_content)
            
            # Create resource with new plural
            resource = AndroidResourceFile(xml_path)
            resource.strings["test"] = "Test"
            resource.plurals["new_plural"] = {
                "one": "1 new item",
                "other": "%d new items"
            }
            resource.modified = True
            
            # Update the file
            update_xml_file(resource)
            
            # Verify the new plural was added with proper formatting
            with open(xml_path, encoding="utf-8") as f:
                updated_content = f.read()
            
            self.assertIn('<plurals name="new_plural">', updated_content)
            self.assertIn('<item quantity="one">1 new item</item>', updated_content)
            self.assertIn('<item quantity="other">%d new items</item>', updated_content)
    
    def test_indent_xml_function(self):
        """Test the indent_xml function for proper element indentation."""
        # Create a simple XML structure
        root = ET.Element('resources')
        string_elem = ET.SubElement(root, 'string')
        string_elem.set('name', 'test')
        string_elem.text = 'Test Value'
        
        plurals_elem = ET.SubElement(root, 'plurals')
        plurals_elem.set('name', 'test_plural')
        item1 = ET.SubElement(plurals_elem, 'item')
        item1.set('quantity', 'one')
        item1.text = '1 item'
        item2 = ET.SubElement(plurals_elem, 'item')
        item2.set('quantity', 'other')
        item2.text = '%d items'
        
        # Apply indentation
        indent_xml(root)
        
        # Convert to string
        xml_str = ET.tostring(root, encoding='unicode')
        
        # Verify indentation structure
        self.assertIn('\n    <string', xml_str)
        self.assertIn('\n    <plurals', xml_str)
        self.assertIn('\n        <item', xml_str)


if __name__ == "__main__":
    unittest.main()