from abc import ABC

import voluptuous as vol


class BaseApp:
    args = {}
    config_schema = vol.Schema({}, extra=vol.ALLOW_EXTRA)

    def initialize(self):
        """Initialization of Base App class."""
        self.log("INIIALIZING")
        self.args = self.config_schema(self.args)
        self.initialize_app()

    def initialize_app(self):
        pass
