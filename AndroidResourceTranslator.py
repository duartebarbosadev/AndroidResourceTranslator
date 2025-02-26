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
from pathlib import Path
from xml.etree import ElementTree
from collections import defaultdict
from typing import Dict, Set, List
from lxml import etree

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
        logger.debug(f"Detected language '{language}' from {values_dir}")
        return language
    language = values_dir.replace("values-", "")
    logger.debug(f"Fallback language detection: {language}")
    return language


def find_resource_files(resources_path: str, ignore_folders: List[str] = None) -> Dict[str, AndroidModule]:
    """
    Recursively search for strings.xml files in "values*" directories.
    Files whose paths contain any folder listed in ignore_folders are skipped.
    Files are grouped by module and language.
    """
    resources_dir = Path(resources_path)
    modules: Dict[str, AndroidModule] = {}
    logger.info(f"Scanning for resource files in {resources_dir}")

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
        path_key = str(module_path.resolve())
        if path_key not in modules:
            modules[path_key] = AndroidModule(module_name, identifier=path_key)
            logger.debug(f"Created module entry for {module_name} (path: {path_key})")
        resource_file = AndroidResourceFile(xml_file_path, language)
        modules[path_key].add_resource(language, resource_file)
    return modules


def update_xml_file(resource: AndroidResourceFile) -> None:
    """
    Update the XML file represented by an AndroidResourceFile by appending missing elements,
    while preserving the original formatting as much as possible.
    """

    # Only update if the resource was modified
    if not resource.modified:
        return

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
                new_item.tail = "\n" + item_indent
                plural_elem.append(new_item)
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

