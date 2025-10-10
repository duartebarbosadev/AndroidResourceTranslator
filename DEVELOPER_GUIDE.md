# Developer Guide - Local Testing

This guide explains how to test the Android Resource Translator locally on your machine without using GitHub Actions.

## Prerequisites

- Python 3.x installed
- An Android project with `strings.xml` files
- API key from OpenAI or OpenRouter

## Setup

### 1. Create Virtual Environment

```bash
# Navigate to the project directory
cd AndroidResourceTranslator

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\activate

# Windows CMD:
.venv\Scripts\activate.bat

# macOS/Linux:
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:

- `openai>=1.61.1` - OpenAI API client (works with OpenRouter too)
- `lxml>=4.9.1` - XML parsing
- `pathspec>=0.12.1` - Gitignore pattern matching
- `babel>=2.17.0` - Language name localization

## Configuration

### Set API Key

Choose one provider and set the corresponding environment variable:

#### Option A: OpenAI (Default)

```bash
# Windows PowerShell:
$env:OPENAI_API_KEY = "sk-your-openai-api-key-here"

# Windows CMD:
set OPENAI_API_KEY=sk-your-openai-api-key-here

# macOS/Linux:
export OPENAI_API_KEY="sk-your-openai-api-key-here"
```

Get your key: https://platform.openai.com/api-keys

#### Option B: OpenRouter (400+ Models)

```bash
# Windows PowerShell:
$env:OPENROUTER_API_KEY = "sk-or-your-openrouter-api-key-here"

# Windows CMD:
set OPENROUTER_API_KEY=sk-or-your-openrouter-api-key-here

# macOS/Linux:
export OPENROUTER_API_KEY="sk-or-your-openrouter-api-key-here"
```

Get your key: https://openrouter.ai/keys

## Usage

### Basic Commands

#### 1. Using OpenAI (Default)

```bash
python app/AndroidResourceTranslator.py /path/to/your/android/project --auto-translate
```

#### 2. Using OpenRouter with Google Gemini

```bash
python app/AndroidResourceTranslator.py /path/to/your/android/project \
  --auto-translate \
  --llm-provider openrouter \
  --model google/gemini-2.0-flash-exp
```

#### 3. Using OpenRouter with Anthropic Claude

```bash
python app/AndroidResourceTranslator.py /path/to/your/android/project \
  --auto-translate \
  --llm-provider openrouter \
  --model anthropic/claude-3.5-sonnet
```

#### 4. Using OpenRouter with Meta Llama

```bash
python app/AndroidResourceTranslator.py /path/to/your/android/project \
  --auto-translate \
  --llm-provider openrouter \
  --model meta-llama/llama-3.1-405b-instruct
```

### Advanced Options

#### Add Project Context

Provide context about your app for better translations:

```bash
python app/AndroidResourceTranslator.py /path/to/project \
  --auto-translate \
  --project-context "MyApp is a fitness tracking app for runners"
```

#### Enable Debug Logging

See detailed information about what the script is doing:

```bash
python app/AndroidResourceTranslator.py /path/to/project \
  --auto-translate \
  --log-trace
```

#### Ignore Specific Folders

Skip certain directories during scanning:

```bash
python app/AndroidResourceTranslator.py /path/to/project \
  --auto-translate \
  --ignore-folders build,test,debug
```

#### Specify Resource Paths

Point to specific resource directories:

```bash
python app/AndroidResourceTranslator.py \
  ./app/src/main/res \
  ./library/src/main/res \
  --auto-translate
