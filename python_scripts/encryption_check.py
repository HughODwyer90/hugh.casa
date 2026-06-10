import re

KEY_PATTERN = re.compile(
    r"api:\s*(?:#.*\n|\s)*"
    r"encryption:\s*(?:#.*\n|\s)*"
    r"key:\s*[\"']?([^\"'\n]+)[\"']?",
    re.MULTILINE,
)

def has_encryption_key(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = KEY_PATTERN.search(content)
        if not match:
            return False
        key_value = match.group(1).strip()
        print(f"Captured key value: '{key_value}'")
        return not key_value.startswith("!secret")
    except Exception:
        return False

print(has_encryption_key("/config/esphome/ir_receiver.yaml"))