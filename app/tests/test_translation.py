#!/usr/bin/env python3
"""
Tests for translation functionality in AndroidResourceTranslator.

This module tests the text translation and OpenAI integration features including:
- Single string translation
- Plural string translation
- Auto-translation of resources
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from AndroidResourceTranslator import (
    auto_translate_resources,
    AndroidModule,
    UpdatedDefaultResources,
    detect_updated_default_resources,
    _find_updated_default_resource_entries,
    _normalize_github_event_path,
)
from string_utils import (
    escape_apostrophes,
    escape_double_quotes,
    escape_special_chars,
)
from llm_provider import LLMConfig, LLMProvider, translate_strings_batch_with_llm


class TestSpecialCharacterEscaping(unittest.TestCase):
    """Tests for the special character escaping functionality."""

    def test_escape_apostrophes(self):
        """Test that apostrophes are properly escaped."""
        test_cases = [
            # Format: (input, expected output)
            ("No apostrophes here", "No apostrophes here"),
            ("Apostrophe's need escaping", "Apostrophe\\'s need escaping"),
            (
                "Multiple apostrophes' in one's text",
                "Multiple apostrophes\\' in one\\'s text",
            ),
            (
                "Already escaped apostrophe \\'s fine",
                "Already escaped apostrophe \\'s fine",
            ),
            (
                "Mixed escaping: one's and one\\'s",
                "Mixed escaping: one\\'s and one\\'s",
            ),
            ("", ""),  # Empty string
            (None, None),  # None value
            ("Special ' chars ' everywhere '", "Special \\' chars \\' everywhere \\'"),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_apostrophes(input_text)
                self.assertEqual(result, expected)

    def test_escape_double_quotes(self):
        """Test that double quotes are properly escaped."""
        test_cases = [
            # Format: (input, expected output)
            ("No double quotes here", "No double quotes here"),
            ('Text with "quotes"', 'Text with \\"quotes\\"'),
            ('Multiple "double" "quotes"', 'Multiple \\"double\\" \\"quotes\\"'),
            (
                'Already escaped \\"quotes\\" are fine',
                'Already escaped \\"quotes\\" are fine',
            ),
            (
                'Mixed escaping: "quote" and \\"quote\\"',
                'Mixed escaping: \\"quote\\" and \\"quote\\"',
            ),
            ("", ""),  # Empty string
            (None, None),  # None value
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_double_quotes(input_text)
                self.assertEqual(result, expected)

    def test_escape_special_chars(self):
        """Test that all special characters are properly escaped in a single pass."""
        test_cases = [
            # Format: (input, expected output)
            ("Normal text", "Normal text"),
            ("Email: user@example.com", "Email: user\\@example.com"),
            ("@reference style", "\\@reference style"),
            ("Question? Maybe", "Question\\? Maybe"),
            ("?Leading question mark", "\\?Leading question mark"),
            ("Sale at 50% off", "Sale at 50\\% off"),
            # Test with individual special characters
            ("Text with apostrophe's", "Text with apostrophe\\'s"),
            ('Text with "quotes"', 'Text with \\"quotes\\"'),
            ("Line with newline\nbreak", "Line with newline\\nbreak"),
            ("Tabs\there stay visible", "Tabs\\there stay visible"),
            ("Already escaped \\n stays literal", "Already escaped \\n stays literal"),
            ("", ""),  # Empty string
            (None, None),  # None value
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = escape_special_chars(input_text)
                self.assertEqual(result, expected)

    def test_escape_special_chars_aligns_backslashes_with_reference(self):
        """Ensure escaped sequences match the reference string."""
        source = "Progress: %d%% complete\\nKeep going!"
        translated = "Progreso: %d%% completo\\\\n¡Sigue!"
        expected = "Progreso: %d\\% completo\\n¡Sigue!"
        self.assertEqual(
            escape_special_chars(translated, reference_text=source), expected
        )

        source_regex = "Regex guide:\\nUse \\\\d for digits\\nUse \\\\n for new line"
        translated_regex = "Guía regex:\\\\nUsa \\\\\\\\d para dígitos\\\\nUsa \\\\\\\\n para nueva línea"
        expected_regex = (
            "Guía regex:\\nUsa \\\\d para dígitos\\nUsa \\\\n para nueva línea"
        )
        self.assertEqual(
            escape_special_chars(translated_regex, reference_text=source_regex),
            expected_regex,
        )

    def test_escape_special_chars_collapses_duplicate_backslashes_before_quotes(self):
        """Ensure redundant escaping before quotes is reduced to a single backslash."""
        source = "Select one option"
        translated = "Sélectionnez l\\\\'une"
        expected = "Sélectionnez l\\'une"
        self.assertEqual(
            escape_special_chars(translated, reference_text=source), expected
        )

    def test_escape_special_chars_escapes_literal_percent(self):
        """Percent signs should gain a backslash unless part of a placeholder."""
        text = "Poupe \\% extra hoje"
        self.assertEqual(escape_special_chars(text), "Poupe \\% extra hoje")

    def test_escape_special_chars_preserves_placeholders(self):
        """Ensure format placeholders keep a single percent sign."""
        text = "Olá %1$s, tens %d mensagens e 20% de bateria"
        expected = "Olá %1$s, tens %d mensagens e 20\\% de bateria"
        self.assertEqual(escape_special_chars(text), expected)

    def test_escape_special_chars_does_not_double_escape_existing_percent(self):
        """Literal percents that are already escaped should remain single-escaped."""
        text = "Oferta especial: 50\\% de desconto!"
        self.assertEqual(escape_special_chars(text), text)

    def test_escape_special_chars_handles_extended_backslash_runs(self):
        """Triple backslashes before quotes collapse to match the reference."""
        source = "Select one option"
        translated = "Sélectionnez l\\\\\\'une"
        expected = "Sélectionnez l\\'une"
        self.assertEqual(
            escape_special_chars(translated, reference_text=source), expected
        )

    def test_escape_special_chars_preserves_html_markup(self):
        """Ensure escaping preserves inline HTML markup and attributes."""
        simple_html = 'Visit our <a href="https://test.com">website</a> for more info'
        self.assertEqual(escape_special_chars(simple_html), simple_html)

        complex_html = "Don't miss our <a href='https://test.com'>sale</a> at 50% off"
        expected_complex = (
            'Don\\\'t miss our <a href="https://test.com">sale</a> at 50\\% off'
        )
        self.assertEqual(escape_special_chars(complex_html), expected_complex)


class TestAutoTranslation(unittest.TestCase):
    """Tests for the auto-translation workflow."""

    def setUp(self):
        """Set up test modules with default and target languages."""
        # Create a test module
        self.module = AndroidModule("test_module", "test_id")

        # Default language resources
        self.default_resource = MagicMock()
        self.default_resource.strings = {"hello": "Hello World", "goodbye": "Goodbye"}
        self.default_resource.plurals = {"days": {"one": "%d day", "other": "%d days"}}
        self.default_resource.modified = False

        # Spanish language resources with missing translations
        self.es_resource = MagicMock()
        self.es_resource.strings = {
            "hello": "Hola Mundo"  # "goodbye" is missing
        }
        self.es_resource.plurals = {}  # All plurals missing
        self.es_resource.modified = False

        # Add resources to module
        self.module.add_resource("default", self.default_resource)
        self.module.add_resource("es", self.es_resource)

        # Build modules dict
        self.modules = {"test_id": self.module}

    def test_find_updated_default_resource_entries_only_existing_changes(self):
        """Only changed existing default entries should be marked for refresh."""
        current_resource = MagicMock()
        current_resource.strings = {
            "hello": "Hello again",
            "new": "New string",
            "same": "Same",
        }
        current_resource.plurals = {
            "days": {"one": "%d day left", "other": "%d days left"},
            "new_plural": {"other": "%d new items"},
            "same_plural": {"other": "%d item"},
        }

        updated = _find_updated_default_resource_entries(
            previous_strings={"hello": "Hello", "same": "Same"},
            previous_plurals={
                "days": {"one": "%d day", "other": "%d days"},
                "same_plural": {"other": "%d item"},
            },
            current_resource=current_resource,
        )

        self.assertEqual(updated.strings, {"hello"})
        self.assertEqual(updated.plurals, {"days"})

    def test_normalize_github_event_path_preserves_leading_dot_directories(self):
        """Only a literal ./ prefix should be removed from event paths."""
        self.assertEqual(
            _normalize_github_event_path("./app/src/main/res/values/strings.xml"),
            "app/src/main/res/values/strings.xml",
        )
        self.assertEqual(
            _normalize_github_event_path(".github/workflows/translate.yml"),
            ".github/workflows/translate.yml",
        )

    @patch("AndroidResourceTranslator._read_github_event_modified_paths")
    @patch("AndroidResourceTranslator._resolve_previous_commit_ref")
    @patch("AndroidResourceTranslator._run_git_command")
    def test_detect_updated_default_resources_falls_back_to_modified_event_path(
        self,
        mock_run_git_command,
        mock_resolve_previous_commit_ref,
        mock_read_modified_paths,
    ):
        """A shallow GitHub checkout should refresh all entries in modified defaults."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = os.path.realpath(tmp_dir)
            resource_path = os.path.join(
                repo_root, "app", "src", "main", "res", "values", "strings.xml"
            )

            default_resource = MagicMock()
            default_resource.path = Path(resource_path)
            default_resource.strings = {"hello": "Hello", "goodbye": "Goodbye"}
            default_resource.plurals = {"days": {"other": "%d days"}}

            module = AndroidModule("test_module", "test_id")
            module.language_resources["default"] = [default_resource]

            def git_side_effect(args, cwd, text=True):
                if args == ["rev-parse", "--show-toplevel"]:
                    return repo_root
                if args[:3] == ["status", "--porcelain", "--"]:
                    return ""
                return None

            mock_run_git_command.side_effect = git_side_effect
            mock_resolve_previous_commit_ref.return_value = None
            mock_read_modified_paths.return_value = {
                "app/src/main/res/values/strings.xml"
            }

            updated = detect_updated_default_resources({"test_id": module})

        self.assertEqual(updated["test_id"].strings, {"hello", "goodbye"})
        self.assertEqual(updated["test_id"].plurals, {"days"})

    @patch("AndroidResourceTranslator.translate_plurals_batch_with_llm")
    @patch("AndroidResourceTranslator.translate_strings_batch_with_llm")
    @patch("AndroidResourceTranslator.update_xml_file")
    def test_auto_translate(
        self,
        mock_update_xml,
        mock_translate_strings_batch,
        mock_translate_plurals_batch,
    ):
        """Test complete auto-translation workflow."""
        # Configure mocks
        mock_translate_strings_batch.return_value = {"goodbye": "Adiós"}
        mock_translate_plurals_batch.return_value = {
            "days": {"one": "%d día", "other": "%d días"}
        }

        # Create LLMConfig
        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        # Execute auto translation
        result = auto_translate_resources(
            self.modules,
            llm_config=llm_config,
            project_context="Test project",
        )

        # Verify translation calls
        mock_translate_strings_batch.assert_called_once()
        strings_payload = (
            mock_translate_strings_batch.call_args.kwargs.get("strings_dict")
            or mock_translate_strings_batch.call_args.args[0]
        )
        self.assertEqual(strings_payload, {"goodbye": "Goodbye"})

        reference_examples = mock_translate_strings_batch.call_args.kwargs.get(
            "reference_examples"
        )
        self.assertIsNotNone(reference_examples)
        self.assertIn(
            {
                "key": "hello",
                "source": "Hello World",
                "existing_translation": "Hola Mundo",
            },
            reference_examples,
        )

        mock_translate_plurals_batch.assert_called_once()
        plurals_payload = (
            mock_translate_plurals_batch.call_args.kwargs.get("plurals_dict")
            or mock_translate_plurals_batch.call_args.args[0]
        )
        self.assertEqual(
            plurals_payload, {"days": {"one": "%d day", "other": "%d days"}}
        )
        self.assertIsNone(
            mock_translate_plurals_batch.call_args.kwargs.get("reference_examples")
        )

        # Verify file updates
        mock_update_xml.assert_called_once_with(self.es_resource)

        # Verify resource updates
        self.assertEqual(self.es_resource.strings["goodbye"], "Adiós")
        self.assertEqual(
            self.es_resource.plurals["days"], {"one": "%d día", "other": "%d días"}
        )

        # Verify resource was marked modified
        self.assertTrue(self.es_resource.modified)

        # Verify translation log structure
        self.assertIn("test_module", result)
        self.assertIn("es", result["test_module"])
        self.assertIn("strings", result["test_module"]["es"])
        self.assertIn("plurals", result["test_module"]["es"])

    @patch("AndroidResourceTranslator.translate_plurals_batch_with_llm")
    @patch("AndroidResourceTranslator.translate_strings_batch_with_llm")
    @patch("AndroidResourceTranslator.update_xml_file")
    def test_auto_translate_refreshes_updated_existing_string(
        self,
        mock_update_xml,
        mock_translate_strings_batch,
        mock_translate_plurals_batch,
    ):
        """Changed default strings should retranslate existing target entries."""
        self.default_resource.strings = {
            "hello": "Hello again",
            "goodbye": "Goodbye",
        }
        self.es_resource.strings = {
            "hello": "Hola Mundo",
            "goodbye": "Adiós",
        }
        self.es_resource.plurals = {
            "days": {"one": "%d día", "other": "%d días"},
        }
        mock_translate_strings_batch.return_value = {"hello": "Hola de nuevo"}

        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        result = auto_translate_resources(
            self.modules,
            llm_config=llm_config,
            project_context="Test project",
            updated_default_resources={
                "test_id": UpdatedDefaultResources(strings={"hello"})
            },
        )

        mock_translate_strings_batch.assert_called_once()
        strings_payload = mock_translate_strings_batch.call_args.kwargs["strings_dict"]
        self.assertEqual(strings_payload, {"hello": "Hello again"})
        mock_translate_plurals_batch.assert_not_called()
        mock_update_xml.assert_called_once_with(self.es_resource)
        self.assertEqual(self.es_resource.strings["hello"], "Hola de nuevo")
        self.assertEqual(
            result["test_module"]["es"]["strings"][0]["source"], "Hello again"
        )

    @patch("AndroidResourceTranslator.translate_plurals_batch_with_llm")
    @patch("AndroidResourceTranslator.translate_strings_batch_with_llm")
    @patch("AndroidResourceTranslator.update_xml_file")
    def test_auto_translate_refreshes_updated_existing_plural(
        self,
        mock_update_xml,
        mock_translate_strings_batch,
        mock_translate_plurals_batch,
    ):
        """Changed default plurals should replace existing target plural entries."""
        self.es_resource.strings = {
            "hello": "Hola Mundo",
            "goodbye": "Adiós",
        }
        self.es_resource.plurals = {
            "days": {
                "one": "%d día antiguo",
                "few": "%d días antiguos",
                "other": "%d días antiguos",
            }
        }
        mock_translate_plurals_batch.return_value = {
            "days": {"one": "%d día nuevo", "other": "%d días nuevos"}
        }

        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        auto_translate_resources(
            self.modules,
            llm_config=llm_config,
            project_context="Test project",
            updated_default_resources={
                "test_id": UpdatedDefaultResources(plurals={"days"})
            },
        )

        mock_translate_strings_batch.assert_not_called()
        mock_translate_plurals_batch.assert_called_once()
        plurals_payload = mock_translate_plurals_batch.call_args.kwargs["plurals_dict"]
        self.assertEqual(
            plurals_payload, {"days": {"one": "%d day", "other": "%d days"}}
        )
        mock_update_xml.assert_called_once_with(self.es_resource)
        self.assertEqual(
            self.es_resource.plurals["days"],
            {"one": "%d día nuevo", "other": "%d días nuevos"},
        )

    @patch("AndroidResourceTranslator.translate_plurals_batch_with_llm")
    @patch("AndroidResourceTranslator.translate_strings_batch_with_llm")
    @patch("AndroidResourceTranslator.update_xml_file")
    def test_auto_translate_skips_plurals_when_target_has_extra_valid_forms(
        self,
        mock_update_xml,
        mock_translate_strings_batch,
        mock_translate_plurals_batch,
    ):
        """Extra locale-specific plural forms should not trigger retranslation."""
        module = AndroidModule("test_module", "test_id")

        default_resource = MagicMock()
        default_resource.strings = {}
        default_resource.plurals = {"days": {"other": "%d days"}}
        default_resource.modified = False

        sv_resource = MagicMock()
        sv_resource.strings = {}
        sv_resource.plurals = {
            "days": {
                "one": "%d dag",
                "few": "%d dagar",
                "other": "%d dagar",
            }
        }
        sv_resource.modified = False

        module.add_resource("default", default_resource)
        module.add_resource("sv", sv_resource)

        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        result = auto_translate_resources(
            {"test_id": module},
            llm_config=llm_config,
            project_context="Test project",
        )

        mock_translate_strings_batch.assert_not_called()
        mock_translate_plurals_batch.assert_not_called()
        mock_update_xml.assert_not_called()
        self.assertFalse(sv_resource.modified)
        self.assertEqual(sv_resource.plurals["days"]["few"], "%d dagar")
        self.assertEqual(result["test_module"]["sv"]["plurals"], [])

    @patch("AndroidResourceTranslator.translate_plurals_batch_with_llm")
    @patch("AndroidResourceTranslator.translate_strings_batch_with_llm")
    @patch("AndroidResourceTranslator.update_xml_file")
    def test_auto_translate_skips_existing_plural_when_target_only_has_other(
        self,
        mock_update_xml,
        mock_translate_strings_batch,
        mock_translate_plurals_batch,
    ):
        """A target plural that already exists should not be retransmitted."""
        module = AndroidModule("test_module", "test_id")

        default_resource = MagicMock()
        default_resource.strings = {}
        default_resource.plurals = {
            "days": {"one": "%d day", "few": "%d days", "other": "%d days"}
        }
        default_resource.modified = False

        target_resource = MagicMock()
        target_resource.strings = {}
        target_resource.plurals = {"days": {"other": "%d dias"}}
        target_resource.modified = False

        module.add_resource("default", default_resource)
        module.add_resource("pt", target_resource)

        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        result = auto_translate_resources(
            {"test_id": module},
            llm_config=llm_config,
            project_context="Test project",
        )

        mock_translate_strings_batch.assert_not_called()
        mock_translate_plurals_batch.assert_not_called()
        mock_update_xml.assert_not_called()
        self.assertFalse(target_resource.modified)
        self.assertEqual(target_resource.plurals["days"], {"other": "%d dias"})
        self.assertEqual(result["test_module"]["pt"]["plurals"], [])

    @patch("AndroidResourceTranslator.translate_strings_batch_with_llm")
    @patch("AndroidResourceTranslator.update_xml_file")
    def test_auto_translate_raises_on_incomplete_batch_response(
        self,
        mock_update_xml,
        mock_translate_strings_batch,
    ):
        """Partial string batches should fail instead of writing empty values."""
        mock_translate_strings_batch.side_effect = ValueError(
            "LLM returned an incomplete translations array. Missing keys: goodbye"
        )

        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        with self.assertRaisesRegex(ValueError, "Missing keys: goodbye"):
            auto_translate_resources(
                self.modules,
                llm_config=llm_config,
                project_context="Test project",
            )

        self.assertNotIn("goodbye", self.es_resource.strings)
        mock_update_xml.assert_not_called()


class TestBatchTranslationSafety(unittest.TestCase):
    """Tests for safe handling of incomplete batch responses."""

    def test_translate_strings_batch_raises_on_missing_keys(self):
        """The adapter should reject partial LLM batch results."""

        class FakeClient:
            def __init__(self, config):
                self.config = config

            def chat_completion(self, **kwargs):
                return {"translations": [{"key": "hello", "translation": "Hola"}]}

        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI, api_key="test_api_key", model="test-model"
        )

        with patch("llm_provider.LLMClient", FakeClient):
            with self.assertRaisesRegex(ValueError, "Missing keys: goodbye"):
                translate_strings_batch_with_llm(
                    strings_dict={"hello": "Hello", "goodbye": "Goodbye"},
                    system_message="System",
                    user_prompt="Prompt",
                    llm_config=llm_config,
                )


if __name__ == "__main__":
    unittest.main()
