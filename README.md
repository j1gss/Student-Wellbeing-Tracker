# Student Wellbeing Companion

A cozy check-in app: students log mood, pressure, sleep, study, water and movement.
A FastAPI backend stores entries (SQLite), estimates capacity with a random forest,
and returns gentle suggestions with the reason for each.

    frontend/index.html    the UI (single file, no build step)
    backend/main.py        API + model + serves the frontend

## Run it
    cd backend
    python -m venv .venv
    # Windows: .venv\Scripts\activate     Mac/Linux: source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
Open http://localhost:8000  (API docs: http://localhost:8000/docs)

## API
GET /api/history · POST /api/checkin · GET /api/insights · DELETE /api/data

## Working as a team
- Clone: `git clone <repo-url>`, then follow "Run it".
- Never commit the .db file; each person gets their own demo data on first run.
- One branch per feature (`git checkout -b feature/insights`), open a pull request, get one review, then merge to main.
- Pull before you start work: `git pull`.

## Honest limitations
The model is trained on synthetic data from a formula, so it is a prototype of the pipeline,
not a validated predictor. This is a self-reflection tool, not a diagnosis.
Support: university counsellor; Tele-MANAS 14416 (verify before use).

## If the page can't reach the server
The line under the greeting says whether it's connected. Check http://localhost:8000/api/health opens
(if not, the server isn't running), and that the `frontend` folder sits next to or above `main.py`.

## Share it with teammates
1. Same Wi-Fi, right now: run `uvicorn main:app --host 0.0.0.0 --port 8000`, find your IP
   (`ipconfig` / `ifconfig`), and they open `http://<your-ip>:8000`. Allow it through the firewall if asked.
2. Temporary public link: `cloudflared tunnel --url http://localhost:8000` (or ngrok).
3. Always-on link (free): push to GitHub, then on render.com create a Web Service from the repo:
   Root Directory `backend`, Build `pip install -r requirements.txt`,
   Start `uvicorn main:app --host 0.0.0.0 --port $PORT`.
   Free plans sleep when idle and reset the SQLite file on redeploy, so demo data comes back each time.
Deployed, everyone shares one database (no accounts) and "Delete all my data" wipes it for all.
Use made-up entries in the shared demo.

## Accounts and privacy
Each person registers a username and password (hashed with PBKDF2) and only ever reads their own check-ins.
A shared `demo` / `demo1234` account holds sample data: change or delete it before any public launch.
The burn-paper box never sends or stores anything.

## Free permanent link without GitHub (Hugging Face Spaces)
1. Make a free account at huggingface.co, then New Space: SDK **Docker**, hardware CPU basic.
2. Files tab, Add file, Upload files: drag in everything inside the project folder (Dockerfile, README.md, backend, frontend).
3. It builds for a few minutes, then `https://huggingface.co/spaces/<you>/<space>` is your link; the app also lives at `https://<you>-<space>.hf.space`.
Free Spaces sleep when idle and forget the database when they restart.
