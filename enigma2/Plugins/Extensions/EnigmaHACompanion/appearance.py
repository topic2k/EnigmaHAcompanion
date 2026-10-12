"""Shared, resolution-independent layout driven by registered skin profiles."""

import xml.etree.ElementTree as ET

from .companion.i18n import resolve_language, translate
from .skin import resolve_profile
from .skin.base import skin_font


def active_skin():
    try:
        from Components.config import config
        return config.skin.primary_skin.value
    except (ImportError, AttributeError):
        return ""


def active_profile():
    return resolve_profile("auto", active_skin()).id


class Appearance:
    def __init__(self, desktop, selection="auto", language="de"):
        self.language = resolve_language(language)
        self.selection = selection
        self.definition = resolve_profile(selection, active_skin())
        self.profile = self.definition.id
        self.scale = min(desktop.width() / 1280.0, desktop.height() / 720.0)
        self.font = skin_font(self.definition.font_family)
        self.list_font = None
        for name, source in (("width", "width"), ("height", "height"), ("margin", "margin"),
                             ("header", "header"), ("footer", "footer_height"), ("status", "status")):
            setattr(self, name, self.px(getattr(self.definition, source)))
        self.list_width = self.width - 2 * self.margin
        self.list_height = self.height - self.header - self.footer - self.status

    def t(self, message):
        return translate(message, self.language)

    def px(self, value):
        return max(1, int(value * self.scale))

    def menu_font(self, family, size):
        # Profile and external skin defaults apply independently to each auto
        # choice. Explicit receiver choices always take precedence.
        face, pixels, row_height = self.definition.menu_font(self, self.font, 28)
        if self.list_font is not None:
            face, pixels = self.list_font
            row_height = int(pixels * 1.5)
        if family:
            face = skin_font(family)
        if size:
            pixels = max(16, self.px(size))
            row_height = int(pixels * 1.5)
        return face, pixels, row_height

    def apply_list_skin(self, attributes, scale):
        self.list_font = None
        for name, value in attributes:
            if name == "font":
                from skin import parseFont
                font = parseFont(value, scale)
                self.list_font = (font.family, font.pointSize)

    def screen_names(self, setup=False):
        name = "EnigmaHASetup" if setup else "EnigmaHACompanion"
        if self.selection == "auto":
            return [name, "CompanionSetup" if setup else "CompanionScreen"]
        # OpenATV checks named skin screens before the embedded layout. A manual
        # profile uses a reserved name so external screens do not override it.
        return [name + "Builtin"]

    def layout(self, setup=False):
        self.text_labels = {}
        root = ET.Element("screen", name="EnigmaHASetup" if setup else "EnigmaHACompanion",
                          position="center,center", size="%s,%s" % (self.width, self.height),
                          title=self.t("EnigmaHA Companion – Einstellungen") if setup else "EnigmaHA Companion")

        def element(tag, x, y, w, h, **attrs):
            if tag == "eLabel" and "text" in attrs:
                # OpenATV translates XML text attributes using the system
                # language. Label components retain the plugin's own language.
                name = "companion_text_%s" % len(self.text_labels)
                self.text_labels[name] = attrs.pop("text")
                tag = "widget"
                attrs["name"] = name
            return ET.SubElement(root, tag, position="%s,%s" % (x, y),
                                 size="%s,%s" % (w, h), **attrs)

        label_attrs = {"font": "%s;%s" % (self.font, self.px(20)), "valign": "center"}
        list_attrs = {"scrollbarMode": "showOnDemand"}
        self.definition.decorate(self, root, element, label_attrs, list_attrs)

        heading = dict(label_attrs, font="%s;%s" % (
            skin_font(self.definition.heading_family), self.px(26)))
        element("eLabel" if setup else "widget", self.margin, 0, self.list_width,
                self.header - self.px(8), **dict(heading, **(
                    {"text": self.t("EnigmaHA – Einstellungen")} if setup else {"name": "heading"})))
        if setup:
            # ConfigListScreen owns this hidden anchor; the dialog positions the
            # separate help window after Enigma2's default input-helper handling.
            element("widget", 0, 0, 1, 1, name="HelpWindow", transparent="1")
            element("widget", self.margin, self.header, self.list_width,
                    self.list_height + self.status - self.px(8), name="config",
                    font="%s;%s" % (self.font, self.px(22)), itemHeight=str(self.px(40)), **list_attrs)
        else:
            element("widget", self.margin, self.header, self.list_width, self.list_height,
                    name="list", **list_attrs)
            element("widget", self.margin, self.header + self.list_height, self.list_width,
                    self.status, name="status", **label_attrs)
        self.definition.footer(self, element, label_attrs, setup)
        return ET.tostring(root, encoding="unicode")
