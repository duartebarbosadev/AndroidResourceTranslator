#!/usr/bin/env python3
"""
Android Resource Translation Checker & Auto-Translator

This script scans Android resource files (strings.xml) for string and plural resources,
reports missing translations, and can automatically translate missing entries using OpenAI.
"""
import logging
import sys
import json
import re
import os
from pathlib import Path
from xml.etree import ElementTree
from collections import defaultdict
from typing import Dict, Set, List, Tuple
from lxml import etree

# Import git utilities from separate module
from git_utils import (
    parse_gitignore, 
    parse_gitignore_file, 
    find_all_gitignores, 
    is_ignored_by_gitignore, 
    is_ignored_by_gitignores
)

# ------------------------------------------------------------------------------
# Translation Prompt Constants
# ------------------------------------------------------------------------------
TRANSLATION_GUIDELINES = """\
Follow these guidelines carefully.
**Purpose & Context:**  
This translation is for an Android application's UI. Use concise, clear language consistent with standard Android UI conventions. Do not alter the intended meaning of the text.

**Formatting & Structure:**  
- Keep all placeholders (e.g., %d, %s, %1$s) exactly as in the source. If the target language requires reordering, ensure that the same placeholders appear and are correctly positioned according to the language's syntax.
- Maintain the integrity of HTML, CDATA, or XML structures; translate only the textual content.  
- Preserve all whitespace, line breaks, and XML formatting exactly as in the source.  
- Escape apostrophes with a backslash (\\') as required by Android.

**System Terms:**  
Do not translate system state words (e.g., WARNING, FAILED, SUCCESS) or any technical and branded terms. Always leave these in their original English, uppercase form.

**Terminology & Natural Expressions:**  
Translate in a natural, concise style that matches standard Android UI conventions.
Avoid overly literal translations that may sound awkward. When a technical term or proper noun is more recognizable in English for that language, keep it in English.

**Handling Idioms and Metaphors:**
For idiomatic expressions or culturally-charged phrases, translate the intended meaning rather than literally. For example, phrases like "brain rot" if there's no direct translation should be translated to convey "mental decay" in a way that sounds natural in the target language.

**Tone and Formality Consistency:**
Maintain consistent formality throughout the translation based on these principles:
- Default to a conversational but respectful tone appropriate for a consumer android app
- Match the formality level commonly used in popular, well-localized apps in the target language
- When unsure, prefer slightly more formal over too casual, as this is generally safer across cultures
- Use direct address forms (equivalent to "you" in English) that feel natural in the target language

**Technical Terms:**
Terms like 'accessibility service' and app-specific features should be translated using standard UI terminology in the target language.

**Quality Verification:**
After completing translation:
1. Verify no characters from other writing systems have been accidentally included
2. Ensure consistent terminology is used throughout
3. Check that idiomatic expressions are natural in the target language
4. Confirm that the formality level is appropriate and consistent

**Examples (Portuguese of Portugal):**  
- "Message Sent" → ✅ "Mensagem enviada" (❌ "Mensagem foi enviada")  
- "Upload Speed" → ✅ "Velocidade de upload" (❌ "Velocidade de envio")
Always refer to standard, widely accepted terms for the target language's user interface.

**Dialect and Regional Vocabulary:**  
Unless otherwise specified, use always the vocabulary appropriate to the target dialect (e.g., **pt -> Português de Portugal**) and avoid terms from other variants.

**General Note:**  
Preserve all proper nouns, feature names, and trademarked or branded terms in their original English form.

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
   *Example:* If the English source is `<item quantity="other">%d day left</item>`, the target translation should include:
   - `<item quantity="zero">No days left</item>`
   - `<item quantity="one">%d day left</item>`
   - `<item quantity="many">%d days left</item>`
   (Adjust the text according to correct singular and plural usage in the target language. Refer to the target language's guidelines for keys such as zero, one, two, few, many, and other.)
2. **Output Format:**  
   Return ONLY a JSON object containing the plural mapping as a single plain line. Do not include any markdown formatting, code blocks, or additional commentary unless already present in the source.
"""
SYSTEM_MESSAGE_TEMPLATE = """\
You are a professional translator translating textual UI elements within an Android from English into {target_language}. Follow user guidelines closely.
"""
TRANSLATE_FINAL_TEXT = """\
Translate the following string resource provided after the dashed line to the values-{target_language}/string.xml file for the language: {target_language}
----------
"""

