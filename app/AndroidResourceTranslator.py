#!/usr/bin/env python3
"""
Android Resource Auto-Translator

This script scans Android resource files (strings.xml) for string and plural resources,
reports missing translations, and can automatically translate missing entries using OpenAI.
"""

import argparse
import logging
import sys
import re
import os
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, Set, List, Tuple
from lxml import etree
from language_utils import get_language_name

# Import git utilities from separate module
from git_utils import (
    parse_gitignore,
    find_all_gitignores,
    is_ignored_by_gitignore,
    is_ignored_by_gitignores,
)

# Import LLM provider utilities
from llm_provider import (
    LLMProvider,
    LLMConfig,
    translate_strings_batch_with_llm,
    translate_plurals_batch_with_llm,
)

# ------------------------------------------------------------------------------
# Translation Prompt Constants
# ------------------------------------------------------------------------------

# Maximum number of items to translate in a single batch API call
MAX_BATCH_SIZE = 100
# Default number of existing translation pairs/plurals to include as context
DEFAULT_REFERENCE_CONTEXT_LIMIT = 25

TRANSLATION_GUIDELINES = """\
Follow these guidelines carefully.
**Purpose & Context:**  
This translation is for an Android application's UI. Use concise, clear language consistent with standard Android UI conventions. Do not alter the intended meaning of the text.

**Formatting & Structure:**  
- Keep all placeholders (e.g., %d, %s, %1$s, %1$d) exactly as in the source. If the target language requires reordering, ensure that the same placeholders appear and are correctly positioned according to the language's syntax.
- Maintain the integrity of HTML, CDATA, or XML structures; translate only the textual content.  
- Preserve all whitespace, line breaks, and XML formatting exactly as in the source.  
- Escape apostrophes with a backslash (\\') as required by Android.

**Handling Line Breaks:**
When translating phrases with line breaks (e.g., "Temporary\\nUnblock"):
1. Read the entire phrase to understand its complete meaning
2. Translate the complete phrase into the target language
3. Apply the line break in the translation if it maintains similar meaning
4. Only omit the line break if it doesn't make sense in the target language

**System Terms:**  
Do not translate system state words (e.g., WARNING, FAILED, SUCCESS) or any technical and branded terms. Always leave these in their original English, uppercase form.

**Terminology & Natural Expressions:**  
Translate in a natural, concise style that matches standard Android UI conventions.
Avoid overly literal translations that may sound awkward. When a technical term or proper noun is more recognizable in English for that language, keep it in English.

**Technical Term Adoption:**
For tech-specific terms that are commonly borrowed in the target language (such as "scrolling", etc.), use the borrowed term if it's more widely recognized than the native equivalent. For Portuguese (Portugal) specifically, terms like "scrolling" can be kept in English when they're commonly used that way in technology contexts.

**Handling Idioms and Metaphors:**
For idiomatic expressions or culturally-charged phrases, that there's no direct equivalent, translate the intended meaning rather than literally. For example, phrases like "brain rot" if there's no direct translation should be translated to convey "mental decay" in a way that sounds natural in the target language.
Make sure to keep the translation within a reasonable size, not exceeding 20% of the original text length. If the translation is significantly longer, and if possible consider rephrasing or simplifying it while maintaining the original meaning.

**Tone and Formality Consistency:**
  Maintain consistent formality throughout ALL translations based on these principles:
- Default to a conversational but respectful tone appropriate for a consumer android app
- Match the formality level commonly used in popular, well-localized android apps in the target language
- Use direct address forms (equivalent to "you" in English) that feel natural in the target language

**Technical Terms:**
Terms like 'accessibility service' and app-specific features should be translated using standard UI terminology in the target language.

**Examples (Portuguese of Portugal):**  
- "Message Sent" → ✅ "Mensagem enviada" (❌ "Mensagem foi enviada")  
- "Upload Speed" → ✅ "Velocidade de upload" (❌ "Velocidade de envio")
- "Endless scrolling" → ✅ "Scroll sem fim" (❌ "Deslocamento infinito")
- "Temporary\\nUnblock" → ✅ "Desbloquear\\nTemporariamente" (❌ "Temporário\nDesbloquear") (Note that in Portuguese the word order is reversed as per grammar rules)

Learn from the examples above and apply the same principles to other translations.

**Dialect and Regional Vocabulary:**  
Unless otherwise specified, use always the vocabulary appropriate to the target dialect (e.g., **pt -> Português de Portugal**) and avoid terms from other variants.

**Brand Names and Proper Nouns:**
All brand names (like GitHub, Android, Google), proper nouns, feature names, and trademarked terms MUST remain in their original English form with exact spelling. 
Do not apply any grammatical inflections, declensions, or case modifications to these terms in any language, even when the target language's grammar would typically require it. For example, "GitHub" must always remain "GitHub" - never "GitHubie", "GitHuba", etc.

**Quality Verification:**
After completing translation:
1. Verify no characters from other writing systems have been accidentally included
2. Ensure consistent terminology is used throughout
3. Check that idiomatic expressions are natural in the target language
4. Verify translation accuracy
5. Confirm that the formality level is appropriate and consistent
6. Verify all rules and guidelines have been followed!

**IMPORTANT Output Requirements:**  
Return ONLY the final translated text as a single plain line! Preserving only any required formatting from the source.
Do not include the surrounding Android XML structure (<string> tags, etc.). Only output the translated content!
Example:
  Input: "Welcome, <b>%1$s</b>! You have %2$d points."
  Correct output: "Dobrodošli, <b>%1$s</b>! Imate %2$d poena."
  INCORRECT output: "<string name="welcome_message">Dobrodošli, <b>%1$s</b>! Imate %2$d poena.</string>"
"""
PLURAL_GUIDELINES_ADDITION = """\
For plural resources, follow these guidelines:
1. **Plural Keys:**
   If the source resource contains only a single plural key (e.g., "other") but the target language requires multiple forms, include all necessary plural keys as defined by the target language's pluralization rules.
   *Example:* If the English source has `"other": "%d day left"`, the target translation should include all required forms:
   - `"zero"`: "No days left"
   - `"one"`: "%d day left"
   - `"few"`: "%d days left"
   - `"many"`: "%d days left"
   - `"other"`: "%d days left"
   (Adjust the text according to correct singular and plural usage in the target language. Use the appropriate plural keys for the target language: zero, one, two, few, many, and other.)
"""
SYSTEM_MESSAGE_TEMPLATE = """\
You are a professional translator translating textual UI elements within an Android from English into {target_language}. Follow user guidelines closely.
"""
TRANSLATE_FINAL_TEXT = """\
Translate the following string provided after the dashed line to language: {target_language}
----------
"""

