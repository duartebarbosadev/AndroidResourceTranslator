# Sample Android Project for Testing

This is a sample Android project structure designed to test the **Android Resource Translator** tool. It includes a realistic shopping list app with multiple language translations at various completion levels.

## Project Structure

```
sample_project/
├── README.md (this file)
└── MyApp/ (Sample Android module)
    └── src/main/res/
        ├── values/strings.xml          (English - 100% complete)
        ├── values-es/strings.xml       (Spanish - ~60% complete)
        ├── values-pt-rPT/strings.xml   (Portuguese - ~40% complete)
        └── values-zh-rCN/strings.xml   (Chinese - ~15% complete)
```

### Translation States

- **Spanish (`es`)**: ~60% complete - several strings and one plural missing
- **Portuguese (`pt-rPT`)**: ~40% complete - many strings and both plurals missing
- **Chinese (`zh-rCN`)**: ~15% complete - most strings and all plurals missing

## Quick Start

### Prerequisites

1. **Set up Python environment:**

   ```bash
   # Create virtual environment (if not already done)
   python -m venv .venv

   # Activate it
   # Windows:
   .venv\Scripts\activate
   # Unix/macOS:
   source .venv/bin/activate

   # Install dependencies
   pip install -r requirements.txt
   ```
2. **Set up API keys:**

   For OpenRouter (default):

   ```bash
   export OPENROUTER_API_KEY='your-openrouter-api-key-here'
   ```

   Or for OpenAI (alternative):

   ```bash
   export OPENAI_API_KEY='your-openai-api-key-here'
   ```

#### Manual Commands

**Test 1: Check Missing Translations (Dry Run)**

See what translations are missing without making any changes:

```bash
python app/AndroidResourceTranslator.py sample_project/ --dry-run
```

**Test 2: Translate (Default: OpenRouter with Gemini)**

Automatically translate all missing strings using the default provider and model:

```bash
python app/AndroidResourceTranslator.py sample_project/
```

**Test 3: Translate with OpenAI**

Use OpenAI instead of the default OpenRouter:

```bash
python app/AndroidResourceTranslator.py sample_project/ --llm-provider openai --model gpt-4o-mini
```

**Test 4: With Project Context**

Provide additional context for better translations:

```bash
python app/AndroidResourceTranslator.py sample_project/ --project-context "A shopping list mobile application for groceries and household items"
```

**Test 5: With Detailed Logging**

Enable verbose output for debugging:

```bash
python app/AndroidResourceTranslator.py sample_project/ --log-trace
```
## Expected Results

### Dry Run Output

When you run in dry-run mode (`--dry-run`), you'll see a report like:

```
Found 1 module(s) with resources
Module: MyApp

Missing translations in es (Spanish):
  - Strings: get_started, create_new_list, item_quantity, ...
  - Plurals: days_until_expiry

Missing translations in pt-rPT (Portuguese (Portugal)):
  - Strings: welcome_message, get_started, search_hint, ...
  - Plurals: items_remaining, days_until_expiry

Missing translations in zh-rCN (Chinese (Simplified)):
  - Strings: welcome_message, get_started, shopping_lists, ...
  - Plurals: items_remaining, days_until_expiry
```
