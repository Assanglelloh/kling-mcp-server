"""
Kling AI MCP Server — HTTP/SSE version pour Railway
"""

import jwt
import time
import json
import os
import requests
from flask import Flask, Response, request, jsonify

ACCESS_KEY = os.environ.get("KLING_ACCESS_KEY", "")
SECRET_KEY = os.environ.get("KLING_SECRET_KEY", "")
BASE_URL = "https://api.klingai.com"

app = Flask(__name__)

def get_token():
    now = int(time.time())
    payload = {"iss": ACCESS_KEY, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def kling_headers():
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}

TOOLS = [
    {
        "name": "generate_image",
        "description": "Génère une image UGC réaliste via Kling AI à partir d'un prompt texte.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description de l'image (en anglais)"},
                "aspect_ratio": {"type": "string", "default": "1:1", "description": "Format: 1:1, 16:9, 9:16, 4:3"},
                "n": {"type": "integer", "default": 2, "description": "Nombre d'images (1-9)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "generate_video",
        "description": "Génère une vidéo publicitaire UGC via Kling AI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description de la vidéo (en anglais)"},
                "duration": {"type": "string", "default": "5", "description": "Durée: 5 ou 10 secondes"},
                "aspect_ratio": {"type": "string", "default": "9:16", "description": "Format: 9:16, 16:9, 1:1"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "check_task",
        "description": "Vérifie le statut d'une tâche de génération Kling en cours.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID de la tâche"},
                "type": {"type": "string", "enum": ["image", "video"], "description": "Type de tâche"}
            },
            "required": ["task_id", "type"]
        }
    }
]

def call_tool(name, arguments):
    try:
        if name == "generate_image":
            resp = requests.post(
                f"{BASE_URL}/v1/images/generations",
                headers=kling_headers(),
                json={
                    "model_name": "kling-v1",
                    "prompt": arguments["prompt"],
                    "n": arguments.get("n", 2),
                    "aspect_ratio": arguments.get("aspect_ratio", "1:1")
                }
            )
            data = resp.json()
            if data.get("code") != 0:
                return {"error": data.get("message", "Erreur inconnue")}
            return {
                "task_id": data["data"]["task_id"],
                "message": "Génération lancée. Utilise check_task dans 30-60 secondes.",
                "type": "image"
            }

        elif name == "generate_video":
            resp = requests.post(
                f"{BASE_URL}/v1/videos/text2video",
                headers=kling_headers(),
                json={
                    "model_name": "kling-v1",
                    "prompt": arguments["prompt"],
                    "duration": arguments.get("duration", "5"),
                    "aspect_ratio": arguments.get("aspect_ratio", "9:16"),
                    "mode": "std"
                }
            )
            data = resp.json()
            if data.get("code") != 0:
                return {"error": data.get("message", "Erreur inconnue")}
            return {
                "task_id": data["data"]["task_id"],
                "message": "Vidéo en cours de génération (2-5 minutes). Utilise check_task pour récupérer l'URL.",
                "type": "video"
            }

        elif name == "check_task":
            task_type = arguments["type"]
            endpoint = "/v1/images/generations" if task_type == "image" else "/v1/videos/text2video"
            resp = requests.get(
                f"{BASE_URL}{endpoint}/{arguments['task_id']}",
                headers=kling_headers()
            )
            data = resp.json()
            task_data = data.get("data", {})
            status = task_data.get("task_status", "unknown")

            if status == "succeed":
                result = task_data.get("task_result", {})
                items = result.get("images" if task_type == "image" else "videos", [])
                urls = [item.get("url") for item in items if item.get("url")]
                return {"status": "terminé", "urls": urls}
            elif status == "failed":
                return {"status": "échec", "detail": task_data.get("task_status_msg", "")}
            else:
                return {"status": status, "message": "Encore en cours, réessaie dans 30 secondes."}

    except Exception as e:
        return {"error": str(e)}

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "Kling AI MCP Server"})

@app.route("/sse", methods=["GET"])
def sse():
    def event_stream():
        yield f"event: endpoint\ndata: {json.dumps({'uri': '/messages'})}\n\n"
        while True:
            time.sleep(15)
            yield ": keepalive\n\n"

    return Response(event_stream(), mimetype="text/event-stream",
                   headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/messages", methods=["POST"])
def messages():
    body = request.get_json()
    method = body.get("method", "")
    req_id = body.get("id")

    if method == "initialize":
        return jsonify({
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kling-ai", "version": "1.0.0"}
            }
        })

    elif method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": TOOLS}
        })

    elif method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        result = call_tool(tool_name, arguments)
        return jsonify({
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            }
        })

    return jsonify({"jsonrpc": "2.0", "id": req_id, "result": {}})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
