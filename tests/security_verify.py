import urllib.parse

def validate_url(url):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in ['http', 'https']:
        return False
    if any(x in parsed_url.netloc for x in ['localhost', '127.0.0.1', '::1', '169.254']):
        return False
    return True

# Test cases
test_urls = {
    "https://google.com": True,
    "http://example.com/image.png": True,
    "http://localhost/secret": False,
    "http://127.0.0.1:8080/": False,
    "https://169.254.169.254/latest/meta-data/": False,
    "ftp://malicious.com": False,
    "javascript:alert(1)": False
}

print("--- Running SSRF Validation Tests ---")
for url, expected in test_urls.items():
    result = validate_url(url)
    status = "PASS" if result == expected else "FAIL"
    print(f"[{status}] URL: {url} | Expected: {expected} | Got: {result}")

print("\n--- Running Format Robustness Simulation ---")
DEFAULT_MSG = "Welcome {user} to {server}!"
custom_msg = "Welcome {user} to {server}! Here is an {error_key}"

try:
    print(f"Normal format: {DEFAULT_MSG.format(user='User', server='Server')}")
    # Simulate the fix logic
    try:
        formatted = custom_msg.format(user='User', server='Server')
    except (KeyError, ValueError):
        formatted = DEFAULT_MSG.format(user='User', server='Server')
    print(f"Robust format (with invalid key): {formatted}")
    print("[PASS] Formatting survived invalid keys.")
except Exception as e:
    print(f"[FAIL] Formatting crashed: {e}")
