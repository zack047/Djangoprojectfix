import os
from urllib.parse import urlparse
from django import template

register = template.Library()


@register.filter
def is_file_type(filename, extensions_str):
    if not filename:
        return False

    # Strip query params
    path = urlparse(filename).path
    basename = os.path.basename(path)

    extensions = tuple('.' + ext.strip().lower() for ext in extensions_str.split(','))
    return basename.lower().endswith(extensions)


@register.filter(name='add_class')
def add_class(field, css_class):
    try:
        return field.as_widget(attrs={"class": css_class})
    except AttributeError:
        # Return the original object (likely a string), untouched
        return field
