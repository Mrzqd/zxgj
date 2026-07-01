from __future__ import annotations

import json

from sqlalchemy.types import Text, TypeDecorator, UserDefinedType


def format_vector(vector: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.10g}" for value in vector) + "]"


def parse_vector(value) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, tuple):
        return [float(item) for item in value]
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in text.strip("[]").split(",") if item.strip()]
    if not isinstance(parsed, list):
        return None
    return [float(item) for item in parsed]


class PostgresVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dimensions})"


class VectorType(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, dimensions: int):
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgresVector(self.dimensions))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        vector = parse_vector(value)
        if vector is None:
            return None
        if dialect.name == "postgresql":
            return format_vector(vector)
        return json.dumps(vector, separators=(",", ":"))

    def process_result_value(self, value, dialect):
        return parse_vector(value)
