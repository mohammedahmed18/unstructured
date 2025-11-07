from typing import Any, Dict, List, Optional

from unstructured.documents.elements import Text


def stage_for_datasaur(
    elements: List[Text],
    entities: Optional[List[List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Convert a list of elements into a list of dictionaries for use in Datasaur"""
    num_elements = len(elements)
    # Avoid initializing and possibly reallocating _entities later
    if entities is None:
        # Only allocate one list (faster for empty case)
        _entities: List[List[Dict[str, Any]]] = [[]] * num_elements
    else:
        if len(entities) != num_elements:
            raise ValueError("If entities is specified, it must be the same length as elements.")

        for entity_list in entities:
            for entity in entity_list:
                _validate_datasaur_entity(entity)

        _entities = entities

    # Preallocate result list for maximum speed
    result: List[Dict[str, Any]] = [
        {"text": item.text, "entities": _entities[i]} for i, item in enumerate(elements)
    ]

    return result


def _validate_datasaur_entity(entity: Dict[str, Any]):
    """Raises an error if the Datasaur entity is invalid."""
    # Optimize to avoid dict and items call each time in loop
    try:
        if not isinstance(entity["text"], str):
            raise TypeError
        if not isinstance(entity["type"], str):
            raise TypeError
        if not isinstance(entity["start_idx"], int):
            raise TypeError
        if not isinstance(entity["end_idx"], int):
            raise TypeError
    except KeyError as e:
        raise ValueError(f"Key '{e.args[0]}' was expected but not present in the Datasaur entity.")
    except TypeError:
        for key, _type in (("text", str), ("type", str), ("start_idx", int), ("end_idx", int)):
            v = entity.get(key)
            if not isinstance(v, _type):
                raise ValueError(f"Expected type {_type} for {key}. Got {type(v)}.")
