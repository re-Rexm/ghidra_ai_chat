from __future__ import print_function


class LLMError(Exception):
    pass


class LLMClientInterface(object):
    def chat(self, messages, settings):
        """
        messages: list of dicts: {role: 'system'|'user'|'assistant', content: '...'}
        returns: assistant response text
        """
        raise NotImplementedError()


def build_client(settings):
    provider = getattr(settings, "provider", "openrouter")
    provider = (provider or "").strip().lower()
    if provider == "openrouter":
        from ghidra_ai_chat.llm.providers.openrouter import OpenRouterClient

        return OpenRouterClient()
    if provider == "gemini":
        from ghidra_ai_chat.llm.providers.gemini import GeminiClient

        return GeminiClient()
    if provider == "groq":
        from ghidra_ai_chat.llm.providers.groq import GroqClient

        return GroqClient()
    raise LLMError("Unknown provider: %s" % provider)

