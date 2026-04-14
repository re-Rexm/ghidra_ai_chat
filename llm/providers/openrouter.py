from __future__ import print_function

import json

from java.io import BufferedReader, InputStreamReader
from java.net import URL

from ghidra_ai_chat.llm.client import LLMClientInterface, LLMError


def _read_all(stream):
    br = BufferedReader(InputStreamReader(stream, "UTF-8"))
    sb = []
    line = br.readLine()
    while line is not None:
        sb.append(line)
        line = br.readLine()
    return "\n".join(sb)


class OpenRouterClient(LLMClientInterface):
    def chat(self, messages, settings):
        api_key = settings.api_key()
        if not api_key:
            raise LLMError(
                "Missing OpenRouter key. Use ~/Downloads/api_keys.txt (openrouter=...) "
                "or openrouter_api_key.txt, or env %s. Hint: %s"
                % (
                    getattr(settings, "openrouter_key_env_var", "OPENROUTER_API_KEY"),
                    settings.api_key_source(),
                )
            )

        url = URL(getattr(settings, "base_url"))
        conn = url.openConnection()
        conn.setRequestMethod("POST")
        conn.setConnectTimeout(int(getattr(settings, "request_timeout_seconds", 60) * 1000))
        conn.setReadTimeout(int(getattr(settings, "request_timeout_seconds", 60) * 1000))
        conn.setDoOutput(True)

        conn.setRequestProperty("Content-Type", "application/json")
        conn.setRequestProperty("Authorization", "Bearer %s" % api_key)
        # Optional but recommended by OpenRouter for attribution/rate behavior.
        conn.setRequestProperty("HTTP-Referer", "https://ghidra.local")
        conn.setRequestProperty("X-Title", "Ghidra AI Chat Agent")

        payload = {
            "model": getattr(settings, "model"),
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": int(getattr(settings, "max_output_tokens", 512)),
        }

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
            raise LLMError("OpenRouter HTTP %s: %s" % (code, err_body or "<no body>"))

        body = _read_all(conn.getInputStream())
        try:
            obj = json.loads(body)
        except Exception as e:
            raise LLMError("Invalid JSON from OpenRouter: %s\nRaw:\n%s" % (str(e), body))

        try:
            return obj["choices"][0]["message"]["content"]
        except Exception:
            raise LLMError("Unexpected OpenRouter response shape:\n%s" % body)

