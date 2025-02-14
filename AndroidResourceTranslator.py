#!/usr/bin/env python3
"""
Android Resource Translation Checker & Auto-Translator

This script scans Android resource files (strings.xml) for string and plural resources,
reports missing translations, and can automatically translate missing entries using OpenAI.
"""

import sys
import json
import re
import logging
from pathlib import Path
from xml.etree import ElementTree
from collections import defaultdict
from typing import Dict, Set, List
from lxml import etree

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
   *Example:* If the English source is `<item quantity="other">%d day left</item>`, the Portuguese translation should include both `<item quantity="one">%d dia restante</item>` and `<item quantity="many">%d dias restantes</item>`. Ensure that each plural form reflects the proper singular and plural usage with the correct one, many etc as defined by the target language's standard usage. Use the target language's pluralization guidelines as a reference to determine which keys to include and their corresponding forms.
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
    def __init__(self, name: str, identifier: str = None) -> None:
        self.name: str = name
        # A unique identifier (for example the full module path) so that modules
        # in different locations are not merged if they share the same short name.
        self.identifier: str = identifier or name
        self.language_resources: Dict[str, List[AndroidResourceFile]] = defaultdict(list)

    def add_resource(self, language: str, resource: AndroidResourceFile) -> None:
        logger.debug(
            f"Adding resource for language '{language}' in module '{self.name}': {resource.path}"
        )
        self.language_resources[language].append(resource)

    def print_resources(self) -> None:
        logger.info(f"Module: {self.name} (ID: {self.identifier})")
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


def find_resource_files(resources_path: str, ignore_folders: List[str] = None) -> Dict[str, AndroidModule]:
    """
    Recursively search for strings.xml files in "values*" directories.
    Files whose paths contain any folder listed in ignore_folders (if provided) are skipped.
    Files are grouped by module and language.
    """
    resources_dir = Path(resources_path)
    modules: Dict[str, AndroidModule] = {}
    logger.debug(f"Starting search for resource files in {resources_dir}")

    for xml_file_path in resources_dir.rglob("strings.xml"):
        if ignore_folders and any(ignored in xml_file_path.parts for ignored in ignore_folders):
            continue
        if not xml_file_path.parent.name.startswith("values"):
            continue

        language = detect_language_from_path(xml_file_path)
        try:
            module_path = xml_file_path.parent.parent.parent  # e.g. module/src/main/res
        except Exception:
            module_path = xml_file_path.parent
        module_name = module_path.name
        unique_key = str(module_path.resolve())
        if unique_key not in modules:
            modules[unique_key] = AndroidModule(module_name, identifier=unique_key)
            logger.debug(
                f"Created module entry for {module_name} with identifier {unique_key}"
            )
        resource_file = AndroidResourceFile(xml_file_path, language)
        modules[unique_key].add_resource(language, resource_file)
    return modules


def update_xml_file(resource: AndroidResourceFile) -> None:
    """
    Update the XML file represented by an AndroidResourceFile by appending only the missing elements,
    while preserving the original formatting (including comments) as much as possible.
    
    This version uses lxml and makes sure that if new elements are appended, the first new element is
    correctly indented.
    """
    try:
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(str(resource.path), parser)
        root = tree.getroot()
    except Exception as e:
        logger.error(f"Error reading XML file {resource.path}: {e}")
        return

    # Determine sample indentation from an existing child of <resources>; default to 4 spaces.
    sample_indent = "    "
    if len(root) > 0:
        m = re.match(r'\n(\s+)', root[0].tail or "")
        if m:
            sample_indent = m.group(1)

    # Ensure the whitespace before the first child is properly indented.
    if not root.text or not root.text.strip():
        root.text = "\n" + sample_indent

    # --- Update <string> elements (direct children of <resources>) ---
    # Record the original number of children before appending new nodes.
    original_root_count = len(root)
    existing_string_names = {elem.get("name") for elem in root if elem.tag == "string"}
    
    # If there are existing children, ensure the last one ends with a newline and the proper indent.
    if original_root_count > 0:
        last_original = root[original_root_count - 1]
        if not last_original.tail or not last_original.tail.endswith(sample_indent):
            last_original.tail = "\n" + sample_indent

    # Append new <string> elements.
    for key, translation in resource.strings.items():
        if key not in existing_string_names:
            new_elem = etree.Element("string", name=key)
            new_elem.text = translation
            # Set the tail to newline + indent.
            new_elem.tail = "\n" + sample_indent
            root.append(new_elem)
            logger.debug(f"Appended <string name='{key}'> element to {resource.path}")

    # --- Update <plurals> elements ---
    existing_plural_elements = {elem.get("name"): elem for elem in root if elem.tag == "plurals"}
    for plural_name, items in resource.plurals.items():
        if plural_name in existing_plural_elements:
            plural_elem = existing_plural_elements[plural_name]
        else:
            plural_elem = etree.Element("plurals", name=plural_name)
            # Set the text so that inner <item> elements get an extra indent level.
            plural_elem.text = "\n" + sample_indent + "    "
            root.append(plural_elem)
            # Set a tail for the new <plurals> element
            plural_elem.tail = "\n" + sample_indent

        # Use one extra indent level for <item> elements.
        item_indent = sample_indent + "    "
        existing_quantities = {child.get("quantity") for child in plural_elem if child.tag == "item"}
        for qty, translation in items.items():
            if qty not in existing_quantities:
                new_item = etree.Element("item", quantity=qty)
                new_item.text = translation
                new_item.tail = "\n" + item_indent  # temporary tail for the item
                plural_elem.append(new_item)
                logger.debug(
                    f"Appended <item quantity='{qty}'> element to plurals '{plural_name}' in {resource.path}"
                )
        # Adjust the tail of the last <item> so that the closing </plurals> is properly indented.
        if len(plural_elem) > 0:
            plural_elem[-1].tail = "\n" + sample_indent

    # Finally, ensure the last element in <resources> has a tail with just a newline (for the closing tag).
    if len(root) > 0:
        root[-1].tail = "\n"

    try:
        # Serialize the tree to a byte string.
        xml_bytes = etree.tostring(tree, encoding="utf-8", xml_declaration=True, pretty_print=True)
        # Remove any trailing newline characters.
        xml_bytes = xml_bytes.rstrip(b"\n")
        
        # Write the cleaned-up XML back to file.
        with open(resource.path, "wb") as f:
            f.write(xml_bytes)
        
        # Post-process the XML declaration if needed.
        with open(resource.path, "r+", encoding="utf-8") as f:
            content = f.read()
            content = re.sub(
                r"<\?xml version='1\.0' encoding='UTF-8'\?>",
                '<?xml version="1.0" encoding="utf-8"?>',
                content
            )
            f.seek(0)
            f.write(content)
            f.truncate()
        
        logger.info(f"Updated XML file: {resource.path}")
    except Exception as e:
        logger.error(f"Error writing XML file {resource.path}: {e}")


