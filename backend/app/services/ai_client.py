"""
Multi-provider LLM client with API key round-robin (OpenAI, DeepSeek, Google AI / Gemma, YandexGPT).
"""

import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterator

import httpx

from app.core.crypto_secrets import decrypt_secret
from app.services.ai_content_sanitizer import redact_for_llm

logger = logging.getLogger(__name__)

# Avoid pathological request sizes; Gemma 4 has large context but the hosted API
# can return 5xx on very large or bursty bodies.
_GEMMA_MAX_COMBINED_CHARS = 120_000


class AIProvider(StrEnum):
    """Supported third-party model backends."""

    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    YANDEXGPT = "yandexgpt"


# Generative Language API (AI Studio key): v1beta .../models/{id}:generateContent
# Google-hosted Gemma 4 31B (instruction-tuned) — see ai.google.dev/gemma docs.
# Model names must match ListModels (preview builds like ...-preview-04-17 are retired).
# See https://ai.google.dev/gemini-api/docs/models
GOOGLE_GEMMA_MODEL = "gemma-4-31b-it"
# Try in order: Gemma, then several Gemini/Flash (same key). On unknown/regional 404, try next.
GOOGLE_GEMINI_FALLBACK_MODEL = "gemini-2.0-flash-001"
GOOGLE_GENERATIVE_MODEL_CHAIN: tuple[str, ...] = (
    "gemma-4-31b-it",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.5-flash",
    "gemini-1.5-flash-002",
)
OPENAI_MODEL_CHAIN: tuple[str, ...] = ("gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo")
DEEPSEEK_MODEL_CHAIN: tuple[str, ...] = ("deepseek-chat", "deepseek-coder", "deepseek-reasoner")

# Yandex Cloud Foundation Models (OpenAI-compatible: POST /v1/chat/completions)
# If short names 404/400, store creds as FOLDER_ID|API_KEY to use gpt://FOLDER/.../model
YANDEX_GPT_BASE = "https://llm.api.cloud.yandex.net"
YANDEXGPT_MODEL_CHAIN: tuple[str, ...] = (
    "yandexgpt/latest",
    "yandexgpt-lite/latest",
    "yandexgpt-32b/latest",
)

# System prompts; users may override via profile (see effective_ai_prompts).
DEFAULT_PROMPT_SPLIT_SYSTEM = (
    "You help split Redmine issues. Reply ONLY with a JSON array of 2-4 objects "
    'with keys "subject" and "description" (strings). No markdown, no code fences.'
)
DEFAULT_PROMPT_COMPLEXITY_SYSTEM = (
    "Reply with exactly one token: s, m, l, xl, or 2xl. Nothing else."
)
DEFAULT_PROMPT_WIZARD_SYSTEM = (
    "You are an Agile coach. Reply ONLY with one JSON object with keys: "
    '"summary" (string), "close" (bool), "split" (bool), "time_hours" (number or null), '
    '"new_status_suggestion" (string or null), "comment" (string or null).'
)


def effective_ai_prompts(overrides: Any) -> dict[str, str]:
    """
    Merge per-user ``ai_prompts_json`` (split_system, complexity_system, wizard_system) with
    application defaults. Unknown keys are ignored; empty strings fall back to defaults.
    """
    out: dict[str, str] = {
        "split_system": DEFAULT_PROMPT_SPLIT_SYSTEM,
        "complexity_system": DEFAULT_PROMPT_COMPLEXITY_SYSTEM,
        "wizard_system": DEFAULT_PROMPT_WIZARD_SYSTEM,
    }
    if not isinstance(overrides, dict):
        return out
    for k in out:
        v = overrides.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


@dataclass
class APIKeyEntry:
    """One stored key entry after decryption (in-memory for a request)."""

    provider: AIProvider
    name: str
    secret: str


# Thread-safe index for round-robin across keys of same provider
_rr_lock = threading.Lock()
_rr_index: dict[str, int] = {}
_SOCKS_RR_KEY = "ai_socks5"


def _next_index(key: str, n: int) -> int:
    """Return and increment a round-robin index for a named key pool."""
    with _rr_lock:
        i = _rr_index.get(key, 0) % n if n else 0
        _rr_index[key] = i + 1
    return i


def _normalize_socks5_url(line: str) -> str:
    """Accept ``socks5://host:port`` or ``host:port`` (prepend scheme)."""
    s = line.strip()
    if not s:
        return ""
    low = s.lower()
    if low.startswith("socks5://") or low.startswith("socks5h://"):
        return s
    if "://" in s:
        return s
    return f"socks5://{s}"