# ------------------------------------------------------------------------------
# Logger Setup
# ------------------------------------------------------------------------------

logger = logging.getLogger(__name__)

def configure_logging(trace: bool) -> None:
    """Configure logging to console and optionally to a file."""
    log_level = logging.DEBUG if trace else logging.INFO
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.setLevel(log_level)
    logger.addHandler(handler)
    
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
        self.strings: Dict[str, str] = {}          # key -> string value
        self.plurals: Dict[str, Dict[str, str]] = {} # key -> {quantity -> text}
        self.modified: bool = False  # Flag to track if any changes are made
        self.parse_file()

    def parse_file(self) -> None:
        """Parses the strings.xml file and extracts <string> and <plurals> elements. Skips resources with translatable="false"."""
        try:
            tree = ElementTree.parse(self.path)
            root = tree.getroot()
            for elem in root:
                translatable = elem.attrib.get("translatable", "true").lower()
                if translatable == "false":
                    continue

                if elem.tag == "string":
                    name = elem.attrib.get("name")
                    if name:
                        self.strings[name] = (elem.text or "").strip()
                elif elem.tag == "plurals":
                    name = elem.attrib.get("name")
                    if name:
                        quantities: Dict[str, str] = {}
                        for item in elem.findall("item"):
                            quantity = item.attrib.get("quantity")
                            if quantity:
                                quantities[quantity] = (item.text or "").strip()
                        self.plurals[name] = quantities
            logger.debug(f"Parsed {len(self.strings)} strings and {len(self.plurals)} plurals from {self.path}")
        except ElementTree.ParseError as pe:
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
        self.language_resources: Dict[str, List[AndroidResourceFile]] = defaultdict(list)

    def add_resource(self, language: str, resource: AndroidResourceFile) -> None:
        logger.debug(f"Added resource for '{language}' in module '{self.name}': {resource.path.name}")
        self.language_resources[language].append(resource)

    def print_resources(self) -> None:
        logger.info(f"Module: {self.name} (ID: {self.identifier})")
        for language, resources in sorted(self.language_resources.items()):
            for resource in resources:
                sums = resource.summary()
                logger.info(f"  [{language}] {resource.path} | Strings: {sums['strings']}, Plurals: {sums['plurals']}")


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



