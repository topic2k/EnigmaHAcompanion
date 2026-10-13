"""GradientFHD presentation; all skin-specific assets and colors live here."""

import os

from ..base import SkinProfile


def skin_color(name, fallback):
    try:
        from skin import colors
        if name in colors:
            return name
    except ImportError:
        pass
    return fallback


class GradientProfile(SkinProfile):
    id = "gradient"
    label = "GradientFHD"
    skin_directories = ("GradientFHD",)
    width = 740
    height = 600
    font_family = "Gradient_Font"
    heading_family = "Italic"

    def menu_font(self, appearance, family, size):
        # GradientFHD's Menu template uses Gradient_Font;42 at 1080p.
        return appearance.font, appearance.px(28), appearance.px(40)

    def decorate(self, appearance, root, element, label_attrs, list_attrs):
        import enigma
        color = skin_color
        bg = color("gradient_BGO", "#16152131")
        bottom = color("gradient_BGU", "#16000000")
        accent = color("gradient_BGLM", "#001b5a91")
        dark = color("gradient_BGLL", "#00152131")
        root.set("flags", "wfNoBorder")
        root.set("backgroundColor", "#ff000000")
        background = bg
        title_background = accent
        if hasattr(getattr(enigma, "eLabel", None), "setBackgroundGradient"):
            background = "%s,%s,%s,vertical" % (bg, bottom, bottom)
            title_background = "%s,%s,%s,horizontal" % (accent, bg, bottom)
        element("eLabel", 0, 0, appearance.width, appearance.height, backgroundColor=background, zPosition="-2")
        element("eLabel", 0, 0, appearance.width, appearance.header - appearance.px(8),
                backgroundColor=title_background, zPosition="-1")
        element("eLabel", appearance.margin, appearance.height - appearance.footer, appearance.list_width, appearance.px(1),
                backgroundColor=accent)
        label_attrs.update(transparent="1", foregroundColor=color("gradient_foreground", "#00dbe1e4"))
        list_attrs.update(transparent="1", foregroundColor=label_attrs["foregroundColor"],
                          foregroundColorSelected=color("gradient_foreground_selection", "#00d7d7d7"),
                          backgroundColorSelected=accent)
        listbox = getattr(enigma, "eListbox", None)
        if hasattr(listbox, "setItemGradientSelected"):
            list_attrs["itemGradientSelected"] = "%s,%s,%s,horizontal" % (accent, dark, dark)
        if hasattr(listbox, "setItemCornerRadiusSelected"):
            list_attrs["itemCornerRadiusSelected"] = str(appearance.px(8))

    def footer(self, appearance, element, label_attrs, setup):
        rows = [
            [("key_red", "Abbrechen" if setup else "Schließen", 20, "Rot"),
             ("key_green", "Speichern" if setup else "Öffnen/Schalten", 20, "Grün"),
             ("key_yellow", "Auswahl/Text" if setup else "Aktualisieren", 20, "Gelb")],
            [("ok", "Auswahl/Text" if setup else "Öffnen/Schalten", 40, "OK"),
             ("key_leftright" if setup else "menu", "Wert ändern" if setup else "Einstellungen", 40, "◀ ▶" if setup else "Menü"),
             ("exit", "Abbrechen" if setup else "Zurück", 40, "Exit")],
        ]
        if not setup:
            rows[0].append(("key_blue", "Einstellungen", 20, "Blau"))
            rows[1] = [("menu", "Einstellungen", 40, "Menü"),
                       ("key_recall", "Zurück", 40, "Recall"),
                       ("info", "Informationen", 40, "Info"),
                       ("exit", "Schließen", 40, "Exit")]
        attrs = dict(label_attrs, font="%s;%s" % (appearance.font, appearance.px(18)))
        for row_index, row in enumerate(rows):
            column = appearance.list_width // len(row)
            y = appearance.height - appearance.footer + appearance.px(5 + 30 * row_index)
            for index, (asset, text, icon_width, fallback) in enumerate(row):
                x = appearance.margin + index * column
                path = (os.path.join(os.path.dirname(__file__), "buttons", "key_recall.png")
                        if asset == "key_recall" else "/usr/share/enigma2/GradientFHD/buttons/%s.png" % asset)
                width = appearance.px(icon_width)
                if os.path.isfile(path):
                    height = (max(1, round(width * 38 / 60)) if asset == "key_recall" else
                              appearance.px(20 if asset.startswith("key_") and asset != "key_leftright" else 25))
                    element("ePixmap", x, y + (appearance.px(26) - height) // 2, width, height,
                            pixmap=path, alphatest="blend", scale="1")
                else:
                    width = appearance.px(max(44, len(appearance.t(fallback)) * 10))
                    element("eLabel", x, y, width, appearance.px(26), text=appearance.t(fallback), **attrs)
                element("eLabel", x + width + appearance.px(5), y,
                        column - width - appearance.px(9), appearance.px(26), text=appearance.t(text), **attrs)

        # Retain the component required by external screen definitions.
        element("widget", 0, 0, 1, 1, name="hint" if setup else "footer", transparent="1")