def parse_socks5_proxies(raw: Any) -> list[str]:
    """
    Parse stored JSON list or newline-separated text into SOCKS5 proxy URLs.

    Args:
        raw: List of strings from ``app_settings.ai_socks5_proxies_json``, or None.

    Returns:
        Non-empty normalized URLs, round-robin order preserved.
    """
    if not raw:
        return []
    lines: list[str]
    if isinstance(raw, list):
        lines = [str(x).strip() for x in raw if str(x).strip()]
    elif isinstance(raw, str):
        lines = [x.strip() for x in raw.splitlines() if x.strip()]
    else:
        return []
    out: list[str] = []
    for line in lines:
        u = _normalize_socks5_url(line)
        if u:
            out.append(u)
    return out


def _pick_socks_proxy_url(urls: list[str]) -> str | None:
    """Round-robin pick among configured SOCKS5 proxies."""
    if not urls:
        return None
    i = _next_index(_SOCKS_RR_KEY, len(urls))
    return urls[i]


@contextmanager
def _ai_http_client(proxy_url: str | None) -> Iterator[httpx.Client]:
    """
    Sync httpx client for outbound AI calls. Optional SOCKS5 ``proxy_url`` (round-robin
    chosen by caller).
    """
    kw: dict[str, Any] = {"timeout": 120.0, "trust_env": False}
    if proxy_url:
        kw["proxy"] = proxy_url
    with httpx.Client(**kw) as client:
        yield client


def parse_ai_keys_json(raw: Any) -> list[APIKeyEntry]:
    """
    Convert stored app_settings ai_keys_json (list of dicts) into entries.

    Args:
        raw: Deserialized JSON from DB (list of {provider, name, encrypted}).

    Returns:
        Decrypted list of key entries; skips invalid items.
    """
    if not raw or not isinstance(raw, list):
        return []
    out: list[APIKeyEntry] = []
    for item in raw:
        try:
            p = AIProvider(str(item.get("provider", "")).lower())
            name = str(item.get("name", "default"))
            enc = str(item.get("encrypted", ""))
            if not enc:
                continue
            sec = decrypt_secret(enc)
            out.append(APIKeyEntry(provider=p, name=name, secret=sec))
        except Exception:  # noqa: S112
            continue
    return out


def _pick_key(entries: list[APIKeyEntry], provider: AIProvider | None = None) -> APIKeyEntry:
    """
    Select one key using round-robin, optionally restricted by provider.

    Args:
        entries: All keys.
        provider: If set, filter to this provider.

    Returns:
        The chosen entry.

    Raises:
        ValueError: If no keys are available.
    """
    pool = [e for e in entries if provider is None or e.provider == provider]
    if not pool:
        msg = "No AI API keys configured"
        raise ValueError(msg)
    idx = _next_index("all", len(pool))
    return pool[idx]


def _parse_yandex_secret(secret: str) -> tuple[str, tuple[str, ...]]:
    """
    Return (api_key, model_ids). If ``secret`` is ``FOLDER_ID|API_KEY``, build ``gpt://`` URIs.

    Yandex Cloud often needs catalog id in the model name; short names like ``yandexgpt/latest``
    work for some accounts.
    """
    raw = secret.strip()
    if "|" in raw:
        folder, key = raw.split("|", 1)
        folder, key = folder.strip(), key.strip()
        if folder and key:
            return key, (
                f"gpt://{folder}/yandexgpt/latest",
                f"gpt://{folder}/yandexgpt-lite/latest",
            )
    return raw, YANDEXGPT_MODEL_CHAIN


def _openai_complete_one(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    *,
    use_api_key_auth: bool = False,
) -> httpx.Response:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    authz = f"Api-Key {api_key}" if use_api_key_auth else f"Bearer {api_key}"
    return client.post(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        headers={"Authorization": authz, "Content-Type": "application/json"},
        json=body,
        timeout=120.0,
    )


def _openai_complete(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    system: str,
    user: str,
    models: tuple[str, ...],
    *,
    use_api_key_auth: bool = False,
) -> str:
    """
    OpenAI-compatible /chat/completions: try each model in ``models`` on failure.

    On 4xx/404 (bad id), 429, 5xx — logs and continues to the next id when possible.
    """
    last: httpx.Response | None = None
    for idx, m in enumerate(models):
        r = _openai_complete_one(
            client,
            base_url,
            api_key,
            m,
            system,
            user,
            use_api_key_auth=use_api_key_auth,
        )
        if r.is_success:
            return str(r.json()["choices"][0]["message"]["content"])
        code = r.status_code
        body_snip = (r.text or "")[:400]
        if idx < len(models) - 1 and code in (400, 404, 429, 500, 502, 503, 504):
            logger.warning(
                "OpenAI-compatible model=%s HTTP %s: %s — trying next", m, code, body_snip
            )
            last = r
            continue
        r.raise_for_status()
    if last is not None:
        last.raise_for_status()
    msg = "OpenAI-compatible: no model in chain"
    raise ValueError(msg)