def find_resource_files(resources_path: str, ignore_folders: List[str] = None) -> Dict[str, AndroidModule]:
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
            logger.info(f"Using {total_patterns} patterns from .gitignore files in directory hierarchy")
        else:
            # Fallback to just the root .gitignore if no ignore_folders specified
            gitignore_patterns = parse_gitignore(resources_path)
            if gitignore_patterns:
                logger.info(f"Using {len(gitignore_patterns)} patterns from .gitignore in {resources_dir}")
            else:
                gitignore_patterns = []

    # Recursively find all strings.xml files
    for xml_file_path in resources_dir.rglob("strings.xml"):
        # Skip files in ignored directories
        if ignore_folders and any(ignored in str(xml_file_path.parts) for ignored in ignore_folders):
            logger.debug(f"Skipping {xml_file_path} (matched ignore_folders)")
            continue
        elif all_gitignores:
            # Use the full hierarchical gitignore implementation
            if is_ignored_by_gitignores(xml_file_path, all_gitignores):
                logger.debug(f"Skipping {xml_file_path} (matched gitignore pattern from hierarchy)")
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
            logger.debug(f"Created module entry for '{module_name}' (key: {module_key})")
            
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
        m = re.match(r'\n(\s+)', root[0].tail or "")
        if m:
            sample_indent = m.group(1)

    # Ensure proper indentation before the first child
    if not root.text or not root.text.strip():
        root.text = "\n" + sample_indent

    # --- Handle <string> elements ---
    
    # Map existing string elements by name for quick lookup
    original_root_count = len(root)
    existing_string_elements = {elem.get("name"): elem for elem in root if elem.tag == "string"}
    
    # Ensure consistent formatting between elements
    if original_root_count > 0:
        last_original = root[original_root_count - 1]
        if not last_original.tail or not last_original.tail.endswith(sample_indent):
            last_original.tail = "\n" + sample_indent

    # Process each string resource
    for key, translation in resource.strings.items():
        if key in existing_string_elements:
            # Update existing string if the text has changed
            if existing_string_elements[key].text != translation:
                existing_string_elements[key].text = translation
                logger.debug(f"Updated <string name='{key}'> element in {resource.path}")
        else:
            # Create and append a new string element
            new_elem = etree.Element("string", name=key)
            new_elem.text = translation
            new_elem.tail = "\n" + sample_indent
            root.append(new_elem)
            logger.debug(f"Appended <string name='{key}'> element to {resource.path}")

    # --- Handle <plurals> elements ---
    
    # Map existing plurals elements by name
    existing_plural_elements = {elem.get("name"): elem for elem in root if elem.tag == "plurals"}
    
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
        existing_quantity_items = {child.get("quantity"): child 
                                 for child in plural_elem 
                                 if child.tag == "item"}
        
        # Process each quantity variation
        for qty, translation in items.items():
            if qty in existing_quantity_items:
                # Update existing item if text has changed
                if existing_quantity_items[qty].text != translation:
                    existing_quantity_items[qty].text = translation
                    logger.debug(f"Updated plural '{plural_name}' quantity '{qty}' in {resource.path}")
            else:
                # Create and append a new item element
                new_item = etree.Element("item", quantity=qty)
                new_item.text = translation
                new_item.tail = "\n" + item_indent
                plural_elem.append(new_item)
                logger.debug(f"Added plural '{plural_name}' quantity '{qty}' to {resource.path}")
                
        # Ensure proper formatting for the last item in a plurals element
        if len(plural_elem) > 0:
            plural_elem[-1].tail = "\n" + sample_indent

    # Ensure the closing tag of the root element is properly formatted
    if len(root) > 0:
        root[-1].tail = "\n"

    try:
        # Serialize and write the XML back to the file
        xml_bytes = etree.tostring(tree, encoding="utf-8", xml_declaration=True, pretty_print=True)
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
                flags=re.IGNORECASE
            )
            f.seek(0)
            f.write(content)
            f.truncate()
            
        logger.info(f"Updated XML file: {resource.path}")
        resource.modified = False
    except Exception as e:
        logger.error(f"Error writing XML file {resource.path}: {e}")
        raise


def indent_xml(elem: ElementTree.Element, level: int = 0) -> None:
    """
    Recursively indent an XML element tree for pretty-printing.
    
    This utility function adds appropriate indentation to an XML element tree,
    making the XML output more readable by humans. It works by modifying the 
    text and tail attributes of each element to include newlines and spaces.
    
    The function handles both container elements (with children) and leaf elements 
    (without children) differently to ensure proper formatting:
    - Container elements get their children indented one level deeper
    - The last child in a container receives special formatting for its tail
    - Leaf elements get proper indentation for their tail content
    
    Args:
        elem: The XML element to indent
        level: The current indentation level (0 for root element)
        
    Returns:
        None - the element tree is modified in place
    """
    pad = "    "  # Standard 4 spaces per indentation level

    # Elements with children need special handling
    if len(elem):
        # Indent the text immediately inside the opening tag if it's just whitespace
        if not elem.text or not elem.text.strip():
            elem.text = "\n" + (level + 1) * pad
        
        # Process all children except the last one
        for child in elem[:-1]:
            # Recursively indent the child
            indent_xml(child, level + 1)
            # Add appropriate indentation after the child's closing tag
            if not child.tail or not child.tail.strip():
                child.tail = "\n" + (level + 1) * pad
        
        # Handle the last child specially
        indent_xml(elem[-1], level + 1)
        # Indent after the last child's closing tag (one level less)
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = "\n" + level * pad
    
    # For elements without children, just handle the tail if we're not at the root
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = "\n" + level * pad


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