# ------------------------------------------------------------------------------
# Logger Setup
# ------------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def _create_secure_fragment_parser() -> etree.XMLParser:
    """Return an XML parser configured to avoid external entity resolution."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
        recover=False,
    )


def _normalize_inner_xml(text: str) -> str:
    """Normalize inner XML content for comparison."""
    if text is None:
        return ""
    return text.strip()


def _serialize_inner_xml(element) -> str:
    """Serialize the inner XML of an element, preserving nested markup."""
    segments: List[str] = []

    if element.text:
        segments.append(element.text)

    for child in element:
        segments.append(etree.tostring(child, encoding="unicode", with_tail=False))
        if child.tail:
            segments.append(child.tail)

    return _normalize_inner_xml("".join(segments))


def _set_element_inner_xml(element, content: str) -> None:
    """Replace an element's inner XML while keeping nested markup intact."""
    # Remove existing children
    for child in list(element):
        element.remove(child)

    if content is None:
        element.text = None
        return

    content = content.strip()

    if not content:
        element.text = ""
        return

    try:
        parser = _create_secure_fragment_parser()
        wrapper = etree.fromstring(
            f"<__wrapper__>{content}</__wrapper__>", parser=parser
        )
    except etree.XMLSyntaxError:
        element.text = content
        return

    element.text = wrapper.text

    for child in wrapper:
        element.append(child)


def configure_logging(trace: bool) -> None:
    """Configure logging to console and optionally to a file."""
    log_level = logging.DEBUG if trace else logging.INFO
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Configure the root logger so every module shares the same handlers/level.
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    else:
        for existing_handler in root_logger.handlers:
            existing_handler.setFormatter(formatter)

    # Keep this module logger aligned with the configured level.
    logger.setLevel(log_level)

    # Suppress noisy debug logs from HTTP client/SDK libraries unless they escalate.
    noisy_loggers = [
        "openai",
        "openai._base_client",
        "openai._http_client",
        "httpx",
        "httpcore",
    ]
    for name in noisy_loggers:
        noisy_logger = logging.getLogger(name)
        noisy_logger.setLevel(logging.WARNING)


# ------------------------------------------------------------------------------
# Android Resource Parsing & Updating
# ------------------------------------------------------------------------------


class AndroidResourceFile:
    """
    Represents a strings.xml file in an Android project containing <string> and <plurals> resources.
    """

    def __init__(self, path: Path, language: str = "default") -> None:
        self.path: Path = path
        self.language: str = language
        self.strings: Dict[str, str] = {}  # key -> string value
        self.plurals: Dict[str, Dict[str, str]] = {}  # key -> {quantity -> text}
        self.modified: bool = False  # Flag to track if any changes are made
        self.parse_file()

    def parse_file(self) -> None:
        """Parses the strings.xml file and extracts <string> and <plurals> elements. Skips resources with translatable="false"."""
        try:
            parser = etree.XMLParser(remove_blank_text=False)
            tree = etree.parse(str(self.path), parser)
            root = tree.getroot()
            for elem in root:
                translatable = elem.attrib.get("translatable", "true").lower()
                if translatable == "false":
                    continue

                if elem.tag == "string":
                    name = elem.attrib.get("name")
                    if name:
                        full_text = _serialize_inner_xml(elem)
                        self.strings[name] = full_text
                elif elem.tag == "plurals":
                    name = elem.attrib.get("name")
                    if name:
                        quantities: Dict[str, str] = {}
                        for item in elem.findall("item"):
                            quantity = item.attrib.get("quantity")
                            if quantity:
                                full_text = _serialize_inner_xml(item)
                                quantities[quantity] = full_text
                        self.plurals[name] = quantities
            logger.debug(
                f"Parsed {len(self.strings)} strings and {len(self.plurals)} plurals from {self.path}"
            )
        except etree.XMLSyntaxError as pe:
            logger.error(f"XML parse error in {self.path}: {pe}")
            raise
        except Exception as e:
            logger.error(f"Error parsing {self.path}: {e}")
            raise

    def summary(self) -> Dict[str, int]:
        """Return a summary of resource counts."""
        return {"strings": len(self.strings), "plurals": len(self.plurals)}


class AndroidModule:
    """
    Represents an Android module containing several strings.xml files for different languages.
    """

    def __init__(self, name: str, identifier: str = None) -> None:
        self.name: str = name
        # Unique identifier so that modules in different locations are not merged if they share the same short name.
        self.identifier: str = identifier or name
        self.language_resources: Dict[str, List[AndroidResourceFile]] = defaultdict(
            list
        )

    def add_resource(self, language: str, resource: AndroidResourceFile) -> None:
        logger.debug(
            f"Added resource for '{language}' in module '{self.name}': {resource.path.name}"
        )
        self.language_resources[language].append(resource)

    def print_resources(self) -> None:
        logger.info(f"Module: {self.name} (ID: {self.identifier})")
        for language, resources in sorted(self.language_resources.items()):
            for resource in resources:
                sums = resource.summary()
                logger.debug(
                    f"  [{language}] {resource.path} | Strings: {sums['strings']}, Plurals: {sums['plurals']}"
                )


def detect_language_from_path(file_path: Path) -> str:
    """
    Detect language code from an Android resource folder name.

    In Android, resource folders follow a naming convention to indicate
    the language they contain. This function extracts the language code
    from the folder name:

    Examples:
      - "values"           -> "default" (base/source language, usually English)
      - "values-es"        -> "es" (Spanish)
      - "values-zh-rCN"    -> "zh-rCN" (Chinese Simplified)
      - "values-b+sr+Latn" -> "b+sr+Latn" (Serbian in Latin script)

    The function tries to match the standard pattern first (values-XX),
    and falls back to a simpler replacement if the pattern doesn't match.

    Args:
        file_path: Path object pointing to a resource file

    Returns:
        String representing the language code, or "default" for the base language
    """
    values_dir = file_path.parent.name

    # Base language case
    if values_dir == "values":
        return "default"

    # Standard pattern: values-XX
    match = re.match(r"values-(.+)", values_dir)
    if not match:
        raise ValueError(
            f"Invalid Android resource folder name: '{values_dir}'. "
            "Expected format 'values' or 'values-<lang>'."
        )

    language = match.group(1)
    logger.debug(f"Detected language '{language}' from {values_dir}")
    return language


