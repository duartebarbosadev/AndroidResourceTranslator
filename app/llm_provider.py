#!/usr/bin/env python3
"""
LLM Provider Module

This module provides an abstraction layer for communicating with different
LLM providers (OpenAI, OpenRouter, Anthropic, Google, etc.) using a unified interface
powered by LiteLLM and Instructor. It handles structured outputs with Pydantic
and provider-specific configurations.
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import litellm
import instructor

logger = logging.getLogger(__name__)

# Suppress noisy logging from litellm/openai unless error/warning
logging.getLogger("litellm").setLevel(logging.WARNING)


# ------------------------------------------------------------------------------
# Pydantic Schemas for Structured Outputs (Instructor)
# ------------------------------------------------------------------------------


class SingleTranslation(BaseModel):
    """Schema for translating single strings."""

    translation: str = Field(
        ...,
        description="The translated text in the target language with proper character escaping",
    )


class PluralTranslation(BaseModel):
    """Schema for translating plural resources with individual quantity forms."""

    one: Optional[str] = Field(
        None, description="Translation for singular quantity (e.g., '1 day')"
    )
    other: str = Field(
        ...,
        description="Translation for other quantities (e.g., '%d days') - this is the default fallback",
    )
    zero: Optional[str] = Field(
        None,
        description="Translation for zero quantity if the target language requires it",
    )
    two: Optional[str] = Field(
        None,
        description="Translation for dual quantity if the target language requires it",
    )
    few: Optional[str] = Field(
        None,
        description="Translation for few quantity if the target language requires it",
    )
    many: Optional[str] = Field(
        None,
        description="Translation for many quantity if the target language requires it",
    )


class StringBatchItem(BaseModel):
    """Single item in a batch string translation."""

    key: str = Field(..., description="The string resource key from the input")
    translation: str = Field(..., description="The translated text for this key")


class StringBatchTranslation(BaseModel):
    """Schema for batch translating multiple strings at once."""

    translations: List[StringBatchItem] = Field(
        ..., description="Array of translation objects, one for each input string"
    )


class PluralBatchItem(BaseModel):
    """Single item in a batch plural translation."""

    plural_name: str = Field(..., description="The plural resource name from the input")
    quantities: PluralTranslation = Field(
        ..., description="Translations for each quantity form"
    )


class PluralsBatchTranslation(BaseModel):
    """Schema for batch translating multiple plural resources at once."""

    translations: List[PluralBatchItem] = Field(
        ...,
        description="Array of plural translation objects, one for each input plural resource",
    )


# ------------------------------------------------------------------------------
# Core Interfaces and Clients
# ------------------------------------------------------------------------------


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    OPENROUTER = "openrouter"


@dataclass
class LLMConfig:
    """
    Configuration for LLM API access.
    """

    provider: LLMProvider
    api_key: str
    model: str
    site_url: Optional[str] = None
    site_name: Optional[str] = None
    send_site_info: bool = True

    def __post_init__(self):
        """Validate configuration after initialization."""
        if isinstance(self.provider, str):
            self.provider = LLMProvider(self.provider.lower())

        if not self.api_key:
            raise ValueError("API key is required")

        if not self.model:
            raise ValueError("Model name is required")


class LLMClient:
    """
    Client for interacting with LLM APIs using LiteLLM and Instructor.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        # Patch LiteLLM with Instructor for robust structured outputs
        self.client = instructor.from_litellm(completion=litellm.completion)

        logger.info(
            f"Initialized LLM client with provider={config.provider.value}, "
            f"model={config.model}"
        )

    def chat_completion(
        self,
        messages: list,
        response_model: Optional[type] = None,
        temperature: float = 0,
        **kwargs,
    ) -> Any:
        """
        Send a chat completion request to the LLM API using LiteLLM and Instructor.
        """
        # Format model string for LiteLLM
        model_str = self.config.model
        if self.config.provider == LLMProvider.OPENROUTER and not model_str.startswith(
            "openrouter/"
        ):
            model_str = f"openrouter/{model_str}"
        elif self.config.provider == LLMProvider.OPENAI and not any(
            model_str.startswith(p) for p in ["openai/", "gpt-"]
        ):
            model_str = f"openai/{model_str}"

        # Build payload parameters
        api_params = {
            "model": model_str,
            "messages": messages,
            "temperature": temperature,
            "api_key": self.config.api_key,
            **kwargs,
        }

        # Add provider-specific headers (OpenRouter ranking / site info)
        if (
            self.config.provider == LLMProvider.OPENROUTER
            and self.config.send_site_info
        ):
            extra_headers = {}
            if self.config.site_url:
                extra_headers["HTTP-Referer"] = self.config.site_url
            if self.config.site_name:
                extra_headers["X-Title"] = self.config.site_name
            if extra_headers:
                api_params["extra_headers"] = extra_headers

        logger.debug(
            f"Sending chat completion request via LiteLLM (model: {model_str}, "
            f"response_model: {response_model.__name__ if response_model else 'None'})"
        )

        try:
            if response_model:
                return self.client.chat.completions.create(
                    response_model=response_model,
                    **api_params,
                )
            else:
                response = litellm.completion(**api_params)
                return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error during LLM API call: {e}")
            raise


