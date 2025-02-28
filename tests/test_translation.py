import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add parent directory to path so we can import the main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    translate_text,
    translate_plural_text,
    auto_translate_resources,
    AndroidResourceFile,
    AndroidModule
)

class TestTranslation(unittest.TestCase):
    
    @patch('AndroidResourceTranslator.call_openai')
    def test_translate_text(self, mock_call_openai):
        mock_call_openai.return_value = "Hola Mundo"
        result = translate_text("Hello World", "es", "test_api_key", "test-model", "")
        self.assertEqual(result, "Hola Mundo")
        mock_call_openai.assert_called_once()

    @patch('AndroidResourceTranslator.call_openai')
    def test_translate_text_empty_string(self, mock_call_openai):
        mock_call_openai.return_value = ""
        result = translate_text("", "es", "test_api_key", "test-model", "")
        self.assertEqual(result, "")
        mock_call_openai.assert_not_called()

    @patch('AndroidResourceTranslator.call_openai')
    def test_translate_plural_text(self, mock_call_openai):
        mock_call_openai.return_value = '{"one": "%d elemento", "other": "%d elementos"}'
        source_plural = {"one": "%d item", "other": "%d items"}
        result = translate_plural_text(source_plural, "es", "test_api_key", "test-model", "")
        self.assertEqual(result["one"], "%d elemento")
        self.assertEqual(result["other"], "%d elementos")
        mock_call_openai.assert_called_once()

    @patch('AndroidResourceTranslator.call_openai')
    def test_translate_plural_text_empty_dict(self, mock_call_openai):
        mock_call_openai.return_value = "{}"
        result = translate_plural_text({}, "es", "test_api_key", "test-model", "")
        self.assertEqual(result, {})
        mock_call_openai.assert_called_once()

    @patch('AndroidResourceTranslator.call_openai')
    def test_translate_plural_text_error(self, mock_call_openai):
        mock_call_openai.side_effect = Exception("API error")
        source_plural = {"one": "%d item", "other": "%d items"}
        with self.assertRaises(Exception) as context:
            translate_plural_text(source_plural, "es", "test_api_key", "test-model", "")
        self.assertTrue("API error" in str(context.exception))
        mock_call_openai.assert_called_once()

    @patch('AndroidResourceTranslator.translate_text')
    @patch('AndroidResourceTranslator.translate_plural_text')
    @patch('AndroidResourceTranslator.update_xml_file')
    @patch('AndroidResourceTranslator.AndroidResourceFile.parse_file')
    def test_auto_translate_resources(self, mock_parse_file, mock_update_xml, mock_translate_plural, mock_translate_text):
        mock_translate_text.return_value = "Translated text"
        mock_translate_plural.return_value = {"one": "Translated one", "other": "Translated other"}
        modules = {"test_module": AndroidModule("test_module")}
        default_resource = AndroidResourceFile(Path("dummy/path"), "default")
        default_resource.strings = {"key1": "value1", "key2": "value2"}
        default_resource.plurals = {"plural1": {"one": "one value", "other": "other value"}}
        target_resource = AndroidResourceFile(Path("dummy/path"), "es")
        target_resource.strings = {"key1": "Spanish value1"}
        target_resource.plurals = {}
        modules["test_module"].language_resources["default"] = [default_resource]
        modules["test_module"].language_resources["es"] = [target_resource]
        translation_log = auto_translate_resources(modules, "test_api_key", "test-model", "", False)
        self.assertIn("test_module", translation_log)
        self.assertIn("es", translation_log["test_module"])
        self.assertTrue(target_resource.modified)
        mock_translate_text.assert_called()
        mock_translate_plural.assert_called()
        mock_update_xml.assert_called_with(target_resource)
        self.assertIn("key2", target_resource.strings)
        self.assertEqual(target_resource.strings["key2"], "Translated text")
        self.assertIn("plural1", target_resource.plurals)

if __name__ == "__main__":
    unittest.main()