def call_openai(prompt: str, system_message: str, api_key: str, model: str) -> str:
    """
    Call the OpenAI API to generate translated text using the chat completions endpoint.
    
    This function handles the communication with OpenAI's API to generate translations.
    It sets up a chat completion request with system and user messages to provide
    appropriate context and instructions for translation.
    
    The function uses a temperature of 0 to ensure consistent, deterministic translations.
    This is important for maintaining coherence across different runs and avoiding
    creative variations that could be inappropriate for UI strings.
    
    Args:
        prompt: The user prompt containing the text to translate and guidelines
        system_message: The system message defining the translator's role and context
        api_key: OpenAI API key for authentication
        model: The specific OpenAI model to use (e.g., "gpt-4o-mini", "gpt-4")
        
    Returns:
        The translated text extracted from the API response
        
    Raises:
        ImportError: If the OpenAI Python package is not installed
        Exception: For any API-related errors (authentication, rate limits, etc.)
    """
    # Check if the OpenAI package is installed
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("OpenAI package not installed. Please install it using 'pip install openai'.")
        raise ImportError("OpenAI package not installed. Run 'pip install openai' first.")
    
    try:
        # Initialize the OpenAI client with the provided API key
        client = OpenAI(api_key=api_key)
        
        # Log the request details at debug level
        logger.debug(
            f"Sending request to OpenAI (model: {model}) with system prompt: {system_message} "
            f"and user prompt:\n{prompt}"
        )
        
        # Make the API call using the chat completions endpoint
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            temperature=0,  # Use deterministic output for consistent translations
        )
        
        # Extract and clean up the generated text
        translation = response.choices[0].message.content.strip()
        
        # Log the response at debug level
        logger.debug(f"Received response from OpenAI: {translation}")
        logger.debug("\n-------\n")

        return translation
        
    except Exception as e:
        # Log any errors that occur during the API call
        logger.error(f"Error calling OpenAI API: {e}")
        raise


def translate_text(text: str, target_language: str, api_key: str, model: str, project_context: str) -> str:
    """
    Translate a single string resource to the target language using OpenAI.
    
    This function handles the translation of a simple text string (typically from an 
    Android string resource) to the specified target language. It builds a prompt 
    using the translation guidelines, sends it to the OpenAI API, and returns the 
    translated result.
    
    The translation follows specific guidelines for mobile UI strings, maintaining
    proper formatting, placeholders, and Android-specific requirements. If project 
    context is provided, it's included to help provide more accurate translations.
    
    Args:
        text: The source text to translate
        target_language: The target language code (e.g., "es", "fr", "zh-rCN")
        api_key: OpenAI API key for authentication
        model: OpenAI model to use for translation
        project_context: Optional additional context about the project
        
    Returns:
        The translated text in the target language
        
    Note:
        Empty strings are returned as-is without calling the API
    """
    # Don't process empty strings
    if text.strip() == "":
        return ""
        
    # Build the prompt with translation guidelines and the source text
    prompt = (TRANSLATION_GUIDELINES +
              TRANSLATE_FINAL_TEXT.format(target_language=target_language) +
              text)
              
    # Configure the system message for the API call
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=target_language)
    if project_context:
        system_message += f"\nProject context: {project_context}"
        
    # Call OpenAI API to get the translation
    translated = call_openai(prompt, system_message, api_key, model)
    
    # Ensure apostrophes are properly escaped
    translated = escape_apostrophes(translated)

    return translated


