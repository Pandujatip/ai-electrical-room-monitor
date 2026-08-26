import os
import time
import uuid
import hashlib
import json
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

HOST = os.environ["IMOU_OPENAPI_HOST"].rstrip("/")
APP_ID = os.environ["IMOU_APP_ID"]
APP_SECRET = os.environ["IMOU_APP_SECRET"]


def sign(timestamp, nonce):
    raw = f"time:{timestamp},nonce:{nonce},appSecret:{APP_SECRET}"
    return hashlib.md5(raw.encode()).hexdigest()


def call_api(endpoint, params):
    timestamp = int(time.time())
    nonce = str(uuid.uuid4())

    body = {
        "system": {
            "ver": "1.0",
            "appId": APP_ID,
            "sign": sign(timestamp, nonce),
            "time": timestamp,
            "nonce": nonce,
        },
        "id": str(uuid.uuid4()),
        "params": params,
    }

    request = urllib.request.Request(
        f"{HOST}/openapi/{endpoint}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json;charset=UTF-8"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


# 1. Ambil accessToken
token_response = call_api("accessToken", {})
result = token_response["result"]

if result["code"] != "0":
    raise RuntimeError(token_response)

access_token = result["data"]["accessToken"]
device_id = "A74A2BJPCGF386A"

# Query detailed device information. This endpoint is available for this app
# and includes deviceAbility/channelAbility (including AudioTalk and PlaySound).
details = call_api(
    "listDeviceDetailsByIds",
    {
        "token": access_token,
        "deviceList": [
            {
                "deviceId": device_id,
                "channelId": ["0"],
            }
        ],
    },
)

detail_result = details.get("result", {})
detail_data = detail_result.get("data", {})
detail_device = (detail_data.get("deviceList") or [{}])[0]
detail_channel = (detail_device.get("channelList") or [{}])[0]

# Never print devicePassword, playToken, deviceUsername, or similar secrets.
safe_details = {
    "code": detail_result.get("code"),
    "msg": detail_result.get("msg"),
    "deviceId": detail_device.get("deviceId"),
    "deviceName": detail_device.get("deviceName"),
    "deviceModel": detail_device.get("deviceModel"),
    "deviceStatus": detail_device.get("deviceStatus"),
    "productId": detail_device.get("productId"),
    "channelId": detail_channel.get("channelId"),
    "channelStatus": detail_channel.get("channelStatus"),
    "channelAbility": detail_channel.get("channelAbility"),
}
print(json.dumps(safe_details, indent=2))

# 2. Ambil daftar perangkat terikat
devices_response = call_api(
    "deviceBaseList",
    {
        "token": access_token,
        "bindId": -1,
        "limit": 128,
        "type": "bind",
        "needApInfo": False,
    },
)

device_result = devices_response.get("result", {})
device_data = device_result.get("data", {})
safe_devices = [
    {
        "deviceId": item.get("deviceId"),
        "channels": item.get("channels"),
    }
    for item in device_data.get("deviceList", [])
]
print(json.dumps({
    "code": device_result.get("code"),
    "msg": device_result.get("msg"),
    "count": device_data.get("count", 0),
    "deviceList": safe_devices,
}, indent=2))
