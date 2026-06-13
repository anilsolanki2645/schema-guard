import re
from urllib.parse import urlparse, urlunparse

# Regex to check if key should be masked
SECRET_KEYS_PATTERN = re.compile(r'(secret|pwd|passwd|password|token)', re.IGNORECASE)

def mask_dict(data: dict) -> dict:
    """
    Recursively traverse and mask sensitive keys in a dictionary.
    """
    if not isinstance(data, dict):
        return data
        
    masked = {}
    for k, v in data.items():
        if isinstance(v, dict):
            masked[k] = mask_dict(v)
        elif isinstance(v, list):
            masked[k] = [mask_dict(item) if isinstance(item, dict) else item for item in v]
        elif isinstance(k, str) and SECRET_KEYS_PATTERN.search(k):
            masked[k] = "******"
        else:
            # Also try to mask string connection URLs if present
            if isinstance(v, str) and any(prefix in v.lower() for prefix in ["postgresql://", "mysql://", "sqlite://", "oracle://"]):
                masked[k] = mask_connection_string(v)
            else:
                masked[k] = v
    return masked

def mask_connection_string(url: str) -> str:
    """
    Parse a connection string and mask the password if present.
    """
    try:
        parsed = urlparse(url)
        if parsed.password:
            # Re-construct userinfo with masked password
            netloc = parsed.netloc
            # Replacing password in netloc: username:password@host:port -> username:******@host:port
            if '@' in netloc:
                userinfo, hostinfo = netloc.rsplit('@', 1)
                if ':' in userinfo:
                    username, _ = userinfo.split(':', 1)
                    netloc = f"{username}:******@{hostinfo}"
                else:
                    # just password? or username?
                    netloc = f"{userinfo}:******@{hostinfo}"
            new_parsed = parsed._replace(netloc=netloc)
            return urlunparse(new_parsed)
    except Exception:
        pass
    return url


# Regex to mask passwords inside connection strings in general logs/text
URL_PASSWORD_RE = re.compile(r'([a-zA-Z0-9\+\.]+://[^:]+:)([^@]+)(@[^/]+)')

def mask_secrets(text: str) -> str:
    """
    Find and mask credentials inside connection URLs in any raw text/string.
    """
    if not isinstance(text, str):
        return text
    return URL_PASSWORD_RE.sub(r'\1******\3', text)
