"""Minimal Gemini REST client (server side only - the key never reaches the browser).

Model IDs are configuration: GEMINI_MODEL (primary), GEMINI_FALLBACK_MODEL
(used automatically if the primary ID is unknown to the API) and optional
per-bot overrides from Settings → AI.
"""
import logging
import math
import re
import threading
import time

from flask import current_app

log = logging.getLogger("astra.ai")
_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


class GeminiError(RuntimeError):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _cfg(key):
    return current_app.config.get(key)


def configured():
    return bool(_cfg("GEMINI_API_KEY"))


_local = threading.local()


def _http():
    """One keep-alive session per thread: skips a TLS handshake (~200-400 ms) on every call."""
    import requests

    sess = getattr(_local, "session", None)
    if sess is None:
        sess = _local.session = requests.Session()
    return sess


def _post(path, payload, timeout=None, conn=None):
    """conn = (api_base, api_key, default_timeout); pass it from worker threads (no app context there)."""
    import requests

    base, key, default_timeout = conn or (_cfg("GEMINI_API_BASE"), _cfg("GEMINI_API_KEY"), _cfg("GEMINI_TIMEOUT"))
    if not key:
        raise GeminiError("Gemini API key is not configured.", 503)
    try:
        resp = _http().post(
            f"{base}/{path}", json=payload, timeout=timeout or default_timeout,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        raise GeminiError(f"Gemini did not respond ({exc.__class__.__name__}). The model may be overloaded, or your connection is down.", 504) from exc
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message", resp.text[:200])
        except ValueError:
            msg = resp.text[:200]
        raise GeminiError(msg, resp.status_code)
    return resp.json()


def _model_chain(preferred=None):
    chain = []
    fallbacks = [f.strip() for f in (_cfg("GEMINI_FALLBACK_MODEL") or "").split(",")]
    # rolling aliases as last resorts: survive model retirements and "high demand" 503s on flash models
    for m in (preferred, _cfg("GEMINI_MODEL"), *fallbacks, "gemini-flash-latest", "gemini-flash-lite-latest"):
        if m and _MODEL_RE.match(m) and m not in chain:
            chain.append(m)
    if not chain:
        raise GeminiError("No valid Gemini model configured.", 503)
    now = time.monotonic()
    ready = [m for m in chain if _COOLDOWN.get(m, 0) <= now]
    return ready or chain[-1:]  # skip models whose quota is used up (until it resets)


_COOLDOWN = {}  # model -> monotonic time when it may be tried again (quota exhausted)
_RETRY_RE = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.I)


def _note_quota(model, exc):
    """A 429 'quota exceeded' (e.g. free-tier daily cap) won't clear for hours: stop wasting a round trip
    on that model for every message. Short rate limits get a short pause."""
    if exc.status != 429:
        return
    m = _RETRY_RE.search(str(exc))
    secs = (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)) if m else 60
    _COOLDOWN[model] = time.monotonic() + max(30, min(secs, 6 * 3600))
    log.warning("Gemini model %s is out of quota; skipping it for %d min", model, int((_COOLDOWN[model] - time.monotonic()) / 60))


def _should_fall_back(exc):
    """Model missing, overloaded, rate-limited, server error or timeout → try the next model.
    Bad API key / permission problems are raised immediately (another model won't help)."""
    msg = str(exc).lower()
    if exc.status in (401, 403):
        return False
    if exc.status == 400 and "model" not in msg and "argument" not in msg:
        return False
    return True


_NO_FAST = set()  # models that rejected the minimal-thinking option (remembered for this process)
_hedge_pool = None


def _call(m, payload, fast, timeout, conn):
    """One model call → (text, model). Raises GeminiError (and remembers quota exhaustion)."""
    try:
        return _call_once(m, payload, fast, timeout, conn)
    except GeminiError as exc:
        _note_quota(m, exc)
        raise


def _call_once(m, payload, fast, timeout, conn):
    path = f"models/{m}:generateContent"
    if fast and m not in _NO_FAST:
        body = {**payload, "generationConfig": {**payload["generationConfig"], "thinkingConfig": {"thinkingBudget": 0}}}
        try:
            data = _post(path, body, timeout=timeout, conn=conn)
        except GeminiError as exc:
            if exc.status != 400:
                raise
            _NO_FAST.add(m)  # this model doesn't accept that option: retry once as a normal request
            log.info("Model %s rejected thinkingConfig (%s); retrying without it", m, exc)
            data = _post(path, payload, timeout=timeout, conn=conn)
    else:
        data = _post(path, payload, timeout=timeout, conn=conn)
    cands = data.get("candidates") or []
    if not cands:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise GeminiError(f"Gemini returned no answer ({reason}).", 502)
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(x.get("text", "") for x in parts if not x.get("thought"))
    if not text.strip():
        raise GeminiError(f"Empty response (finish reason: {cands[0].get('finishReason', '?')}).", 502)
    return text.strip(), m


