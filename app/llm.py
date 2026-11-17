import json
import logging
import time

from openai import APIConnectionError, AzureOpenAI, BadRequestError, RateLimitError

log = logging.getLogger("shopdesk.llm")


class Blocked(Exception):
    pass


_client = None
_skip_temperature = False


def _get_client(settings):
    global _client
    if _client is None:
        if not (settings.endpoint and settings.api_key and settings.deployment):
            raise RuntimeError("Azure OpenAI settings are missing, check your .env file")
        _client = AzureOpenAI(
            azure_endpoint=settings.endpoint,
            api_key=settings.api_key,
            api_version=settings.api_version,
        )
    return _client


def _is_filtered(error):
    text = str(error).lower()
    return "content_filter" in text or "content management policy" in text


def _complete(settings, system, user, as_json, temperature=0.0, attempts=4):
    global _skip_temperature
    kwargs = {
        "model": settings.deployment,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if as_json:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(attempts):
        if not _skip_temperature:
            kwargs["temperature"] = temperature
        try:
            reply = _get_client(settings).chat.completions.create(**kwargs)
            text = reply.choices[0].message.content or ""
            return json.loads(text) if as_json else text.strip()
        except BadRequestError as e:
            if _is_filtered(e):
                raise Blocked("the request was blocked by the content filter")
            # some deployments only accept the default temperature
            if "temperature" in str(e).lower() and "temperature" in kwargs:
                kwargs.pop("temperature")
                _skip_temperature = True
                continue
            raise
        except (RateLimitError, APIConnectionError) as e:
            wait = 2 ** attempt
            log.warning("llm call failed (%s), retrying in %ss", type(e).__name__, wait)
            time.sleep(wait)
        except json.JSONDecodeError:
            log.warning("model returned invalid json, retrying")
    raise RuntimeError("the language model did not return a usable answer")


def ask_json(settings, system, user):
    return _complete(settings, system, user, as_json=True)


def ask_text(settings, system, user):
    return _complete(settings, system, user, as_json=False)


def stream_text(settings, system, user, temperature=0.0, attempts=4):
    """Yields the answer piece by piece. Retries only if nothing has been sent yet."""
    global _skip_temperature
    kwargs = {
        "model": settings.deployment,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": True,
    }
    started = False
    for attempt in range(attempts):
        if not _skip_temperature:
            kwargs["temperature"] = temperature
        try:
            for chunk in _get_client(settings).chat.completions.create(**kwargs):
                if not chunk.choices:
                    continue
                piece = chunk.choices[0].delta.content
                if piece:
                    started = True
                    yield piece
            return
        except BadRequestError as e:
            if _is_filtered(e):
                raise Blocked("the request was blocked by the content filter")
            if not started and "temperature" in str(e).lower() and "temperature" in kwargs:
                kwargs.pop("temperature")
                _skip_temperature = True
                continue
            raise
        except (RateLimitError, APIConnectionError) as e:
            if started:
                raise
            wait = 2 ** attempt
            log.warning("llm stream failed (%s), retrying in %ss", type(e).__name__, wait)
            time.sleep(wait)
    raise RuntimeError("the language model did not return a usable answer")
