# Scrolless Crash Reproduction Fixture

This fixture mirrors the Scrolless string set that triggered the `help_step3_description:` KeyError during batch translation. Use it to reproduce and test fixes for the colon-suffix bug in `_translate_missing_strings`.

## Structure

```
sample_project/ScrollessCrashRepro/
└── mobile/src/main/res/
    ├── values/strings.xml          # English source strings (41 keys)
    ├── values-de/strings.xml       # Deliberately incomplete translations
    ├── values-hu/strings.xml
    ├── values-ja/strings.xml
    ├── values-nb-rNO/strings.xml
    └── values-ta-rIN/strings.xml
```

Each non-default locale contains only `app_name`, ensuring the translator has to process the full batch of keys, just like in the production failure.

## Running the Translator Against the Fixture

```bash
python app/AndroidResourceTranslator.py sample_project/ScrollessCrashRepro/ \
  --project-context "Scrolless is an Android app designed to help users reduce time spent on social media and avoid brainrot by limiting endless scrolling of Reels, Shorts, and TikToks."
```

Pointing the action or CLI at this directory (instead of your real project) allows you to reproduce the exact failing conditions without touching the production repository.
