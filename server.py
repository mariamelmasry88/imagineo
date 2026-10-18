import os
import time
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import db
import engine
import options

here = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app):
    db.setup()
    engine.start()
    yield


app = FastAPI(title="Imagineo", lifespan=lifespan)
# the login uses a token header, not cookies, so any website may call the api.

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("origins", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class signupbody(BaseModel):
    name: str = Field(max_length=40)
    email: str = Field(max_length=120)
    password: str = Field(max_length=100)


class loginbody(BaseModel):
    name: str = Field(max_length=40)
    password: str = Field(max_length=100)


class makebody(BaseModel):
    idea: str = Field(min_length=3, max_length=300)
    count: int = Field(ge=options.mincount, le=options.maxcount)
    style: str
    level: str
    seed: int = Field(ge=0, le=99999)


# ---------- login helpers ----------

tries = {}


def blocked(name):
    now = time.time()
    recent = [t for t in tries.get(name, []) if now - t < 600]
    tries[name] = recent
    return len(recent) >= 5


def failed(name):
    tries.setdefault(name, []).append(time.time())


def gettoken(authorization: str = Header(default="")):
    return authorization.removeprefix("Bearer ").strip()


def needuser(token: str = Depends(gettoken)):
    user = db.usersession(token)
    if user is None:
        raise HTTPException(status_code=401, detail="please log in")
    return user


# ---------- open endpoints ----------

@app.get("/api/status")
def status():
    return {
        "ready": engine.state["ready"],
        "note": engine.state["note"],
        "error": engine.state["error"],
        "waiting": engine.waitingcount(),
    }


@app.get("/api/options")
def getoptions():
    return {
        "styles": list(options.styles.keys()),
        "levels": list(options.levels.keys()),
        "mincount": options.mincount,
        "maxcount": options.maxcount,
    }


@app.post("/api/signup")
def signup(body: signupbody):
    ok, msg = db.signup(body.name, body.email, body.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True}


@app.post("/api/login")
def login(body: loginbody):
    name = body.name.strip().lower()
    if blocked(name):
        raise HTTPException(status_code=429, detail="too many wrong tries, wait a few minutes")
    user = db.login(name, body.password)
    if user is None:
        failed(name)
        raise HTTPException(status_code=401, detail="wrong username or password")
    tries.pop(name, None)
    return {"token": db.newsession(user["id"]), "name": user["name"]}


# ---------- endpoints that need a login ----------

@app.get("/api/me")
def me(user=Depends(needuser)):
    return {"name": user["name"]}


@app.post("/api/logout")
def logout(token: str = Depends(gettoken), user=Depends(needuser)):
    db.endsession(token)
    return {"ok": True}


@app.post("/api/generate")
def generate(body: makebody, user=Depends(needuser)):
    if body.style not in options.styles or body.level not in options.levels:
        raise HTTPException(status_code=400, detail="unknown style or reading level")
    try:
        jobid = engine.addjob(
            user["id"], body.idea.strip(), body.count, body.style, body.level, body.seed
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"id": jobid}


@app.get("/api/jobs/{jobid}")
def getjob(jobid: str, user=Depends(needuser)):
    view = engine.jobview(jobid, user["id"])
    if view is None:
        raise HTTPException(status_code=404, detail="job not found")
    return view


@app.get("/api/boards")
def boards(user=Depends(needuser)):
    return db.listboards(user["id"])


@app.get("/api/boards/{boardid}")
def getboard(boardid: int, user=Depends(needuser)):
    board = db.getboard(boardid, user["id"])
    if board is None:
        raise HTTPException(status_code=404, detail="storyboard not found")
    return board


@app.get("/api/boards/{boardid}/image/{n}")
def image(boardid: int, n: int, user=Depends(needuser)):
    path = db.imagepath(boardid, user["id"], n)
    if path is None:
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/boards/{boardid}/cover")
def cover(boardid: int, user=Depends(needuser)):
    path = db.imagepath(boardid, user["id"], "cover")
    if path is None:
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/boards/{boardid}/zip")
def download(boardid: int, user=Depends(needuser)):
    data = db.zipboard(boardid, user["id"])
    if data is None:
        raise HTTPException(status_code=404, detail="storyboard not found")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="storyboard{boardid}.zip"'},
    )


@app.delete("/api/boards/{boardid}")
def remove(boardid: int, user=Depends(needuser)):
    if not db.deleteboard(boardid, user["id"]):
        raise HTTPException(status_code=404, detail="storyboard not found")
    return {"ok": True}


# the website itself, served from the web folder (must come last)
app.mount("/", StaticFiles(directory=os.path.join(here, "web"), html=True), name="web")
