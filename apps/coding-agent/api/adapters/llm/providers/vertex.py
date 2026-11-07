"""Google Vertex AI, with the `thought_signature` trap handled where it belongs.

Two working shapes exist in this repository, and the choice between them is **data** (`wire` on the
model row), not a fork in the code:

| wire | npm | cost | verdict |
|---|---|---|---|
| `vertex_native` | `@ai-sdk/google-vertex` | one more npm package in the agent image | preferred: it round-trips signatures itself |
| `vertex_openai` | `@ai-sdk/openai-compatible` | needs the shim process | fallback: generic clients drop `extra_content` |

The stored secret is the **service-account JSON**, not a bearer token. That is deliberate (04 §Gemini):
the JSON is the signing identity, so a rotation is one row update rather than a redeploy, and the app
can cache a minted token for the child's lifetime and refresh it on a switch without re-entering the
vault.

Token minting and the token cache live here, not in the child, because
(a) the app can share one token across a switch, and
(b) it keeps the child's dependency surface unchanged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx

from ....config import settings
from ....domain.llm import CredentialError, ModelSpec, ProviderKind, ResolvedModel, WireProtocol
from ....ports import ChildEnv, ProviderDescriptor, Secret
from .base import PROVIDER_KEY_ENV, BaseAdapter

#: Google's own name for "a service-account key file". The built-in Vertex provider reads it.
GOOGLE_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
#: Refresh a minute before expiry: a token that expires mid-turn is an unexplained 401.
EARLY = 60.0


@dataclass
class TokenCache:
    """`(token, expiry)` per credential fingerprint. In memory only, cleared on revoke.

    A cached token is a short-lived capability, not a secret at rest: it never touches the database,
    never appears in a log, and dies with the process.
    """

    _rows: dict[str, tuple[str, float]] = field(default_factory=dict)

    def get(self, key: str, now: float | None = None) -> str | None:
        row = self._rows.get(key)
        if row is None:
            return None
        token, expiry = row
        if (now if now is not None else time.time()) >= expiry - EARLY:
            self._rows.pop(key, None)
            return None
        return token

    def put(self, key: str, token: str, expires_in: float) -> None:
        self._rows[key] = (token, time.time() + max(expires_in, EARLY + 1))

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self._rows.clear()
        else:
            self._rows.pop(key, None)


class VertexAdapter(BaseAdapter):
    kind = ProviderKind.GOOGLE_VERTEX
    wire = WireProtocol.VERTEX_NATIVE
    npm = "@ai-sdk/google-vertex"
    bearer = True

    def __init__(self, cache: TokenCache | None = None) -> None:
        self.tokens = cache or TokenCache()

    # -- descriptor ------------------------------------------------------------
    def base_url(self, spec: ModelSpec, *, host: str = "", project: str = "") -> str:
        """The OpenAI-compatible Vertex endpoint, which is what the agent's compatible client needs.

        `location` defaults to `global`, the value the repository's working script uses
        (`experiments/steps/06_opencode_vertex_gemini.sh`).
        """
        cfg = settings()
        location = cfg.llm_vertex_location or "global"
        proj = project or cfg.llm_vertex_project or "{project}"
        if cfg.llm_vertex_base_url:
            return str(cfg.llm_vertex_base_url).rstrip("/")
        return (f"https://aiplatform.googleapis.com/v1/projects/{proj}"
                f"/locations/{location}/endpoints/openapi")

    @staticmethod
    def _native(spec: ModelSpec) -> bool:
        return (spec.wire or WireProtocol.VERTEX_NATIVE) is WireProtocol.VERTEX_NATIVE

    def agent_key(self, spec: ModelSpec) -> str:
        """The agent's built-in `google-vertex` catalogue lists `gemini-3.8-flash`, no publisher."""
        if self._native(spec):
            return spec.endpoint.split("/", 1)[1] if spec.endpoint.startswith("google/") else spec.endpoint
        return spec.endpoint

    def env_var(self, spec: ModelSpec) -> str:
        """Native: a path to a key file (Google's own variable). Shim: the fixed bearer variable."""
        return GOOGLE_CREDENTIALS_ENV if self._native(spec) else super().env_var(spec)

    async def child_env(self, resolved: ResolvedModel, secret: Secret) -> ChildEnv:
        """What the agent needs to reach Vertex as this service account.

        Native wire: the built-in provider reads the key from a **file**, and takes the project and
        the region as variables. So the key is returned as file content (the caller owns where it
        lives and when it is removed). Shim wire: the app mints the access token itself and hands over only
        that, which is the narrower credential.
        """
        if resolved.wire is not WireProtocol.VERTEX_NATIVE:
            return ChildEnv(vars={PROVIDER_KEY_ENV: await self.access_token(secret)})
        if secret.value.strip().startswith("ya29."):
            raise CredentialError("kind", "this model needs a service-account key; a bare access "
                                          "token cannot be refreshed by the agent")
        cfg = settings()
        project = self.project_of(secret) or cfg.llm_vertex_project
        if not project:
            raise CredentialError("project_id", "no project: add the project this key bills to")
        return ChildEnv(
            vars={"GOOGLE_VERTEX_PROJECT": project,
                  "GOOGLE_VERTEX_LOCATION": cfg.llm_vertex_location or "global"},
            files={GOOGLE_CREDENTIALS_ENV: secret.value})

    def extra_body(self, spec: ModelSpec) -> dict:
        """Signature handling is a property of the wire, and the wire is on the row."""
        if spec.wire is WireProtocol.VERTEX_OPENAI:
            return {"extra_content": {"google": {"thought_signature": "passthrough"}}}
        return {}

    # -- credentials -----------------------------------------------------------
    @staticmethod
    def project_of(secret: Secret | None) -> str:
        """The `project_id` from the service-account JSON, or "" — never the whole blob."""
        if secret is None:
            return ""
        try:
            data = json.loads(secret.value)
        except (json.JSONDecodeError, TypeError):
            return ""
        project = data.get("project_id") if isinstance(data, dict) else None
        return str(project or "")

    async def access_token(self, secret: Secret, *, client: httpx.AsyncClient | None = None) -> str:
        """Mint an access token from the service-account JSON, cached to `expiry - 60 s`.

        A JSON that is already a bearer token (`ya29.…`) is passed through: users paste tokens too, and
        refusing them would be a worse experience than accepting the simpler credential.
        """
        if secret.value.strip().startswith("ya29."):
            return secret.value.strip()
        key = secret.ref or secret.value[-16:]
        cached = self.tokens.get(key)
        if cached:
            return cached
        assertion = self._assertion(secret)
        own = client is None
        http = client or httpx.AsyncClient(timeout=15)
        try:
            r = await http.post(TOKEN_URL, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            })
            if r.status_code >= 300:
                from ....domain.redact import redact

                raise PermissionError(redact(f"token exchange failed: {r.status_code} {r.text}")[:300])
            body = r.json()
            token = str(body.get("access_token") or "")
            if not token:
                raise PermissionError("token exchange returned no access_token")
            self.tokens.put(key, token, float(body.get("expires_in") or 3599))
            return token
        finally:
            if own:
                await http.aclose()

    @staticmethod
    def _assertion(secret: Secret) -> str:
        """A signed RS256 JWT assertion. `cryptography` does the signing; no google SDK needed."""
        import base64
        import json as _json

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        data = _json.loads(secret.value)
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "iss": data.get("client_email", ""),
            "scope": SCOPE,
            "aud": data.get("token_uri") or TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        }

        def enc(obj: dict) -> str:
            raw = _json.dumps(obj, separators=(",", ":")).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        signing_input = f"{enc(header)}.{enc(claims)}".encode()
        key = serialization.load_pem_private_key(str(data.get("private_key", "")).encode(), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{signing_input.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    # -- probe -----------------------------------------------------------------
    async def probe(self, desc: ProviderDescriptor, secret: Secret | None,
                    *, client: httpx.AsyncClient | None = None) -> tuple[str, str]:
        if secret is None:
            return "unauthorised", "no key: add a service-account JSON to use this model"
        try:
            token = await self.access_token(secret, client=client)
        except PermissionError as exc:
            return "unauthorised", str(exc)[:400]
        url = f"{desc.base_url}/chat/completions"
        payload = {"model": desc.model_key, "messages": [{"role": "user", "content": "ok"}],
                   "max_tokens": 1}
        return await self._post(url, payload, {"Authorization": f"Bearer {token}"}, client)
