import probatio

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import SelectSelector

from .const import CONF_LANGUAGE, DEFAULT_LANGUAGE, DOMAIN, LANGUAGES, LEGACY_LANGUAGE

FONT_FAMILIES = ("Regular", "Fixed", "Console", "Italic", "Gradient_Font")


class CompanionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CompanionOptionsFlow()

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            # Persist the new default only for new entries. Published entries
            # without a language option keep their legacy browser preference.
            return self.async_create_entry(title="EnigmaHA Companion", data={},
                                           options={CONF_LANGUAGE: DEFAULT_LANGUAGE})
        return self.async_show_form(step_id="user")


class CompanionOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        runtime = self.hass.data.get(DOMAIN, {}).get("runtime")
        if runtime is None or not runtime.active:
            return self.async_abort(reason="integration_unavailable")
        display = runtime.menu["display"]
        fonts = list(FONT_FAMILIES)
        if display["font_family"] not in fonts:
            fonts.append(display["font_family"])
        sizes = [str(size) for size in range(16, 65)]
        language = self.config_entry.options.get(CONF_LANGUAGE, LEGACY_LANGUAGE)
        if language not in LANGUAGES:
            language = LEGACY_LANGUAGE
        if user_input is not None:
            if user_input.get(CONF_LANGUAGE) not in LANGUAGES:
                errors[CONF_LANGUAGE] = "invalid_language"
            family = user_input.get("font_family", display["font_family"])
            size = user_input.get("font_size", display["font_size"])
            if family not in fonts:
                errors["font_family"] = "invalid_font_family"
            if str(size) not in sizes:
                errors["font_size"] = "invalid_font_size"
            if not errors:
                try:
                    await runtime.async_set_display({"font_family": family, "font_size": int(size)})
                except (OSError, HomeAssistantError) as error:
                    errors["base"] = str(error) if str(error) in {
                        "integration_unavailable", "revision_limit"} else "storage_failed"
                else:
                    return self.async_create_entry(title="", data={
                        **self.config_entry.options, CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    })
        return self.async_show_form(step_id="init", errors=errors, data_schema=probatio.Schema({
            probatio.Required(CONF_LANGUAGE, default=language): SelectSelector({
                "mode": "dropdown", "translation_key": "language", "options": list(LANGUAGES),
            }),
            probatio.Required("font_family", default=display["font_family"]): SelectSelector({
                "mode": "dropdown", "translation_key": "font_family", "options": fonts,
            }),
            probatio.Required("font_size", default=str(display["font_size"])): SelectSelector({
                "mode": "dropdown", "translation_key": "font_size", "options": sizes,
            }),
        }))