def translate_plural_text(source_plural: Dict[str, str], target_language: str, api_key: str, model: str, project_context: str) -> Dict[str, str]:
    """
    Translate Android plural resources to the target language using OpenAI.
    
    This function handles the translation of plural string resources, which require
    special handling because different languages have different plural forms. For
    example, English typically has two forms (singular/plural), while Slavic languages 
    may have multiple forms for different quantities.
    
    The function:
    1. Converts the source plural dictionary to JSON format
    2. Creates a prompt with special guidelines for plurals
    3. Calls the OpenAI API to get translations for all plural forms
    4. Parses the JSON response back into a dictionary
    
    Args:
        source_plural: Dictionary mapping plural quantity keys to strings
                      (e.g., {"one": "%d day", "other": "%d days"})
        target_language: The target language code (e.g., "es", "fr", "zh-rCN")
        api_key: OpenAI API key for authentication
        model: OpenAI model to use for translation
        project_context: Optional additional context about the project
        
    Returns:
        Dictionary mapping plural quantity keys to translated strings
        
    Raises:
        Exception: If there's an error parsing the JSON response
    """
    # Convert source plural forms to JSON format
    source_json = json.dumps(source_plural, indent=2)
    
    # Build the prompt with both standard and plural-specific guidelines
    prompt = (TRANSLATION_GUIDELINES +
              PLURAL_GUIDELINES_ADDITION +
              TRANSLATE_FINAL_TEXT.format(target_language=target_language) +
              source_json)
              
    # Configure the system message for the API call
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=target_language)
    if project_context:
        system_message += f"\nProject context: {project_context}"
    
    # Call OpenAI API to get the translation
    translation_output = call_openai(prompt, system_message, api_key, model)
    
    # Parse the response as JSON
    try:
        plural_dict = json.loads(translation_output)
        
        # Validate the response is a dictionary
        if isinstance(plural_dict, dict):
            # Ensure apostrophes are properly escaped in all plural forms
            for quantity, text in plural_dict.items():
                plural_dict[quantity] = escape_apostrophes(text)
            return plural_dict
        else:
            # Fallback if not a proper dictionary
            logger.warning(f"Unexpected plural translation format: {translation_output}")
            return {"other": escape_apostrophes(translation_output)}
    except Exception as e:
        logger.error(f"Error parsing plural translation JSON: {e}. Falling back to single form.")
        raise

# ------------------------------------------------------------------------------
# Translation Validation
# ------------------------------------------------------------------------------

def validate_translation(source_text: str, current_translation: str, target_language: str, is_plural: bool = False) -> str:
    """
    Prompt the user to validate and optionally correct a translation.
    
    This function provides an interactive way for users to review translations
    before they are applied. It displays the source text and its translation,
    then asks the user if they accept it or want to provide a correction.
    
    The function is particularly useful for:
    - Reviewing automatically generated translations
    - Correcting any mistakes or awkward phrasing
    
    Args:
        source_text: The original text in the source language
        current_translation: The translated text to validate
        target_language: The language code of the translation
        is_plural: Whether this is a plural resource (for display purposes)
        
    Returns:
        The validated translation (either the original or a corrected version)
    """
    print("\n----- Validate Translation -----")
    
    # Display appropriate resource type label
    resource_type = "Plural Resource" if is_plural else "String Resource"
    
    # Show the source and translated text to the user
    print(f"Source {resource_type}: {source_text}")
    print(f"Current Translation in {target_language}: {current_translation}")
    
    # Ask the user if they accept the translation
    response = input("Do you accept this translation? (y/n): ").strip().lower()
    
    if response == "y":
        # User accepts the translation as-is
        return current_translation
    else:
        # User wants to provide a correction
        new_trans = input("Enter the corrected translation: ").strip()
        return new_trans

# ------------------------------------------------------------------------------
# Auto-Translation Process
# ------------------------------------------------------------------------------

