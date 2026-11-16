"""A software security key for tests: answers Web Authentication options the way a browser and
an ES256 authenticator would, with "none" attestation. Synthetic keys only."""

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url as b64

UP, UV, BE, BS, AT = 0x01, 0x04, 0x08, 0x10, 0x40


def _sha256(data):
    return hashlib.sha256(data).digest()


class SoftKey:
    def __init__(self, *, origin="http://testserver", synced=False, counter=True):
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.origin = origin
        self.synced = synced
        self.counter = counter
        self.sign_count = 0
        self.user_handle = None

    def _flags(self, *, attested=False):
        flags = UP | UV
        if self.synced:
            flags |= BE | BS
        if attested:
            flags |= AT
        return flags

    def _cose_key(self):
        numbers = self.private.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # EC2
                3: -7,  # ES256
                -1: 1,  # P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, kind, challenge, origin):
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin or self.origin}
        ).encode()

    def register(self, options, *, origin=None, rp_id=None):
        """What navigator.credentials.create() returns for the options the page embeds."""
        self.user_handle = options["user"]["id"]
        client_data = self._client_data("webauthn.create", options["challenge"], origin)
        auth_data = (
            _sha256((rp_id or options["rp"]["id"]).encode())
            + bytes([self._flags(attested=True)])
            + struct.pack(">I", self.sign_count)
            + bytes(16)  # AAGUID: none disclosed.
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return json.dumps(
            {
                "id": b64(self.credential_id),
                "rawId": b64(self.credential_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": b64(client_data),
                    "attestationObject": b64(attestation),
                    "transports": ["usb", "nfc"],
                },
                "clientExtensionResults": {},
            }
        )

    def answer(self, options, *, origin=None, rp_id=None, count=None, tamper=False):
        """What navigator.credentials.get() returns for the options the page embeds."""
        if count is not None:
            self.sign_count = count
        elif self.counter:
            self.sign_count += 1
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        auth_data = (
            _sha256((rp_id or options["rpId"]).encode())
            + bytes([self._flags()])
            + struct.pack(">I", self.sign_count)
        )
        signature = self.private.sign(auth_data + _sha256(client_data), ec.ECDSA(hashes.SHA256()))
        if tamper:
            auth_data = auth_data[:-1] + bytes([(auth_data[-1] + 1) % 256])
        response = {
            "clientDataJSON": b64(client_data),
            "authenticatorData": b64(auth_data),
            "signature": b64(signature),
        }
        if self.user_handle:
            response["userHandle"] = self.user_handle
        return json.dumps(
            {
                "id": b64(self.credential_id),
                "rawId": b64(self.credential_id),
                "type": "public-key",
                "response": response,
                "clientExtensionResults": {},
            }
        )
