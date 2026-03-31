from __future__ import print_function

import os
from java.lang import System


class Settings(object):
    def __init__(self):
        self.provider = "openrouter"
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "openrouter/free"
        self.api_key_env_var = "OPENROUTER_API_KEY"
        # Less intrusive option: keep a temporary session key in a local file.
        # Put only the raw key text in this file, then delete it after your session.
        self.api_key_file_path = os.path.join(
            System.getProperty("user.home"),
            ".ghidra_ai_chat",
            "session_api_key.txt",
        )

        self.request_timeout_seconds = 60
        self.decompile_timeout_seconds = 30

        self.max_output_tokens = 512
        # crude budgeting by characters (Jython-friendly). Adjust in UI.
        self.max_context_chars = 18000
        self.max_history_chars = 6000

        # Context toggles (default minimal + decompile)
        self.include_decompile = True
        self.include_strings = False
        self.include_imports = False
        self.include_xrefs = False

        self.max_strings = 40
        self.max_imports = 80
        self.max_xrefs = 80

    def api_key(self):
        # Priority: temporary key file -> environment variable fallback.
        p = self.api_key_file_path
        if p and os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    key = f.read().decode("utf-8").strip()
                if key:
                    return key
            except Exception:
                pass
        return os.environ.get(self.api_key_env_var, "")

    def api_key_source(self):
        p = self.api_key_file_path
        if p and os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    key = f.read().decode("utf-8").strip()
                if key:
                    return "file:%s" % p
            except Exception:
                pass
        if os.environ.get(self.api_key_env_var, ""):
            return "env:%s" % self.api_key_env_var
        return "none"


DEFAULT_SETTINGS = Settings()