# ------------------------------------------------------------------------------
# Translation Orchestration Helpers
# ------------------------------------------------------------------------------


def translate_with_llm(
    text: str, system_message: str, user_prompt: str, llm_config: LLMConfig
) -> str:
    """
    Translate text using the configured LLM provider with function calling via Instructor.
    """
    if not text or not text.strip():
        return ""

    client = LLMClient(llm_config)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_completion(
        messages=messages,
        response_model=SingleTranslation,
        temperature=0,
    )

    return result.translation


def translate_plural_with_llm(
    plural_json: str, system_message: str, user_prompt: str, llm_config: LLMConfig
) -> Dict[str, str]:
    """
    Translate plural resources using the configured LLM provider with function calling via Instructor.
    """
    client = LLMClient(llm_config)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_completion(
        messages=messages,
        response_model=PluralTranslation,
        temperature=0,
    )

    # Convert Pydantic model to dictionary
    result_dict = result.model_dump(exclude_none=True)

    # Validate mandatory 'other' fallback
    if "other" not in result_dict:
        logger.warning(
            f"LLM did not provide 'other' key for plural translation. "
            f"Provided keys: {list(result_dict.keys())}."
        )
        if len(result_dict) == 1:
            key = list(result_dict.keys())[0]
            result_dict["other"] = result_dict[key]
        elif len(result_dict) == 0:
            raise ValueError("LLM returned no plural translations")

    return result_dict


def translate_strings_batch_with_llm(
    strings_dict: Dict[str, str],
    system_message: str,
    user_prompt: str,
    llm_config: LLMConfig,
    reference_examples: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    """
    Translate multiple strings in a single API call using batch mode via Instructor.
    """
    if not strings_dict:
        return {}

    client = LLMClient(llm_config)

    import json

    strings_json = json.dumps(strings_dict, indent=2, ensure_ascii=False)
    full_user_prompt = user_prompt

    if reference_examples:
        reference_json = json.dumps(reference_examples, indent=2, ensure_ascii=False)
        full_user_prompt += (
            "\n\nUse the following existing translations from the target project "
            "as context for tone and terminology. Do not modify them:\n"
            + reference_json
        )

    full_user_prompt += (
        "\n\nTranslate ALL the strings below from English to the target language.\n"
        + "The strings are provided as JSON key-value pairs. Translate only the values:\n"
        + strings_json
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": full_user_prompt},
    ]

    result = client.chat_completion(
        messages=messages,
        response_model=StringBatchTranslation,
        temperature=0,
    )

    translations = {}
    for item in result.translations:
        if item.key and item.translation is not None:
            translations[item.key] = item.translation

    # Validate that we got translations for all requested keys
    missing_keys = set(strings_dict.keys()) - set(translations.keys())
    if missing_keys:
        raise ValueError(
            "LLM returned an incomplete translations array. Missing keys: "
            + ", ".join(sorted(missing_keys))
        )

    return translations


def translate_plurals_batch_with_llm(
    plurals_dict: Dict[str, Dict[str, str]],
    system_message: str,
    user_prompt: str,
    llm_config: LLMConfig,
    reference_examples: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Translate multiple plural resources in a single API call using batch mode via Instructor.
    """
    if not plurals_dict:
        return {}

    client = LLMClient(llm_config)

    import json

    plurals_json = json.dumps(plurals_dict, indent=2, ensure_ascii=False)
    full_user_prompt = user_prompt

    if reference_examples:
        reference_json = json.dumps(reference_examples, indent=2, ensure_ascii=False)
        full_user_prompt += (
            "\n\nUse the following existing plural translations from the target "
            "project as context. Do not modify them:\n" + reference_json
        )

    full_user_prompt += (
        "\n\nTranslate ALL the plural resources below from English to the target language.\n"
        + "Each plural resource has a name and quantity forms. Translate the text in each quantity form:\n"
        + plurals_json
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": full_user_prompt},
    ]

    result = client.chat_completion(
        messages=messages,
        response_model=PluralsBatchTranslation,
        temperature=0,
    )

    translations = {}
    for item in result.translations:
        plural_name = item.plural_name
        quantities_dict = item.quantities.model_dump(exclude_none=True)

        if plural_name and quantities_dict:
            translations[plural_name] = quantities_dict

    # Post-process missing other fallbacks
    for plural_name, quantities in translations.items():
        if "other" not in quantities:
            if quantities:
                first_key = list(quantities.keys())[0]
                quantities["other"] = quantities[first_key]

    return translations
