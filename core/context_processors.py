from django.conf import settings


def product(request):
    """Template values shared by every page (AGPL-3.0 section 13 source offer)."""
    return {"source_code_url": settings.SOURCE_CODE_URL}