def _translate_missing_strings(
    res: AndroidResourceFile,
    missing_strings: set,
    module_default_strings: Dict[str, str],
    lang: str,
    openai_api_key: str,
    openai_model: str,
    project_context: str,
    validate_translations: bool
) -> List[Dict]:
    """
    Helper function to translate missing strings for a resource file.
    Returns a list of translation results.
    """
    results = []
    for key in sorted(missing_strings):
        source_text = module_default_strings[key]
        # Skip empty strings
        if source_text.strip() == "":
            res.strings[key] = ""
            continue
            
        try:
            # Translate the string
            translated = translate_text(
                source_text, 
                target_language=lang,
                api_key=openai_api_key, 
                model=openai_model,
                project_context=project_context
            )
            
            logger.info(f"Translated string '{key}' to {lang}: '{source_text}' -> '{translated}'")

            # Validate if required
            if validate_translations:
                translated = validate_translation(source_text, translated, target_language=lang)
                
            # Update the resource
            res.strings[key] = translated
            res.modified = True
            
            # Add to results
            results.append({
                "key": key,
                "source": source_text,
                "translation": translated,
            })
        except Exception as e:
            logger.error(f"Error translating string '{key}': {e}")
            raise
            
    return results


def _translate_missing_plurals(
    res: AndroidResourceFile,
    missing_plurals: Dict[str, Dict[str, str]],
    lang: str,
    openai_api_key: str,
    openai_model: str,
    project_context: str,
    validate_translations: bool
) -> List[Dict]:
    """
    Helper function to translate missing plurals for a resource file.
    Returns a list of translation results.
    """
    results = []
    for plural_name, default_map in missing_plurals.items():
        current_map = res.plurals.get(plural_name, {})
        try:
            # Generate plural translations
            generated_plural = translate_plural_text(
                default_map, 
                target_language=lang,
                api_key=openai_api_key, 
                model=openai_model,
                project_context=project_context
            )
            
            # Merge with existing translations
            merged = generated_plural.copy()
            merged.update(current_map)
            res.plurals[plural_name] = merged
            res.modified = True
            
            logger.info(f"Translated plural group '{plural_name}' for language '{lang}': {res.plurals[plural_name]}")
            
            # Validate if required
            if validate_translations:
                for plural_key in generated_plural:
                    if plural_key in current_map:
                        continue
                    src_text = default_map.get(plural_key, default_map.get("other", ""))
                    validated = validate_translation(
                        src_text, 
                        res.plurals[plural_name][plural_key],
                        target_language=lang, 
                        is_plural=True
                    )
                    res.plurals[plural_name][plural_key] = validated
                    
            # Add to results
            results.append({
                "plural_name": plural_name,
                "translations": res.plurals[plural_name],
            })
        except Exception as e:
            logger.error(f"Error translating plural '{plural_name}': {e}")
            raise
            
    return results


def _collect_default_resources(module: AndroidModule) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
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
            entry = translated_info.setdefault(lang, {'strings': set(), 'plurals': set()})
            
            # Collect string keys
            for s in details.get("strings", []):
                entry['strings'].add(s["key"])
                
            # Collect plural names
            for p in details.get("plurals", []):
                entry['plurals'].add(p["plural_name"])
                
    # Log summary for each language
    for lang, items in translated_info.items():
        if not items['strings'] and not items['plurals']:
            continue
            
        msg_parts = [f"Language '{lang}':"]
        
        if items['strings']:
            msg_parts.append(f"Strings translated: {', '.join(sorted(items['strings']))}")
            
        if items['plurals']:
            msg_parts.append(f"Plurals translated: {', '.join(sorted(items['plurals']))}")
            
        logger.info(" ".join(msg_parts))