def call_openai(prompt: str, system_message: str, api_key: str, model: str) -> str:
    """
    Call the OpenAI API with the given prompt and system message.
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
    logger.debug("\n-------\n")

    return translation


def translate_text(text: str, target_language: str, api_key: str, model: str, project_context: str, source_language: str = "English") -> str:
    """
    Translate a simple string resource from source_language to target_language, following Android guidelines.
    """
    if text.strip() == "":
        return ""
    prompt = (TRANSLATION_GUIDELINES +
              TRANSLATE_FINAL_TEXT.format(target_language=target_language) +
              text)
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
    prompt = (TRANSLATION_GUIDELINES +
              PLURAL_GUIDELINES_ADDITION +
              TRANSLATE_FINAL_TEXT.format(target_language=target_language) +
              source_json)
    system_message = SYSTEM_MESSAGE_TEMPLATE.format(target_language=target_language)
    if project_context:
        system_message += f"\nProject context: {project_context}"
    translation_output = call_openai(prompt, system_message, api_key, model)
    try:
        plural_dict = json.loads(translation_output)
        return plural_dict if isinstance(plural_dict, dict) else {"other": translation_output}
    except Exception as e:
        logger.error(f"Error parsing plural translation JSON: {e}. Falling back to single form.")
        return {"other": translation_output}

# ------------------------------------------------------------------------------
# Translation Validation
# ------------------------------------------------------------------------------

def validate_translation(source_text: str, current_translation: str, target_language: str, is_plural: bool = False) -> str:
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
    languages_covered = set()

    for module in modules.values():
        if "default" not in module.language_resources:
            logger.warning(f"Module '{module.name}' missing default resources; skipping auto translation.")
            continue

        module_default_strings: Dict[str, str] = {}
        module_default_plurals: Dict[str, Dict[str, str]] = defaultdict(dict)
        for res in module.language_resources["default"]:
            for key, val in res.strings.items():
                module_default_strings.setdefault(key, val)
            for plural_name, quantities in res.plurals.items():
                for qty, text in quantities.items():
                    module_default_plurals[plural_name].setdefault(qty, text)

        for lang, resources in module.language_resources.items():
            if lang == "default":
                continue
            translation_log.setdefault(module.name, {})[lang] = {"strings": [], "plurals": []}
            for res in resources:
                missing_strings = set(module_default_strings.keys()) - set(res.strings.keys())
                missing_plurals = {}
                for plural_name, default_map in module_default_plurals.items():
                    current_map = res.plurals.get(plural_name, {})
                    if not current_map or set(current_map.keys()) != set(default_map.keys()):
                        missing_plurals[plural_name] = default_map
                # Log only if there are missing translations
                if not missing_strings and not missing_plurals:
                    continue
                
                # Track languages receiving translations
                languages_covered.add(lang)
                
                logger.info(f"Auto-translating missing resources for module '{module.name}', language '{lang}'")
                for key in sorted(missing_strings):
                    source_text = module_default_strings[key]
                    if source_text.strip() == "":
                        res.strings[key] = ""
                        continue
                    try:
                        translated = translate_text(source_text, target_language=lang,
                                                    api_key=openai_api_key, model=openai_model,
                                                    project_context=project_context)
                        
                        logger.info(f"Translated string '{key}' to {lang}: '{source_text}' -> '{translated}'")

                        if validate_translations:
                            translated = validate_translation(source_text, translated, target_language=lang)
                        res.strings[key] = translated
                        res.modified = True
                        total_translated += 1
                        translation_log[module.name][lang]["strings"].append({
                            "key": key,
                            "source": source_text,
                            "translation": translated,
                        })
                    except Exception as e:
                        logger.error(f"Error translating string '{key}': {e}")

                for plural_name, default_map in module_default_plurals.items():
                    current_map = res.plurals.get(plural_name, {})
                    if not current_map or set(current_map.keys()) != set(default_map.keys()):
                        try:
                            generated_plural = translate_plural_text(default_map, target_language=lang,
                                                                       api_key=openai_api_key, model=openai_model,
                                                                       project_context=project_context)
                            merged = generated_plural.copy()
                            merged.update(current_map)
                            res.plurals[plural_name] = merged
                            res.modified = True
                            total_translated += len(generated_plural)
                            logger.info(f"Translated plural group '{plural_name}' for language '{lang}': {res.plurals[plural_name]}")
                            if validate_translations:
                                for plural_key in generated_plural:
                                    if plural_key in current_map:
                                        continue
                                    src_text = default_map.get(plural_key, default_map.get("other", ""))
                                    validated = validate_translation(src_text, res.plurals[plural_name][plural_key],
                                                                       target_language=lang, is_plural=True)
                                    res.plurals[plural_name][plural_key] = validated
                            translation_log[module.name][lang]["plurals"].append({
                                "plural_name": plural_name,
                                "translations": res.plurals[plural_name],
                            })
                        except Exception as e:
                            logger.error(f"Error translating plural '{plural_name}': {e}")
                if res.modified:
                    update_xml_file(res)
    
    # After processing all modules, add detailed log for translated resource names.
    if total_translated > 0:
        translated_info = {}
        for mod, lang_details in translation_log.items():
            for lang, details in lang_details.items():
                entry = translated_info.setdefault(lang, {'strings': set(), 'plurals': set()})
                for s in details.get("strings", []):
                    entry['strings'].add(s["key"])
                for p in details.get("plurals", []):
                    entry['plurals'].add(p["plural_name"])
        for lang, items in translated_info.items():
            if not items['strings'] and not items['plurals']:
                continue
            msg = f"Language '{lang}':"
            if items['strings']:
                msg += f" Strings translated: {', '.join(sorted(items['strings']))}"
            if items['plurals']:
                msg += f"; Plurals translated: {', '.join(sorted(items['plurals']))}"
            logger.info(msg)
    else:
        logger.info("No translations needed")
        
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
    missing_count = 0
    
    for module in modules.values():
        module_has_missing = False
        module_log_lines = []
        default_strings: Set[str] = set()
        default_plural_quantities: Dict[str, Set[str]] = {}
        
        if "default" not in module.language_resources:
            logger.warning(f"  No default resources for module '{module.name}'")
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
                missing_count += 1
                module_has_missing = True
                missing_str = f"strings: {', '.join(sorted(missing_strings))}" if missing_strings else ""
                missing_plu = (" | plurals: " + ", ".join([f"{k}({', '.join(sorted(v))})" 
                                                            for k, v in missing_plurals.items()])
                               if missing_plurals else "")
                module_log_lines.append(f"  [{lang}]: missing {missing_str}{missing_plu}")
        
        if module_has_missing:
            logger.info(f"Module: {module.name} (has missing translations)")
            for line in module_log_lines:
                logger.info(line)
    
    if missing_count == 0:
        logger.info("All translations are complete.")

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
        ignore_folders = [folder.strip() for folder in os.environ.get("INPUT_IGNORE_FOLDERS", "build").split(',') if folder.strip()]

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
        parser.add_argument("--ignore-folders", default="build",
                            help="Comma separated list of folder names to ignore during scanning. (e.g. build).")
        args = parser.parse_args()
        
        resources_paths = args.resources_paths
        auto_translate = args.auto_translate
        validate_translations = args.validate_translations
        log_trace = args.log_trace
        openai_model = args.openai_model
        project_context = args.project_context
        ignore_folders = [folder.strip() for folder in args.ignore_folders.split(',') if folder.strip()]
        openai_api_key = os.environ.get("OPENAI_API_KEY")
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