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
            r = requests.post(f"{BASE_URL}/v1/images/generations", headers=kh(), json={"model_name":"kling-v1","prompt":args["prompt"],"n":args.get("n",2),"aspect_ratio":args.get("aspect_ratio","1:1")})
            d = r.json()
            return {"error": d.get("message")} if d.get("code") != 0 else {"task_id": d["data"]["task_id"], "message": "Utilise check_task dans 30-60s.", "type": "image"}
        elif name == "generate_video":
            r = requests.post(f"{BASE_URL}/v1/videos/text2video", headers=kh(), json={"model_name":"kling-v1","prompt":args["prompt"],"duration":args.get("duration","5"),"aspect_ratio":args.get("aspect_ratio","9:16"),"mode":"std"})
            d = r.json()
            return {"error": d.get("message")} if d.get("code") != 0 else {"task_id": d["data"]["task_id"], "message": "Vidéo en cours (2-5 min). Utilise check_task.", "type": "video"}
        elif name == "check_task":
            ep = "/v1/images/generations" if args["type"]=="image" else "/v1/videos/text2video"
            r = requests.get(f"{BASE_URL}{ep}/{args['task_id']}", headers=kh())
            d = r.json(); td = d.get("data",{}); st = td.get("task_status","unknown")
            if st == "succeed":
                items = td.get("task_result",{}).get("images" if args["type"]=="image" else "videos",[])
                return {"status":"terminé","urls":[i.get("url") for i in items if i.get("url")]}
            elif st == "failed":
                return {"status":"échec","detail":td.get("task_status_msg","")}
            return {"status":st,"message":"Encore en cours, réessaie dans 30s."}
    except Exception as e:
        return {"error": str(e)}

@app.route("/.well-known/oauth-authorization-server")
def oauth_meta():
    b = request.host_url.rstrip("/")
    return jsonify({"issuer":b,"authorization_endpoint":f"{b}/authorize","token_endpoint":f"{b}/token","registration_endpoint":f"{b}/register","response_types_supported":["code"],"grant_types_supported":["authorization_code"],"code_challenge_methods_supported":["S256"]})

@app.route("/register", methods=["POST"])
def register():
    body = request.get_json(silent=True) or {}
    return jsonify({"client_id":"kling-client-001","client_secret":"kling-secret-001","client_id_issued_at":int(time.time()),"redirect_uris":body.get("redirect_uris",[]),"grant_types":["authorization_code"],"response_types":["code"],"token_endpoint_auth_method":"client_secret_post"}), 201

@app.route("/authorize")
def authorize():
    return redirect(f"{request.args.get('redirect_uri','')}&code=kling-ok&state={request.args.get('state','')}")

@app.route("/token", methods=["POST"])
def token():
    return jsonify({"access_token":"kling-static-token","token_type":"bearer","expires_in":86400})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status":"ok"})

@app.route("/sse", methods=["GET"])
def sse():
    def stream():
        yield f"event: endpoint\ndata: {json.dumps({'uri':'/messages'})}\n\n"
        while True:
            time.sleep(15); yield ": keepalive\n\n"
    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.route("/messages", methods=["POST"])
def messages():
    body = request.get_json(); method = body.get("method",""); rid = body.get("id")
    if method == "initialize":
        return jsonify({"jsonrpc":"2.0","id":rid,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"kling-ai","version":"1.0.0"}}})
    elif method == "tools/list":
        return jsonify({"jsonrpc":"2.0","id":rid,"result":{"tools":TOOLS}})
    elif method == "tools/call":
        p = body.get("params",{}); result = call_tool(p.get("name"), p.get("arguments",{}))
        return jsonify({"jsonrpc":"2.0","id":rid,"result":{"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False,indent=2)}]}})
    return jsonify({"jsonrpc":"2.0","id":rid,"result":{}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8000)))