def _gemma_generate_content_body(system: str, user: str, max_output_tokens: int) -> dict[str, Any]:
    """
    Build JSON body for Generative Language API compatible with Gemma 4 on Gemini API.

    Gemma official REST examples use ``contents: [{ "parts": [{ "text": "..." }] }]``
    without ``role`` on the content; using ``role: "user"`` has caused HTTP 500 for some
    ``gemma-*`` models. System + user are merged into one text block.

    Do not set ``thinkingConfig`` here: ``gemma-4-31b-it`` returns HTTP 400
    ("Thinking level is not supported for this model") if any thinking level is sent.
    """
    full = f"{system}\n\n{user}" if (system and system.strip()) else user
    if len(full) > _GEMMA_MAX_COMBINED_CHARS:
        full = full[:_GEMMA_MAX_COMBINED_CHARS] + "\n\n[...truncated for API size limits]"
    return {
        "contents": [{"parts": [{"text": full}]}],
        "generationConfig": {
            "maxOutputTokens": min(max_output_tokens, 8192),
            "temperature": 0.4,
        },
    }


def _text_from_gemma_parts(parts: list[dict[str, Any]]) -> str:
    """Concatenate text parts, skipping model \"thought\" segments when marked."""
    out: list[str] = []
    for p in parts:
        if p.get("thought") is True:
            continue
        t = p.get("text")
        if t:
            out.append(str(t))
    s = "".join(out)
    if s:
        return s
    return "".join(str(p.get("text", "")) for p in parts if p.get("text") is not None)


def _http_error_message(response: httpx.Response) -> str:
    t = (response.text or "")[:1200]
    try:
        j = response.json()
        if isinstance(j, dict) and j.get("error"):
            e = j["error"]
            if isinstance(e, dict) and e.get("message"):
                return str(e["message"])
    except Exception:  # noqa: S110
        pass
    return t or f"empty body (HTTP {response.status_code})"


