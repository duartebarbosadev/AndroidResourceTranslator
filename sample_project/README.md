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
python app/AndroidResourceTranslator.py sample_project/
```

**Test 2: Auto-translate (Default: OpenRouter with Gemini)**

Automatically translate all missing strings using the default provider and model:

```bash
python app/AndroidResourceTranslator.py sample_project/ --auto-translate
```

**Test 3: Auto-translate with OpenAI**

Use OpenAI instead of the default OpenRouter:

```bash
python app/AndroidResourceTranslator.py sample_project/ \
    --auto-translate \
    --llm-provider openai \
    --model gpt-4o-mini
```

**Test 4: With Project Context**

Provide additional context for better translations:

```bash
python app/AndroidResourceTranslator.py sample_project/ \
    --auto-translate \
    --project-context "A shopping list mobile application for groceries and household items"
```

**Test 5: With Detailed Logging**

Enable verbose output for debugging:

```bash
python app/AndroidResourceTranslator.py sample_project/ \
    --auto-translate \
    --log-trace
```

## Command Reference

### Basic Usage

```bash
python app/AndroidResourceTranslator.py <path> [options]
```

### Available Options

| Option                              | Description                               | Default                                     |
| ----------------------------------- | ----------------------------------------- | ------------------------------------------- |
| `--auto-translate`, `-a`        | Enable automatic translation              | `False`                                   |
| `--validate-translations`, `-v` | Manually validate each translation        | `False`                                   |
| `--log-trace`, `-l`             | Enable detailed logging                   | `False`                                   |
| `--llm-provider`                  | LLM provider:`openai` or `openrouter` | `openrouter`                              |
| `--model`                         | Model to use                              | `google/gemini-2.5-flash-preview-09-2025` |
| `--openrouter-site-url`           | Site URL for OpenRouter rankings          | (AndroidResourceTranslator GitHub)          |
| `--openrouter-site-name`          | Site name for OpenRouter rankings         | `AndroidResourceTranslatorAction`         |
| `--openrouter-send-site-info`     | Send site info to OpenRouter              | `True`                                    |
| `--project-context`               | Additional context for translations       | (none)                                      |
| `--ignore-folders`                | Comma-separated folders to ignore         | (follows .gitignore)                        |
| `--openai-api-key`                | API key (or use env var)                  | `$OPENAI_API_KEY`                         |
| `--openrouter-api-key`            | OpenRouter API key                        | `$OPENROUTER_API_KEY`                     |

### Supported Models

**OpenRouter (Default):**

- `google/gemini-2.5-flash-preview-09-2025` - Google Gemini 2.5 Flash (default, cost-effective)
- `google/gemini-2.5-flash` - Google Gemini 2.0 Flash
- `anthropic/claude-3.5-sonnet` - Anthropic Claude 3.5 Sonnet
- `meta-llama/llama-3.1-405b-instruct` - Meta Llama 3.1 405B
- `openai/gpt-4o` - OpenAI GPT-4o (via OpenRouter)

**OpenAI:**

- `gpt-4o-mini` (cost-effective)
- `gpt-4o` (more powerful)
- `gpt-4-turbo`

See [OpenRouter Models](https://openrouter.ai/docs/models) for the complete list.

## Expected Results

### Dry Run Output

When you run without `--auto-translate`, you'll see a report like:

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