def indent_xml(elem: ElementTree.Element, level: int = 0) -> None:
    """
    Recursively indent an XML element for pretty-printing.
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

def call_openai(prompt: str, system_message: str, api_key: str, model: str = "gpt-3.5-turbo") -> str:
    """
    Helper function to call the OpenAI API with the given prompt and system message.
    Returns the response text.
    """
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    logger.debug(
        f"Sending request to OpenAI with system prompt: {system_message} and user prompt:\n{prompt}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    translation = response.choices[0].message.content.strip()
    logger.debug(f"Received response from OpenAI: {translation}")
    return translation


def translate_text(text: str, target_language: str, api_key: str, model: str, project_context: str, source_language: str = "English") -> str:
    """
    Translates a simple string resource from source_language to target_language, following Android guidelines.
    """
    if text.strip() == "":
        return ""

    prompt = TRANSLATION_GUIDELINES.format(target_language=target_language) + text
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=target_language)
    if project_context:
        system_message += f"\nProject context: {project_context}"
    translated = call_openai(prompt, system_message, api_key, model)
    return translated


def translate_plural_text(source_plural: Dict[str, str], target_language: str, api_key: str, model: str, project_context: str) -> Dict[str, str]:
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
    if project_context:
        system_message += f"\nProject context: {project_context}"
    translation_output = call_openai(prompt, system_message, api_key, model)
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
    openai_model: str,
    project_context: str,
    validate_translations: bool = False,
) -> dict:
    """
    For each non-default language resource, auto-translate missing strings and plural items.
    Returns a translation_log dictionary with details of the translations performed.
    """
    translation_log = {}
    for module in modules.values():
        if "default" not in module.language_resources:
            logger.warning(
                f"Module '{module.name}' missing default language resources; skipping auto translation."
            )
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
            translation_log.setdefault(module.name, {})[lang] = {"strings": [], "plurals": []}
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
                        translated = translate_text(
                            source_text,
                            target_language=lang,
                            api_key=openai_api_key,
                            model=openai_model,
                            project_context=project_context,
                        )
                        logger.info(f"Translated string '{key}': '{source_text}' -> '{translated}'")
                        if validate_translations:
                            translated = validate_translation(source_text, translated, target_language=lang)
                            logger.info(f"Validated string '{key}': now '{translated}'")
                        res.strings[key] = translated

                        # Record the translation for reporting.
                        translation_log[module.name][lang]["strings"].append({
                            "key": key,
                            "source": source_text,
                            "translation": translated,
                        })
                    except Exception as e:
                        logger.error(f"Error translating string '{key}': {e}")

                # Process plurals.
                for plural_name, default_map in module_default_plurals.items():
                    current_map = res.plurals.get(plural_name, {})
                    if not current_map or set(current_map.keys()) != set(default_map.keys()):
                        try:
                            generated_plural = translate_plural_text(
                                default_map,
                                target_language=lang,
                                api_key=openai_api_key,
                                model=openai_model,
                                project_context=project_context,
                            )
                            merged = generated_plural.copy()
                            merged.update(current_map)
                            res.plurals[plural_name] = merged
                            logger.info(f"Translated plural group '{plural_name}' for language '{lang}': {res.plurals[plural_name]}")
                            if validate_translations:
                                for plural_key in generated_plural:
                                    if plural_key in current_map:
                                        continue
                                    src_text = default_map.get(plural_key, default_map.get("other", ""))
                                    validated = validate_translation(src_text, res.plurals[plural_name][plural_key],
                                                                       target_language=lang, is_plural=True)
                                    res.plurals[plural_name][plural_key] = validated
                            # Record the plural translation.
                            translation_log[module.name][lang]["plurals"].append({
                                "plural_name": plural_name,
                                "translations": res.plurals[plural_name],
                            })
                        except Exception as e:
                            logger.error(f"Error translating plural '{plural_name}': {e}")
                update_xml_file(res)
    return translation_log

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
                missing_plu = (" | plurals: " + ", ".join([f"{k}({', '.join(sorted(v))})" 
                                                            for k, v in missing_plurals.items()])
                               if missing_plurals else "")
                logger.info(f"  [{lang}]: missing {missing_str}{missing_plu}")
            else:
                logger.info(f"  [{lang}]: complete")

# ------------------------------------------------------------------------------
# Translation Report Generator
# ------------------------------------------------------------------------------

def create_translation_report(translation_log):
    """
    Generate a Markdown formatted translation report as a string.
    """
    report = "# Translation Report\n\n"
    for module, languages in translation_log.items():
        report += f"## Module: {module}\n\n"
        for lang, details in languages.items():
            report += f"### Language: {lang}\n\n"
            if details.get("strings"):
                report += "#### Strings\n\n"
                report += "| Key | Source Text | Translated Text |\n"
                report += "| --- | ----------- | --------------- |\n"
                for entry in details["strings"]:
                    key = entry["key"]
                    source = entry["source"].replace("\n", " ")
                    translation = entry["translation"].replace("\n", " ")
                    report += f"| {key} | {source} | {translation} |\n"
                report += "\n"
            if details.get("plurals"):
                report += "#### Plural Resources\n\n"
                for plural in details["plurals"]:
                    plural_name = plural["plural_name"]
                    report += f"**{plural_name}**\n\n"
                    report += "| Quantity | Translated Text |\n"
                    report += "| -------- | --------------- |\n"
                    for qty, text in plural["translations"].items():
                        report += f"| {qty} | {text} |\n"
                    report += "\n"
    return report

# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------

def main() -> None:
    import os
    import sys
    import argparse

    # Determine if we are running inside GitHub Actions.
    is_github = os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"

    if is_github:
        resources_paths_input = os.environ.get("INPUT_RESOURCES_PATHS")
        resources_paths = [p.strip() for p in resources_paths_input.split(',') if p.strip()] if resources_paths_input else []
        auto_translate = os.environ.get("INPUT_AUTO_TRANSLATE", "false").lower() == "true"
        # No manual validation on GitHub; force it off.
        validate_translations = False  
        log_trace = os.environ.get("INPUT_LOG_TRACE", "false").lower() == "true"
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        openai_model = os.environ.get("INPUT_OPENAI_MODEL", "gpt-3.5-turbo")
        project_context = os.environ.get("INPUT_PROJECT_CONTEXT", "")
        ignore_folders = [folder.strip() for folder in os.environ.get("INPUT_IGNORE_FOLDERS", "build").split(',') if folder.strip()]
    else:
        parser = argparse.ArgumentParser(
            description="Android Resource Translation"
        )
        parser.add_argument("resources_paths", nargs="+", help="Paths to the Android project directories containing resource files")
        parser.add_argument("-a", "--auto-translate", action="store_true",
                            help="Automatically translate missing resources using OpenAI")
        parser.add_argument("-v", "--validate-translations", action="store_true",
                            help="Enable manual validation for OpenAI returned translations before saving into the XML file")
        parser.add_argument("-l", "--log-trace", action="store_true",
                            help="Log detailed trace information about operations including requests and responses with OpenAI")
        parser.add_argument("--openai-model", default="gpt-3.5-turbo",
                            help="Specify the OpenAI model to use for translation.")
        parser.add_argument("--project-context", default="",
                            help="Specify additional project context to include in translation prompts.")
        parser.add_argument("--ignore-folders", default="build",
                            help="Comma separated list of folder names to ignore during resource scanning (e.g., build).")
        args = parser.parse_args()
        
        resources_paths = args.resources_paths
        auto_translate = args.auto_translate
        validate_translations = args.validate_translations
        log_trace = args.log_trace
        openai_model = args.openai_model
        project_context = args.project_context
        ignore_folders = [folder.strip() for folder in args.ignore_folders.split(',') if folder.strip()]
        openai_api_key = os.environ.get("OPENAI_API_KEY")
    
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

    logger.info("Found string resources:")
    for module in sorted(merged_modules.values(), key=lambda m: m.name):
        module.print_resources()

    translation_log = {}
    # If auto_translate is enabled, run the auto-translation process.
    if auto_translate:
        if not openai_api_key:
            logger.error("Error: OPENAI_API_KEY environment variable not set!")
            sys.exit(1)
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
        print("Translation Report:")
        print(report_output)

if __name__ == "__main__":
    main()