def _generative_post_with_retries(
    client: httpx.Client, api_key: str, model: str, body: dict[str, Any]
) -> httpx.Response:
    """POST generateContent; one retry on 429/5xx."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    last_response: httpx.Response | None = None
    for attempt in range(2):
        r = client.post(
            url,
            params={"key": api_key},
            json=body,
            timeout=120.0,
        )
        last_response = r
        if r.status_code < 500 and r.status_code != 429:
            break
        if attempt == 0 and r.status_code in (429, 500, 502, 503, 504):
            logger.warning(
                "Google Generative API model=%s transient %s; retrying once. Body: %s",
                model,
                r.status_code,
                (r.text or "")[:500],
            )
            time.sleep(1.5)
            continue
        break
    assert last_response is not None
    return last_response


def _parse_generative_content_response(r: httpx.Response) -> str:
    """Parse successful generateContent JSON to text, or raise ValueError."""
    if r.is_error:
        msg = _http_error_message(r)
        logger.error("Generative API HTTP %s: %s", r.status_code, msg[:800])
        raise ValueError(f"Generative API HTTP {r.status_code}: {msg}")
    data = r.json()
    if data.get("error"):
        e = data["error"]
        msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
        err = f"Generative API error: {msg}"
        raise ValueError(err)
    cands = data.get("candidates") or []
    if not cands:
        fb = data.get("promptFeedback")
        if fb:
            raise ValueError(f"No candidates (promptFeedback): {fb!s}")
        raise ValueError("Empty candidates from generative model")
    parts = (cands[0].get("content") or {}).get("parts", []) or []
    return _text_from_gemma_parts(parts)


def _http_status_worth_model_fallback(r: httpx.Response) -> bool:
    if not r.is_error:
        return False
    return r.status_code in (404, 429, 500, 502, 503, 504)


def _gemini_complete(
    client: httpx.Client, api_key: str, model: str, system: str, user: str
) -> str:
    """
    Call Google Generative Language API (generateContent) for Gemma / Gemini family.

    Walks through ``GOOGLE_GENERATIVE_MODEL_CHAIN`` (Gemma, several Gemini/Flash) on
    404/429/5xx. ``model`` is kept for signature compatibility; chain is fixed in code.

    Args:
        api_key: API key in query.
        model: Unused (legacy); chain defined by ``GOOGLE_GENERATIVE_MODEL_CHAIN``.
        system: Prepended to user (single contents.parts block for Gemma compatibility).
        user: Main prompt.

    Returns:
        Model text.
    """
    _ = model
    body = _gemma_generate_content_body(system, user, max_output_tokens=8192)
    order = GOOGLE_GENERATIVE_MODEL_CHAIN
    for idx, m in enumerate(order):
        r = _generative_post_with_retries(client, api_key, m, body)
        try:
            return _parse_generative_content_response(r)
        except ValueError:
            if idx < len(order) - 1 and _http_status_worth_model_fallback(r):
                logger.warning(
                    "Model %s failed (HTTP %s), falling back to %s",
                    m,
                    r.status_code,
                    order[idx + 1],
                )
                continue
            raise


def suggest_task_split(
    issue_text: str,
    title: str,
    keys: list[APIKeyEntry],
    *,
    prompts: Any = None,
    redmine_context: str = "",
    socks5_proxies: list[str] | None = None,
) -> list[dict[str, str]]:
    """
    Ask an LLM to propose 2–4 child tasks (subject + description only).

    Args:
        issue_text: Long description of parent issue.
        title: Parent subject.
        keys: API keys pool.
        prompts: Optional ``users.ai_prompts_json`` (merged with defaults inside).
        redmine_context: Subtasks and related issues (plain text) so the model avoids duplicating
            work already captured in Redmine.
        socks5_proxies: Optional round-robin SOCKS5 URLs for outbound AI traffic.

    Returns:
        List of { "subject", "description" }.
    """
    p = effective_ai_prompts(prompts)
    e = _pick_key(keys)
    system = p["split_system"]
    user = f"Parent title: {title}\n\nDescription:\n{issue_text or ''}\n"
    if str(redmine_context).strip():
        user += f"\n{str(redmine_context).strip()}\n"
    urls = parse_socks5_proxies(socks5_proxies)
    proxy = _pick_socks_proxy_url(urls) if urls else None
    with _ai_http_client(proxy) as client:
        raw = _call_provider(e, system, user, client)
    return _parse_json_array(raw)


def suggest_wizard_actions(
    issue_title: str,
    issue_text: str,
    status: str,
    spent_hours: float,
    keys: list[APIKeyEntry],
    *,
    prompts: Any = None,
    socks5_proxies: list[str] | None = None,
) -> dict[str, Any]:
    """
    Ask the model for one-line suggestions: close, split, log time, change status, comment.

    Returns JSON with keys: summary, close, split, time_hours, new_status_suggestion, comment
    (values can be null where not applicable).
    """
    p = effective_ai_prompts(prompts)
    e = _pick_key(keys)
    system = p["wizard_system"]
    user = f"Task: {issue_title}\nStatus: {status}\nSpent: {spent_hours}h\n\n{issue_text}"
    urls = parse_socks5_proxies(socks5_proxies)
    proxy = _pick_socks_proxy_url(urls) if urls else None
    with _ai_http_client(proxy) as client:
        raw = _call_provider(e, system, user, client)
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {"summary": raw.strip()[:500]}
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"summary": raw.strip()[:500]}


def suggest_complexity(
    issue_title: str,
    issue_text: str,
    keys: list[APIKeyEntry],
    *,
    prompts: Any = None,
    socks5_proxies: list[str] | None = None,
) -> str:
    """
    Return one of s,m,l,xl,2xl as suggested t-shirt size.

    Args:
        issue_title: Issue subject.
        issue_text: Description.
        keys: API pool.
        prompts: Optional per-user system prompt override JSON.

    Returns:
        One token complexity label.
    """
    p = effective_ai_prompts(prompts)
    e = _pick_key(keys)
    system = p["complexity_system"]
    user = f"{issue_title}\n\n{issue_text or ''}"
    urls = parse_socks5_proxies(socks5_proxies)
    proxy = _pick_socks_proxy_url(urls) if urls else None
    with _ai_http_client(proxy) as client:
        raw = _call_provider(e, system, user, client).strip().lower()
    if "2xl" in raw:
        return "2xl"
    for token in ("xl", "l", "m", "s"):
        if re.search(rf"\b{re.escape(token)}\b", raw):
            return token
    return "m"


def test_provider_reachability(
    provider: AIProvider,
    api_key: str,
    socks5_proxies: list[str] | None = None,
) -> tuple[bool, str]:
    """
    One minimal call per provider to verify that the key works (no full completion cost).

    Args:
        provider: Backend to probe.
        api_key: Plaintext API key.

    Returns:
        (True, \"\") on success, or (False, short error text).
    """
    urls = parse_socks5_proxies(socks5_proxies)
    proxy = _pick_socks_proxy_url(urls) if urls else None
    try:
        with _ai_http_client(proxy) as client:
            if provider == AIProvider.OPENAI:
                r = _openai_complete_one(
                    client,
                    "https://api.openai.com",
                    api_key,
                    OPENAI_MODEL_CHAIN[0],
                    "You are a test.",
                    ".",
                )
                r.raise_for_status()
                return True, ""
            if provider == AIProvider.DEEPSEEK:
                r = _openai_complete_one(
                    client,
                    "https://api.deepseek.com",
                    api_key,
                    DEEPSEEK_MODEL_CHAIN[0],
                    "You are a test.",
                    ".",
                )
                r.raise_for_status()
                return True, ""
            if provider == AIProvider.YANDEXGPT:
                yk, ymodels = _parse_yandex_secret(api_key)
                r = _openai_complete_one(
                    client,
                    YANDEX_GPT_BASE,
                    yk,
                    ymodels[0],
                    "You are a test.",
                    ".",
                    use_api_key_auth=True,
                )
                r.raise_for_status()
                return True, ""
            if provider == AIProvider.GEMINI:
                probe = _gemma_generate_content_body("You are a test.", ".", max_output_tokens=8)
                for m in GOOGLE_GENERATIVE_MODEL_CHAIN[:3]:
                    gurl = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
                    r = client.post(
                        gurl,
                        params={"key": api_key},
                        json=probe,
                        timeout=25.0,
                    )
                    if m == GOOGLE_GEMMA_MODEL and r.status_code in (500, 502, 503, 504, 429):
                        continue
                    if not r.is_success:
                        r.raise_for_status()
                    j = r.json()
                    if j.get("error"):
                        e = j["error"]
                        err_msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
                        if m == GOOGLE_GEMMA_MODEL and "Internal" in (err_msg or ""):
                            continue
                        return False, err_msg[:400]
                    if not (j.get("candidates") or []):
                        if m == GOOGLE_GEMMA_MODEL:
                            continue
                        return False, "No candidates (check key / model access in AI Studio)"
                    return True, ""
                return False, "Gemma and Flash fallback both failed (check status page / key)"
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:400]
        return False, f"HTTP {e.response.status_code}: {body}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:300]
    return False, "unknown provider"


def _call_provider(e: APIKeyEntry, system: str, user: str, client: httpx.Client) -> str:
    """
    Route to the correct provider implementation.

    Args:
        e: Key entry to bill against.
        system: System prompt.
        user: User content (issue text, etc.); redacted for PII before send.
        client: HTTP client (SOCKS5 if configured in outer ``_ai_http_client``).

    Returns:
        Model text.
    """
    user = redact_for_llm(user)
    if e.provider == AIProvider.OPENAI:
        return _openai_complete(
            client,
            "https://api.openai.com",
            e.secret,
            system,
            user,
            OPENAI_MODEL_CHAIN,
        )
    if e.provider == AIProvider.DEEPSEEK:
        return _openai_complete(
            client,
            "https://api.deepseek.com",
            e.secret,
            system,
            user,
            DEEPSEEK_MODEL_CHAIN,
        )
    if e.provider == AIProvider.YANDEXGPT:
        yk, ymodels = _parse_yandex_secret(e.secret)
        return _openai_complete(
            client,
            YANDEX_GPT_BASE,
            yk,
            system,
            user,
            ymodels,
            use_api_key_auth=True,
        )
    if e.provider == AIProvider.GEMINI:
        return _gemini_complete(client, e.secret, GOOGLE_GEMMA_MODEL, system, user)
    return _openai_complete(
        client,
        "https://api.openai.com",
        e.secret,
        system,
        user,
        OPENAI_MODEL_CHAIN,
    )


def _parse_json_array(text: str) -> list[dict[str, str]]:
    """Parse model output that should be a JSON array of {subject, description}."""
    t = text.strip()
    m = re.search(r"\[[\s\S]*\]", t)
    if m:
        t = m.group(0)
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return [
            {
                "subject": "Subtask 1",
                "description": "Please refine split manually; model did not return JSON.",
            }
        ]
    if not isinstance(data, list):
        return [
            {
                "subject": "Subtask 1",
                "description": str(data)[:2000],
            }
        ]
    return [
        {
            "subject": str(d.get("subject", "Subtask"))[:500],
            "description": str(d.get("description", ""))[:5000],
        }
        for d in data
        if isinstance(d, dict)
    ][:4]
