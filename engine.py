import os
import queue
import threading
import time
import traceback
import uuid
import db

# fake=1 skips the models and makes placeholder pictures,so you can try the website on any laptop without a gpu
fake = os.environ.get("fake") == "1"

state = {"ready": False, "note": "starting", "error": ""}
jobs = {}
todo = queue.Queue()
lock = threading.Lock()
maxwaiting = 10


def start():
    threading.Thread(target=run, daemon=True).start()


def run():
    try:
        if fake:
            tok = model = pipe = None
            state["note"] = "fake mode, no models"
        else:
            from story import loadllm
            from images import loadimager

            state["note"] = "loading the story model"
            tok, model = loadllm()
            state["note"] = "loading the image model"
            pipe = loadimager()
        state["ready"] = True
        state["note"] = "ready"
    except Exception:
        traceback.print_exc()
        state["error"] = "the models could not be loaded, check server.log"
        state["note"] = "failed"
        return
    while True:
        job = todo.get()
        dojob(job, tok, model, pipe)


def step(job, text):
    job["step"] = text


def friendly(e):
    if "out of memory" in str(e).lower():
        return "the gpu ran out of memory, try fewer scenes"
    return "something went wrong while making the storyboard, please try again"


def dojob(job, tok, model, pipe):
    job["status"] = "working"
    try:
        if fake:
            story, data, pics = fakemake(job)
        else:
            story, data, pics = realmake(job, tok, model, pipe)
        job["boardid"] = db.savedboard(
            job["userid"], job["idea"], story, data, job["style"], job["level"], pics
        )
        job["step"] = "done"
        job["status"] = "done"
    except Exception as e:
        traceback.print_exc()
        job["error"] = friendly(e)
        job["status"] = "failed"


def realmake(job, tok, model, pipe):
    import torch
    from scenes import writestory, getscenes
    from images import drawscene

    step(job, "writing the story")
    story = writestory(tok, model, job["idea"], job["level"])
    step(job, "splitting it into scenes")
    data = getscenes(tok, model, story, job["count"])
    pics = []
    total = len(data["scenes"])
    for i, scene in enumerate(data["scenes"]):
        step(job, f"drawing picture {i + 1} of {total}")
        pics.append(drawscene(pipe, data["character"], scene, job["style"], job["seed"]))
    torch.cuda.empty_cache()
    return story, data, pics


def fakemake(job):
    from PIL import Image, ImageDraw

    step(job, "writing the story")
    time.sleep(1)
    step(job, "splitting it into scenes")
    time.sleep(1)
    scenes = []
    pics = []
    colors = ["#6d28d9", "#be185d", "#0f766e", "#b45309", "#1d4ed8", "#4d7c0f"]
    for i in range(job["count"]):
        step(job, f"drawing picture {i + 1} of {job['count']}")
        time.sleep(1)
        scenes.append(
            {"text": f"This is scene {i + 1} of the fake story about {job['idea']}.", "image": "fake"}
        )
        img = Image.new("RGB", (512, 512), colors[i % len(colors)])
        ImageDraw.Draw(img).text((200, 250), f"scene {i + 1}", fill="white")
        pics.append(img)
    story = f"This is a fake story about {job['idea']}. " + " ".join(s["text"] for s in scenes)
    return story, {"character": "a fake hero", "scenes": scenes}, pics


def addjob(userid, idea, count, style, level, seed):
    with lock:
        if not state["ready"]:
            raise ValueError("the server is still loading the models, please wait")
        waiting = [j for j in jobs.values() if j["status"] in ("queued", "working")]
        if any(j["userid"] == userid for j in waiting):
            raise ValueError("you already have a storyboard in progress")
        if len(waiting) >= maxwaiting:
            raise ValueError("the server is busy, please try again in a few minutes")
        job = {
            "id": uuid.uuid4().hex,
            "userid": userid,
            "idea": idea,
            "count": count,
            "style": style,
            "level": level,
            "seed": seed,
            "status": "queued",
            "step": "waiting for your turn",
            "boardid": None,
            "error": "",
            "created": time.time(),
        }
        jobs[job["id"]] = job
        # keep the list small
        old = sorted(jobs.values(), key=lambda j: j["created"])[:-100]
        for j in old:
            if j["status"] in ("done", "failed"):
                jobs.pop(j["id"], None)
        todo.put(job)
        return job["id"]


def jobview(jobid, userid):
    job = jobs.get(jobid)
    if job is None or job["userid"] != userid:
        return None
    ahead = 0
    if job["status"] == "queued":
        ahead = len(
            [
                j
                for j in jobs.values()
                if j["status"] in ("queued", "working") and j["created"] < job["created"]
            ]
        )
    return {
        "status": job["status"],
        "step": job["step"],
        "boardid": job["boardid"],
        "error": job["error"],
        "ahead": ahead,
    }


def waitingcount():
    return len([j for j in jobs.values() if j["status"] in ("queued", "working")])
