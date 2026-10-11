"""Shared OpenATV profile interface and layout defaults.

Geometry is specified at 1280x720; Appearance scales it to the desktop.
Profile hooks receive the shared layout builder and may add skin decorations.
"""

def skin_font(preferred):
    try:
        from enigma import getFontFaces
        if preferred in getFontFaces():
            return preferred
    except ImportError:
        pass
    return "Regular"


class SkinProfile:
    skin_directories = ()
    width = 1176
    height = 634
    margin = 20
    header = 54
    footer_height = 70
    status = 32
    font_family = "Regular"
    heading_family = "Regular"

    def menu_font(self, appearance, family, size):
        size = max(16, appearance.px(size))
        return skin_font(family), size, int(size * 1.5)

    def decorate(self, appearance, root, element, label_attrs, list_attrs):
        """Optionally add backgrounds and update label/list attributes in place."""

    def footer(self, appearance, element, label_attrs, setup):
        element("widget", appearance.margin, appearance.height - appearance.footer + appearance.px(6),
                appearance.list_width, appearance.footer - appearance.px(12),
                name="hint" if setup else "footer", **label_attrs)