def find_resource_files(
    resources_path: str, ignore_folders: List[str] = None
) -> Dict[str, AndroidModule]:
    """
    Recursively search for and organize Android string resource files by module.

    This function scans the given directory tree for strings.xml files located in
    "values" or "values-XX" directories, where XX represents language codes. It
    organizes these files into module structures based on the project hierarchy.

    Files can be excluded from processing using either:
    1. An explicit list of folders to ignore (via ignore_folders parameter)
    2. Patterns from .gitignore files (if ignore_folders is not provided)

    The function assumes a standard Android project structure:
      <module_name>/src/main/res/values(-locale)/strings.xml
    and uses the directory five levels up from each strings.xml file as the module
    root directory.

    Args:
        resources_path: Path to the root directory to scan for resources
        ignore_folders: Optional list of folder names to ignore during scanning

    Returns:
        Dictionary mapping module identifiers to AndroidModule objects containing
        the resource files organized by language

    Raises:
        Exception: If there's an error determining the module structure
    """
    resources_dir = Path(resources_path)
    modules: Dict[str, AndroidModule] = {}
    logger.info(f"Scanning for resource files in {resources_dir}")

    # Determine which files to ignore:
    # 1. Use explicit ignore_folders if provided
    # 2. Otherwise, use patterns from .gitignore files with proper precedence
    if ignore_folders:
        logger.info(f"Using explicit ignore folders: {', '.join(ignore_folders)}")
        gitignore_patterns = []
        all_gitignores = {}
    else:
        # Find all .gitignore files in the directory hierarchy
        all_gitignores = find_all_gitignores(resources_path)
        if all_gitignores:
            total_patterns = sum(len(patterns) for patterns in all_gitignores.values())
            logger.info(
                f"Using {total_patterns} patterns from .gitignore files in directory hierarchy"
            )
        else:
            # Fallback to just the root .gitignore if no ignore_folders specified
            gitignore_patterns = parse_gitignore(resources_path)
            if gitignore_patterns:
                logger.info(
                    f"Using {len(gitignore_patterns)} patterns from .gitignore in {resources_dir}"
                )
            else:
                gitignore_patterns = []

    # Recursively find all strings.xml files
    for xml_file_path in resources_dir.rglob("strings.xml"):
        # Skip files in ignored directories
        if ignore_folders and any(
            ignored in str(xml_file_path.parts) for ignored in ignore_folders
        ):
            logger.debug(f"Skipping {xml_file_path} (matched ignore_folders)")
            continue
        elif all_gitignores:
            # Use the full hierarchical gitignore implementation
            if is_ignored_by_gitignores(xml_file_path, all_gitignores):
                logger.debug(
                    f"Skipping {xml_file_path} (matched gitignore pattern from hierarchy)"
                )
                continue
        elif not ignore_folders and gitignore_patterns:
            # Use the single file gitignore implementation
            if is_ignored_by_gitignore(xml_file_path, gitignore_patterns):
                logger.debug(f"Skipping {xml_file_path} (matched gitignore pattern)")
                continue

        # Process only files in "values" or "values-XX" directories
        if not xml_file_path.parent.name.startswith("values"):
            continue

        # Detect which language this resource file is for
        language = detect_language_from_path(xml_file_path)

        try:
            # Identify the module based on the project structure
            # With a fixed structure, the module folder is 5 levels up from strings.xml.
            # Example: app/src/main/res/values/strings.xml → module is "app"
            module_path = xml_file_path.parents[4]
        except Exception as e:
            logger.error(f"Error determining module folder for {xml_file_path}: {e}")
            raise

        # Use both the module name and its full path as an identifier
        # This ensures we don't merge modules with the same name from different paths
        module_name = module_path.name
        module_key = str(module_path.resolve())

        # Create the module entry if it doesn't exist yet
        if module_key not in modules:
            modules[module_key] = AndroidModule(module_name, identifier=module_key)
            logger.debug(
                f"Created module entry for '{module_name}' (key: {module_key})"
            )

        # Parse and add the resource file to the appropriate module and language
        resource_file = AndroidResourceFile(xml_file_path, language)
        modules[module_key].add_resource(language, resource_file)

    return modules


def update_xml_file(resource: AndroidResourceFile) -> None:
    """
    Update Android string resources XML file while preserving formatting.

    This function writes the modified string and plural resources back to the XML file,
    carefully maintaining the original formatting, indentation, and XML structure.
    It either updates existing elements or appends new ones as needed.

    The function performs the following operations:
    1. Reads the existing XML file and parses its structure
    2. Preserves the original indentation style
    3. Updates or adds <string> elements
    4. Updates or adds <plurals> elements and their nested <item> elements
    5. Ensures proper XML formatting with consistent indentation
    6. Writes the modified XML back to the file with the correct encoding

    Args:
        resource: AndroidResourceFile object containing the updated resources

    Returns:
        None

    Raises:
        Exception: If there's an error reading, parsing, or writing the XML file
    """
    # Only update if the resource was modified
    if not resource.modified:
        return

    try:
        # Parse the XML with a parser that preserves whitespace
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(str(resource.path), parser)
        root = tree.getroot()
    except Exception as e:
        logger.error(f"Error reading XML file {resource.path}: {e}")
        raise

    # Detect the indentation style from the existing file (default to 4 spaces)
    sample_indent = "    "
    if len(root) > 0:
        m = re.match(r"\n(\s+)", root[0].tail or "")
        if m:
            sample_indent = m.group(1)

    # Ensure proper indentation before the first child
    if not root.text or not root.text.strip():
        root.text = "\n" + sample_indent

    # --- Handle <string> elements ---

    # Map existing string elements by name for quick lookup
    original_root_count = len(root)
    existing_string_elements = {
        elem.get("name"): elem for elem in root if elem.tag == "string"
    }

    # Ensure consistent formatting between elements
    if original_root_count > 0:
        last_original = root[original_root_count - 1]
        if not last_original.tail or not last_original.tail.endswith(sample_indent):
            last_original.tail = "\n" + sample_indent

    # Process each string resource
    for key, translation in resource.strings.items():
        normalized_translation = _normalize_inner_xml(translation)

        if key in existing_string_elements:
            current_value = _serialize_inner_xml(existing_string_elements[key])
            if _normalize_inner_xml(current_value) != normalized_translation:
                _set_element_inner_xml(existing_string_elements[key], translation)
                logger.debug(
                    f"Updated <string name='{key}'> element in {resource.path}"
                )
        else:
            # Create and append a new string element
            new_elem = etree.Element("string", name=key)
            _set_element_inner_xml(new_elem, translation)
            new_elem.tail = "\n" + sample_indent
            root.append(new_elem)
            logger.debug(f"Appended <string name='{key}'> element to {resource.path}")

    # --- Handle <plurals> elements ---

    # Map existing plurals elements by name
    existing_plural_elements = {
        elem.get("name"): elem for elem in root if elem.tag == "plurals"
    }

    # Process each plural resource
    for plural_name, items in resource.plurals.items():
        # Get or create the plural element
        if plural_name in existing_plural_elements:
            plural_elem = existing_plural_elements[plural_name]
        else:
            # Create a new plurals element with proper nesting
            plural_elem = etree.Element("plurals", name=plural_name)
            plural_elem.text = "\n" + sample_indent + "    "
            plural_elem.tail = "\n" + sample_indent
            root.append(plural_elem)

        # Calculate the indentation for the nested item elements
        item_indent = sample_indent + "    "

        # Map existing item elements by quantity
        existing_quantity_items = {
            child.get("quantity"): child for child in plural_elem if child.tag == "item"
        }

        # Process each quantity variation
        for qty, translation in items.items():
            normalized_translation = _normalize_inner_xml(translation)
            if qty in existing_quantity_items:
                current_value = _serialize_inner_xml(existing_quantity_items[qty])
                if _normalize_inner_xml(current_value) != normalized_translation:
                    _set_element_inner_xml(existing_quantity_items[qty], translation)
                    logger.debug(
                        f"Updated plural '{plural_name}' quantity '{qty}' in {resource.path}"
                    )
            else:
                # Create and append a new item element
                new_item = etree.Element("item", quantity=qty)
                _set_element_inner_xml(new_item, translation)
                new_item.tail = "\n" + item_indent
                plural_elem.append(new_item)
                logger.debug(
                    f"Added plural '{plural_name}' quantity '{qty}' to {resource.path}"
                )

        # Ensure proper formatting for the last item in a plurals element
        if len(plural_elem) > 0:
            plural_elem[-1].tail = "\n" + sample_indent

    # Ensure the closing tag of the root element is properly formatted
    if len(root) > 0:
        root[-1].tail = "\n"

    try:
        # Serialize and write the XML back to the file
        xml_bytes = etree.tostring(
            tree, encoding="utf-8", xml_declaration=True, pretty_print=True
        )
        xml_bytes = xml_bytes.rstrip(b"\n")  # Remove trailing newlines

        with open(resource.path, "wb") as f:
            f.write(xml_bytes)

        # Standardize the XML declaration format
        with open(resource.path, "r+", encoding="utf-8") as f:
            content = f.read()
            content = re.sub(
                r"<\?xml version=['\"]1\.0['\"] encoding=['\"]utf-8['\"]\?>",
                '<?xml version="1.0" encoding="utf-8"?>',
                content,
                flags=re.IGNORECASE,
            )
            f.seek(0)
            f.write(content)
            f.truncate()

        logger.info(f"Updated XML file: {resource.path}")
        resource.modified = False
    except Exception as e:
        logger.error(f"Error writing XML file {resource.path}: {e}")
        raise


