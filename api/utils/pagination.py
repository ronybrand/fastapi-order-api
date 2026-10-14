import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, inspect
from sqlalchemy.orm import Query
from sqlalchemy.sql.base import ColumnCollection

from api.schemas.schemas import SearchRequest
from api.utils.custom_api_exception import CustomAPIException

_OPERATORS = {
    "eq": lambda c, v: c == v,
    "neq": lambda c, v: c != v,
    "gt": lambda c, v: c > v,
    "gte": lambda c, v: c >= v,
    "lt": lambda c, v: c < v,
    "lte": lambda c, v: c <= v,
    "in": lambda c, v: c.in_(v if isinstance(v, list) else [v]),
    "between": lambda c, v: c.between(v[0], v[1]),
    "lk": lambda c, v: c.ilike(f"%{_escape_like(v)}%", escape="\\"),
}


def _escape_like(value) -> str:
    """% e _ do termo do cliente sao literais, nao curingas (o escape do LIKE e a barra)."""
    return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _is_searchable(column) -> bool:
    """Coluna marcada como sensivel (info={"sensitive": True}) nunca entra em filtro/ordenacao:
    um `lk`/`gte` sobre ela revelaria o valor caractere a caractere mesmo que a resposta o omita."""
    return not column.info.get("sensitive")


_LIST_OPERATORS = {"in", "between"}
_BOOLEAN_LITERALS = {"true": True, "false": False}


def _coerce(column, value):
    """Converte o valor do cliente para o tipo Python da coluna, estritamente: qualquer valor que
    nao seja do tipo vira ValueError (400 VALIDATION-05) em vez de ser aceito por um construtor
    permissivo (`bool("false")` e True; `datetime("2026-01-01")` e TypeError) ou de chegar ao
    Postgres como erro de tipo (500)."""
    if value is None:
        raise ValueError("A value is required")
    python_type = column.type.python_type
    if python_type is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in _BOOLEAN_LITERALS:
            return _BOOLEAN_LITERALS[value.lower()]
        raise ValueError(f"Not a boolean: {value!r}")
    if python_type is int:
        if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
            raise ValueError(f"Not an integer: {value!r}")
        return int(value)
    if python_type is datetime:
        return datetime.fromisoformat(str(value))
    if python_type is date:
        return date.fromisoformat(str(value))
    if python_type is Decimal:
        return Decimal(str(value))
    if python_type is UUID:
        return UUID(str(value))
    if isinstance(python_type, type) and issubclass(python_type, enum.Enum):
        return python_type(value)
    if python_type is str:
        return str(value)
    return python_type(value)


def _build_condition(column, conditions: list[dict]):
    clauses = []
    for condition in conditions:
        operator = condition.get("op", "eq")
        value = condition.get("value")
        build = _OPERATORS.get(operator)
        if build is None:
            raise ValueError(f"Unknown operator: {operator}")
        if operator == "lk" and column.type.python_type is not str:
            raise ValueError("lk is only supported for text fields")
        if operator == "between" and not (isinstance(value, list) and len(value) == 2):
            raise ValueError("between requires exactly two values")
        if isinstance(value, list) and operator not in _LIST_OPERATORS:
            raise ValueError(f"{operator} does not accept a list")
        if isinstance(value, list):
            coerced = [_coerce(column, item) for item in value]
        else:
            coerced = _coerce(column, value)
        clauses.append(build(column, coerced))
    return clauses[0] if len(clauses) == 1 else and_(*clauses)


def paginate(query: Query, model: type, request: SearchRequest) -> tuple[list, int]:
    """Motor de busca/filtro/paginação compartilhado entre domínios (ver skill
    fastapi-feature, seção "Busca, filtro e paginação"). Resolve campo via metadata do
    model (`inspect(model).columns`), nunca via allowlist mantida à mão por domínio."""
    columns: ColumnCollection = inspect(model).columns

    for field, conditions in (request.filters or {}).items():
        column = columns.get(field)
        if column is None or not _is_searchable(column):
            continue  # campo de filtro desconhecido (ou sensivel): ignora essa condição, não é erro
        try:
            query = query.filter(_build_condition(column, conditions))
        except (ValueError, TypeError, ArithmeticError, NotImplementedError):
            raise CustomAPIException(
                status_code=400,
                message=f"Invalid value for field: {field}",
                code="VALIDATION-05",
                params={"field": field},
            ) from None

    sort_column = model.id
    if request.sort:
        field = request.sort.lstrip("-")
        column = columns.get(field)
        if column is None or not _is_searchable(column):
            raise CustomAPIException(
                status_code=400,
                message=f"Unknown sort field: {field}",
                code="VALIDATION-06",
                params={"field": field},
            )
        sort_column = column.desc() if request.sort.startswith("-") else column.asc()

    total = query.count()
    items = (
        query.order_by(sort_column, model.id)
        .offset(request.page * request.size)
        .limit(request.size)
        .all()
    )
    return items, total