def auto_translate_resources(modules: Dict[str, AndroidModule],
                             openai_api_key: str,
                             openai_model: str,
                             project_context: str,
                             validate_translations: bool = False) -> dict:
    """
    For each non-default language resource, auto-translate missing strings and plural items.
    Returns a translation_log dictionary with details of the translations performed.
    """
    translation_log = {}
    total_translated = 0

    for module in modules.values():
        if "default" not in module.language_resources:
            logger.warning(f"Module '{module.name}' missing default resources; skipping auto translation.")
            continue

        # Collect default resources
        module_default_strings, module_default_plurals = _collect_default_resources(module)

        # Process each non-default language
        for lang, resources in module.language_resources.items():
            if lang == "default":
                continue
                
            # Initialize translation log for this language
            translation_log.setdefault(module.name, {})[lang] = {"strings": [], "plurals": []}
            
            for res in resources:
                # Find missing translations
                missing_strings = set(module_default_strings.keys()) - set(res.strings.keys())
                
                # Find missing plurals
                missing_plurals = {}
                for plural_name, default_map in module_default_plurals.items():
                    current_map = res.plurals.get(plural_name, {})
                    if not current_map or set(current_map.keys()) != set(default_map.keys()):
                        missing_plurals[plural_name] = default_map
                        
                # Skip if nothing to translate
                if not missing_strings and not missing_plurals:
                    continue
                
                logger.info(f"Auto-translating missing resources for module '{module.name}', language '{lang}'")
                
                # Translate missing strings
                if missing_strings:
                    string_results = _translate_missing_strings(
                        res, missing_strings, module_default_strings, lang,
                        openai_api_key, openai_model, project_context, validate_translations
                    )
                    translation_log[module.name][lang]["strings"].extend(string_results)
                    total_translated += len(string_results)
                
                # Translate missing plurals
                if missing_plurals:
                    plural_results = _translate_missing_plurals(
                        res, missing_plurals, lang,
                        openai_api_key, openai_model, project_context, validate_translations
                    )
                    translation_log[module.name][lang]["plurals"].extend(plural_results)
                    total_translated += sum(len(p["translations"]) for p in plural_results)
                
                # Update the XML file if needed
                if res.modified:
                    update_xml_file(res)
    
    # Generate summary
    _generate_translation_summary(translation_log, total_translated)
        
    return translation_log

# ------------------------------------------------------------------------------
# Missing Translation Report
# ------------------------------------------------------------------------------

def _collect_default_translations(module: AndroidModule) -> Tuple[Set[str], Dict[str, Set[str]]]:
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
            default_plural_quantities.setdefault(plural_name, set()).update(quantities.keys())
            
    return default_strings, default_plural_quantities


def _collect_language_translations(resources: List[AndroidResourceFile]) -> Tuple[Set[str], Dict[str, Set[str]]]:
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
            lang_plural_quantities.setdefault(plural_name, set()).update(quantities.keys())
            
    return lang_strings, lang_plural_quantities