# ------------------------------------------------------------------------------
# Translation & OpenAI API Integration
# ------------------------------------------------------------------------------


def escape_apostrophes(text: str) -> str:
    """
    Ensure apostrophes in the text are properly escaped for Android resource files.

    This function checks if apostrophes are already properly escaped with a backslash (\')
    and adds the escape character if needed. This is critical for Android resource files
    as unescaped apostrophes will cause XML parsing errors.

    Args:
        text: The text to process

    Returns:
        The text with properly escaped apostrophes
    """
    # Skip processing if the text is empty or None
    if not text:
        return text

    # Replace any standalone apostrophes (not already escaped) with escaped versions
    # This regex looks for apostrophes that aren't already preceded by a backslash
    return re.sub(r"(?<!\\)'", r"\'", text)


def escape_percent(text: str) -> str:
    """
    Ensure percent signs in the text are properly escaped for Android resource files.

    This function checks if percent signs are already properly escaped with a backslash (\\%)
    and adds the escape character if needed. This is important for Android resource files
    as unescaped percent signs can be mistaken for format specifiers.

    Args:
        text: The text to process

    Returns:
        The text with properly escaped percent signs
    """
    # Skip processing if the text is empty or None
    if not text:
        return text

    # Replace any standalone percent signs (not already escaped) with escaped versions
    # This regex looks for percent signs that aren't already preceded by a backslash
    # and aren't part of a format specifier like %s, %d, %1$s, etc.
    return re.sub(r"(?<!\\)%(?![0-9]?[$]?[sd])", r"\\%", text)


def escape_double_quotes(text: str) -> str:
    """
    Ensure double quotes in the text are properly escaped for Android resource files.

    This function checks if double quotes are already properly escaped with a backslash (\")
    and adds the escape character if needed. This is essential for Android resource files
    as unescaped double quotes can cause XML parsing errors.

    Args:
        text: The text to process

    Returns:
        The text with properly escaped double quotes
    """
    # Skip processing if the text is empty or None
    if not text:
        return text

    # Replace any standalone double quotes (not already escaped) with escaped versions
    # This regex looks for double quotes that aren't already preceded by a backslash
    return re.sub(r'(?<!\\)"', r'\\"', text)


def escape_at_symbol(text: str) -> str:
    """
    Ensure at symbols in the text are properly escaped for Android resource files.

    This function checks if at symbols are already properly escaped with a backslash (\\@)
    and adds the escape character if needed. This is important for Android resource files
    as unescaped at symbols can be interpreted as references to resources.

    Args:
        text: The text to process

    Returns:
        The text with properly escaped at symbols
    """
    # Skip processing if the text is empty or None
    if not text:
        return text

    # Replace any standalone at symbols (not already escaped) with escaped versions
    # This regex looks for at symbols that aren't already preceded by a backslash
    return re.sub(r"(?<!\\)@", r"\\@", text)


def escape_special_chars(text: str) -> str:
    """
    Ensure all special characters in the text are properly escaped for Android resource files.

    This function applies all individual escape functions to handle apostrophes, percent signs,
    double quotes, and at symbols in a single pass.

    Args:
        text: The text to process

    Returns:
        The text with all special characters properly escaped
    """
    # Skip processing if the text is empty or None
    if not text:
        return text

    def _escape_plain(chunk: str) -> str:
        if not chunk:
            return chunk
        chunk = escape_apostrophes(chunk)
        chunk = escape_percent(chunk)
        chunk = escape_double_quotes(chunk)
        chunk = escape_at_symbol(chunk)
        return chunk

    def _escape_fragment(node) -> None:
        if node.text:
            node.text = _escape_plain(node.text)
        for child in node:
            _escape_fragment(child)
            if child.tail:
                child.tail = _escape_plain(child.tail)

    # Detect potential markup to avoid corrupting attributes
    contains_markup = "<" in text and ">" in text

    if contains_markup:
        try:
            parser = _create_secure_fragment_parser()
            wrapper = etree.fromstring(
                f"<__wrapper__>{text}</__wrapper__>", parser=parser
            )
            _escape_fragment(wrapper)
            return _serialize_inner_xml(wrapper)
        except etree.XMLSyntaxError:
            # Fall back to plain escaping if content isn't valid XML
            pass

    return _escape_plain(text)


# ------------------------------------------------------------------------------
# Auto-Translation Process
# ------------------------------------------------------------------------------


def _build_reference_string_examples(
    res: "AndroidResourceFile",
    default_strings: Dict[str, str],
    exclude_keys: Set[str],
    limit: int,
) -> List[Dict[str, str]]:
    """
    Collect previously translated string examples for context.

    Args:
        res: Target language resource file.
        default_strings: Dictionary of default language strings.
        exclude_keys: Keys currently being translated (omit from context).
        limit: Maximum number of examples to include.

    Returns:
        A list of dictionaries containing key, source, and existing translation.
    """
    examples: List[Dict[str, str]] = []

    for key in sorted(res.strings.keys()):
        if key in exclude_keys:
            continue

        source_text = default_strings.get(key)
        translation_text = res.strings.get(key)

        if not source_text or not translation_text:
            continue

        examples.append(
            {
                "key": key,
                "source": source_text,
                "existing_translation": translation_text,
            }
        )

        if len(examples) >= limit:
            break

    return examples


