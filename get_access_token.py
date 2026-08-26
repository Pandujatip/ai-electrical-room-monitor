import os
import time
import uuid
import hashlib
import json
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

OPENAPI_HOST = os.environ["IMOU_OPENAPI_HOST"].rstrip("/")
APP_ID = os.environ["IMOU_APP_ID"]
APP_SECRET = os.environ["IMOU_APP_SECRET"]


def calculate_sign(timestamp, nonce):
    raw = f"time:{timestamp},nonce:{nonce},appSecret:{APP_SECRET}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def main():
    timestamp = int(time.time())
    nonce = str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    body = {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": calculate_sign(timestamp, nonce),
            "time": timestamp,
            "nonce": nonce,
        },
        "id": request_id,
        "params": {},
    }

    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    url = f"{OPENAPI_HOST}/openapi/accessToken"

    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json;charset=UTF-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

        print(json.dumps(result, indent=2))

        code = result.get("result", {}).get("code")
        if code == "0":
            print("\nAccessToken berhasil diperoleh.")
        else:
            print(f"\nAPI mengembalikan kode: {code}")

    except urllib.error.HTTPError as error:
        print(f"HTTP Error {error.code}")
        print(error.read().decode("utf-8", errors="replace"))
    except Exception as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    main()