from schema_guard.masking import mask_dict, mask_connection_string, mask_secrets

def test_mask_dict_sensitive_keys():
    data = {
        "host": "localhost",
        "port": 5432,
        "password": "my-secret-pass",
        "secret_key": "12345",
        "auth_token": "token-123",
        "nested": {
            "passwd": "nested-pass",
            "safe_value": "hello"
        },
        "list_of_dicts": [
            {"password": "pass1"},
            {"user": "anil"}
        ]
    }
    
    masked = mask_dict(data)
    
    assert masked["host"] == "localhost"
    assert masked["port"] == 5432
    assert masked["password"] == "******"
    assert masked["secret_key"] == "******"
    assert masked["auth_token"] == "******"
    assert masked["nested"]["passwd"] == "******"
    assert masked["nested"]["safe_value"] == "hello"
    assert masked["list_of_dicts"][0]["password"] == "******"
    assert masked["list_of_dicts"][1]["user"] == "anil"

def test_mask_connection_string():
    url = "postgresql://myuser:mypass123@localhost:5432/mydb"
    masked = mask_connection_string(url)
    assert "mypass123" not in masked
    assert masked == "postgresql://myuser:******@localhost:5432/mydb"

def test_mask_dict_with_url():
    data = {
        "db_url": "postgresql://myuser:mypass123@localhost:5432/mydb",
        "normal_key": "val"
    }
    masked = mask_dict(data)
    assert masked["db_url"] == "postgresql://myuser:******@localhost:5432/mydb"
    assert masked["normal_key"] == "val"

def test_mask_secrets_raw_text():
    text = "Failed to connect to mysql+pymysql://root:password123@127.0.0.1:3306/test_db due to timeout."
    masked = mask_secrets(text)
    assert "password123" not in masked
    assert masked == "Failed to connect to mysql+pymysql://root:******@127.0.0.1:3306/test_db due to timeout."

