#!/usr/bin/env python3
"""
LLM Provider Module

This module provides an abstraction layer for communicating with different
LLM providers (OpenAI, OpenRouter, Anthropic, Google, etc.) using a unified interface
powered by LiteLLM. It handles structured outputs with Pydantic and provider-specific
configurations.
"""

import logging
import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import litellm

logger = logging.getLogger(__name__)
DEFAULT_LLM_TIMEOUT_SECONDS = 60

# Suppress noisy logging from litellm/openai unless error/warning
litellm.set_verbose = False
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)


# ------------------------------------------------------------------------------
# Pydantic Schemas for Structured Outputs
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
    other: Optional[str] = Field(
        None,
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


@dataclass
class LLMConfig:
    """
    Configuration for LLM API access.
    """

    provider: str
    model: str
    api_key: Optional[str] = None
    site_url: Optional[str] = None
    site_name: Optional[str] = None
    send_site_info: bool = True
    timeout_seconds: int = DEFAULT_LLM_TIMEOUT_SECONDS

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.model:
            raise ValueError("Model name is required")


class LLMClient:
    """
    Client for interacting with LLM APIs using LiteLLM.
    """

    def __init__(self, config: LLMConfig):
        self.config = config

        logger.info(
            f"Initialized LLM client with provider={config.provider}, "
            f"model={config.model}"
        )

    @staticmethod
    def _strip_json_markdown_fence(content: str) -> str:
        """Remove a surrounding Markdown code fence from model JSON output."""
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content

    @staticmethod
    def _coerce_structured_payload(
        content: str, response_model: type[BaseModel]
    ) -> str:
        """Normalize common provider deviations before Pydantic validation."""
        content = LLMClient._strip_json_markdown_fence(content)

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return content

        if response_model is StringBatchTranslation and isinstance(payload, dict):
            if "translations" not in payload:
                payload = {
                    "translations": [
                        {"key": key, "translation": value}
                        for key, value in payload.items()
                    ]
                }
        elif response_model is PluralsBatchTranslation and isinstance(payload, dict):
            if "translations" not in payload:
                payload = {
                    "translations": [
                        {"plural_name": key, "quantities": value}
                        for key, value in payload.items()
                    ]
                }

        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _get_message_value(message: Any, key: str) -> str:
        """Read a string field from either an object-style or dict-style message."""
        if isinstance(message, dict):
            value = message.get(key)
        else:
            value = getattr(message, key, None)
        return value if isinstance(value, str) else ""

    def chat_completion(
        self,
        messages: list,
        response_model: Optional[type] = None,
        temperature: float = 0,
        **kwargs,
    ) -> Any:
        """
        Send a chat completion request to the LLM API using LiteLLM.
        """
        # Build payload parameters
        api_params = {
            "model": self.config.model,
            "custom_llm_provider": self.config.provider,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": kwargs.pop("max_tokens", 4096),
            "timeout": kwargs.pop("timeout", self.config.timeout_seconds),
            **kwargs,
        }

        if self.config.api_key:
            api_params["api_key"] = self.config.api_key

        # Add provider-specific headers (OpenRouter ranking / site info)
        provider_lower = self.config.provider.lower() if self.config.provider else ""
        if provider_lower == "openrouter" and self.config.send_site_info:
            extra_headers = {}
            if self.config.site_url:
                extra_headers["HTTP-Referer"] = self.config.site_url
            if self.config.site_name:
                extra_headers["X-Title"] = self.config.site_name
            if extra_headers:
                api_params["extra_headers"] = extra_headers

        # If response_model is provided, use LiteLLM's native structured outputs (response_format)
        if response_model:
            api_params["response_format"] = response_model

        logger.debug(
            f"Sending chat completion request via LiteLLM (model: {self.config.model}, "
            f"provider: {self.config.provider})"
        )

        try:
            response = litellm.completion(**api_params)
            message = response.choices[0].message
            content = self._get_message_value(message, "content").strip()
            reasoning_content = self._get_message_value(
                message, "reasoning_content"
            ).strip()

            if not content and reasoning_content:
                logger.info(
                    "Content is empty but reasoning_content is present. "
                    "Falling back to reasoning_content for structured output parsing."
                )
                content = reasoning_content

            if response_model:
                # Natively parse and validate the JSON string into the Pydantic model
                content = self._coerce_structured_payload(content, response_model)
                return response_model.model_validate_json(content)
            return content

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
    Translate text using the configured LLM provider with structured output validation.
    """
    if not text or not text.strip():
        return ""

    client = LLMClient(llm_config)
    full_user_prompt = f"{user_prompt}\n\nText to translate:\n{text}"

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": full_user_prompt},
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
    Translate plural resources using the configured LLM provider with structured output validation.
    """
    client = LLMClient(llm_config)
    full_user_prompt = f"{user_prompt}\n\nPlural JSON to translate:\n{plural_json}"

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": full_user_prompt},
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
        if result_dict:
            key = list(result_dict.keys())[0]
            result_dict["other"] = result_dict[key]
        else:
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
    Translate multiple strings in a single API call using structured output validation.
    """
    if not strings_dict:
        return {}

    client = LLMClient(llm_config)

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
    Translate multiple plural resources in a single API call using structured output validation.
    """
    if not plurals_dict:
        return {}

    client = LLMClient(llm_config)

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

    missing_plurals = set(plurals_dict.keys()) - set(translations.keys())
    if missing_plurals:
        raise ValueError(
            "LLM returned an incomplete plural translations array. Missing plurals: "
            + ", ".join(sorted(missing_plurals))
        )

    # Post-process missing other fallbacks
    for plural_name, quantities in translations.items():
        if "other" not in quantities:
            if quantities:
                first_key = list(quantities.keys())[0]
                quantities["other"] = quantities[first_key]

    return translations