def _hedged(chain, payload, fast, timeout, budget, hedge_after, conn):
    """Start the first model; if it hasn't answered after `hedge_after` seconds (or it fails), start the
    next one IN PARALLEL and return whichever answers first. Cuts the long tail when a model is overloaded."""
    global _hedge_pool
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    if _hedge_pool is None:
        _hedge_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")
    deadline = time.monotonic() + (budget or 60)
    pending, nxt, last_error = {}, 0, None

    def launch():
        nonlocal nxt
        left = deadline - time.monotonic()
        f = _hedge_pool.submit(_call, chain[nxt], payload, fast, min(timeout or left, left), conn)
        pending[f] = chain[nxt]
        nxt += 1

    launch()
    while pending:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        done, _ = wait(list(pending), timeout=min(hedge_after, left), return_when=FIRST_COMPLETED)
        failed = False
        for f in done:
            m = pending.pop(f)
            try:
                return f.result()
            except GeminiError as exc:
                last_error, failed = exc, True
                if not _should_fall_back(exc):
                    raise
                log.warning("Gemini model %s failed (%s: %s)", m, exc.status, exc)
        if nxt < len(chain) and deadline - time.monotonic() > 3 and (failed or not done):
            if not done:
                log.info("Gemini model %s slow; also trying %s", list(pending.values())[-1], chain[nxt])
            launch()
    raise last_error or GeminiError("Gemini took too long to respond. The AI service may be overloaded; try again.", 504)


def generate(system, contents, model=None, temperature=0.6, max_tokens=8192, timeout=None, json_mode=False,
             budget=None, fast=False, hedge_after=None):
    """contents: list of {"role": "user"|"model", "text": str}. Returns (text, model_used).
    Tries the preferred model, then GEMINI_MODEL, then GEMINI_FALLBACK_MODEL.
    timeout: per-model seconds. budget: total seconds across the chain. fast: minimal "thinking"
    (dropped automatically for models that reject it). hedge_after: start the next model in parallel
    when the current one is slower than this many seconds."""
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": c["role"], "parts": [{"text": c["text"]}]} for c in contents if c.get("text")],
        "generationConfig": {"temperature": float(temperature), "maxOutputTokens": int(max_tokens)},
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    chain = _model_chain(model)
    conn = (_cfg("GEMINI_API_BASE"), _cfg("GEMINI_API_KEY"), _cfg("GEMINI_TIMEOUT"))
    if hedge_after:
        return _hedged(chain, payload, fast, timeout, budget, hedge_after, conn)
    last_error = None
    deadline = time.monotonic() + budget if budget else None
    for i, m in enumerate(chain):
        call_timeout = timeout
        if deadline:
            left = deadline - time.monotonic()
            if left < 3:
                raise last_error or GeminiError("Gemini took too long to respond.", 504)
            call_timeout = min(timeout or left, left)
        try:
            return _call(m, payload, fast, call_timeout, conn)
        except GeminiError as exc:
            last_error = exc
            if i < len(chain) - 1 and _should_fall_back(exc):
                log.warning("Gemini model %s failed (%s: %s); falling back to %s", m, exc.status, exc, chain[i + 1])
                continue
            raise
    raise last_error or GeminiError("No Gemini model available.")


def list_models():
    import requests

    key = _cfg("GEMINI_API_KEY")
    if not key:
        raise GeminiError("Gemini API key is not configured.", 503)
    resp = requests.get(f"{_cfg('GEMINI_API_BASE')}/models", params={"pageSize": 200},
                        headers={"x-goog-api-key": key}, timeout=20)
    if resp.status_code >= 400:
        raise GeminiError(resp.text[:200], resp.status_code)
    out = []
    for m in resp.json().get("models", []):
        methods = m.get("supportedGenerationMethods", [])
        out.append({"id": m.get("name", "").replace("models/", ""), "label": m.get("displayName", ""),
                    "generate": "generateContent" in methods, "embed": "embedContent" in methods})
    return out


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
def embeddings_enabled(config=None):
    cfg = config or current_app.config
    return cfg.get("EMBEDDINGS_PROVIDER") == "gemini" and bool(cfg.get("GEMINI_API_KEY"))


def _normalise(vec):
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(texts, task_type="RETRIEVAL_DOCUMENT"):
    """Embed up to 100 texts. Returns list of unit vectors."""
    model = _cfg("GEMINI_EMBEDDING_MODEL")
    if not _MODEL_RE.match(model or ""):
        raise GeminiError("Invalid embedding model id", 503)
    dim = int(_cfg("EMBEDDING_DIM") or 768)
    payload = {"requests": [
        {"model": f"models/{model}", "content": {"parts": [{"text": t[:8000]}]},
         "taskType": task_type, "outputDimensionality": dim}
        for t in texts[:100]
    ]}
    data = _post(f"models/{model}:batchEmbedContents", payload, timeout=40)
    return [_normalise(e.get("values", [])) for e in data.get("embeddings", [])]
