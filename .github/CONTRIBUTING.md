# Contributing to Android Resource Translator

Thank you for your interest in contributing! This guide will help you get started with development, testing, and submitting contributions.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Development Setup](#development-setup)
- [Testing Your Changes](#testing-your-changes)
- [Code Quality](#code-quality)
- [Submitting Changes](#submitting-changes)
- [Getting Help](#getting-help)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## Ways to Contribute

### Report Bugs
Found a bug? [Open an issue](https://github.com/duartebarbosadev/AndroidResourceTranslator/issues/new) with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Your environment (OS, Python version, etc.)

### Suggest Features
Have an idea? [Open an issue](https://github.com/duartebarbosadev/AndroidResourceTranslator/issues/new) describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

### Contribute Code
Fix bugs, implement features, or improve performance by submitting pull requests.

### Improve Documentation
Help make our docs better by fixing typos, clarifying explanations, or adding examples.

### Showcase Your Project
Using Android Resource Translator? Add your project to the "Projects Using Android Resource Translator" section in the [README.md](../README.md).

## Development Setup

### 1. Fork and Clone

```bash
git clone https://github.com/duartebarbosadev/AndroidResourceTranslator.git
cd AndroidResourceTranslator
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Unix/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up API Keys

You'll need API keys for testing translation functionality.

**Option 1: OpenRouter**
```bash
export OPENROUTER_API_KEY='your-openrouter-api-key-here'
```
Get your key from [OpenRouter](https://openrouter.ai/keys)

**Option 2: OpenAI**
```bash
export OPENAI_API_KEY='your-openai-api-key-here'
```
Get your key from [OpenAI Platform](https://platform.openai.com/)

> ⚠️ **Cost Warning**: Be mindful that testing with real API calls will incur usage costs.

## Testing Your Changes

### Unit Tests

Run the complete test suite:

```bash
# Run all tests
python -m unittest discover tests
```

### Integration Testing with Sample Project

The [`sample_project/`](../sample_project/) directory contains a realistic Android app structure for testing. See the [sample project README](../sample_project/README.md) for detailed usage examples.

**Quick Test - Dry Run:**
```bash
python app/AndroidResourceTranslator.py sample_project/ --dry-run
```

**Test Translation:**
```bash
python app/AndroidResourceTranslator.py sample_project/
```

**Test with OpenRouter (Gemini):**
```bash
python app/AndroidResourceTranslator.py sample_project/ \
    --llm-provider openrouter \
    --model google/gemini-2.5-flash-preview-09-2025
```

**Test with Project Context:**
```bash
python app/AndroidResourceTranslator.py sample_project/ \
    --project-context "A shopping list mobile application"
```

## Code Quality

We use [Ruff](https://docs.astral.sh/ruff/) for code formatting and linting.

### Before Submitting a PR

**1. Run Ruff formatter:**
```bash
ruff format app/
```

**2. Run Ruff linter:**
```bash
ruff check app/ --fix
```

**3. Verify all checks pass:**
```bash
ruff check app/
```

## Getting Help

If you need help with contributing, feel free to:

1. Open an issue with your question
2. Reach out to the maintainers

## Recognition

Contributors will be acknowledged in the project's documentation. 
Thank you for your valuable contributions!
