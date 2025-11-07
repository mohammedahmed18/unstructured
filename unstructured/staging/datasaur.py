from typing import Any, Dict, List, Optional

from unstructured.documents.elements import Text

_KEYS_AND_TYPES = (("text", str), ("type", str), ("start_idx", int), ("end_idx", int))


def stage_for_datasaur(
    elements: List[Text],
    entities: Optional[List[List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Convert a list of elements into a list of dictionaries for use in Datasaur"""
    elements_len = len(elements)
    if entities is None:
        _entities: List[List[Dict[str, Any]]] = [[] for _ in range(elements_len)]
    else:
        if len(entities) != elements_len:
            raise ValueError("If entities is specified, it must be the same length as elements.")

        for entity_list in entities:
            for entity in entity_list:
                _validate_datasaur_entity(entity)

        _entities = entities

    return [{"text": item.text, "entities": ent} for item, ent in zip(elements, _entities)]


def _validate_datasaur_entity(entity: Dict[str, Any]):
    """Raises an error if the Datasaur entity is invalid."""
    for key, _type in _KEYS_AND_TYPES:
        if key not in entity:
            raise ValueError(f"Key '{key}' was expected but not present in the Datasaur entity.")
        if not isinstance(entity[key], _type):
            raise ValueError(f"Expected type {_type} for {key}. Got {type(key)}.")
