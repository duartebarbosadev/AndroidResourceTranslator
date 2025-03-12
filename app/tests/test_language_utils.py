#!/usr/bin/env python3
"""
Tests for language utilities in AndroidResourceTranslator.

This module tests the functionality of language code handling and translations,
particularly the get_language_name function and related utilities.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import logging

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from language_utils import (
    get_language_name
)


class TestLanguageUtils(unittest.TestCase):
    """Tests for language utility functions."""
    
    def test_get_language_name_known_language(self):
        """Test getting names for known languages."""
        self.assertEqual(get_language_name("en"), "English")
        self.assertEqual(get_language_name("es"), "Spanish")
        self.assertEqual(get_language_name("fr"), "French")
        self.assertEqual(get_language_name("ja"), "Japanese")
    
    def test_get_language_name_with_region(self):
        """Test getting names for language+region codes."""
        self.assertEqual(get_language_name("en-US"), "English (United States)")
        self.assertEqual(get_language_name("es-MX"), "Spanish (Mexico)")
        self.assertEqual(get_language_name("pt-BR"), "Portuguese (Brazil)")
    
    def test_get_language_name_android_format(self):
        """Test with Android's resource format (using rXX instead of -XX)."""
        self.assertEqual(get_language_name("en-rUS"), "English (United States)")
        self.assertEqual(get_language_name("zh-rCN"), "Chinese (Simplified Han,China)")
    
    def test_get_language_name_unknown_language(self):
        """Test that unknown languages return their code."""
        # These languages don't exist, so the code itself should be returned
        self.assertEqual(get_language_name("xx"), "xx")
        self.assertEqual(get_language_name("zz-rXX"), "zz-rXX")
        self.assertEqual(get_language_name("custom-lang"), "custom-lang")
        self.assertEqual(get_language_name("night"), "night")  # Non-existent code
    
    def test_get_language_name_default(self):
        """Test special handling of 'default' language code."""
        self.assertEqual(get_language_name("default"), "Default (English)")
    
    def test_additional_language_codes(self):
        """Test additional language codes from the provided list."""
        # Test standard language codes
        self.assertEqual(get_language_name("b+sr+Latn"), "Serbian (Latin)")
        self.assertEqual(get_language_name("ca"), "Catalan")
        self.assertEqual(get_language_name("cs"), "Czech")
        self.assertEqual(get_language_name("de"), "German")
        self.assertEqual(get_language_name("el"), "Greek")
        self.assertEqual(get_language_name("es"), "Spanish")
        self.assertEqual(get_language_name("fr"), "French")
        self.assertEqual(get_language_name("hi"), "Hindi")
        self.assertEqual(get_language_name("hr"), "Croatian")
        self.assertEqual(get_language_name("hu"), "Hungarian")
        self.assertEqual(get_language_name("it"), "Italian")
        self.assertEqual(get_language_name("ja"), "Japanese")
        self.assertEqual(get_language_name("ml"), "Malayalam")
        self.assertEqual(get_language_name("mr"), "Marathi")
        self.assertEqual(get_language_name("nl"), "Dutch")
        self.assertEqual(get_language_name("pl"), "Polish")
        self.assertEqual(get_language_name("pt"), "Portuguese")
        self.assertEqual(get_language_name("ro"), "Romanian")
        self.assertEqual(get_language_name("ru"), "Russian")
        self.assertEqual(get_language_name("sr"), "Serbian")
        self.assertEqual(get_language_name("vi"), "Vietnamese")
        
        # Test Android-formatted regional codes
        self.assertEqual(get_language_name("fi-rFI"), "Finnish (Finland)")
        self.assertEqual(get_language_name("nb-rNO"), "Norwegian Bokmål (Norway)")
        self.assertEqual(get_language_name("nn-rNO"), "Norwegian Nynorsk (Norway)")
        self.assertEqual(get_language_name("pt-rBR"), "Portuguese (Brazil)")
        self.assertEqual(get_language_name("sk-rSK"), "Slovak (Slovakia)")
        self.assertEqual(get_language_name("sv-rSE"), "Swedish (Sweden)")
        self.assertEqual(get_language_name("ta-rIN"), "Tamil (India)")
        self.assertEqual(get_language_name("tr-rTR"), "Turkish (Türkiye)")
        self.assertEqual(get_language_name("uk-rUA"), "Ukrainian (Ukraine)")
        self.assertEqual(get_language_name("zh-rCN"), "Chinese (Simplified Han,China)")
        self.assertEqual(get_language_name("zh-rTW"), "Chinese (Traditional Han,Taiwan)")
    
    @patch('language_utils.logger')
    def test_get_language_name_logs_warning(self, mock_logger):
        """Test that get_language_name logs a warning for unknown languages."""
        unknown_code = "unknown-lang"
        result = get_language_name(unknown_code)
        
        # Check the code is returned
        self.assertEqual(result, unknown_code)
        
        # Check warning was logged
        mock_logger.warning.assert_called_once()
        # Extract the call arguments
        args, _ = mock_logger.warning.call_args
        # Check the warning message contains the unknown code
        self.assertIn(unknown_code, args[0])
    
if __name__ == "__main__":
    unittest.main()