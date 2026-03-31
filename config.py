from __future__ import print_function

import os
from java.lang import System


class Settings(object):
    def __init__(self):
        self.provider = "openrouter"
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "openrouter/free"
        self.api_key_env_var = "OPENROUTER_API_KEY"
        self.api_key_file_env_var = "GHIDRA_AI_CHAT_API_KEY_FILE"
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

    def _candidate_key_paths(self):
        paths = []

        # Highest priority: explicit file path override.
        env_path = os.environ.get(self.api_key_file_env_var, "").strip()
        if env_path:
            paths.append(env_path)

        # Default session key file.
        if self.api_key_file_path:
            paths.append(self.api_key_file_path)

        # Common convenience location requested by users.
        home = System.getProperty("user.home")
        if home:
            paths.append(os.path.join(home, "Downloads", "api_key.txt"))

        # Windows fallback if Java user.home differs from USERPROFILE.
        up = os.environ.get("USERPROFILE", "").strip()
        if up:
            paths.append(os.path.join(up, ".ghidra_ai_chat", "session_api_key.txt"))
            paths.append(os.path.join(up, "Downloads", "api_key.txt"))

        seen = {}
        out = []
        for p in paths:
            if p and p not in seen:
                seen[p] = True
                out.append(p)
        return out

    def _read_key_from_file(self, path):
        with open(path, "rb") as f:
            raw = f.read()
        # utf-8-sig handles BOM that some editors add.
        key = raw.decode("utf-8-sig").strip()
        # Strip accidental surrounding quotes.
        if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
            key = key[1:-1].strip()
        return key

    def api_key(self):
        # Priority: key file candidates -> environment variable fallback.
        for p in self._candidate_key_paths():
            if p and os.path.isfile(p):
                try:
                    key = self._read_key_from_file(p)
                    if key:
                        return key
                except Exception:
                    pass
        return os.environ.get(self.api_key_env_var, "")

    def api_key_source(self):
        for p in self._candidate_key_paths():
            if p and os.path.isfile(p):
                try:
                    key = self._read_key_from_file(p)
                    if key:
                        return "file:%s" % p
                except Exception:
                    pass
        if os.environ.get(self.api_key_env_var, ""):
            return "env:%s" % self.api_key_env_var
        return "none (checked: %s)" % ", ".join(self._candidate_key_paths())


DEFAULT_SETTINGS = Settings()