def _build_reference_plural_examples(
    res: "AndroidResourceFile",
    default_plurals: Dict[str, Dict[str, str]],
    exclude_names: Set[str],
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Collect previously translated plural examples for context.

    Args:
        res: Target language resource file.
        default_plurals: Default language plural definitions.
        exclude_names: Plural resource names currently being translated.
        limit: Maximum number of examples to include.

    Returns:
        A list of dictionaries containing plural name, default values,
        and existing translations.
    """
    examples: List[Dict[str, Any]] = []

    for plural_name in sorted(res.plurals.keys()):
        if plural_name in exclude_names:
            continue

        default_quantities = default_plurals.get(plural_name)
        existing_quantities = res.plurals.get(plural_name)

        if not default_quantities or not existing_quantities:
            continue

        examples.append(
            {
                "plural_name": plural_name,
                "source": dict(sorted(default_quantities.items())),
                "existing_translation": dict(sorted(existing_quantities.items())),
            }
        )

        if len(examples) >= limit:
            break

    return examples


def _translate_missing_strings(
    res: AndroidResourceFile,
    missing_strings: set,
    module_default_strings: Dict[str, str],
    lang: str,
    llm_config: LLMConfig,
    project_context: str,
    include_reference_context: bool,
    reference_context_limit: int,
) -> List[Dict]:
    """
    Helper function to translate missing strings for a resource file.
    Returns a list of translation results.

    Args:
        res: Resource file to update
        missing_strings: Set of missing string keys to translate
        module_default_strings: Dict of all default strings
        lang: Target language code
        llm_config: LLM provider configuration
        project_context: Optional project context
        include_reference_context: Whether to include existing translations as context
        reference_context_limit: Maximum number of reference examples to include

    Returns:
        List of translation result dictionaries
    """
    results = []

    # Filter out empty strings first
    non_empty_strings = {
        key: module_default_strings[key]
        for key in sorted(missing_strings)
        if module_default_strings[key].strip() != ""
    }

    # Handle empty strings separately
    for key in sorted(missing_strings):
        if module_default_strings[key].strip() == "":
            res.strings[key] = ""

    if not non_empty_strings:
        return results

    # Get the language name for prompts
    language_name = get_language_name(lang)

    # Build the base prompt (without specific strings)
    base_prompt = TRANSLATION_GUIDELINES + TRANSLATE_FINAL_TEXT.format(
        target_language=language_name
    )

    # Configure the system message
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=language_name)
    if project_context:
        system_message += f"\nProject context: {project_context}"

    logger.info(
        f"Translating {len(non_empty_strings)} strings for {lang} using batch mode"
    )

    # Split into chunks if needed
    string_keys = list(non_empty_strings.keys())
    for i in range(0, len(string_keys), MAX_BATCH_SIZE):
        chunk_keys = string_keys[i : i + MAX_BATCH_SIZE]
        chunk_dict = {key: non_empty_strings[key] for key in chunk_keys}

        logger.info(
            f"Translating batch of {len(chunk_dict)} strings (chunk {i // MAX_BATCH_SIZE + 1})"
        )

        reference_examples: List[Dict[str, str]] = []
        if include_reference_context and reference_context_limit > 0:
            reference_examples = _build_reference_string_examples(
                res=res,
                default_strings=module_default_strings,
                exclude_keys=set(chunk_keys),
                limit=reference_context_limit,
            )

        translate_kwargs = {
            "strings_dict": chunk_dict,
            "system_message": system_message,
            "user_prompt": base_prompt,
            "llm_config": llm_config,
        }

        if include_reference_context and reference_examples:
            translate_kwargs["reference_examples"] = reference_examples

        try:
            # Translate the entire batch
            translations = translate_strings_batch_with_llm(**translate_kwargs)

            # Process results
            for key, translated in translations.items():
                source_text = chunk_dict[key]

                # Ensure special characters are escaped
                translated = escape_special_chars(translated)

                logger.info(
                    f"Translated string '{key}' to {lang}: '{source_text}' -> '{translated}'"
                )

                # Update the resource
                res.strings[key] = translated
                res.modified = True

                # Add to results
                results.append(
                    {
                        "key": key,
                        "source": source_text,
                        "translation": translated,
                    }
                )

        except Exception as e:
            logger.error(f"Error translating string batch: {e}")
            raise

    return results


def _translate_missing_plurals(
    res: AndroidResourceFile,
    missing_plurals: Dict[str, Dict[str, str]],
    module_default_plurals: Dict[str, Dict[str, str]],
    lang: str,
    llm_config: LLMConfig,
    project_context: str,
    include_reference_context: bool,
    reference_context_limit: int,
) -> List[Dict]:
    """
    Helper function to translate missing plurals for a resource file.
    Returns a list of translation results.

    Args:
        res: Resource file to update
        missing_plurals: Dict of missing plural resources {name: {quantity: text}}
        module_default_plurals: Dict of default plurals for the module
        lang: Target language code
        llm_config: LLM provider configuration
        project_context: Optional project context
        include_reference_context: Whether to include existing translations as context
        reference_context_limit: Maximum number of reference examples to include

    Returns:
        List of translation result dictionaries
    """
    results = []

    if not missing_plurals:
        return results

    # Get the language name for prompts
    language_name = get_language_name(lang)

    # Build the base prompt (without specific plurals)
    base_prompt = (
        TRANSLATION_GUIDELINES
        + PLURAL_GUIDELINES_ADDITION
        + TRANSLATE_FINAL_TEXT.format(target_language=language_name)
    )

    # Configure the system message
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=language_name)
    if project_context:
        system_message += f"\nProject context: {project_context}"

    logger.info(
        f"Translating {len(missing_plurals)} plurals for {lang} using batch mode"
    )

    # Split into chunks if needed
    plural_names = list(missing_plurals.keys())
    for i in range(0, len(plural_names), MAX_BATCH_SIZE):
        chunk_names = plural_names[i : i + MAX_BATCH_SIZE]
        chunk_dict = {name: missing_plurals[name] for name in chunk_names}

        logger.info(
            f"Translating batch of {len(chunk_dict)} plurals (chunk {i // MAX_BATCH_SIZE + 1})"
        )

        reference_examples: List[Dict[str, Any]] = []
        if include_reference_context and reference_context_limit > 0:
            reference_examples = _build_reference_plural_examples(
                res=res,
                default_plurals=module_default_plurals,
                exclude_names=set(chunk_names),
                limit=reference_context_limit,
            )

        translate_kwargs = {
            "plurals_dict": chunk_dict,
            "system_message": system_message,
            "user_prompt": base_prompt,
            "llm_config": llm_config,
        }

        if include_reference_context and reference_examples:
            translate_kwargs["reference_examples"] = reference_examples

        try:
            # Translate the entire batch
            translations = translate_plurals_batch_with_llm(**translate_kwargs)

            # Process results
            for plural_name, generated_plural in translations.items():
                current_map = res.plurals.get(plural_name, {})

                # Ensure special characters are escaped
                for quantity, text in generated_plural.items():
                    generated_plural[quantity] = escape_special_chars(text)

                # Merge with existing translations
                merged = generated_plural.copy()
                merged.update(current_map)
                res.plurals[plural_name] = merged
                res.modified = True

                logger.info(
                    f"Translated plural group '{plural_name}' for language '{lang}': {res.plurals[plural_name]}"
                )

                # Add to results
                results.append(
                    {
                        "plural_name": plural_name,
                        "translations": res.plurals[plural_name],
                    }
                )

        except Exception as e:
            logger.error(f"Error translating plural batch: {e}")
            raise

    return results


def _collect_default_resources(
    module: AndroidModule,
) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    """
    Collect all default string and plural resources from a module.
    """
    module_default_strings: Dict[str, str] = {}
    module_default_plurals: Dict[str, Dict[str, str]] = defaultdict(dict)

    for res in module.language_resources.get("default", []):
        # Collect strings
        for key, val in res.strings.items():
            module_default_strings.setdefault(key, val)

        # Collect plurals
        for plural_name, quantities in res.plurals.items():
            for qty, text in quantities.items():
                module_default_plurals[plural_name].setdefault(qty, text)

    return module_default_strings, module_default_plurals


def _generate_translation_summary(translation_log: dict, total_translated: int) -> None:
    """
    Generate and log a summary of translations performed.
    """
    if total_translated <= 0:
        logger.info("No translations needed")
        return

    translated_info = {}
    for module_name, lang_details in translation_log.items():
        for lang, details in lang_details.items():
            entry = translated_info.setdefault(
                lang, {"strings": set(), "plurals": set()}
            )

            # Collect string keys
            for s in details.get("strings", []):
                entry["strings"].add(s["key"])

            # Collect plural names
            for p in details.get("plurals", []):
                entry["plurals"].add(p["plural_name"])

    # Log summary for each language
    for lang, items in translated_info.items():
        if not items["strings"] and not items["plurals"]:
            continue

        msg_parts = [f"Language '{lang}':"]

        if items["strings"]:
            msg_parts.append(
                f"Strings translated: {', '.join(sorted(items['strings']))}"
            )

        if items["plurals"]:
            msg_parts.append(
                f"Plurals translated: {', '.join(sorted(items['plurals']))}"
            )

        logger.info(" ".join(msg_parts))


def auto_translate_resources(
    modules: Dict[str, AndroidModule],
    llm_config: LLMConfig,
    project_context: str,
    include_reference_context: bool = True,
    reference_context_limit: int = DEFAULT_REFERENCE_CONTEXT_LIMIT,
) -> dict:
    """
    For each non-default language resource, auto-translate missing strings and plural items.
    Returns a translation_log dictionary with details of the translations performed.

    Args:
        modules: Dictionary of Android modules to process
        llm_config: LLM provider configuration
        project_context: Optional project context for translations
    """
    translation_log = {}
    total_translated = 0

    for module in modules.values():
        if "default" not in module.language_resources:
            logger.warning(
                f"Module '{module.name}' missing default resources; skipping auto translation."
            )
            continue

        # Collect default resources
        module_default_strings, module_default_plurals = _collect_default_resources(
            module
        )

        # Process each non-default language
        for lang, resources in module.language_resources.items():
            if lang == "default":
                continue

            # Initialize translation log for this language
            translation_log.setdefault(module.name, {})[lang] = {
                "strings": [],
                "plurals": [],
            }

            for res in resources:
                # Find missing translations
                missing_strings = set(module_default_strings.keys()) - set(
                    res.strings.keys()
                )

                # Find missing plurals
                missing_plurals = {}
                for plural_name, default_map in module_default_plurals.items():
                    current_map = res.plurals.get(plural_name, {})
                    if not current_map or set(current_map.keys()) != set(
                        default_map.keys()
                    ):
                        missing_plurals[plural_name] = default_map

                # Skip if nothing to translate
                if not missing_strings and not missing_plurals:
                    continue

                logger.info(
                    f"Auto-translating missing resources for module '{module.name}', language '{lang}'"
                )

                # Translate missing strings
                if missing_strings:
                    string_results = _translate_missing_strings(
                        res,
                        missing_strings,
                        module_default_strings,
                        lang,
                        llm_config,
                        project_context,
                        include_reference_context,
                        reference_context_limit,
                    )
                    translation_log[module.name][lang]["strings"].extend(string_results)
                    total_translated += len(string_results)

                # Translate missing plurals
                if missing_plurals:
                    plural_results = _translate_missing_plurals(
                        res,
                        missing_plurals,
                        module_default_plurals,
                        lang,
                        llm_config,
                        project_context,
                        include_reference_context,
                        reference_context_limit,
                    )
                    translation_log[module.name][lang]["plurals"].extend(plural_results)
                    total_translated += sum(
                        len(p["translations"]) for p in plural_results
                    )

                # Update the XML file if needed
                if res.modified:
                    update_xml_file(res)

    # Generate summary
    _generate_translation_summary(translation_log, total_translated)

    return translation_log


# ------------------------------------------------------------------------------
# Missing Translation Report
# ------------------------------------------------------------------------------


def _collect_default_translations(
    module: AndroidModule,
) -> Tuple[Set[str], Dict[str, Set[str]]]:
    """
    Collect all default string keys and plural quantities from a module.

    Args:
        module: The Android module to collect default translations from

    Returns:
        A tuple containing (set of string keys, dict of plural name -> quantities)
    """
    default_strings: Set[str] = set()
    default_plural_quantities: Dict[str, Set[str]] = {}

    if "default" not in module.language_resources:
        return default_strings, default_plural_quantities

    for resource in module.language_resources["default"]:
        default_strings.update(resource.strings.keys())
        for plural_name, quantities in resource.plurals.items():
            default_plural_quantities.setdefault(plural_name, set()).update(
                quantities.keys()
            )

    return default_strings, default_plural_quantities


def _collect_language_translations(
    resources: List[AndroidResourceFile],
) -> Tuple[Set[str], Dict[str, Set[str]]]:
    """
    Collect all string keys and plural quantities from a list of resources.

    Args:
        resources: List of AndroidResourceFile objects

    Returns:
        A tuple containing (set of string keys, dict of plural name -> quantities)
    """
    lang_strings: Set[str] = set()
    lang_plural_quantities: Dict[str, Set[str]] = {}

    for resource in resources:
        lang_strings.update(resource.strings.keys())
        for plural_name, quantities in resource.plurals.items():
            lang_plural_quantities.setdefault(plural_name, set()).update(
                quantities.keys()
            )

    return lang_strings, lang_plural_quantities


def _format_missing_translations(
    missing_strings: Set[str], missing_plurals: Dict[str, Set[str]]
) -> str:
    """
    Format missing translations for logging.

    Args:
        missing_strings: Set of missing string keys
        missing_plurals: Dict of missing plural names and quantities

    Returns:
        Formatted string describing what's missing
    """
    parts = []

    if missing_strings:
        parts.append(f"strings: {', '.join(sorted(missing_strings))}")

    if missing_plurals:
        plurals_part = ", ".join(
            [f"{k}({', '.join(sorted(v))})" for k, v in missing_plurals.items()]
        )
        parts.append(f"plurals: {plurals_part}")

    return " | ".join(parts)


def check_missing_translations(modules: Dict[str, AndroidModule]) -> dict:
    """
    For each module, compare non-default language resources against the union of keys
    in the default language. Checks for missing <string> keys and missing plural quantities.

    Args:
        modules: Dictionary of module identifiers to AndroidModule objects

    Returns:
        A dictionary of missing translations for potential reporting
    """
    logger.info("Missing Translations Report")
    missing_count = 0
    missing_report = {}

    for module in modules.values():
        module_has_missing = False
        module_log_lines = []

        if "default" not in module.language_resources:
            logger.warning(f"  No default resources for module '{module.name}'")
            continue

        # Collect defaults
        default_strings, default_plural_quantities = _collect_default_translations(
            module
        )

        # Check each non-default language
        for lang, resources in sorted(module.language_resources.items()):
            if lang == "default":
                continue

            # Collect this language's translations
            lang_strings, lang_plural_quantities = _collect_language_translations(
                resources
            )

            # Find what's missing
            missing_strings = default_strings - lang_strings
            missing_plurals: Dict[str, Set[str]] = {}

            for plural_name, def_qty in default_plural_quantities.items():
                current_qty = lang_plural_quantities.get(plural_name, set())
                diff = def_qty - current_qty
                if diff:
                    missing_plurals[plural_name] = diff

            # Log and report if anything is missing
            if missing_strings or missing_plurals:
                missing_count += 1
                module_has_missing = True

                # Format for logging
                missing_description = _format_missing_translations(
                    missing_strings, missing_plurals
                )
                module_log_lines.append(f"  [{lang}]: missing {missing_description}")

                # Add to the report dictionary
                if module.name not in missing_report:
                    missing_report[module.name] = {}
                missing_report[module.name][lang] = {
                    "strings": list(missing_strings),
                    "plurals": {
                        name: list(quantities)
                        for name, quantities in missing_plurals.items()
                    },
                }

        # Log for this module
        if module_has_missing:
            logger.info(f"Module: {module.name} (has missing translations)")
            for line in module_log_lines:
                logger.info(line)

    # Summary log
    if missing_count == 0:
        logger.info("All translations are complete.")

    return missing_report


# ------------------------------------------------------------------------------
# Translation Report Generator
# ------------------------------------------------------------------------------


def create_translation_report(translation_log):
    """
    Generate a Markdown formatted translation report as a string.
    """
    report = "# Translation Report\n\n"
    has_translations = False

    for module, languages in translation_log.items():
        module_has_translations = False
        module_report = f"## Module: {module}\n\n"
        languages_report = ""

        for lang, details in languages.items():
            has_string_translations = bool(details.get("strings"))
            has_plural_translations = bool(details.get("plurals"))

            if not (has_string_translations or has_plural_translations):
                continue

            module_has_translations = True
            has_translations = True
            # Get the language name from the code (will return lang code if name not found)
            lang_name = get_language_name(lang)
            languages_report += f"### Language: {lang_name}\n\n"

            if has_string_translations:
                languages_report += "| Key | Source Text | Translated Text |\n"
                languages_report += "| --- | ----------- | --------------- |\n"
                for entry in details["strings"]:
                    key = entry["key"]
                    source = entry["source"].replace("\n", " ")
                    translation = entry["translation"].replace("\n", " ")
                    languages_report += f"| {key} | {source} | {translation} |\n"
                languages_report += "\n"

            if has_plural_translations:
                languages_report += "#### Plural Resources\n\n"
                for plural in details["plurals"]:
                    plural_name = plural["plural_name"]
                    languages_report += f"**{plural_name}**\n\n"
                    languages_report += "| Quantity | Translated Text |\n"
                    languages_report += "| -------- | --------------- |\n"
                    for qty, text in plural["translations"].items():
                        languages_report += f"| {qty} | {text} |\n"
                    languages_report += "\n"

        if module_has_translations:
            report += module_report + languages_report

    if not has_translations:
        report += "No translations were performed."

    return report


# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------


def main() -> None:
    """
    Main entry point for the Android Resource Translator script.
    Parses command-line arguments or environment variables, finds resource files,
    checks for missing translations, and auto-translates them.
    """
    is_github = os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"
    if is_github:
        resources_paths_input = os.environ.get("INPUT_RESOURCES_PATHS")
        resources_paths = (
            [p.strip() for p in resources_paths_input.split(",") if p.strip()]
            if resources_paths_input
            else []
        )
        dry_run = os.environ.get("INPUT_DRY_RUN", "false").lower() == "true"
        log_trace = os.environ.get("INPUT_LOG_TRACE", "false").lower() == "true"

        # LLM Provider configuration
        llm_provider = os.environ.get("INPUT_LLM_PROVIDER", "openrouter").lower()
        model = os.environ.get("INPUT_MODEL") or os.environ.get(
            "INPUT_OPENAI_MODEL", "google/gemini-2.5-flash-preview-09-2025"
        )  # Support legacy param

        # API Keys - check provider-specific key first, then fall back to OpenAI key for compatibility
        if llm_provider == "openrouter":
            api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
                "OPENAI_API_KEY"
            )
        else:
            api_key = os.environ.get("OPENAI_API_KEY")

        # OpenRouter-specific settings
        openrouter_site_url = os.environ.get(
            "INPUT_OPENROUTER_SITE_URL",
            "https://github.com/duartebarbosadev/AndroidResourceTranslator",
        )
        openrouter_site_name = os.environ.get(
            "INPUT_OPENROUTER_SITE_NAME", "AndroidResourceTranslatorAction"
        )
        openrouter_send_site_info = (
            os.environ.get("INPUT_OPENROUTER_SEND_SITE_INFO", "true").lower() == "true"
        )

        project_context = os.environ.get("INPUT_PROJECT_CONTEXT", "")

        include_reference_context = (
            os.environ.get("INPUT_INCLUDE_REFERENCE_CONTEXT", "true").lower() == "true"
        )
        reference_context_limit_raw = os.environ.get(
            "INPUT_REFERENCE_CONTEXT_LIMIT", str(DEFAULT_REFERENCE_CONTEXT_LIMIT)
        )
        try:
            reference_context_limit = int(reference_context_limit_raw)
        except ValueError:
            print(
                f"Invalid INPUT_REFERENCE_CONTEXT_LIMIT value "
                f"('{reference_context_limit_raw}'); falling back to "
                f"{DEFAULT_REFERENCE_CONTEXT_LIMIT}"
            )
            reference_context_limit = DEFAULT_REFERENCE_CONTEXT_LIMIT

        ignore_folders_input = os.environ.get("INPUT_IGNORE_FOLDERS", "")
        ignore_folders = (
            [
                folder.strip()
                for folder in ignore_folders_input.split(",")
                if folder.strip()
            ]
            if ignore_folders_input
            else []
        )

        startup_message_prefix = "Running with parameters from environment variables."

    else:
        parser = argparse.ArgumentParser(description="Android Resource Translator")
        parser.add_argument(
            "resources_paths",
            nargs="+",
            help="Paths to Android project directories with resource files",
        )
        parser.add_argument(
            "-d",
            "--dry-run",
            action="store_true",
            help="Run in dry-run mode (only report missing translations without translating)",
        )
        parser.add_argument(
            "-l",
            "--log-trace",
            action="store_true",
            help="Log detailed trace information",
        )

        # LLM Provider arguments
        parser.add_argument(
            "--llm-provider",
            choices=["openai", "openrouter"],
            default="openrouter",
            help="LLM provider to use (default: openrouter)",
        )
        parser.add_argument(
            "--model",
            default="google/gemini-2.5-flash-preview-09-2025",
            help="Model to use for translation (default: google/gemini-2.5-flash-preview-09-2025)",
        )
        parser.add_argument(
            "--openai-model",
            dest="model_legacy",
            default=None,
            help="(Deprecated: use --model) OpenAI model to use",
        )

        # API Key arguments
        parser.add_argument(
            "--openai-api-key",
            dest="openai_api_key",
            default=None,
            help="OpenAI API key",
        )
        parser.add_argument(
            "--openrouter-api-key",
            dest="openrouter_api_key",
            default=None,
            help="OpenRouter API key",
        )

        # OpenRouter-specific arguments
        parser.add_argument(
            "--openrouter-site-url",
            default="https://github.com/duartebarbosadev/AndroidResourceTranslator",
            help="Your site URL for OpenRouter rankings (default: AndroidResourceTranslator GitHub repo)",
        )
        parser.add_argument(
            "--openrouter-site-name",
            default="AndroidResourceTranslatorAction",
            help="Your site name for OpenRouter rankings (default: AndroidResourceTranslatorAction)",
        )
        parser.add_argument(
            "--openrouter-send-site-info",
            action="store_true",
            default=True,
            help="Send site URL and name to OpenRouter for rankings (use --no-openrouter-send-site-info to disable)",
        )
        parser.add_argument(
            "--no-openrouter-send-site-info",
            dest="openrouter_send_site_info",
            action="store_false",
            help="Disable sending site URL and name to OpenRouter",
        )

        # Other arguments
        parser.add_argument(
            "--project-context",
            default="",
            help="Additional project context for translation prompts",
        )
        parser.add_argument(
            "--ignore-folders",
            default="",
            help="Comma separated list of folder names to ignore during scanning. "
            "If empty, .gitignore patterns will be used instead.",
        )
        parser.add_argument(
            "--include-reference-context",
            dest="include_reference_context",
            action="store_true",
            default=None,
            help="Include existing translations as additional context for the LLM (enabled by default).",
        )
        parser.add_argument(
            "--no-include-reference-context",
            dest="include_reference_context",
            action="store_false",
            help="Disable sending existing translations as context to the LLM.",
        )
        parser.add_argument(
            "--reference-context-limit",
            type=int,
            default=DEFAULT_REFERENCE_CONTEXT_LIMIT,
            help="Maximum number of existing translations to include as context (0 disables context).",
        )

        args = parser.parse_args()

        resources_paths = args.resources_paths
        dry_run = args.dry_run
        log_trace = args.log_trace

        # LLM Provider configuration
        llm_provider = args.llm_provider
        model = args.model_legacy or args.model  # Support legacy --openai-model

        # API Keys - determine based on provider (strict matching)
        if llm_provider == "openrouter":
            api_key = args.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        else:
            api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")

        openrouter_site_url = args.openrouter_site_url
        openrouter_site_name = args.openrouter_site_name
        openrouter_send_site_info = args.openrouter_send_site_info

        project_context = args.project_context
        include_reference_context = (
            args.include_reference_context
            if args.include_reference_context is not None
            else True
        )
        reference_context_limit = args.reference_context_limit
        ignore_folders = [
            folder.strip()
            for folder in args.ignore_folders.split(",")
            if folder.strip()
        ]
        # Don't print args because it will come with the API KEY
        startup_message_prefix = "Running with command-line parameters."

    if reference_context_limit < 0:
        print(
            f"Reference context limit {reference_context_limit} is negative; "
            "resetting to 0 (disables context)."
        )
        reference_context_limit = 0

    include_reference_context = (
        include_reference_context and reference_context_limit > 0
    )

    runtime_details = (
        f"Resources Paths: {resources_paths}, Dry Run: {dry_run}, "
        f"Log Trace: {log_trace}, "
        f"LLM Provider: {llm_provider}, Model: {model}, "
        f"Project Context: {project_context}, Ignore Folders: {ignore_folders}, "
        f"Include Reference Context: {include_reference_context}, "
        f"Reference Context Limit: {reference_context_limit}"
    )
    if startup_message_prefix:
        print(f"{startup_message_prefix} {runtime_details}")
    else:
        print(runtime_details)

    configure_logging(log_trace)

    # Early validation: Check API key if not in dry-run mode
    if not dry_run and not api_key:
        env_var_name = (
            "OPENROUTER_API_KEY" if llm_provider == "openrouter" else "OPENAI_API_KEY"
        )
        print("\n========================================")
        print("ERROR: API key not found!")
        print("========================================")
        print(
            "Translation is enabled (not in dry-run mode) but no API key was provided."
        )
        print("\nTo fix this:")
        print(
            f"\n1. For GitHub Actions, add {env_var_name} to your repository secrets:"
        )
        print("   - Go to Settings > Secrets and variables > Actions")
        print(f"   - Add a new secret named: {env_var_name}")
        print("   - Pass it via env in your workflow:")
        print("     env:")
        print(f"       {env_var_name}: ${{{{ secrets.{env_var_name} }}}}")
        print("\n2. For local execution, set the environment variable:")
        print(f"   export {env_var_name}=your_key_here")
        print("\n3. Or pass it as a command-line argument:")
        print(f"   --{llm_provider}-api-key YOUR_KEY")
        if llm_provider == "openrouter":
            print("\nGet your API key at: https://openrouter.ai/keys")
        else:
            print("\nGet your API key at: https://platform.openai.com/api-keys")
        print("========================================\n")
        sys.exit(1)

    if not resources_paths:
        print("Error: 'resources_paths' input not provided.")
        sys.exit(1)
    for path in resources_paths:
        if not os.path.exists(path):
            logger.error(f"Error: The specified path {path} does not exist!")
            sys.exit(1)

    # Merge resources from multiple resource directories.
    merged_modules: Dict[str, AndroidModule] = {}
    for res_path in resources_paths:
        modules = find_resource_files(res_path, ignore_folders)
        for identifier, mod in modules.items():
            if identifier in merged_modules:
                # Merge language_resources from modules with the same unique identifier.
                for lang, resources in mod.language_resources.items():
                    merged_modules[identifier].language_resources.setdefault(
                        lang, []
                    ).extend(resources)
            else:
                merged_modules[identifier] = mod

    if not merged_modules:
        logger.error("No resource files found!")
        sys.exit(1)

    modules_count = len(merged_modules)
    resources_count = sum(
        len(resources)
        for mod in merged_modules.values()
        for resources in mod.language_resources.values()
    )
    logger.info(f"Found {modules_count} modules with {resources_count} resource files")

    if log_trace:
        for module in sorted(merged_modules.values(), key=lambda m: m.name):
            module.print_resources()

    translation_log = {}
    # If not in dry-run mode, run the translation process.
    if not dry_run:
        # Create LLM configuration
        try:
            llm_config = LLMConfig(
                provider=LLMProvider(llm_provider),
                api_key=api_key,
                model=model,
                site_url=openrouter_site_url if llm_provider == "openrouter" else None,
                site_name=openrouter_site_name
                if llm_provider == "openrouter"
                else None,
                send_site_info=openrouter_send_site_info
                if llm_provider == "openrouter"
                else True,
            )
        except ValueError as e:
            logger.error(f"Error creating LLM configuration: {e}")
            sys.exit(1)

        logger.info(f"Starting translation using {llm_provider} with model {model}")
        translation_log = auto_translate_resources(
            merged_modules,
            llm_config,
            project_context,
            include_reference_context=include_reference_context,
            reference_context_limit=reference_context_limit,
        )

    # Whether or not auto-translation was performed, still check for missing translations.
    check_missing_translations(merged_modules)

    # Generate the translation report (this will be empty if no auto-translation occurred).
    report_output = create_translation_report(translation_log)

    # Output the report
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            # Use a unique delimiter to prevent collision if translations contain "EOF"
            delimiter = "EOF_TRANSLATION_REPORT_9d8e7f6a"
            print(f"translation_report<<{delimiter}", file=f)
            print(report_output, file=f)
            print(delimiter, file=f)
    else:
        if not dry_run:
            print("\nTranslation Report:")
            print(report_output)


if __name__ == "__main__":
    main()
