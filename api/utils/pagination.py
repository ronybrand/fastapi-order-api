from sqlalchemy import inspect
from sqlalchemy.orm import Query

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
    "lk": lambda c, v: c.ilike(f"%{v}%"),
}


def _build_condition(column, conditions: list[dict]):
    clauses = []
    for condition in conditions:
        operator = condition.get("op", "eq")
        value = condition.get("value")
        build = _OPERATORS.get(operator)
        if build is None:
            raise ValueError(f"Unknown operator: {operator}")
        coerced = column.type.python_type(value) if not isinstance(value, list) else value
        clauses.append(build(column, coerced))
    return clauses[0] if len(clauses) == 1 else clauses


def paginate(query: Query, model: type, request: SearchRequest) -> tuple[list, int]:
    """Motor de busca/filtro/paginação compartilhado entre domínios (ver skill
    fastapi-feature, seção "Busca, filtro e paginação"). Resolve campo via metadata do
    model (`inspect(model).columns`), nunca via allowlist mantida à mão por domínio."""
    columns = inspect(model).columns

    for field, conditions in (request.filters or {}).items():
        column = columns.get(field)
        if column is None:
            continue  # campo de filtro desconhecido: ignora essa condição, não é erro
        try:
            query = query.filter(_build_condition(column, conditions))
        except (ValueError, TypeError):
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
        if column is None:
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
