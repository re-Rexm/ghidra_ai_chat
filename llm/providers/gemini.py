from __future__ import print_function

import json

from java.io import BufferedReader, InputStreamReader
from java.net import URL
from java.net import URLEncoder

from ghidra_ai_chat.llm.client import LLMClientInterface, LLMError


def _read_all(stream):
    br = BufferedReader(InputStreamReader(stream, "UTF-8"))
    sb = []
    line = br.readLine()
    while line is not None:
        sb.append(line)
        line = br.readLine()
    return "\n".join(sb)


def _messages_to_gemini_body(messages, settings):
    system_texts = []
    contents = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_texts.append({"text": str(content)})
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": str(content)}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": str(content)}]})
        else:
            contents.append({"role": "user", "parts": [{"text": str(content)}]})

    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": int(getattr(settings, "max_output_tokens", 512)),
        },
    }
    if system_texts:
        body["systemInstruction"] = {"parts": system_texts}
    return body


def _extract_text_from_response(obj):
    try:
        cands = obj.get("candidates") if isinstance(obj, dict) else None
        if not cands:
            return None
        parts = cands[0].get("content", {}).get("parts", [])
        texts = []
        for p in parts:
            if isinstance(p, dict) and "text" in p:
                texts.append(p["text"])
        if texts:
            return "".join(texts)
    except Exception:
        return None
    return None


class GeminiClient(LLMClientInterface):
    def chat(self, messages, settings):
        api_key = settings.api_key()
        if not api_key:
            raise LLMError(
                "Missing Gemini API key. Add gemini/google line to api_keys.txt, or use "
                "~/Downloads/gemini_api_key.txt, or set %s / %s. Source hint: %s"
                % (
                    getattr(settings, "gemini_key_env_var", "GEMINI_API_KEY"),
                    getattr(settings, "google_key_env_var", "GOOGLE_API_KEY"),
                    settings.api_key_source(),
                )
            )

        model = settings.model
        tmpl = getattr(settings, "gemini_generate_url_tmpl")
        path = tmpl % model
        q = "key=%s" % URLEncoder.encode(api_key, "UTF-8")
        url = URL(path + "?" + q)

        conn = url.openConnection()
        conn.setRequestMethod("POST")
        conn.setConnectTimeout(int(getattr(settings, "request_timeout_seconds", 60) * 1000))
        conn.setReadTimeout(int(getattr(settings, "request_timeout_seconds", 60) * 1000))
        conn.setDoOutput(True)
        conn.setRequestProperty("Content-Type", "application/json")

        payload = _messages_to_gemini_body(messages, settings)
        data = json.dumps(payload)
        out = conn.getOutputStream()
        out.write(data.encode("UTF-8"))
        out.flush()
        out.close()

        code = conn.getResponseCode()
        if code < 200 or code >= 300:
            err_body = ""
            try:
                err_body = _read_all(conn.getErrorStream())
            except Exception:
                err_body = ""
            raise LLMError("Gemini HTTP %s: %s" % (code, err_body or "<no body>"))

        body = _read_all(conn.getInputStream())
        try:
            obj = json.loads(body)
        except Exception as e:
            raise LLMError("Invalid JSON from Gemini: %s\nRaw:\n%s" % (str(e), body))

        text = _extract_text_from_response(obj)
        if text is not None:
            return text
        raise LLMError("Unexpected Gemini response shape:\n%s" % body)
