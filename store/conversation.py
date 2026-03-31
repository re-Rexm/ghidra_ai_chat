from __future__ import print_function

import json
import os
import re

from java.lang import System


def _safe_filename(s):
    s = s or "unknown"
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    s = s.strip("._-")
    return s[:120] if len(s) > 120 else s


def _store_dir():
    home = System.getProperty("user.home")
    d = os.path.join(home, ".ghidra_ai_chat")
    if not os.path.isdir(d):
        try:
            os.makedirs(d)
        except Exception:
            pass
    return d


def _program_key(context):
    prog = (context or {}).get("program", {}) if context else {}
    name = prog.get("name") or "program"
    image_base = prog.get("imageBase") or ""
    lang = prog.get("language") or ""
    return _safe_filename("%s__%s__%s" % (name, image_base, lang))


def load_history(context):
    """
    Returns list of message dicts: {role, content}
    """
    key = _program_key(context)
    path = os.path.join(_store_dir(), key + ".json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as f:
            data = f.read().decode("utf-8")
        obj = json.loads(data)
        hist = obj.get("history", [])
        if isinstance(hist, list):
            # basic shape validation
            out = []
            for m in hist:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                content = m.get("content")
                if role and content is not None:
                    out.append({"role": role, "content": str(content)})
            return out
    except Exception:
        return []
    return []


def save_history(context, history):
    key = _program_key(context)
    path = os.path.join(_store_dir(), key + ".json")
    try:
        obj = {"history": history[-200:]}  # cap file size
        raw = json.dumps(obj, indent=2, sort_keys=True)
        with open(path, "wb") as f:
            f.write(raw.encode("utf-8"))
    except Exception:
        pass