```

## Command-Line Reference

| Option                      | Short  | Description                                       | Default         |
| --------------------------- | ------ | ------------------------------------------------- | --------------- |
| `--auto-translate`        | `-a` | Enable automatic translation                      | `false`       |
| `--llm-provider`          | -      | Choose `openai` or `openrouter`               | `openai`      |
| `--model`                 | -      | Model identifier                                  | `gpt-4o-mini` |
| `--openai-model`          | -      | (Deprecated, use `--model`)                     | -               |
| `--project-context`       | -      | Additional context for translations               | `""`          |
| `--log-trace`             | `-l` | Enable detailed logging                           | `false`       |
| `--ignore-folders`        | -      | Folders to skip (comma-separated)                 | `""`          |
| `--openai-api-key`        | -      | OpenAI API key (or use env var)                   | -               |
| `--openrouter-api-key`    | -      | OpenRouter API key (or use env var)               | -               |
| `--openrouter-site-url`   | -      | Your site URL (for OpenRouter rankings)           | `""`          |
| `--openrouter-site-name`  | -      | Your site name (for OpenRouter rankings)          | `""`          |
| `--validate-translations` | `-v` | Manual validation (not recommended for local use) | `false`       |

## Available Models

### OpenAI Models

`gpt-4o-mini`
`gpt-4o`

### OpenRouter Models (Examples)

`google/gemini-2.0-flash-exp`
`anthropic/claude-3.5-sonnet`
`meta-llama/llama-3.1-405b-instruct`
`openai/gpt-4o`

See all models: https://openrouter.ai/docs/models

## Expected Project Structure

Your Android project should follow the standard structure:

```
your-android-project/
├── app/
│   └── src/
│       └── main/
│           └── res/
│               ├── values/
│               │   └── strings.xml       # English (default)
│               ├── values-es/
│               │   └── strings.xml       # Spanish
│               ├── values-pt-rPT/
│               │   └── strings.xml       # Portuguese (Portugal)
│               └── values-zh-rCN/
│                   └── strings.xml       # Chinese (Simplified)
└── library/
    └── src/
        └── main/
            └── res/
                └── values/
                    └── strings.xml
```

## Example Output

```
INFO: Found 2 modules with 8 resource files
INFO: Starting auto-translation using openai with model gpt-4o-mini
INFO: Auto-translating missing resources for module 'app', language 'es'
INFO: Translated string 'welcome_message' to es: 'Welcome!' -> '¡Bienvenido!'
INFO: Translated string 'app_name' to es: 'MyApp' -> 'MiApp'
INFO: Translated 5 strings successfully
INFO: Updated XML file: app/src/main/res/values-es/strings.xml
```

## What the Script Does

1. **Scans** your project for `strings.xml` files in `values/` and `values-XX/` folders
2. **Detects** missing translations by comparing against the default (English) resources
3. **Translates** missing strings using the selected LLM provider
4. **Updates** the XML files while preserving formatting and structure
5. **Preserves** all special elements:
   - Placeholders: `%s`, `%d`, `%1$s`, `%2$d`, etc.
   - HTML tags: `<b>`, `<i>`, `<u>`, etc.
   - CDATA sections
   - XML entities
   - Special characters (properly escaped)

## Testing with Sample Data

If you don't have an Android project handy, you can create a simple test structure:

```bash
# Create test structure
mkdir -p test_project/app/src/main/res/values
mkdir -p test_project/app/src/main/res/values-es

# Create default strings.xml
cat > test_project/app/src/main/res/values/strings.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">MyApp</string>
    <string name="welcome_message">Welcome to MyApp!</string>
    <string name="button_start">Start</string>
</resources>
EOF

# Create empty Spanish strings.xml (to be populated)
cat > test_project/app/src/main/res/values-es/strings.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">MyApp</string>
</resources>
EOF

# Run translator
python app/AndroidResourceTranslator.py test_project --auto-translate
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'lxml'"

**Solution:**

```bash
pip install -r requirements.txt
```

### "Error: API key not set!"

**Solution:**

```bash
# Verify your environment variable is set
# Windows PowerShell:
echo $env:OPENAI_API_KEY

# Windows CMD:
echo %OPENAI_API_KEY%

# macOS/Linux:
echo $OPENAI_API_KEY
```

### "No resource files found!"

**Solution:**

- Check that your path points to the Android project root or a valid resource directory
- Verify that `strings.xml` files exist in `values/` folders
- Try using `--log-trace` to see what the script is scanning

### "ImportError: cannot import name 'LLMConfig'"

**Solution:**

- Make sure you're running from the correct directory
- Verify that `app/llm_provider.py` exists
- Try: `cd AndroidResourceTranslator && python app/AndroidResourceTranslator.py ...`

### Translations are not accurate

**Solution:**

- Add `--project-context` with details about your app
- Try a different model (e.g., `gpt-4o` or `claude-3.5-sonnet`)
- Check that your source English strings are clear and unambiguous

## Next Steps

Once you've tested locally and are satisfied with the results, consider:

1. Setting up the **GitHub Action** for automatic translations on commits
2. Reading the main [README.md](README.md) for GitHub Actions setup
3. Checking [CLAUDE.md](CLAUDE.md) for detailed architecture documentation
4. Reading [CONTRIBUTING.md](CONTRIBUTING.md) if you want to contribute

## Support

If you encounter issues:

1. Enable `--log-trace` to see detailed logging
2. Check the error message carefully
3. Verify your API key is set correctly
4. Make sure your Android project structure is correct
5. Open an issue on GitHub if you need help

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.
