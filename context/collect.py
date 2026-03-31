from __future__ import print_function

import re

from ghidra.program.model.symbol import RefType
from ghidra.app.decompiler import DecompInterface


def _safe_str(x):
    try:
        return str(x)
    except Exception:
        try:
            return repr(x)
        except Exception:
            return "<unprintable>"


def _addr_to_str(addr):
    if addr is None:
        return ""
    return addr.toString()


def _get_current_function(script):
    try:
        if script.currentFunction is not None:
            return script.currentFunction
    except Exception:
        pass

    try:
        if script.currentAddress is not None:
            fm = script.currentProgram.getFunctionManager()
            return fm.getFunctionContaining(script.currentAddress)
    except Exception:
        pass

    return None


def _decompile_function(script, func, timeout_seconds):
    if func is None:
        return ""
    di = DecompInterface()
    di.openProgram(script.currentProgram)
    res = di.decompileFunction(func, timeout_seconds, script.monitor)
    if not res or not res.decompileCompleted():
        msg = ""
        try:
            msg = res.getErrorMessage() if res else ""
        except Exception:
            msg = ""
        if msg:
            return "/* decompile failed: %s */" % msg
        return "/* decompile failed */"
    df = res.getDecompiledFunction()
    if df is None:
        return "/* decompile returned no function */"
    try:
        return df.getC()
    except Exception as e:
        return "/* decompile getC() failed: %s */" % _safe_str(e)


def _collect_program_summary(script):
    p = script.currentProgram
    if p is None:
        return {}
    lang = None
    comp = None
    try:
        lang = p.getLanguage().getLanguageID().toString()
    except Exception:
        lang = None
    try:
        comp = p.getCompilerSpec().getCompilerSpecID().toString()
    except Exception:
        comp = None
    try:
        image_base = _addr_to_str(p.getImageBase())
    except Exception:
        image_base = ""
    try:
        fmt = p.getExecutableFormat()
    except Exception:
        fmt = ""
    try:
        name = p.getName()
    except Exception:
        name = ""
    return {
        "name": name,
        "language": lang,
        "compiler": comp,
        "imageBase": image_base,
        "format": fmt,
    }


def _collect_function_summary(func):
    if func is None:
        return {}
    try:
        sig = func.getPrototypeString(False, False)
    except Exception:
        sig = ""
    return {
        "name": func.getName(),
        "entry": _addr_to_str(func.getEntryPoint()),
        "signature": sig,
    }


def _collect_imports(script, max_items):
    p = script.currentProgram
    if p is None:
        return []
    out = []
    try:
        symtab = p.getSymbolTable()
        it = symtab.getExternalSymbols()
        while it.hasNext() and len(out) < max_items:
            s = it.next()
            out.append(_safe_str(s.getName(True)))
    except Exception:
        # Not all programs have externals; ignore
        pass
    return out


def _collect_strings(script, max_items):
    """
    Cheap-ish global string sampling using Data that looks like strings.
    This is intentionally lightweight for v1.
    """
    p = script.currentProgram
    if p is None:
        return []
    out = []
    try:
        listing = p.getListing()
        data_it = listing.getDefinedData(True)
        while data_it.hasNext() and len(out) < max_items:
            d = data_it.next()
            dt = None
            try:
                dt = d.getDataType()
            except Exception:
                dt = None
            if dt is None:
                continue
            name = ""
            try:
                name = dt.getName().lower()
            except Exception:
                name = ""
            if "string" not in name:
                continue
            try:
                v = d.getValue()
                if v is None:
                    continue
                s = _safe_str(v)
            except Exception:
                continue
            s = re.sub(r"\s+", " ", s).strip()
            if not s:
                continue
            addr = _addr_to_str(d.getAddress())
            out.append("%s: %s" % (addr, s))
    except Exception:
        pass
    return out


def _collect_xrefs(script, func, max_items):
    p = script.currentProgram
    if p is None or func is None:
        return []
    out = []
    try:
        refman = p.getReferenceManager()
        entry = func.getEntryPoint()
        refs = refman.getReferencesTo(entry)
        for r in refs:
            if len(out) >= max_items:
                break
            try:
                from_addr = _addr_to_str(r.getFromAddress())
                rt = r.getReferenceType()
                kind = _safe_str(rt) if rt else ""
                out.append("%s -> %s (%s)" % (from_addr, _addr_to_str(entry), kind))
            except Exception:
                continue
    except Exception:
        pass
    return out


def collect_context(script, settings):
    """
    Returns a dict with context fields, suitable for prompt building and preview.
    """
    p = script.currentProgram
    if p is None:
        return {
            "error": "No program is currently open.",
            "program": {},
            "location": {},
            "function": {},
            "decompile": "",
            "strings": [],
            "imports": [],
            "xrefs": [],
        }

    try:
        loc_addr = script.currentAddress
    except Exception:
        loc_addr = None

    func = _get_current_function(script)

    decomp = ""
    if getattr(settings, "include_decompile", True):
        decomp = _decompile_function(script, func, settings.decompile_timeout_seconds)

    strings = []
    if getattr(settings, "include_strings", False):
        strings = _collect_strings(script, settings.max_strings)

    imports = []
    if getattr(settings, "include_imports", False):
        imports = _collect_imports(script, settings.max_imports)

    xrefs = []
    if getattr(settings, "include_xrefs", False):
        xrefs = _collect_xrefs(script, func, settings.max_xrefs)

    return {
        "error": "",
        "program": _collect_program_summary(script),
        "location": {"address": _addr_to_str(loc_addr)},
        "function": _collect_function_summary(func),
        "decompile": decomp,
        "strings": strings,
        "imports": imports,
        "xrefs": xrefs,
    }

