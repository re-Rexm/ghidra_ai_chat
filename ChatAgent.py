
#@author 
#@category _NEW_
#@keybinding 
#@menupath 
#@toolbar 
#@runtime Jython

from __future__ import print_function

import sys

# Jython sometimes needs sys.path help when scripts are nested
import os
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)

from ghidra_ai_chat.ui.ChatPanel import launch_chat_window


class _ScriptCtx(object):
    """
    Read Ghidra cursor/program from the script module globals each time.
    Ghidra updates currentAddress / currentLocation in this dict as the user navigates.
    """

    def __init__(self, gdict):
        object.__init__(self)
        self._gdict = gdict

    def _g(self, name, default=None):
        try:
            if hasattr(self._gdict, "get"):
                return self._gdict.get(name, default)
        except Exception:
            pass
        try:
            return self._gdict[name]
        except Exception:
            return default

    @property
    def currentProgram(self):
        p = self._g("currentProgram", None)
        if p is not None:
            return p
        st = self._g("state", None)
        if st is not None:
            try:
                return st.getCurrentProgram()
            except Exception:
                pass
        return None

    @property
    def currentLocation(self):
        loc = self._g("currentLocation", None)
        if loc is not None:
            return loc
        st = self._g("state", None)
        if st is not None:
            try:
                return st.getCurrentLocation()
            except Exception:
                pass
        return None

    @property
    def currentAddress(self):
        loc = self.currentLocation
        if loc is not None:
            try:
                a = loc.getAddress()
                if a is not None:
                    return a
            except Exception:
                pass
        addr = self._g("currentAddress", None)
        if addr is not None:
            return addr
        st = self._g("state", None)
        if st is not None:
            try:
                ca = st.getCurrentLocation()
                if ca is not None:
                    return ca.getAddress()
            except Exception:
                pass
        return None

    @property
    def currentFunction(self):
        fn = self._g("currentFunction", None)
        if fn is not None:
            return fn
        p = self.currentProgram
        a = self.currentAddress
        if p is not None and a is not None:
            try:
                return p.getFunctionManager().getFunctionContaining(a)
            except Exception:
                pass
        return None

    @property
    def monitor(self):
        m = self._g("monitor", None)
        if m is not None:
            return m
        try:
            from ghidra.util.task import ConsoleTaskMonitor
            return ConsoleTaskMonitor()
        except Exception:
            return None


def _main():
    script_ctx = _ScriptCtx(globals())
    if script_ctx.currentProgram is None:
        raise RuntimeError("No program is open. Load a binary in Ghidra first.")
    launch_chat_window(script_ctx)


_main()
