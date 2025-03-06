# Android Resource Translator

*WIP*

**Android Resource Translator** scans your `strings.xml` files for missing translations and automatically translates them using OpenAI’s language models.

<!--[![GitHub Action](https://img.shields.io/badge/GitHub%20Action-enabled-brightgreen)](https://github.com/)-->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)

## GitHub Actions Workflow Examples

### Simple Example

If you want to quickly try out the action with minimal configuration, add this step to your workflow:

```yaml
- name: Run Android Resource Translator
  uses: duartebarbosadev/AndroidResourceTranslator@v1
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
        # (Optional inputs)
        #with:
          #resources_paths: "./app/src/main/res"  # default will search entire project
          #openai_model: "gpt-3.5-turbo" # default is 4o-mini
          #log_trace: "true" #default is true
          #validate_translations: "false"
          #ignore_folders: "build" # Default will follow .gitignore
          #project_context: "Your project context here" # (Default is no context)
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

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
  
            This pull request was automatically generated.
          labels: "translation, automated pr"
          assignees: "[yourname]"
          reviewers: "[yourname]"
```

## Local Execution

To run the translator on your local machine, execute:

```bash
python AndroidResourceTranslator.py /path/to/your/android/project --auto-translate
```

You can also pass additional parameters like `--project-context` and `--validate-translations` as needed.

## Configuration

The action supports the following inputs:

| Input                   | Description                                                                                                                                                                                                                                    | Default Value                  | Optional | Example                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | -------- | ---------------------------------------------------------------------- |
| **resources_paths**     | Paths to the Android resource directories. Typically includes directories such as `app/src/main/res`, `library/src/main/res`, etc. If not provided, this action will search throughout the entire project folder.                         | `${{ github.workspace }}`      | Yes      | `./app/src/main/res, ./library/src/main/res, ./feature/src/main/res`   |
| **auto_translate**      | Automatically translate missing resources. Set it to `false` to disable auto-translation.                                                                                                                                                        | `"false"`                      | Yes      | `"true"` or `"false"`                                                  |
| **validate_translations** | Enable manual validation of OpenAI translations before saving. When enabled, you will be prompted to confirm each translation.                                                                                                                   | `"false"`                      | Yes      | `"true"` or `"false"`                                                  |
| **log_trace**           | Enable detailed logging. Use `"true"` for verbose output.                                                                                                                                                                                     | `"false"`                      | Yes      | `"true"`                                                               |
| **openai_model**        | Specify the OpenAI model to use for translation. We advise using `gpt-4o-mini`.                                                                                                                                                                 | `"gpt-4o-mini"`                | Yes      | `"gpt-3.5-turbo"`, `"gpt-4o"`                                            |
| **project_context**     | Additional project context to include in translation prompts.                                                                                                                                                                                 | `""`                           | Yes      | `"Android launcher application"`                                       |
| **ignore_folders**      | Comma-separated list of folder names to ignore during resource scanning. If empty, .gitignore file will be used instead.                                                                                                                     | `""`                           | Yes      | `"build,temp,cache"`                                                   |
| **openai_api_key**      | OpenAI API key to use for translation.                                                                                                                                                                                                         | N/A                            | Yes      |                                                                        |

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

## Changelog

All notable changes are documented in [CHANGELOG.md](./CHANGELOG.md).

## License

This project is licensed under the [MIT License](./LICENSE).

If you have any questions or need assistance, feel free to open an issue or reach out.

*Built with ❤️ by [Duarte Barbosa](https://github.com/duartebarbosadev).*