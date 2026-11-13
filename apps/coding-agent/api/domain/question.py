"""Restricted non-sensitive ACP forms. Authority and credentials never come from these answers."""

import math
import re

SECRET = re.compile(
    r"password|api.?key|access.?token|refresh.?token|private.?key|recovery.?code|payment.?credential", re.I
)


def validate_schema(schema):
    if (
        schema.get("type") != "object"
        or not isinstance(schema.get("properties"), dict)
        or len(schema["properties"]) > 12
    ):
        raise ValueError("Only a bounded flat form is supported")
    for name, field in schema["properties"].items():
        if SECRET.search(
            name + " " + str(field.get("title", "")) + " " + str(field.get("description", ""))
        ):
            raise ValueError("Credentials cannot be requested through an agent form")
        if field.get("type") not in ("string", "number", "integer", "boolean"):
            raise ValueError("Only primitive form fields are supported")
        if len(field.get("enum", [])) > 50:
            raise ValueError("Too many choices")
    return schema


def validate_content(schema, content):
    validate_schema(schema)
    props = schema["properties"]
    if set(content) - set(props):
        raise ValueError("The response contains an unrequested field")
    if set(schema.get("required", [])) - set(content):
        raise ValueError("Complete the required fields")
    for key, value in content.items():
        field = props[key]
        kind = field["type"]
        if kind == "string" and (
            not isinstance(value, str)
            or len(value) > min(field.get("maxLength", 2000), 2000)
            or len(value) < field.get("minLength", 0)
        ):
            raise ValueError("Invalid text for " + key)
        if kind in ("number", "integer"):
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or (kind == "integer" and int(value) != value)
            ):
                raise ValueError("Invalid number for " + key)
            if value < field.get("minimum", -math.inf) or value > field.get("maximum", math.inf):
                raise ValueError("Number is outside the requested range")
        if kind == "boolean" and not isinstance(value, bool):
            raise ValueError("Invalid choice for " + key)
        if "enum" in field and value not in field["enum"]:
            raise ValueError("Choose an offered value")
    return content
