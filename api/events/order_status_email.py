from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Renderiza templates/email/order_status_changed.html via Jinja2: o HTML fica num arquivo
# separado do código, não embutido em string.
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "email"
_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)
_template = _env.get_template("order_status_changed.html")


def build_order_status_email_html(event: dict) -> str:
    return _template.render(
        customer_name=event["customer_name"],
        old_status=event["old_status"],
        new_status=event["new_status"],
        short_order_id=event["order_id"][:8].upper(),
        changed_at=event["changed_at"],
        total_amount=event["total_amount"],
    )
