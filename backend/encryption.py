"""
Canary File Encryption Module
==============================
- Files are stored encrypted on disk
- Dashboard mein encrypted content dikhta hai (gibberish)
- File ke andar key type karo → real content decode ho jata hai
- Key galat → encrypted content hi dikhti hai

How it works:
  - AES-based Fernet symmetric encryption
  - Each canary file ka apna unique key hota hai (DB mein stored)
  - File on disk = encrypted bytes
  - Decryption sirf app ke through hoti hai (ya correct key se)
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken


def _key_from_password(password: str) -> bytes:
    """Derive a Fernet-compatible key from a user password."""
    hashed = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(hashed)


def generate_key() -> str:
    """Generate a random encryption key (shown to user once)."""
    return Fernet.generate_key().decode()


def encrypt_content(content: str, key: str) -> bytes:
    """Encrypt plaintext content with given key. Returns encrypted bytes."""
    fernet = Fernet(_key_from_password(key))
    return fernet.encrypt(content.encode('utf-8'))


def decrypt_content(encrypted_bytes: bytes, key: str) -> tuple[bool, str]:
    """
    Try to decrypt with given key.
    Returns (success: bool, content: str)
    """
    try:
        fernet = Fernet(_key_from_password(key))
        plaintext = fernet.decrypt(encrypted_bytes)
        return True, plaintext.decode('utf-8')
    except (InvalidToken, Exception):
        return False, ''


def make_encrypted_file(plaintext: str, key: str, filepath: str):
    """
    Write an encrypted canary file to disk.
    The file looks like:
      -----BEGIN CANARY ENCRYPTED FILE-----
      <base64 encrypted blob>
      -----END CANARY ENCRYPTED FILE-----
    """
    encrypted = encrypt_content(plaintext, key)
    b64       = base64.b64encode(encrypted).decode()

    # Wrap in 64-char lines (PEM-style)
    wrapped = '\n'.join(b64[i:i+64] for i in range(0, len(b64), 64))

    content = (
        "-----BEGIN CANARY ENCRYPTED FILE-----\n"
        f"{wrapped}\n"
        "-----END CANARY ENCRYPTED FILE-----\n"
        "\n"
        "This file is protected by Canary-File Security System.\n"
        "Unauthorized access has been logged and reported.\n"
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def read_and_decrypt(filepath: str, key: str) -> tuple[bool, str]:
    """
    Read an encrypted canary file and attempt decryption.
    Returns (success, plaintext_or_empty)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read()

        # Extract base64 blob between headers
        lines = raw.splitlines()
        b64_lines = []
        inside = False
        for line in lines:
            if '-----BEGIN CANARY ENCRYPTED FILE-----' in line:
                inside = True
                continue
            if '-----END CANARY ENCRYPTED FILE-----' in line:
                inside = False
                continue
            if inside:
                b64_lines.append(line.strip())

        if not b64_lines:
            return False, ''

        b64_data   = ''.join(b64_lines)
        enc_bytes  = base64.b64decode(b64_data)
        return decrypt_content(enc_bytes, key)

    except Exception as e:
        return False, str(e)


def is_encrypted_file(filepath: str) -> bool:
    """Check if a file is a Canary encrypted file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline().strip()
        return '-----BEGIN CANARY ENCRYPTED FILE-----' in first_line
    except Exception:
        return False
