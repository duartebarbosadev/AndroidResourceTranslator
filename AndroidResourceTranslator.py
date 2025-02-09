#!/usr/bin/env python3
"""
Android Resource Translation Checker & Auto-Translator

This script scans Android resource files (strings.xml) for string and plural resources,
reports missing translations, and can automatically translate missing entries using OpenAI.
It has been refactored for better modularity, error handling, logging, and configuration.
"""

import os
import sys
import json
import re
import argparse
import logging
from pathlib import Path
from xml.etree import ElementTree
from collections import defaultdict
from typing import Dict, Set, List, Tuple

try:
    import openai
except ImportError:
    print("Error: openai package not installed. Please install it with pip install openai")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Configuration Constants
# ------------------------------------------------------------------------------

TRANSLATION_GUIDELINES = """\
Translate the following resource for an Android app provided after the dashed line to {target_language}.

Guidelines:
1. **Purpose & Context:**  
   The translation is for an Android application's UI. Use terminology and phrasing consistent with software interfaces.

2. **Formatting & Structure:**  
   - Preserve all placeholders (e.g., %d, %s, %1$s) exactly as they appear.  
   - Keep HTML, CDATA, or XML structure unchanged, translating only textual content.  
   - Escape apostrophes with a backslash (\\') as required by Android.

3. **System Terms:**  
   Do not translate system state words such as WARNING, FAILED, SUCCESS, PAUSED, or RUNNING. They must remain in English and in uppercase.

4. **Terminology & Natural Expressions:**  
   Use correct, context-appropriate terminology. Avoid literal translations that sound unnatural. Prioritize commonly used phrasing over word-for-word accuracy.  
   When a technical term (e.g., "upload", "server") is more natural untranslated, keep it in English.

   **Examples (Portuguese of Portugal):**
   - "Day Limit" → ✅ "Limite diário" (❌ "Limite do dia")
   - "Network Connection" → ✅ "Ligação de rede" (❌ "Conexão de rede")
   - "Start Time" → ✅ "Hora de início" (❌ "Hora de começar")
   - "Message Sent" → ✅ "Mensagem enviada" (❌ "Mensagem foi enviada")
   - "Upload Speed" → ✅ "Velocidade de upload" (❌ "Velocidade de envio")

5. **Dialect and Regional Vocabulary:**  
   Use native vocabulary for the specified dialect (e.g., **Português de Portugal**), avoiding terms from other variants.

6. **Output Requirements:**  
   Return ONLY the final translated text as a single plain line, preserving any required formatting from the source.
----------
"""

PLURAL_GUIDELINES_ADDITION = """\
6. **Plural Resources:**
   For plural translations, if the source resource contains only a single plural key (e.g., "other") but the target language requires multiple plural forms, return all the appropriate plural keys for the target language.
   *Example:* If the English source is `<item quantity="other">%d day left</item>`, the Portuguese translation should include both `<item quantity="one">%d dia restante</item>` and `<item quantity="many">%d dias restantes</item>`. Note that in this case, the Portuguese does not need to include the "other" key, but it is expected in the result.
   The full set supported by Android is zero, one, two, few, many, and other.

7. **Output Requirements:**
   Return ONLY a JSON object containing the translated plural mapping as a single plain line. Do not include any markdown formatting, code blocks, or additional commentary, except if any such formatting is already present in the source string provided.
----------
"""

