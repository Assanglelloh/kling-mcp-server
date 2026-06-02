import jwt, time, json, os, requests
from flask import Flask, Response, request, jsonify, redirect

ACCESS_KEY = os.environ.get("KLING_ACCESS_KEY", "")
SECRET_KEY = os.environ.get("KLING_SECRET_KEY", "")
BASE_URL = "https://api.klingai.com"
app = Flask(__name__)

def get_token():
    now = int(time.time())
    return jwt.encode({"iss": ACCESS_KEY, "exp": now+1800, "nbf": now-5}, SECRET_KEY, algorithm="HS256")

def kh():
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}

TOOLS = [
    {"name": "generate_image", "description": "Génère une image via Kling AI.", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "aspect_ratio": {"type": "string", "default": "1:1"}, "n": {"type": "integer", "default": 2}}, "required": ["prompt"]}},
    {"name": "generate_video", "description": "Génère une vidéo via Kling AI.", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "duration": {"type": "string", "default": "5"}, "aspect_ratio": {"type": "string", "default": "9:16"}}, "required": ["prompt"]}},
    {"name": "check_task", "description": "Vérifie le statut d'une tâche Kling.", "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "type": {"type": "string", "enum": ["image","video"]}}, "required": ["task_id","type"]}}
]

def call_tool(name, args):
    try:
        if name == "generate_image":
            r = requests.post(f"{BASE_URL}/v1/images/
