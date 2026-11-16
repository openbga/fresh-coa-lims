"""A local OpenID Connect provider for tests: discovery, authorization, token and key set.

It runs an HTTP server on 127.0.0.1 in a thread. The authorization endpoint answers at once for
the subject the test chose (next_subject), or with the error it chose, so that a test drives the
whole code flow with PKCE: the application fetches discovery, exchanges the code at the token
endpoint and checks the ID token against the key set, all over HTTP. Attributes let a test make
the provider misbehave (claims, signing key, missing ID token, rotated keys). Synthetic only.
"""

import base64
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

CLIENT_ID = "lims-test-client"
CLIENT_SECRET = "synthetic-test-secret-not-real"


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Provider:
    def __init__(self):
        self.key = RSAKey.generate_key(2048, parameters={"kid": "key-1"})
        self.published = [self.key]
        self.next_subject = None
        self.claims = {}  # Extra claims for the next ID tokens, by subject.
        self.override = {}  # Claims replaced in every ID token (tampering tests).
        self.sign_with = None  # Another key to sign with (not published).
        self.unsigned = False
        self.symmetric = False
        self.omit_id_token = False
        self.token_error = None
        self.error = None
        self.answer_iss = None  # RFC 9207 iss parameter in the authorization response.
        self.metadata_override = {}
        self.authorize_requests = []
        self.token_requests = []
        self.codes = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.issuer = f"http://127.0.0.1:{self.server.server_address[1]}/realm"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def rotate(self):
        """Publish only a new key and sign with it from now on."""
        self.key = RSAKey.generate_key(2048, parameters={"kid": f"key-{secrets.token_hex(4)}"})
        self.published = [self.key]

    def metadata(self):
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "jwks_uri": f"{self.issuer}/jwks",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic"],
            "code_challenge_methods_supported": ["S256"],
            **self.metadata_override,
        }

    def id_token(self, subject, nonce):
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "sub": subject,
            "aud": CLIENT_ID,
            "exp": now + 300,
            "iat": now,
            "nonce": nonce,
            **self.claims.get(subject, {}),
            **self.override,
        }
        claims = {k: v for k, v in claims.items() if v is not None}
        if self.unsigned:
            header = _b64(json.dumps({"alg": "none"}).encode())
            return f"{header}.{_b64(json.dumps(claims).encode())}."
        if self.symmetric:
            from joserfc.jwk import OctKey

            key = OctKey.import_key(CLIENT_SECRET.encode())
            return jwt.encode({"alg": "HS256"}, claims, key)
        key = self.sign_with or self.key
        return jwt.encode({"alg": "RS256", "kid": key.kid}, claims, key)

    def _handler(self):
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urlsplit(self.path)
                path = url.path.removeprefix("/realm")
                if path == "/.well-known/openid-configuration":
                    return self._json(200, provider.metadata())
                if path == "/jwks":
                    keys = KeySet(provider.published).as_dict(private=False)
                    return self._json(200, keys)
                if path == "/authorize":
                    params = {k: v[0] for k, v in parse_qs(url.query).items()}
                    provider.authorize_requests.append(params)
                    answer = {"state": params.get("state", "")}
                    if provider.error:
                        answer["error"] = provider.error
                    else:
                        code = secrets.token_urlsafe(16)
                        provider.codes[code] = {
                            "subject": provider.next_subject,
                            "nonce": params.get("nonce"),
                            "challenge": params.get("code_challenge"),
                            "redirect_uri": params.get("redirect_uri"),
                            "client_id": params.get("client_id"),
                        }
                        answer["code"] = code
                    if provider.answer_iss:
                        answer["iss"] = provider.answer_iss
                    self.send_response(302)
                    self.send_header("Location", f"{params['redirect_uri']}?{urlencode(answer)}")
                    self.end_headers()
                    return None
                return self._json(404, {"error": "not_found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
                provider.token_requests.append(form)
                expected = (
                    "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
                )
                if self.headers.get("Authorization") != expected:
                    return self._json(401, {"error": "invalid_client"})
                if provider.token_error:
                    return self._json(400, {"error": provider.token_error})
                grant = provider.codes.pop(form.get("code"), None)
                verifier = form.get("code_verifier", "")
                if (
                    grant is None
                    or form.get("grant_type") != "authorization_code"
                    or form.get("redirect_uri") != grant["redirect_uri"]
                    or _b64(hashlib.sha256(verifier.encode()).digest()) != grant["challenge"]
                ):
                    return self._json(400, {"error": "invalid_grant"})
                body = {"access_token": secrets.token_urlsafe(16), "token_type": "Bearer"}
                body["expires_in"] = 300
                if not provider.omit_id_token:
                    body["id_token"] = provider.id_token(grant["subject"], grant["nonce"])
                return self._json(200, body)

        return Handler
