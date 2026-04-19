import requests
import base64
import time

url: str = "http://127.0.0.1:8000/generate"

payload = {
    "prompt":"cinematic "
}

response = requests.post(url,json = payload)

if response.status_code == 200:
    data = response.json()

    #decode the Base64 string back into raw image bytes
    image_data = base64.b64decode(data["image_base64"])

    #saving it disk 
    filename = "test_output.jpg"

    
