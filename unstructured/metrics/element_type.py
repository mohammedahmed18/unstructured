from __future__ import annotations

import json

from typing_extensions import TypeAlias

FrequencyDict: TypeAlias = "dict[tuple[str, int | None], int]"
"""Like:
    {
        ("ListItem", 0): 2,
        ("NarrativeText", None): 2,
        ("Title", 0): 5,
        ("UncategorizedText", None): 6,
    }
"""


def get_element_type_frequency(
    elements: str,
) -> FrequencyDict:
    """
    Calculate the frequency of Element Types from a list of elements.

    Args:
        elements (str): String-formatted json of all elements (as a result of elements_to_json).
    Returns:
        Element type and its frequency in dictionary format.
    """
    frequency: dict[tuple[str, int | None], int] = {}
    if len(elements) == 0:
        return frequency
    for element in json.loads(elements):
        type = element.get("type")
        category_depth = element["metadata"].get("category_depth")
        key = (type, category_depth)
        if key not in frequency:
            frequency[key] = 1
        else:
            frequency[key] += 1
    return frequency


def calculate_element_type_percent_match(
    output: FrequencyDict,
    source: FrequencyDict,
    category_depth_weight: float = 0.5,
) -> float:
    """Calculate the percent match between two frequency dictionary.

    Intended to use with `get_element_type_frequency` function. The function counts the absolute
    exact match (type and depth), and counts the weighted match (correct type but different depth),
    then normalized with source's total elements.
    """
    if len(output) == 0 or len(source) == 0:
        return 0.0
    total_source_element_count = 0
    total_match_element_count = 0

    unmatched_depth_output: dict[str, int] = {}
    unmatched_depth_source: dict[str, int] = {}

    # Track which items remain unmatched after exact matching
    source_remaining = source.copy()
    output_remaining = output.copy()

    # Fast path: do all exact matches, updating element-level remainders for outputs
    for k, out_count in output.items():
        src_count = source.get(k, 0)
        if src_count:
            match_count = min(out_count, src_count)
            total_match_element_count += match_count
            total_source_element_count += match_count

            rem_output = out_count - match_count
            rem_source = src_count - match_count

            if rem_output > 0:
                etype = k[0]
                unmatched_depth_output[etype] = unmatched_depth_output.get(etype, 0) + rem_output
                output_remaining[k] = rem_output
            else:
                output_remaining.pop(k, None)

            if rem_source > 0:
                source_remaining[k] = rem_source
            else:
                source_remaining.pop(k, None)
        else:
            etype = k[0]
            unmatched_depth_output[etype] = unmatched_depth_output.get(etype, 0) + out_count

    # Now, collect unmatched leftovers from source_remaining, summed by element type
    unmatched_depth_source = _convert_to_frequency_without_depth(source_remaining)

    # Add up the remaining total for normalization
    total_source_element_count += sum(unmatched_depth_source.values())

    # Partial matches weighted
    for etype, src_val in unmatched_depth_source.items():
        if etype in unmatched_depth_output:
            match_count = min(unmatched_depth_output[etype], src_val)
            total_match_element_count += match_count * category_depth_weight

    # Prevent division by zero, clamp result in [0, 1]
    if total_source_element_count == 0:
        return 0.0
    return min(max(total_match_element_count / total_source_element_count, 0.0), 1.0)


def _convert_to_frequency_without_depth(d: FrequencyDict) -> dict[str, int]:
    """
    Takes in element frequency with depth of format (type, depth): value
    and converts to dictionary without depth of format type: value
    """
    res: dict[str, int] = {}
    for (element_type, _), v in d.items():
        res[element_type] = res.get(element_type, 0) + v
    return res