def _format_missing_translations(
    missing_strings: Set[str], 
    missing_plurals: Dict[str, Set[str]]
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
        plurals_part = ", ".join([
            f"{k}({', '.join(sorted(v))})" 
            for k, v in missing_plurals.items()
        ])
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
        default_strings, default_plural_quantities = _collect_default_translations(module)

        # Check each non-default language
        for lang, resources in sorted(module.language_resources.items()):
            if lang == "default":
                continue
                
            # Collect this language's translations
            lang_strings, lang_plural_quantities = _collect_language_translations(resources)
                    
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
                missing_description = _format_missing_translations(missing_strings, missing_plurals)
                module_log_lines.append(f"  [{lang}]: missing {missing_description}")
                
                # Add to the report dictionary
                if module.name not in missing_report:
                    missing_report[module.name] = {}
                missing_report[module.name][lang] = {
                    "strings": list(missing_strings),
                    "plurals": {name: list(quantities) for name, quantities in missing_plurals.items()}
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
            languages_report += f"### Language: {lang}\n\n"
            
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
    import os
    import argparse

    is_github = os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"
    if is_github:
        resources_paths_input = os.environ.get("INPUT_RESOURCES_PATHS")
        resources_paths = [p.strip() for p in resources_paths_input.split(',') if p.strip()] if resources_paths_input else []
        auto_translate = os.environ.get("INPUT_AUTO_TRANSLATE", "false").lower() == "true"
        # No manual validation on GitHub; force it off.
        validate_translations = False  
        log_trace = os.environ.get("INPUT_LOG_TRACE", "false").lower() == "true"
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        openai_model = os.environ.get("INPUT_OPENAI_MODEL", "gpt-4o-mini")
        project_context = os.environ.get("INPUT_PROJECT_CONTEXT", "")
        ignore_folders_input = os.environ.get("INPUT_IGNORE_FOLDERS", "")
        ignore_folders = [folder.strip() for folder in ignore_folders_input.split(',') if folder.strip()] if ignore_folders_input else []

        print(
            "Running with parameters from environment variables."
            f"Resources Paths: {resources_paths}, Auto Translate: {auto_translate}, "
            f"Validate Translations: {validate_translations}, Log Trace: {log_trace}, "
            f"OpenAI Model: {openai_model}, "
            f"Project Context: {project_context}, Ignore Folders: {ignore_folders}"
        )

    else:
        parser = argparse.ArgumentParser(description="Android Resource Translator")
        parser.add_argument("resources_paths", nargs="+", help="Paths to Android project directories with resource files")
        parser.add_argument("-a", "--auto-translate", action="store_true",
                            help="Automatically translate missing resources using OpenAI")
        parser.add_argument("-v", "--validate-translations", action="store_true",
                            help="Enable manual validation of OpenAI translations before saving")
        parser.add_argument("-l", "--log-trace", action="store_true",
                            help="Log detailed trace information")
        parser.add_argument("--openai-model", default="gpt-4o-mini",
                            help="Specify the OpenAI model to use for translation.")
        parser.add_argument("--project-context", default="",
                            help="Additional project context for translation prompts.")
        parser.add_argument("--ignore-folders", default="",
                            help="Comma separated list of folder names to ignore during scanning. "
                                 "If empty, .gitignore patterns will be used instead.")
        parser.add_argument("--openai-api-key", dest="openai_api_key", default=None,
                            help="OpenAI API key to use for translation.")
        args = parser.parse_args()
        
        resources_paths = args.resources_paths
        auto_translate = args.auto_translate
        validate_translations = args.validate_translations
        log_trace = args.log_trace
        openai_model = args.openai_model
        project_context = args.project_context
        ignore_folders = [folder.strip() for folder in args.ignore_folders.split(',') if folder.strip()]
        openai_api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")
        print(f"Starting with arguments: {args}")

    configure_logging(log_trace)

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
                    merged_modules[identifier].language_resources.setdefault(lang, []).extend(resources)
            else:
                merged_modules[identifier] = mod

    if not merged_modules:
        logger.error("No resource files found!")
        sys.exit(1)

    modules_count = len(merged_modules)
    resources_count = sum(len(resources) for mod in merged_modules.values() for resources in mod.language_resources.values())
    logger.info(f"Found {modules_count} modules with {resources_count} resource files")
    
    if log_trace:
        for module in sorted(merged_modules.values(), key=lambda m: m.name):
            module.print_resources()

    translation_log = {}
    # If auto_translate is enabled, run the auto-translation process.
    if auto_translate:
        if not openai_api_key:
            logger.error("Error: OPENAI_API_KEY environment variable not set!")
            sys.exit(1)
        logger.info(f"Starting auto-translation using {openai_model}")
        translation_log = auto_translate_resources(
            merged_modules,
            openai_api_key,
            openai_model,
            project_context,
            validate_translations=validate_translations,
        )

    # Whether or not auto-translation was performed, still check for missing translations.
    check_missing_translations(merged_modules)

    # Generate the translation report (this will be empty if no auto-translation occurred).
    report_output = create_translation_report(translation_log)

    # Output the report
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            print("translation_report<<EOF", file=f)
            print(report_output, file=f)
            print("EOF", file=f)
    else:
        if auto_translate:
            print("\nTranslation Report:")
            print(report_output)

if __name__ == "__main__":
    main()
