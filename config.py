from __future__ import print_function

import os
from java.lang import System


class Settings(object):
    def __init__(self):
        self.provider = "openrouter"

        self.openrouter_base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.gemini_generate_url_tmpl = (
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
        )

        self.models_by_provider = {
            "openrouter": "openrouter/free",
            "gemini": "gemini-2.0-flash",
        }

        self.api_key_file_env_var = "GHIDRA_AI_CHAT_API_KEY_FILE"
        self.keys_file_env_var = "GHIDRA_AI_CHAT_KEYS_FILE"

        self.openrouter_key_env_var = "OPENROUTER_API_KEY"
        self.gemini_key_env_var = "GEMINI_API_KEY"
        self.google_key_env_var = "GOOGLE_API_KEY"

        # Legacy single-file session key (treated as OpenRouter if present).
        self.api_key_file_path = os.path.join(
            System.getProperty("user.home"),
            ".ghidra_ai_chat",
            "session_api_key.txt",
        )

        self.request_timeout_seconds = 60
        self.decompile_timeout_seconds = 600

        self.max_output_tokens = 512
        self.max_context_chars = 18000
        self.max_history_chars = 6000

        self.include_decompile = True
        self.include_strings = False
        self.include_imports = False
        self.include_xrefs = False
        self.disasm_lines_before = 6
        self.disasm_lines_after = 10

        self.max_strings = 40
        self.max_imports = 80
        self.max_xrefs = 80

    @property
    def model(self):
        prov = (self.provider or "openrouter").strip().lower()
        return self.models_by_provider.get(prov, self.models_by_provider["openrouter"])

    @model.setter
    def model(self, value):
        prov = (self.provider or "openrouter").strip().lower()
        self.models_by_provider[prov] = (value or "").strip()

    @property
    def base_url(self):
        prov = (self.provider or "openrouter").strip().lower()
        if prov == "openrouter":
            return self.openrouter_base_url
        return self.gemini_generate_url_tmpl

    @base_url.setter
    def base_url(self, value):
        prov = (self.provider or "openrouter").strip().lower()
        if prov == "openrouter":
            self.openrouter_base_url = value

    def _home(self):
        return System.getProperty("user.home") or ""

    def _multi_key_paths(self):
        paths = []
        # Add code directory first for per-session keys
        code_dir = os.path.dirname(__file__)
        paths.append(os.path.join(code_dir, "api_keys.txt"))
        envp = os.environ.get(self.keys_file_env_var, "").strip()
        if envp:
            paths.append(envp)
        h = self._home()
        if h:
            paths.append(os.path.join(h, ".ghidra_ai_chat", "api_keys.txt"))
            paths.append(os.path.join(h, "Downloads", "api_keys.txt"))
        up = os.environ.get("USERPROFILE", "").strip()
        if up:
            paths.append(os.path.join(up, ".ghidra_ai_chat", "api_keys.txt"))
            paths.append(os.path.join(up, "Downloads", "api_keys.txt"))
        return _unique_paths(paths)

    def _parse_multi_keys(self, path):
        if not path or not os.path.isfile(path):
            return {}
        out = {}
        try:
            with open(path, "rb") as f:
                raw = f.read().decode("utf-8-sig")
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().lower()
                v = v.strip().strip("'").strip('"')
                if k and v:
                    out[k] = v
        except Exception:
            return {}
        return out

    def _key_from_multi_files(self, provider):
        prov = (provider or "").strip().lower()
        aliases = []
        if prov == "openrouter":
            aliases = ["openrouter"]
        elif prov == "gemini":
            aliases = ["gemini", "google", "google_api_key", "gemini_api_key"]
        for p in self._multi_key_paths():
            m = self._parse_multi_keys(p)
            if not m:
                continue
            for a in aliases:
                if a in m and m[a]:
                    return m[a], "file:%s (%s)" % (p, a)
        return "", ""

    def _single_key_paths_for_provider(self, provider):
        prov = (provider or "").strip().lower()
        h = self._home()
        up = os.environ.get("USERPROFILE", "").strip()
        paths = []

        env_one = os.environ.get(self.api_key_file_env_var, "").strip()
        if env_one:
            paths.append(env_one)

        if prov == "openrouter":
            if h:
                paths.extend(
                    [
                        os.path.join(h, ".ghidra_ai_chat", "openrouter_api_key.txt"),
                        os.path.join(h, "Downloads", "openrouter_api_key.txt"),
                        os.path.join(h, ".ghidra_ai_chat", "session_api_key.txt"),
                        os.path.join(h, "Downloads", "api_key.txt"),
                    ]
                )
            if self.api_key_file_path:
                paths.append(self.api_key_file_path)
            if up:
                paths.extend(
                    [
                        os.path.join(up, ".ghidra_ai_chat", "openrouter_api_key.txt"),
                        os.path.join(up, "Downloads", "openrouter_api_key.txt"),
                        os.path.join(up, ".ghidra_ai_chat", "session_api_key.txt"),
                        os.path.join(up, "Downloads", "api_key.txt"),
                    ]
                )

        elif prov == "gemini":
            if h:
                paths.extend(
                    [
                        os.path.join(h, ".ghidra_ai_chat", "gemini_api_key.txt"),
                        os.path.join(h, "Downloads", "gemini_api_key.txt"),
                        os.path.join(h, ".ghidra_ai_chat", "google_api_key.txt"),
                        os.path.join(h, "Downloads", "google_api_key.txt"),
                    ]
                )
            if up:
                paths.extend(
                    [
                        os.path.join(up, ".ghidra_ai_chat", "gemini_api_key.txt"),
                        os.path.join(up, "Downloads", "gemini_api_key.txt"),
                        os.path.join(up, ".ghidra_ai_chat", "google_api_key.txt"),
                        os.path.join(up, "Downloads", "google_api_key.txt"),
                    ]
                )

        return _unique_paths(paths)

    def _read_key_from_file(self, path):
        with open(path, "rb") as f:
            raw = f.read()
        key = raw.decode("utf-8-sig").strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
            key = key[1:-1].strip()
        return key

    def api_key(self):
        prov = (self.provider or "openrouter").strip().lower()
        k, _src = self._key_from_multi_files(prov)
        if k:
            return k
        for p in self._single_key_paths_for_provider(prov):
            if p and os.path.isfile(p):
                try:
                    key = self._read_key_from_file(p)
                    if key:
                        if "=" in key and "\n" in key:
                            continue
                        return key
                except Exception:
                    pass
        if prov == "openrouter":
            return os.environ.get(self.openrouter_key_env_var, "")
        if prov == "gemini":
            return os.environ.get(self.gemini_key_env_var, "") or os.environ.get(
                self.google_key_env_var, ""
            )
        return ""

    def api_key_source(self):
        prov = (self.provider or "openrouter").strip().lower()
        k, src = self._key_from_multi_files(prov)
        if k and src:
            return "%s | %s" % (prov, src)
        for p in self._single_key_paths_for_provider(prov):
            if p and os.path.isfile(p):
                try:
                    key = self._read_key_from_file(p)
                    if key and not ("=" in key and "\n" in key):
                        return "%s | file:%s" % (prov, p)
                except Exception:
                    pass
        if prov == "openrouter" and os.environ.get(self.openrouter_key_env_var, ""):
            return "%s | env:%s" % (prov, self.openrouter_key_env_var)
        if prov == "gemini":
            if os.environ.get(self.gemini_key_env_var, ""):
                return "%s | env:%s" % (prov, self.gemini_key_env_var)
            if os.environ.get(self.google_key_env_var, ""):
                return "%s | env:%s" % (prov, self.google_key_env_var)
        return "%s | none (checked multi + single-file paths)" % prov


def _unique_paths(paths):
    seen = {}
    out = []
    for p in paths:
        if p and p not in seen:
            seen[p] = True
            out.append(p)
    return out


DEFAULT_SETTINGS = Settings()
