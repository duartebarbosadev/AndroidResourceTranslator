#!/usr/bin/env python3
"""Utility helpers for sanitizing string resources before writing to XML."""

from typing import List, Optional, Tuple
import re

__all__ = [
    "escape_apostrophes",
    "escape_double_quotes",
    "escape_special_chars",
]

_BACKSLASH_SEQUENCE_TARGETS = set("nrtbf\"'dsDS")
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_HTML_SINGLE_QUOTE_ATTR_PATTERN = re.compile(r"(\s+[\w:-]+)=\'([^\']*)\'")


def _escape_character(text: str, target: str) -> str:
    """Escape occurrences of a character unless already escaped."""
    if not text:
        return text

    result: List[str] = []
    backslash_run = 0

    for ch in text:
        if ch == "\\":
            backslash_run += 1
            result.append(ch)
            continue

        if ch == target:
            if backslash_run % 2 == 0:
                result.append(f"\\{target}")
            else:
                result.append(ch)
            backslash_run = 0
            continue

        result.append(ch)
        backslash_run = 0

    return "".join(result)


def escape_apostrophes(text: Optional[str]) -> Optional[str]:
    """Escape apostrophes with a single backslash, preserving existing escapes."""
    if text is None:
        return None
    if text == "":
        return ""
    return _escape_character(text, "'")


def escape_double_quotes(text: Optional[str]) -> Optional[str]:
    """Escape double quotes with a single backslash, preserving existing escapes."""
    if text is None:
        return None
    if text == "":
        return ""
    return _escape_character(text, '"')


def _normalize_reference_text(reference_text: Optional[str]) -> Optional[str]:
    if reference_text is None:
        return None
    return reference_text.replace("\r\n", "\n").replace("\r", "\n")


def _extract_backslash_sequences(text: str) -> List[Tuple[str, int]]:
    sequences: List[Tuple[str, int]] = []
    length = len(text)
    i = 0

    while i < length:
        if text[i] != "\\":
            i += 1
            continue

        start = i
        while i < length and text[i] == "\\":
            i += 1

        slash_count = i - start
        if i >= length:
            break

        follower = text[i]
        if follower in _BACKSLASH_SEQUENCE_TARGETS:
            sequences.append((follower, slash_count))
        i += 1

    return sequences


def _align_backslash_sequences_with_reference(
    text: str, reference_text: Optional[str]
) -> str:
    if not text:
        return text

    normalized_reference = _normalize_reference_text(reference_text)
    if not normalized_reference:
        return text

    reference_sequences = _extract_backslash_sequences(normalized_reference)
    if not reference_sequences:
        return text

    ref_index = 0
    ref_len = len(reference_sequences)
    result: List[str] = []
    length = len(text)
    i = 0

    while i < length:
        if text[i] != "\\":
            result.append(text[i])
            i += 1
            continue

        start = i
        while i < length and text[i] == "\\":
            i += 1

        slash_count = i - start
        if i >= length:
            result.append("\\" * slash_count)
            break

        follower = text[i]
        if follower in _BACKSLASH_SEQUENCE_TARGETS:
            desired_count: Optional[int] = None
            for idx in range(ref_index, ref_len):
                seq_char, seq_count = reference_sequences[idx]
                if seq_char == follower:
                    desired_count = seq_count
                    ref_index = idx + 1
                    break

            if desired_count is not None:
                if desired_count > 0:
                    result.append("\\" * desired_count)
                result.append(follower)
                i += 1
                continue

        result.append("\\" * slash_count)
        continue

    return "".join(result)


def _collapse_redundant_quote_backslashes(text: str) -> str:
    """
    Collapses two or more consecutive backslashes that appear immediately before a quote character
    (either single or double quote) into exactly one backslash plus the quote character.
    This ensures that redundant escaping is removed, e.g., \\\\\" becomes \\".
    """
    if not text:
        return text
    return re.sub(r"\\{2,}([\"'])", r"\\\1", text)


def _normalize_line_breaks(text: str) -> str:
    if not text:
        return text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\\n")


def _normalize_html_tag_attributes(segment: str) -> str:
    if not segment or not segment.startswith("<"):
        return segment
    return _HTML_SINGLE_QUOTE_ATTR_PATTERN.sub(
        lambda match: f'{match.group(1)}="{match.group(2)}"', segment
    )


def escape_special_chars(
    text: Optional[str], reference_text: Optional[str] = None
) -> Optional[str]:
    """Escape problematic characters while preserving HTML and reference formatting."""
    if text is None:
        return None
    if text == "":
        return ""

    contains_html = bool(_HTML_TAG_PATTERN.search(text))
    value = _normalize_line_breaks(text)

    if contains_html:
        segments = re.split(r"(<[^>]+>)", value)
        processed_segments: List[str] = []
        for segment in segments:
            if not segment:
                continue
            if segment.startswith("<") and segment.endswith(">"):
                processed_segments.append(_normalize_html_tag_attributes(segment))
                continue

            escaped_segment = escape_apostrophes(segment)
            escaped_segment = escape_double_quotes(escaped_segment)
            processed_segments.append(escaped_segment)

        value = "".join(processed_segments)
    else:
        value = escape_apostrophes(value)
        value = escape_double_quotes(value)

    value = _align_backslash_sequences_with_reference(value, reference_text)
    value = _collapse_redundant_quote_backslashes(value)
    return value
