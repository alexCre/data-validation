from validation.registry import operator


@operator(
    "get_field",
    category="relational",
    description=(
        "Projects a field out of a record produced by another expression "
        "(e.g. get_field(first_by(photos, ...), field_name='category'))."
    ),
    input_types=["record"],
    output_type="any",
    parameters={"field_name": "str"},
)
def get_field(record, field_name: str):
    if record is None:
        return None
    return record.get(field_name)


@operator(
    "related_record_exists",
    category="relational",
    description="True if a related record (e.g. a farmer's contract) exists for this lot.",
    input_types=["record"],
    output_type="bool",
)
def related_record_exists(record) -> bool:
    return record is not None


@operator(
    "status_equals",
    category="relational",
    description="True if a status field equals the expected value (e.g. contract status == SIGNED).",
    input_types=["any", "any"],
    output_type="bool",
)
def status_equals(status, expected) -> bool | None:
    if status is None or expected is None:
        return None
    return status == expected


@operator(
    "dataset_membership",
    category="relational",
    description="True if value is a member of a reference dataset/list (e.g. LIPA DS26 membership).",
    input_types=["any"],
    output_type="bool",
    parameters={"dataset": "list[any]"},
)
def dataset_membership(value, dataset: list) -> bool | None:
    if value is None:
        return None
    return value in dataset
