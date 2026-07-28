from sqlalchemy import inspect

REDACTED = "***REDACTED***"


def mask_sensitive(obj):
    """Substitui por REDACTED todo campo marcado como sensível (`info={"sensitive": True}`
    em Column, `json_schema_extra={"sensitive": True}` em Field) — usado ao logar uma
    instância de model/schema inteira. Nunca use para montar a resposta HTTP: a resposta
    já deve simplesmente não declarar o campo sensível (ver schemas de response)."""
    mapper = inspect(type(obj), raiseerr=False)
    if mapper is not None and hasattr(mapper, "columns"):
        masked = {}
        for column in mapper.columns:
            value = getattr(obj, column.key)
            masked[column.key] = REDACTED if column.info.get("sensitive") and value is not None else value
        return masked

    model_fields = getattr(type(obj), "model_fields", None)
    if model_fields is not None:
        masked = {}
        for name, field in model_fields.items():
            value = getattr(obj, name)
            extra = field.json_schema_extra or {}
            sensitive = isinstance(extra, dict) and extra.get("sensitive")
            masked[name] = REDACTED if sensitive and value is not None else value
        return masked

    return obj
