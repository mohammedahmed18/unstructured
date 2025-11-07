import csv
import io
from typing import Dict, Generator, Iterable, List, Optional, Union

from unstructured.documents.elements import Text

PRODIGY_TYPE = List[Dict[str, Union[str, Dict[str, str]]]]


def _validate_prodigy_metadata(
    elements: List[Text],
    metadata: Optional[List[Dict[str, str]]] = None,
) -> Iterable[Dict[str, str]]:
    """
    Returns validated metadata list for Prodigy bricks.
    Raises ValueError with error message if metadata is not valid.
    """
    if metadata:
        if len(metadata) != len(elements):
            raise ValueError(
                "The length of the metadata parameter does not match with"
                " the length of the elements parameter.",
            )
        for index, metadatum in enumerate(metadata):
            if "id" in metadatum:
                raise ValueError(
                    f'The key "id" is not allowed with metadata parameter at index: {index}',
                )
        validated_metadata = metadata
    else:
        validated_metadata = [{} for _ in elements]
    return validated_metadata


def stage_for_prodigy(
    elements: List[Text],
    metadata: Optional[List[Dict[str, str]]] = None,
) -> PRODIGY_TYPE:
    """
    Converts the document to the JSON format required for use with Prodigy.
    ref: https://prodi.gy/docs/api-loaders#input
    """

    validated_metadata: Iterable[Dict[str, str]] = _validate_prodigy_metadata(elements, metadata)

    prodigy_data: PRODIGY_TYPE = []
    for element, metadatum in zip(elements, validated_metadata):
        if isinstance(element.id, str):
            metadatum["id"] = element.id
        data: Dict[str, Union[str, Dict[str, str]]] = {"text": element.text, "meta": metadatum}
        prodigy_data.append(data)

    return prodigy_data


def stage_csv_for_prodigy(
    elements: List[Text],
    metadata: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Converts the document to the CSV format required for use with Prodigy.
    ref: https://prodi.gy/docs/api-loaders#input
    """
    validated_metadata: Iterable[Dict[str, str]] = _validate_prodigy_metadata(elements, metadata)

    # CSV fieldnames construction: optimize by collecting all keys in a set directly
    # and lowercasing them once, no need to use union + chain
    fieldname_set = set()
    for metadatum in validated_metadata:
        fieldname_set.update(k.lower() for k in metadatum)
    csv_fieldnames = ["text", "id"]
    csv_fieldnames += sorted(fieldname_set)  # sorting for deterministic column order

    # Avoid inner function creation per call: use generator expression for rows for perf

    def _get_rows() -> Generator[Dict[str, str], None, None]:
        for element, metadatum in zip(elements, validated_metadata):
            # Lowercase keys once only if needed
            if metadatum:
                # fast path: dictionary comprehension for lowercased key metadata dict
                metadatum_lower = {key.lower(): value for key, value in metadatum.items()}
                row_data = dict(text=element.text, **metadatum_lower)
            else:
                row_data = {"text": element.text}
            if isinstance(element.id, str):
                row_data["id"] = element.id
            yield row_data

    with io.StringIO() as buffer:
        writer = csv.DictWriter(buffer, fieldnames=csv_fieldnames, extrasaction="ignore")
        writer.writeheader()
        # writerows accepts any iterable; avoiding conversion to list
        writer.writerows(_get_rows())
        return buffer.getvalue()
