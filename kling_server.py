import jwt
import time
import json
import requests
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

ACCESS_KEY = os.environ.get("KLING_ACCESS_KEY", "")
SECRET_KEY = os.environ.get("KLING_SECRET_KEY", "")
BASE_URL = "https://api.klingai.com"

def get_token():
    now = int(time.time())
    payload = {"iss": ACCESS_KEY, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def headers():
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}

app = Server("kling-ai")

@app.list_tools()
async def list_tools():
    return [
        types.Tool(name="generate_image", description="Génère une image UGC réaliste via Kling AI", inputSchema={"type":"object","properties":{"prompt":{"type":"string"},"aspect_ratio":{"type":"string","default":"1:1"},"n":{"type":"integer","default":2}},"required":["prompt"]}),
        types.Tool(name="generate_video", description="Génère une vidéo publicitaire via Kling AI", inputSchema={"type":"object","properties":{"prompt":{"type":"string"},"duration":{"type":"string","default":"5"},"aspect_ratio":{"type":"string","default":"9:16"}},"required":["prompt"]}),
        types.Tool(name="check_task", description="Vérifie le statut d'une tâche Kling", inputSchema={"type":"object","properties":{"task_id":{"type":"string"},"type":{"type":"string","enum":["image","video"]}},"required":["task_id","type"]})
    ]

@app.call_tool()
async def call_tool(name, arguments):
    try:
        if name == "generate_image":
            resp = requests.post(f"{BASE_URL}/v1/images/generations", headers=headers(), json={"model_name":"kling-v1","prompt":arguments["prompt"],"n":arguments.get("n",2),"aspect_ratio":arguments.get("aspect_ratio","1:1")})
            data = resp.json()
            if data.get("code") != 0:
                return [types.TextContent(type="text", text=f"Erreur: {data.get('message')}")]
            return [types.TextContent(type="text", text=json.dumps({"task_id":data["data"]["task_id"],"message":"Génération lancée, utilise check_task dans 30-60s"},ensure_ascii=False))]
        elif name == "generate_video":
            resp = requests.post(f"{BASE_URL}/v1/videos/text2video", headers=headers(), json={"model_name":"kling-v1","prompt":arguments["prompt"],"duration":arguments.get("duration","5"),"aspect_ratio":arguments.get("aspect_ratio","9:16"),"mode":"std"})
            data = resp.json()
            if data.get("code") != 0:
                return [types.TextContent(type="text", text=f"Erreur: {data.get('message')}")]
            return [types.TextContent(type="text", text=json.dumps({"task_id":data["data"]["task_id"],"message":"Vidéo en cours, utilise check_task dans 2-5 minutes"},ensure_ascii=False))]
        elif name == "check_task":
            endpoint = "/v1/images/generations" if arguments["type"]=="image" else "/v1/videos/text2video"
            resp = requests.get(f"{BASE_URL}{endpoint}/{arguments['task_id']}", headers=headers())
            data = resp.json()
            status = data.get("data",{}).get("task_status","")
            if status == "succeed":
                works = data["data"]["task_result"].get("images" if arguments["type"]=="image" else "videos",[])
                return [types.TextContent(type="text", text=json.dumps({"status":"terminé","urls":[w["url"] for w in works]},ensure_ascii=False))]
            return [types.TextContent(type="text", text=json.dumps({"status":status,"message":"Encore en cours..."},ensure_ascii=False))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Erreur: {str(e)}")]

async def main():
    async with stdio_server() as (r,w):
        await app.run(r, w, app.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
