from django.contrib.staticfiles import finders
from django.template.loader import render_to_string

from apps.siteconfig.models import SiteSettings


def render_invoice_pdf(order) -> bytes:
    from weasyprint import HTML

    font = finders.find("dist/fonts/Vazirmatn-Variable.woff2")
    html = render_to_string(
        "shop/invoice.html",
        {"order": order, "site": SiteSettings.load(), "font_url": f"file://{font}" if font else ""},
    )
    return HTML(string=html).write_pdf()
