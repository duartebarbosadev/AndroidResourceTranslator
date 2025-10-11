#!/usr/bin/env python3
"""
LLM Provider Module

This module provides an abstraction layer for communicating with different
LLM providers (OpenAI, OpenRouter) using a unified interface. It handles
provider-specific configurations, API endpoints, and authentication.
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Tool/Function Calling Schemas for Structured Outputs
# ------------------------------------------------------------------------------

# Tool schema for translating single strings
# Uses strict: True for guaranteed schema compliance (OpenAI Structured Outputs)
TRANSLATE_STRING_TOOL = {
    "type": "function",
    "function": {
        "name": "translate_string",
        "description": "Translate a single Android UI string to the target language following all translation guidelines",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "translation": {
                    "type": "string",
                    "description": "The translated text in the target language with proper character escaping",
                }
            },
            "required": ["translation"],
            "additionalProperties": False,
        },
    },
}

# Tool schema for translating plural resources
# Returns a dictionary mapping quantity keys to translated strings
# Note: We explicitly define all 6 Android plural keys as optional properties
# to help the model understand what to return without requiring strict mode
TRANSLATE_PLURAL_TOOL = {
    "type": "function",
    "function": {
        "name": "translate_plural",
        "description": "Translate Android plural resources with all appropriate quantity forms for the target language",
        "parameters": {
            "type": "object",
            "properties": {
                "one": {
                    "type": "string",
                    "description": "Translation for singular quantity (e.g., '1 day')",
                },
                "other": {
                    "type": "string",
                    "description": "Translation for other quantities (e.g., '%d days') - this is the default fallback",
                },
                "zero": {
                    "type": "string",
                    "description": "Translation for zero quantity if the target language requires it",
                },
                "two": {
                    "type": "string",
                    "description": "Translation for dual quantity if the target language requires it",
                },
                "few": {
                    "type": "string",
                    "description": "Translation for few quantity if the target language requires it (e.g., Slavic languages)",
                },
                "many": {
                    "type": "string",
                    "description": "Translation for many quantity if the target language requires it (e.g., Slavic languages)",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
}


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    OPENROUTER = "openrouter"


@dataclass
class LLMConfig:
    """
    Configuration for LLM API access.

    Attributes:
        provider: The LLM provider to use (OpenAI or OpenRouter)
        api_key: API key for authentication
        model: Model identifier (e.g., "gpt-4o-mini" or "google/gemini-2.5-flash-preview-09-2025")
        site_url: Optional site URL for OpenRouter rankings
        site_name: Optional site name for OpenRouter rankings
        send_site_info: Whether to send site URL/name to OpenRouter (default: True)
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
    Client for interacting with LLM APIs.

    Supports both OpenAI and OpenRouter with a unified interface.
    Uses the OpenAI Python SDK as both providers are API-compatible.
    """

    # Provider-specific base URLs
    BASE_URLS = {
        LLMProvider.OPENAI: "https://api.openai.com/v1",
        LLMProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    }

    def __init__(self, config: LLMConfig):
        """
        Initialize the LLM client with provider configuration.

        Args:
            config: LLMConfig object with provider settings

        Raises:
            ImportError: If the OpenAI package is not installed
        """
        self.config = config
        self.client = self._create_client()

        logger.info(
            f"Initialized LLM client with provider={config.provider.value}, "
            f"model={config.model}"
        )

    def _create_client(self):
        """
        Create and configure the OpenAI client for the selected provider.

        Returns:
            Configured OpenAI client instance

        Raises:
            ImportError: If the OpenAI package is not installed
        """
        try:
            from openai import OpenAI
        except ImportError:
            logger.error(
                "OpenAI package not installed. Please install it using 'pip install openai'."
            )
            raise ImportError(
                "OpenAI package not installed. Run 'pip install openai' first."
            )

        base_url = self.BASE_URLS[self.config.provider]

        logger.debug(f"Creating OpenAI client with base_url={base_url}")

        return OpenAI(api_key=self.config.api_key, base_url=base_url)

    def _get_extra_headers(self) -> Dict[str, str]:
        """
        Get provider-specific extra headers.

        For OpenRouter, includes HTTP-Referer and X-Title for rankings
        (only if send_site_info is True).

        Returns:
            Dictionary of extra headers to include in requests
        """
        if (
            self.config.provider == LLMProvider.OPENROUTER
            and self.config.send_site_info
        ):
            headers = {}

            if self.config.site_url:
                headers["HTTP-Referer"] = self.config.site_url
                logger.debug(f"Adding HTTP-Referer header: {self.config.site_url}")

            if self.config.site_name:
                headers["X-Title"] = self.config.site_name
                logger.debug(f"Adding X-Title header: {self.config.site_name}")

            return headers

        return {}

    def chat_completion(
        self,
        messages: list,
        tools: Optional[list] = None,
        tool_choice: str = "required",
        temperature: float = 0,
        **kwargs,
    ) -> Any:
        """
        Send a chat completion request to the LLM API with optional function calling.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions for function calling
            tool_choice: Controls which tool is called: "auto", "required", or "none" (default: "required")
            temperature: Sampling temperature (0 = deterministic, 1 = creative)
            **kwargs: Additional arguments to pass to the API

        Returns:
            If tools are provided: Dict containing the function arguments
            If no tools: String containing the generated text response

        Raises:
            Exception: For any API-related errors (authentication, rate limits, etc.)
        """
        try:
            extra_headers = self._get_extra_headers()

            logger.debug(
                f"Sending chat completion request to {self.config.provider.value} "
                f"(model: {self.config.model}, temperature: {temperature}, "
                f"tools: {'yes' if tools else 'no'})"
            )

            # Prepare API call parameters
            api_params = {
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature,
                **kwargs,
            }

            # Add tools/function calling support
            if tools:
                api_params["tools"] = tools
                api_params["tool_choice"] = tool_choice
                # Structured outputs require parallel_tool_calls: false
                api_params["parallel_tool_calls"] = False

            # Add extra headers for OpenRouter
            if extra_headers:
                api_params["extra_headers"] = extra_headers

            # Make the API call
            response = self.client.chat.completions.create(**api_params)

            # Parse response based on whether tools were used
            if tools:
                # Extract function call arguments
                message = response.choices[0].message

                if not message.tool_calls:
                    raise ValueError(
                        "Model did not return any tool calls despite tool_choice='required'"
                    )

                tool_call = message.tool_calls[0]
                function_name = tool_call.function.name
                arguments_str = tool_call.function.arguments

                logger.debug(f"Raw function arguments string: {arguments_str}")

                # Parse the JSON arguments
                import json

                arguments = json.loads(arguments_str)

                logger.debug(
                    f"Function called: {function_name} with {len(arguments)} parameters"
                )
                logger.debug(f"Parsed arguments: {arguments}")

                return arguments

            else:
                # Extract text content (backward compatibility)
                generated_text = response.choices[0].message.content.strip()

                logger.debug(
                    f"Received response from {self.config.provider.value}: {generated_text[:100]}..."
                )

                return generated_text

        except Exception as e:
            logger.error(f"Error calling {self.config.provider.value} API: {e}")
            raise


def translate_with_llm(
    text: str, system_message: str, user_prompt: str, llm_config: LLMConfig
) -> str:
    """
    Translate text using the configured LLM provider with function calling.

    This is the main entry point for single string translations.
    Uses temperature=0 for deterministic, consistent translations.
    Leverages function calling with structured outputs for 100% reliable schema compliance.

    Args:
        text: The text to translate
        system_message: System prompt defining the translator's role
        user_prompt: User prompt with translation guidelines and target language
        llm_config: LLM provider configuration

    Returns:
        The translated text as a string

    Raises:
        Exception: For any API-related errors
    """
    if not text or not text.strip():
        return ""

    client = LLMClient(llm_config)

    # Construct the messages for the chat completion
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_prompt},
    ]

    # Use function calling with structured output for guaranteed reliability
    result = client.chat_completion(
        messages=messages,
        tools=[TRANSLATE_STRING_TOOL],
        tool_choice="required",
        temperature=0,  # Deterministic output for consistent translations
    )

    # Extract translation from function call result
    # The schema guarantees this will always have a "translation" key
    return result["translation"]


def translate_plural_with_llm(
    plural_json: str, system_message: str, user_prompt: str, llm_config: LLMConfig
) -> Dict[str, str]:
    """
    Translate plural resources using the configured LLM provider with function calling.

    This function handles plural resources and returns a structured dictionary.
    Leverages function calling with structured outputs to guarantee correct schema.

    Args:
        plural_json: JSON string of plural forms to translate
        system_message: System prompt defining the translator's role
        user_prompt: User prompt with plural-specific guidelines
        llm_config: LLM provider configuration

    Returns:
        Dictionary mapping plural quantity keys to translated strings
        (e.g., {"one": "1 day", "other": "%d days"})

    Raises:
        Exception: For any API-related errors
    """
    client = LLMClient(llm_config)

    # Construct the messages for the chat completion
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_prompt},
    ]

    # Use function calling with structured output for guaranteed reliability
    result = client.chat_completion(
        messages=messages,
        tools=[TRANSLATE_PLURAL_TOOL],
        tool_choice="required",
        temperature=0,  # Deterministic output for consistent translations
    )

    # Extract translations from function call result
    # The result now directly contains the plural keys (one, other, zero, two, few, many)
    logger.debug(f"Received plural translation result keys: {list(result.keys())}")
    logger.debug(f"Full plural translation result: {result}")

    # Validate that at least one plural key was returned
    if not result:
        raise ValueError("LLM returned empty result for plural resource translation")

    # Validate that at least the "other" key is present (Android's mandatory fallback)
    if "other" not in result:
        logger.warning(
            f"LLM did not provide 'other' key for plural translation. "
            f"Provided keys: {list(result.keys())}. "
            f"'other' is mandatory in Android as a fallback."
        )
        # If there's only one key, use it as 'other' fallback
        if len(result) == 1:
            key = list(result.keys())[0]
            result["other"] = result[key]
            logger.info(f"Using '{key}' value as 'other' fallback")
        elif len(result) == 0:
            raise ValueError("LLM returned no plural translations")

    return result