SYSTEM_MESSAGE_TEMPLATE = """\
You are a software engineer translating textual UI elements within a software application from English into {target_language} while keeping technical terms in English.
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
        self.parse_file()

    def parse_file(self) -> None:
        """Parses the strings.xml file and extracts <string> and <plurals> elements. Skips resources with translatable="false"."""
        try:
            tree = ElementTree.parse(self.path)
            root = tree.getroot()
            logger.debug(f"Parsing file: {self.path}")

            for elem in root:
                translatable = elem.attrib.get("translatable", "true").lower()
                if translatable == "false":
                    continue

                if elem.tag == "string":
                    name = elem.attrib.get("name")
                    if name:
                        self.strings[name] = (elem.text or "").strip()
                        logger.debug(f"Found string: {name} = {self.strings[name]}")
                elif elem.tag == "plurals":
                    name = elem.attrib.get("name")
                    if name:
                        quantities: Dict[str, str] = {}
                        for item in elem.findall("item"):
                            quantity = item.attrib.get("quantity")
                            if quantity:
                                quantities[quantity] = (item.text or "").strip()
                                logger.debug(f"Found plural '{name}' quantity '{quantity}' = {quantities[quantity]}")
                        self.plurals[name] = quantities
        except ElementTree.ParseError as pe:
            logger.error(f"XML parse error in {self.path}: {pe}")
        except Exception as e:
            logger.error(f"Error parsing {self.path}: {e}")

    def summary(self) -> Dict[str, int]:
        """Return a summary of resource counts."""
        return {"strings": len(self.strings), "plurals": len(self.plurals)}


class AndroidModule:
    """
    Represents an Android module containing several strings.xml files for different languages.
    """
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.language_resources: Dict[str, List[AndroidResourceFile]] = defaultdict(list)

    def add_resource(self, language: str, resource: AndroidResourceFile) -> None:
        logger.debug(f"Adding resource for language '{language}' in module '{self.name}': {resource.path}")
        self.language_resources[language].append(resource)

    def print_resources(self) -> None:
        logger.info(f"Module: {self.name}")
        for language, resources in sorted(self.language_resources.items()):
            logger.info(f"  Language: {language}")
            for resource in resources:
                sums = resource.summary()
                logger.info(f"    File: {resource.path} | Strings: {sums['strings']}, Plurals: {sums['plurals']}")


def detect_language_from_path(file_path: Path) -> str:
    """
    Detect language from the folder name.
      - "values"           -> "default"
      - "values-es"        -> "es"
      - "values-zh-rCN"    -> "zh-rCN"
      - "values-b+sr+Latn" -> "b+sr+Latn"
    """
    values_dir = file_path.parent.name
    if values_dir == "values":
        return "default"
    match = re.match(r"values-(.+)", values_dir)
    if match:
        language = match.group(1)
        logger.debug(f"Detected language: {language} from {values_dir}")
        return language
    language = values_dir.replace("values-", "")
    logger.debug(f"Fallback language detection: {language}")
    return language


def find_resource_files(base_path: str) -> Dict[str, AndroidModule]:
    """
    Recursively search for strings.xml files in "values*" directories (ignoring paths with 'build').
    Files are grouped by module and language.
    """
    project_path = Path(base_path)
    modules: Dict[str, AndroidModule] = {}
    logger.debug(f"Starting search for resource files in {project_path}")

    for xml_file_path in project_path.rglob("strings.xml"):
        if "build" in xml_file_path.parts:
            continue
        if not xml_file_path.parent.name.startswith("values"):
            continue

        language = detect_language_from_path(xml_file_path)
        try:
            module_path = xml_file_path.parent.parent.parent  # e.g. module/src/main/res
            module_name = module_path.name
        except Exception:
            module_name = xml_file_path.parent.name

        if module_name not in modules:
            modules[module_name] = AndroidModule(module_name)
            logger.debug(f"Created module entry for {module_name}")

        resource_file = AndroidResourceFile(xml_file_path, language)
        modules[module_name].add_resource(language, resource_file)
    return modules


def update_xml_file(resource: AndroidResourceFile) -> None:
    """
    Update the XML file represented by an AndroidResourceFile with new translations.
    Appends missing <string> and <plurals>/<item> elements and writes back a pretty-printed XML.
    """
    try:
        tree = ElementTree.parse(resource.path)
        root = tree.getroot()
    except Exception as e:
        logger.error(f"Error reading XML file {resource.path}: {e}")
        return

    # Update <string> elements.
    existing_string_names = {elem.attrib.get("name") for elem in root if elem.tag == "string"}
    for key, translation in resource.strings.items():
        if key not in existing_string_names:
            new_elem = ElementTree.Element("string", {"name": key})
            new_elem.text = translation
            root.append(new_elem)
            logger.debug(f"Added <string name='{key}'>{translation}</string> to {resource.path}")

    # Update <plurals> elements.
    existing_plural_elements = {}
    for elem in root:
        if elem.tag == "plurals":
            name = elem.attrib.get("name")
            if name:
                existing_plural_elements[name] = elem

    for plural_name, items in resource.plurals.items():
        if plural_name in existing_plural_elements:
            plural_elem = existing_plural_elements[plural_name]
        else:
            plural_elem = ElementTree.Element("plurals", {"name": plural_name})
            root.append(plural_elem)
            logger.debug(f"Added <plurals name='{plural_name}'> element to {resource.path}")

        existing_quantities = {child.attrib.get("quantity") for child in plural_elem if child.tag == "item"}
        for qty, translation in items.items():
            if qty not in existing_quantities:
                new_item = ElementTree.Element("item", {"quantity": qty})
                new_item.text = translation
                plural_elem.append(new_item)
                logger.debug(f"Added <item quantity='{qty}'>{translation}</item> to plurals '{plural_name}' in {resource.path}")

    indent_xml(root)

    try:
        tree.write(resource.path, encoding="utf-8", xml_declaration=True)
        logger.info(f"Updated XML file: {resource.path}")
    except Exception as e:
        logger.error(f"Error writing XML file {resource.path}: {e}")


def indent_xml(elem: ElementTree.Element, level: int = 0) -> None:
    """
    Recursively indent an XML element for pretty-printing.

    This version sets the text and tail for each element so that:
      - Each child element is indented one level further than its parent.
      - The closing tag of a parent lines up with its opening tag.
      - No extra blank lines appear between sibling elements.
    """
    pad = "    "  # 4 spaces per level

    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = "\n" + (level + 1) * pad

        for child in elem[:-1]:
            indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = "\n" + (level + 1) * pad

        indent_xml(elem[-1], level + 1)
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = "\n" + level * pad
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = "\n" + level * pad


# ------------------------------------------------------------------------------
# Translation & OpenAI API Integration
# ------------------------------------------------------------------------------

def call_openai(prompt: str, system_message: str, api_key: str) -> str:
    """
    Helper function to call the OpenAI API with the given prompt and system message.
    Returns the response text.
    """
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    logger.debug(f"Sending request to OpenAI with system prompt: {system_message} and user prompt:\n{prompt}")
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    translation = response.choices[0].message.content.strip()
    logger.debug(f"Received response from OpenAI: {translation}")
    return translation


def translate_text(text: str, target_language: str, api_key: str, source_language: str = "English") -> str:
    """
    Translates a simple string resource from source_language to target_language, following Android guidelines.
    """
    if text.strip() == "":
        return ""

    prompt = TRANSLATION_GUIDELINES.format(target_language=target_language) + text
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=target_language)
    translated = call_openai(prompt, system_message, api_key)
    return translated


def translate_plural_text(source_plural: Dict[str, str], target_language: str, api_key: str) -> Dict[str, str]:
    """
    Translates a plural resource from English to target_language, following Android guidelines.
    """
    source_json = json.dumps(source_plural, indent=2)
    prompt = (
        TRANSLATION_GUIDELINES.format(target_language=target_language) +
        PLURAL_GUIDELINES_ADDITION +
        source_json
    )
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=target_language)
    translation_output = call_openai(prompt, system_message, api_key)
    try:
        plural_dict = json.loads(translation_output)
        if isinstance(plural_dict, dict):
            return plural_dict
        else:
            return {"other": translation_output}
    except Exception as e:
        logger.error(f"Error parsing plural translation JSON: {e}. Falling back to single form.")
        return {"other": translation_output}

# ------------------------------------------------------------------------------
# Translation Validation
# ------------------------------------------------------------------------------

def validate_translation(
    source_text: str, current_translation: str, target_language: str, is_plural: bool = False
) -> str:
    """
    Prompts the user to validate the translation. Displays the source text and the current translation,
    then asks if the translation is acceptable. If not, the user can input a corrected version.
    """
    print("\n----- Validate Translation -----")
    print(f"Source Text: {source_text}")
    print(f"Current Translation in {target_language}: {current_translation}")
    response = input("Do you accept this translation? (y/n): ").strip().lower()
    if response == "y":
        return current_translation
    else:
        new_trans = input("Enter the corrected translation: ").strip()
        return new_trans

# ------------------------------------------------------------------------------
# Auto-Translation Process
# ------------------------------------------------------------------------------

def auto_translate_resources(
    modules: Dict[str, AndroidModule],
    openai_api_key: str,
    validate_translations: bool = False,
) -> None:
    """
    For each non-default language resource, auto-translate missing strings and plural items.
    If a source string is empty, it is copied over.
    When validate_translations is enabled, only the newly generated (OpenAI returned) translations
    are prompted for validation.
    """
    for module in modules.values():
        if "default" not in module.language_resources:
            logger.warning(f"Module '{module.name}' missing default language resources; skipping auto translation.")
            continue

        module_default_strings: Dict[str, str] = {}
        module_default_plurals: Dict[str, Dict[str, str]] = defaultdict(dict)
        for res in module.language_resources["default"]:
            for key, val in res.strings.items():
                if key not in module_default_strings:
                    module_default_strings[key] = val
            for plural_name, quantities in res.plurals.items():
                for qty, text in quantities.items():
                    if qty not in module_default_plurals[plural_name]:
                        module_default_plurals[plural_name][qty] = text

        for lang, resources in module.language_resources.items():
            if lang == "default":
                continue
            logger.info(f"Auto-translating missing resources for module '{module.name}', language '{lang}'")
            for res in resources:
                # Process missing strings.
                missing_strings = set(module_default_strings.keys()) - set(res.strings.keys())
                for key in sorted(missing_strings):
                    source_text = module_default_strings[key]
                    if source_text.strip() == "":
                        res.strings[key] = ""
                        logger.info(f"Copied empty string for key '{key}'")
                        continue
                    try:
                        translated = translate_text(source_text, target_language=lang, api_key=openai_api_key)
                        logger.info(f"Translated string '{key}': '{source_text}' -> '{translated}'")
                        if validate_translations:
                            translated = validate_translation(source_text, translated, target_language=lang)
                            logger.info(f"Validated string '{key}': now '{translated}'")
                        res.strings[key] = translated
                    except Exception as e:
                        logger.error(f"Error translating string '{key}': {e}")

                # Process plurals.
                for plural_name, default_map in module_default_plurals.items():
                    current_map = res.plurals.get(plural_name, {})
                    # If missing keys exist (or the keys don't match), get a new translation.
                    if not current_map or set(current_map.keys()) != set(default_map.keys()):
                        try:
                            generated_plural = translate_plural_text(default_map, target_language=lang, api_key=openai_api_key)
                            # Merge: keep already present translations (if any) over OpenAI's result.
                            merged = generated_plural.copy()
                            merged.update(current_map)
                            res.plurals[plural_name] = merged
                            logger.info(f"Translated plural group '{plural_name}' for language '{lang}': {res.plurals[plural_name]}")
                            if validate_translations:
                                # Only validate keys that were newly generated by OpenAI.
                                for plural_key in generated_plural:
                                    # Skip if a translation already existed.
                                    if plural_key in current_map:
                                        continue
                                    src_text = default_map.get(plural_key, default_map.get("other", ""))
                                    validated = validate_translation(src_text, res.plurals[plural_name][plural_key],
                                                                       target_language=lang, is_plural=True)
                                    res.plurals[plural_name][plural_key] = validated
                        except Exception as e:
                            logger.error(f"Error translating plural '{plural_name}': {e}")
                update_xml_file(res)

# ------------------------------------------------------------------------------
# Missing Translation Report
# ------------------------------------------------------------------------------

def check_missing_translations(modules: Dict[str, AndroidModule]) -> None:
    """
    For each module, compare non-default language resources against the union of keys
    in the default language. Checks for missing <string> keys and missing plural quantities.
    """
    logger.info("Missing Translations Report")
    for module in modules.values():
        logger.info(f"Module: {module.name}")
        default_strings: Set[str] = set()
        default_plural_quantities: Dict[str, Set[str]] = {}

        if "default" not in module.language_resources:
            logger.warning(f"  No default language resources found for module '{module.name}'")
            continue

        for resource in module.language_resources["default"]:
            default_strings.update(resource.strings.keys())
            for plural_name, quantities in resource.plurals.items():
                default_plural_quantities.setdefault(plural_name, set()).update(quantities.keys())

        for lang, resources in sorted(module.language_resources.items()):
            if lang == "default":
                continue

            lang_strings: Set[str] = set()
            lang_plural_quantities: Dict[str, Set[str]] = {}
            for resource in resources:
                lang_strings.update(resource.strings.keys())
                for plural_name, quantities in resource.plurals.items():
                    lang_plural_quantities.setdefault(plural_name, set()).update(quantities.keys())

            missing_strings = default_strings - lang_strings
            missing_plurals: Dict[str, Set[str]] = {}
            for plural_name, def_qty in default_plural_quantities.items():
                current_qty = lang_plural_quantities.get(plural_name, set())
                diff = def_qty - current_qty
                if diff:
                    missing_plurals[plural_name] = diff

            if missing_strings or missing_plurals:
                missing_str = f"strings: {', '.join(sorted(missing_strings))}" if missing_strings else ""
                missing_plu = (" | plurals: " + ", ".join([f"{k}({', '.join(sorted(v))})" for k, v in missing_plurals.items()])
                               if missing_plurals else "")
                logger.info(f"  [{lang}]: missing {missing_str}{missing_plu}")
            else:
                logger.info(f"  [{lang}]: complete")

# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------


def main() -> None:
    # Now read the environment variables here.
    project_path = os.environ.get("INPUT_PROJECT_PATH")
    auto_translate = os.environ.get("INPUT_AUTO_TRANSLATE", "false").lower() == "true"
    validate_translations = os.environ.get("INPUT_VALIDATE_TRANSLATIONS", "false").lower() == "true"
    log_trace = os.environ.get("INPUT_LOG_TRACE", "false").lower() == "true"
    openai_api_key = os.environ.get("OPENAI_API_KEY")

    if not project_path:
        print("Error: 'project_path' input not provided.")
        sys.exit(1)

    # Also parse CLI args; for actions these might be overridden.
    parser = argparse.ArgumentParser(
        description="Android Resource Translation Checker (strings.xml only)"
    )
    parser.add_argument("project_path", nargs="?", default=project_path,
                        help="Path to the Android project base directory")
    parser.add_argument("-a", "--auto-translate", action="store_true",
                        help="Automatically translate missing resources using OpenAI")
    parser.add_argument("-v", "--validate-translations", action="store_true",
                        help="Enable manual validation for OpenAI returned translations before saving into the XML file")
    parser.add_argument("-l", "--log-trace", action="store_true",
                        help="Log detailed trace information about operations including requests and responses with OpenAI")
    args = parser.parse_args()

    # If the CLI args override the environment variables, you can use args here.
    project_path = args.project_path

    configure_logging(args.log_trace)

    if not os.path.exists(project_path):
        logger.error("Error: The specified path does not exist!")
        sys.exit(1)

    modules = find_resource_files(project_path)
    if not modules:
        logger.error("No resource files found!")
        sys.exit(1)

    logger.info("Found string resources:")
    for module in sorted(modules.values(), key=lambda m: m.name):
        module.print_resources()

    if args.auto_translate:
        if not openai_api_key:
            logger.error("Error: OPENAI_API_KEY environment variable not set!")
            sys.exit(1)
        auto_translate_resources(
            modules,
            openai_api_key,
            validate_translations=args.validate_translations,
        )

    check_missing_translations(modules)
    
if __name__ == "__main__":
    main()
