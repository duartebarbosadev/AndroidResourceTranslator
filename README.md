# Android Resource Translator

*WIP*

**Android Resource Translator** scans your `strings.xml` files for missing translations and automatically translates them using AI language models (OpenAI or OpenRouter).

<!--[![GitHub Action](https://img.shields.io/badge/GitHub%20Action-enabled-brightgreen)](https://github.com/)-->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)

## GitHub Actions Workflow Examples

### Simple Example (Using OpenRouter with Gemini - Default)

If you want to quickly try out the action with minimal configuration, add this step to your workflow. This uses the default provider (OpenRouter) and model (Gemini google/gemini-2.5-flash-preview-09-2025):

```yaml
- name: Run Android Resource Translator
  uses: duartebarbosadev/AndroidResourceTranslator@v1
  env:
    OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

### Simple Example (Using OpenAI)

```yaml
- name: Run Android Resource Translator
  uses: duartebarbosadev/AndroidResourceTranslator@v1
  with:
    llm_provider: openai
    model: gpt-4o-mini
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### Advanced Workflow Example

For a more complete setup—including checking out your repository, running the translator with additional options, and automatically creating a pull request with the translation report—use the following workflow snippet:

```yaml
name: Auto-translate strings.xml

on:
  push:
    branches:
      - main
    paths:
      - '**/values/strings.xml' # Call only when strings.xml is updated
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: "${{ github.workflow }}-${{ github.ref }}"
  cancel-in-progress: true

jobs:
  perform-auto-translate:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Translate strings.xml to supported languages
        id: translate
        uses: duartebarbosadev/AndroidResourceTranslator@v1
        #with: # (Optional inputs - see readme for default values)
          #llm_provider: openrouter
          #model: google/gemini-2.5-flash-preview-09-2025
          #resources_paths: "./app/src/main/res"  # default with no value will search entire project automatically
          #log_trace: "true" #default is false
          #ignore_folders: "build" # Default will follow .gitignore
          #project_context: "Your project context here" # (Default is no context)
          #openrouter_send_site_info: "false" # Set to false to disable sending site info to OpenRouter
          #include_reference_context: "false" # Disable sharing existing translations as prompt context
          #reference_context_limit: "10" # Reduce or increase how many examples are sent
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}

      - name: Create Pull Request
        uses: peter-evans/create-pull-request@v7
        with:
          branch: auto-translate  # Use a fixed branch name
          commit-message: "[Translate Bot] Auto-generated translations for non-English languages"
          committer: "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
          author: "${{ github.actor }} <${{ github.actor_id }}+${{ github.actor }}@users.noreply.github.com>"
          signoff: "false"
          title: "[Translate Bot] Auto-generated translations for non-English languages"
          body: |
            ${{ steps.translate.outputs.translation_report }}

            ---
            This pull request was automatically generated.
          labels: "translation, automated pr"
          assignees: "[yourname]"
          reviewers: "[yourname]"
```

### ⚠️ API Usage and Pricing Considerations

Please note that each time the action runs, it will process **all** missing translations. This can impact your API usage and associated costs, especially for large projects with many strings or frequent commits. Meaning that you should accept this action PR's as soon as possible to avoid repeating runs.

We recommend the model google/gemini-2.5-flash-preview-09-2025 as it got the best results in our testing and is not as expensive as the bigger models.
## Local Execution

To run the translator on your local machine, execute:

```bash
python AndroidResourceTranslator.py /path/to/your/android/project
```

You can also pass additional parameters like `--project-context` or `--dry-run` (to only check for missing translations without translating) as needed.

## Configuration

The action supports the following inputs:

| Input                        | Description                                                                                                                                                                                                                                    | Default Value                                                          | Optional | Example                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------- |
| **resources_paths**          | Paths to the Android resource directories. Typically includes directories such as `app/src/main/res`, `library/src/main/res`, etc. If not provided, this action will search throughout the entire project folder.                         | `${{ github.workspace }}`                                              | Yes      | `./app/src/main/res, ./library/src/main/res, ./feature/src/main/res`   |
| **dry_run**                  | Run in dry-run mode (only report missing translations without translating). Set to `"true"` to enable dry-run mode.                                                                                                                           | `"false"`                                                              | Yes      | `"true"` or `"false"`                                                  |
| **log_trace**                | Enable detailed logging. Use `"true"` for verbose output.                                                                                                                                                                                     | `"false"`                                                              | Yes      | `"true"`                                                               |
| **llm_provider**             | LLM provider to use for translation. Options are `"openai"` or `"openrouter"`.                                                                                                                                                                 | `"openrouter"`                                                             | Yes      | `"openai"`, `"openrouter"`                                              |
| **model**                    | Model to use for translation. For OpenAI: `gpt-4o-mini`, `gpt-4o`, etc. For OpenRouter: `google/gemini-2.5-flash-preview-09-2025` (recommended), `anthropic/claude-3.5-sonnet`, etc.                                                                                     | `"google/gemini-2.5-flash-preview-09-2025"`                                                        | Yes      | `"google/gemini-2.5-flash-preview-09-2025"`, `"anthropic/claude-3.5-sonnet"`         |
| **openrouter_site_url**      | Your site URL for OpenRouter rankings. Used to identify your application in OpenRouter analytics.                                                                                                                                             | `"https://github.com/duartebarbosadev/AndroidResourceTranslator"`     | Yes      | ``                         |
| **openrouter_site_name**     | Your site name for OpenRouter rankings. Used to identify your application in OpenRouter analytics.                                                                                                                                            | `"AndroidResourceTranslatorAction"`                                    | Yes      | `""`                                                        |
| **openrouter_send_site_info** | Send site URL and name to OpenRouter for rankings. Set to `"false"` to disable.                                                                                                                                                               | `"true"`                                                               | Yes      | `"true"` or `"false"`                                                  |
| **project_context**          | Additional project context to include in translation prompts.                                                                                                                                                                                 | `""`                                                                   | Yes      | `"Android launcher application"`                                       |
| **ignore_folders**           | Comma-separated list of folder names to ignore during resource scanning. If empty, .gitignore file will be used instead.                                                                                                                     | `""`                                                                   | Yes      | `"build,temp,cache"`                                                   |
| **include_reference_context** | Include existing translations from the destination language as context when prompting the LLM. Set to `"false"` to disable the extra context entirely.                                                                                       | `"true"`                                                               | Yes      | `"false"`                                                              |
| **reference_context_limit**  | Maximum number of existing translations to send as context examples. Use `"0"` to skip sending any reference strings even if context is enabled.                                                                                               | `"25"`                                                                 | Yes      | `"10"`                                                                 |

### Environment Variables (API Keys)

Set these as repository secrets and pass them via `env:` in your workflow:

| Variable                | Description                                      | Required For                    |
| ----------------------- | ------------------------------------------------ | ------------------------------- |
| **OPENAI_API_KEY**      | OpenAI API key                                   | OpenAI provider                 |
| **OPENROUTER_API_KEY**  | OpenRouter API key                               | OpenRouter provider             |

## Translation Report Output

After the translation process is executed, the action produces an output called `translation_report`. This report is generated in Markdown format and includes a detailed summary of all translations performed. The report contains:

- **Module Information:**  
  Each module found in your Android project is listed along with its language-specific resources.
- **Strings Translations:**  
  For each module and language, a table displays every key that was translated, including the original text and the resulting translation.
- **Plural Resources Translations:**  
  If plural resources were translated, the report shows each plural resource name along with a table listing each plural quantity (e.g., `one`, `few`, `many`) and their corresponding translations.

This output is particularly useful for manual review and validation. In the provided advanced workflow, the report is automatically inserted into the body of a pull request, allowing maintainers to inspect the changes before merging.

## Projects Using Android Resource Translator

We love to see our tool in action! Here are some projects that are using Android Resource Translator:

- **[Scrolless](https://github.com/duartebarbosadev/Scrolless/)**

*Have a project using Android Resource Translator? Let us know by submitting a pull request to add your project to this list!*

## Contributing

Contributions are very welcome! If you have ideas for improvements or spot any issues, please open an issue or submit a pull request.

For detailed guidelines on how to contribute, please see our [Contributing Guide](.github/CONTRIBUTING.md).

## License

This project is licensed under the [MIT License](./LICENSE).

If you have any questions or need assistance, feel free to open an issue or reach out.

*Built with ❤️ by [Duarte Barbosa](https://github.com/duartebarbosadev).*
