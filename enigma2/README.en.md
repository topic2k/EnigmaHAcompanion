# Enigma2 extension

[Deutsch](README.md) · **English**

The extension displays the menu configured in HA on your receiver.
`Plugins/Extensions/EnigmaHACompanion/` contains screens, keys, settings and layout;
`companion/` contains GUI-independent navigation, translations and the HTTP client.
See [installation](../docs/Installation.en.md), [development](../docs/Development.en.md)
and [update implementation and limitations](../docs/Development.en.md#update-implementation-and-limitations).

## Language

German is the first choice and default. Open **Menu/Blue → Sprache**, select
**English**, save with Green and reopen the plugin. The local configuration
`/etc/enigma2/enigmaha_companion.json` accepts `language: "de"` or `"en"`.
This covers plugin text, help, states and built-in skin layouts. OpenATV system
dialogs and fixed text in external skins follow their own language. Custom HA
menu names are retained. No reconfiguration is required.

## Package and runtime

Build with `python tools/build.py` from the project root. Install the IPK or TAR
from `dist/`; the build bundles the HTTP/navigation modules and shared protocol.
OpenATV with Python 3.13 or newer is required. HTTP runs outside the GUI thread
through Twisted `deferToThread`; callbacks update the screen. Automatic refresh
runs only while the plugin is open. Stale responses are discarded after closing
or changing the connection. Commands are never automatically repeated.

## Layout and skin profiles

Layout is specified at 1280 × 720 and scaled to the desktop. **Automatic** detects
profiles from the active skin path; unknown skins use the standard profile and
active skin window frame/colors. Manual selection overrides detection. Save with
Green and reopen the plugin to apply a profile. The system skin is unchanged.

GradientFHD uses a centered dialog (1110 × 900 at Full HD), transparent background,
title gradient and blue selection. It uses available skin colors, fonts and key
images. Gradients and rounded corners depend on the available Enigma2 APIs;
otherwise simple color surfaces are used.

Profile fonts take precedence over HA and local font choices. GradientFHD uses
`Gradient_Font` at 42 pixels with 60-pixel rows at Full HD. Missing fonts fall
back to `Regular`. The standard profile uses local overrides or HA settings.
Saved font preferences are retained when switching profiles.

The footer loads color-key, OK, Menu and Exit images from
`/usr/share/enigma2/GradientFHD/buttons/`, plus Left/Right in settings. Missing
images are replaced by translated key names. Settings place numeric input help
above the footer.

## Skin author interface

Skins can define `EnigmaHACompanion` and `EnigmaHASetup` screens. In **Automatic**
mode, these take precedence over built-in layouts. Manual profiles use built-in
layouts with reserved names `EnigmaHACompanionBuiltin` and `EnigmaHASetupBuiltin`.

| Screen | Widgets |
| --- | --- |
| `EnigmaHACompanion` | `heading`, `list`, `status`, `footer` |
| `EnigmaHASetup` | `config`, `hint`, hidden `HelpWindow` anchor |

After layout, actual list geometry determines columns and page navigation.

### Add a profile

`appearance.py` owns common layout and resolution scaling. Each skin's code lives
in its own subfolder:

```text
skin/
├── __init__.py              # Profile registry and detection
├── base.py                  # Common interface
├── native/
│   └── __init__.py          # Standard profile
└── GradientFHD/
    └── __init__.py          # GradientFHD profile
```

Create `skin/ExampleHD/__init__.py` with a `SkinProfile` subclass:

```python
from ..base import SkinProfile


class ExampleProfile(SkinProfile):
    id = "example"
    label = "ExampleHD"
    skin_directories = ("ExampleHD",)
    width = 1000
    height = 620
    font_family = "ExampleFont"
    heading_family = "ExampleFont"
```

Import it in `skin/__init__.py` and add an instance to `PROFILES`. This exposes
it to settings, validation and detection. IDs must be unique; `auto` is reserved.
`skin_directories` lists complete directory names. Detection ignores case and
does not match partial names. Additional assets/modules can live in the profile
folder. Translate descriptive profile labels through `companion/i18n.py`.

Dimensions use the 1280 × 720 reference; `Appearance.px()` scales them. Profile hooks:

- `menu_font(appearance, family, size)` returns font, size and row height.
- `decorate(appearance, root, element, label_attrs, list_attrs)` adds backgrounds
  and updates label/list attributes.
- `footer(appearance, element, label_attrs, setup)` builds the footer and must
  supply a `footer` or `hint` widget. Use `appearance.t()` for its text.

`element(tag, x, y, width, height, **attrs)` adds an XML element with already-scaled
geometry. `setup` distinguishes settings from the main view. Additional profiles
do not require navigation, HTTP client or setup changes. Provide readable font
and image fallbacks; GradientFHD demonstrates available OpenATV APIs.

After installing an updated receiver package, restart the GUI. Credentials are
retained. Missing `skin_profile` uses the default `auto`, and missing `language`
uses `de`.

## Navigation and entry points

Up/Down moves by one entry. Ch+ pages up and Ch− pages down. **Reverse Ch+/−**
reverses this direction; save with Green. Help shows the selected direction.
Page size follows visible list and row height. Paging stops at the first/last
entry, and held channel keys repeat.

**Show in main menu** adds an Enigma2 main-menu entry. It is off by default.
Changes apply the next time the main menu opens.
