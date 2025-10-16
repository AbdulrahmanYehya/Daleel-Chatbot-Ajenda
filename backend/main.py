\
    from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    import os, json, tempfile, shutil, uuid, datetime, re, requests
    from pathlib import Path
    from dotenv import load_dotenv
    import arabic_reshaper
    from bidi.algorithm import get_display

    load_dotenv()
    PROJECT_ROOT = Path(__file__).parent
    DATA_DIR = PROJECT_ROOT / "data"
    NOTES_DIR = DATA_DIR / "notes"
    TASKS_FILE = DATA_DIR / "tasks.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if not TASKS_FILE.exists():
        TASKS_FILE.write_text("[]", encoding="utf-8")

    app = FastAPI(title="Ajenda Assistant - Daleel")
    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

    OLLAMA_API = os.getenv("OLLAMA_API", "http://localhost:11434/api/generate")
    MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:4b")
    API_KEY = os.getenv("API_KEY", "change_me")

    class ChatReq(BaseModel):
        user_id: str = Field(...)
        text: str = Field(...)

    def verify_api_key(x_api_key: str = Header(None)):
        if x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    def call_ollama(prompt: str, max_tokens: int = 800):
        body = {"model": MODEL, "prompt": prompt, "max_tokens": max_tokens}
        r = requests.post(OLLAMA_API, json=body, timeout=120)
        r.raise_for_status()
        try:
            j = r.json()
            return j.get("output") or j.get("response") or j.get("text") or json.dumps(j)
        except Exception:
            return r.text

    def extract_json_from_text(text: str):
        s = text.find("{")
        if s == -1:
            s = text.find("[")
        if s == -1:
            return None
        try:
            return json.loads(text[s:])
        except Exception:
            cleaned = re.sub(r"[\r\n]+$", "", text[s:])
            try:
                return json.loads(cleaned)
            except Exception:
                return None

    def is_arabic(s):
        return any('\u0600' <= ch <= '\u06FF' for ch in s)

    def save_task(payload: dict, user_id: str):
        tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        task = {
            "id": str(uuid.uuid4()),
            "title": payload.get("title","Untitled"),
            "description": payload.get("description",""),
            "due": payload.get("due",None),
            "priority": payload.get("priority","normal"),
            "created_by": user_id,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        tasks.append(task)
        TASKS_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        return task

    def save_note_as_pdf(title: str, content: str):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        filename = f"{uuid.uuid4()}.pdf"
        path = NOTES_DIR / filename
        c = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4
        margin = 40
        y = height - margin
        lines = content.split("\n")
        for line in lines:
            if is_arabic(line):
                reshaped = arabic_reshaper.reshape(line)
                bidi_text = get_display(reshaped)
                c.drawRightString(width - margin, y, bidi_text)
            else:
                c.drawString(margin, y, line)
            y -= 14
            if y < margin:
                c.showPage()
                y = height - margin
        c.save()
        return str(path)

    @app.post("/chat", dependencies=[Depends(verify_api_key)])
    def chat(req: ChatReq):
        system = (
            "You are Ajenda assistant (Daleel). When the user requests an action (create_task, create_note, research, summarize, translate), "
            "output ONLY valid JSON with keys: action and payload. Respond in the user's language. Examples:\\n\\n"
            "EN Example:\\nUser: Create a task: Assignment due today at 9 PM\\nAssistant:\\n"
            "{\"action\":\"create_task\",\"payload\":{\"title\":\"Assignment\",\"description\":\"\",\"due\":\"today 9 PM\",\"priority\":\"normal\"}}\\n\\n"
            "AR Example:\\nUser: انشئ مهمة \\\"تسليم الواجب\\\" اليوم الساعة 9 مساءً\\nAssistant:\\n"
            "{\"action\":\"create_task\",\"payload\":{\"title\":\"تسليم الواجب\",\"description\":\"\",\"due\":\"اليوم 9 مساءً\",\"priority\":\"normal\"}}\\n\\n"
            "If the user requests a normal assistant reply, return a plain text reply (not JSON)."
        )
        prompt = system + "\nUser: " + req.text
        resp = call_ollama(prompt)
        parsed = extract_json_from_text(resp if isinstance(resp, str) else json.dumps(resp))
        if not parsed:
            return {"reply": resp}
        action = parsed.get("action")
        payload = parsed.get("payload", {})
        if action == "create_task":
            task = save_task(payload, req.user_id)
            return {"status":"task_created", "task": task}
        if action == "create_note":
            title = payload.get("title","Note")
            content = payload.get("content","")
            pdf_path = save_note_as_pdf(title, content)
            return {"status":"note_created", "file": pdf_path}
        if action == "research":
            if not payload.get("content"):
                research_prompt = f\"Write a detailed research article (about 800-1200 words) titled: {payload.get('title','Research')}. Language: same as user.\"
                content = call_ollama(research_prompt, max_tokens=1500)
            else:
                content = payload.get("content")
            pdf = save_note_as_pdf(payload.get("title","Research"), content)
            return {"status":"research_saved", "file": pdf}
        if action == "summarize":
            source = payload.get("text") or payload.get("url") or ""
            summ_prompt = f\"Summarize the following content in a concise form. Language: same as user. Content:\\n{source}\"
            summary = call_ollama(summ_prompt, max_tokens=500)
            return {"status":"summary","summary": summary}
        if action == "translate":
            text = payload.get("text","")
            target = payload.get("target","ar")
            trans_prompt = f\"Translate the following text to {target}.\\nText:\\n{text}\"
            translation = call_ollama(trans_prompt, max_tokens=500)
            return {"status":"translation","translation": translation}
        return {"reply": resp}

    @app.post("/upload_image", dependencies=[Depends(verify_api_key)])
    async def upload_image(file: UploadFile = File(...)):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, file.filename)
        with open(path, "wb") as f:
            f.write(await file.read())
        try:
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(path), lang="ara+eng")
        except Exception as e:
            shutil.rmtree(tmp)
            raise HTTPException(status_code=500, detail=f"OCR error: {e}")
        shutil.rmtree(tmp)
        return {"text": text}

    @app.post("/upload_audio", dependencies=[Depends(verify_api_key)])
    async def upload_audio(file: UploadFile = File(...)):
        ASR_API_URL = os.getenv("ASR_API_URL")
        ASR_API_KEY = os.getenv("ASR_API_KEY")
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, file.filename)
        with open(path, "wb") as f:
            f.write(await file.read())
        if ASR_API_URL and ASR_API_KEY:
            headers = {"Authorization": f"Bearer {ASR_API_KEY}"}
            files = {"file": open(path, "rb")}
            try:
                r = requests.post(ASR_API_URL, headers=headers, files=files, timeout=120)
                r.raise_for_status()
                res = r.json()
                text = res.get("text") or res.get("transcript") or ""
            except Exception as e:
                shutil.rmtree(tmp)
                raise HTTPException(status_code=500, detail=f"ASR error: {e}")
        else:
            try:
                import whisper
                model = whisper.load_model("small")
                res = model.transcribe(path, language="auto")
                text = res.get("text","")
            except Exception as e:
                shutil.rmtree(tmp)
                raise HTTPException(status_code=500, detail=f"Local ASR error: {e}")
        shutil.rmtree(tmp)
        return {"transcript": text}
