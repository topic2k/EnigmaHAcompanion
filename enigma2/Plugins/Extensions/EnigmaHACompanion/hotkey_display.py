"""Keep the end of Companion labels visible in native OpenATV choice lists."""

HOTKEY_ROOT = "Plugins/Extensions/EnigmaHACompanion"


def elide_left(text, width, measure):
    if measure(text) <= width:
        return text
    if measure("…") > width:
        return ""
    low, high = 0, len(text)
    while low < high:
        middle = (low + high) // 2
        if measure("…" + text[middle:]) <= width:
            high = middle
        else:
            low = middle + 1
    return "…" + text[low:]


def display_rows(rows, width, measure, text_type):
    """Copy only drawing commands; retain full labels and native action IDs."""
    result = []
    for row in rows:
        if (not row or not isinstance(row[0], (tuple, list)) or len(row[0]) < 2
                or not isinstance(row[0][1], str) or not row[0][1].startswith(HOTKEY_ROOT + "/")):
            result.append(row)
            continue
        rendered = list(row)
        for index, command in enumerate(row[1:], 1):
            if (not isinstance(command, tuple) or len(command) < 8
                    or command[0] != text_type or command[7] != row[0][0]):
                continue
            available = max(0, min(command[3], width - command[1]))
            label = elide_left(command[7], available, measure)
            rendered[index] = command[:3] + (available,) + command[4:7] + (label,) + command[8:]
        result.append(rendered)
    return result


def fit_component(component, measure, text_type):
    """Render copies while native selection, toggling and saving use full rows."""
    if getattr(component, "_enigmaha_tail_labels", False):
        return
    original_set = component.setList

    def set_list(rows):
        original_set(rows)
        instance = component.instance
        if instance is None:
            return
        # Account for the actual skin geometry, scrollbar and a small inset.
        width = instance.size().width() - instance.getScrollbarListOffset() - 4
        component.l.setList(display_rows(rows, width, measure, text_type))

    def get_current():
        index = component.getCurrentIndex()
        return component.list[index] if 0 <= index < len(component.list) else None

    component.setList = set_list
    component.getCurrent = get_current
    component._enigmaha_tail_labels = True
    set_list(component.list)


def fit_lists(screen):
    from enigma import eLabel, eListboxPythonMultiContent, eSize, gFont
    from skin import fonts

    # OpenATV skins can append extra metrics. ChoiceList itself consumes only
    # the first three fields, so follow that contract rather than unpacking all.
    family, size, height = fonts.get("ChoiceList", ("Regular", 20, 25))[:3]
    font = gFont(family, size)
    target = eSize(100000, max(height, size * 2))
    measured = {}

    def measure(text):
        if text not in measured:
            measured[text] = eLabel.calculateTextSize(font, text, target, True).width()
        return measured[text]

    for name in ("list", "choosen"):
        fit_component(screen[name], measure, eListboxPythonMultiContent.TYPE_TEXT)
