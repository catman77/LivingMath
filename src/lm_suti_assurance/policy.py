"""Publication policy cannot turn a source declaration into execution permission."""
import re
import json
from .errors import AssuranceError
from .validation import validate

# Conservative concrete token/local-secret guards, not a general PII oracle.
PATTERNS = [r'\b[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
            r'\+[1-9][0-9]?[ -]?[0-9]{3}[ -]?[0-9]{3}[ -]?[0-9]{2}[ -]?[0-9]{2}\b',
            r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,})',
            r'(?i)\b(?:access_token|refresh_token|client_secret|password)\s*["\']?\s*[:=]\s*["\'][^"\']+',
            r'(?:/home/[^/\s"\']+|/Users/[^/\s"\']+|[A-Z]:\\Users\\[^\\\s]+)',
            r'(?i)(?:\.ssh/|\.env\b|oauth\.sqlite3|login-password)']


def export_guard(text):
    def visit(value, depth=0):
        if depth > 48:
            raise AssuranceError('EXPORT_DEPTH_EXCEEDED')
        if isinstance(value, str):
            for pattern in PATTERNS:
                if re.search(pattern, value):
                    raise AssuranceError('EXPORT_SENSITIVE_CONTENT', details={'redact_by_new_record': True})
            try:
                parsed = json.loads(value)
            except (ValueError, RecursionError):
                return
            if isinstance(parsed, (dict, list)):
                visit(parsed, depth + 1)
        elif isinstance(value, dict):
            # Scan a decoded canonical object so nested JSON strings cannot hide keys.
            for key, item in value.items():
                if re.fullmatch(r'(?i)(access_token|refresh_token|client_secret|password)', key):
                    raise AssuranceError('EXPORT_SENSITIVE_CONTENT')
                visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
    visit(text)


def can_publish(source, policy, audience):
    validate('publication-policy', policy)
    rights = source['rights']
    return (rights.get('can_embed') is True and rights.get('status') == 'DECLARED_USER_AUTHORIZED'
            and policy['allow_source_bytes'] is True and audience in policy['audiences'])
