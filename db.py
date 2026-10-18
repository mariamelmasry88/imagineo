import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
import zipfile
from PIL import Image

root = os.environ.get("datadir", "data")
dbpath = root + "/app.db"
rounds = 600000
week = 60 * 60 * 24 * 7
os.makedirs(root + "/boards", exist_ok=True)


def connect():
    con = sqlite3.connect(dbpath, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    return con


def read(sql, args=()):
    con = connect()
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def write(sql, args=()):
    con = connect()
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def setup():
    con = connect()
    con.executescript(
        """
        create table if not exists users (
            id integer primary key autoincrement,
            name text unique not null,
            email text unique not null,
            salt blob not null,
            hash blob not null,
            created real not null
        );
        create table if not exists sessions (
            token text primary key,
            userid integer not null references users(id) on delete cascade,
            expires real not null
        );
        create table if not exists boards (
            id integer primary key autoincrement,
            userid integer not null references users(id) on delete cascade,
            idea text not null,
            story text not null,
            character text not null,
            scenes text not null,
            style text not null,
            level text not null,
            created real not null
        );
        create index if not exists boardsuser on boards(userid);
        """
    )
    con.commit()
    con.close()


# ---------- accounts ----------

def hashpw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, rounds)


def signup(name, email, pw):
    name = name.strip().lower()
    email = email.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,20}", name):
        return False, "username must be 3-20 letters, numbers or underscore"
    if len(email) > 100 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return False, "please enter a valid email"
    if len(pw) < 8 or len(pw) > 100:
        return False, "password must be 8-100 characters"
    salt = os.urandom(16)
    try:
        write(
            "insert into users (name, email, salt, hash, created) values (?, ?, ?, ?, ?)",
            (name, email, salt, hashpw(pw, salt), time.time()),
        )
    except sqlite3.IntegrityError:
        return False, "that username or email is already used"
    return True, "account created"


def login(name, pw):
    rows = read("select * from users where name = ?", (name.strip().lower(),))
    if not rows:
        hashpw(pw, b"0" * 16)  # same work for unknown names, so timing tells nothing
        return None
    row = rows[0]
    if hmac.compare_digest(hashpw(pw, row["salt"]), row["hash"]):
        return {"id": row["id"], "name": row["name"]}
    return None


def digest(token):
    # only the hash of the token is stored, like a password
    return hashlib.sha256(token.encode()).hexdigest()


def newsession(userid):
    write("delete from sessions where expires < ?", (time.time(),))
    token = secrets.token_urlsafe(32)
    write(
        "insert into sessions (token, userid, expires) values (?, ?, ?)",
        (digest(token), userid, time.time() + week),
    )
    return token


def usersession(token):
    if not token:
        return None
    rows = read(
        "select users.id, users.name from sessions join users on users.id = sessions.userid"
        " where sessions.token = ? and sessions.expires > ?",
        (digest(token), time.time()),
    )
    return dict(rows[0]) if rows else None


def endsession(token):
    write("delete from sessions where token = ?", (digest(token),))


# ---------- storyboards ----------

def savedboard(userid, idea, story, data, style, level, pics):
    boardid = write(
        "insert into boards (userid, idea, story, character, scenes, style, level, created)"
        " values (?, ?, ?, ?, ?, ?, ?, ?)",
        (userid, idea, story, data["character"], json.dumps(data["scenes"]), style, level, time.time()),
    )
    folder = f"{root}/boards/{boardid}"
    os.makedirs(folder, exist_ok=True)
    for i, p in enumerate(pics):
        p.convert("RGB").save(f"{folder}/{i + 1}.jpg", quality=92)
    cover = pics[0].convert("RGB")
    cover.thumbnail((360, 360))
    cover.save(f"{folder}/cover.jpg", quality=85)
    return boardid


def listboards(userid):
    rows = read(
        "select id, idea, style, scenes, created from boards where userid = ? order by id desc",
        (userid,),
    )
    return [
        {
            "id": r["id"],
            "idea": r["idea"],
            "style": r["style"],
            "created": r["created"],
            "count": len(json.loads(r["scenes"])),
        }
        for r in rows
    ]


def getboard(boardid, userid):
    # the userid check makes sure nobody can open another person's board
    rows = read("select * from boards where id = ? and userid = ?", (boardid, userid))
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r["id"],
        "idea": r["idea"],
        "story": r["story"],
        "character": r["character"],
        "scenes": json.loads(r["scenes"]),
        "style": r["style"],
        "level": r["level"],
        "created": r["created"],
    }


def imagepath(boardid, userid, name):
    if getboard(boardid, userid) is None:
        return None
    path = f"{root}/boards/{boardid}/{name}.jpg"
    return path if os.path.exists(path) else None


def zipboard(boardid, userid):
    board = getboard(boardid, userid)
    if board is None:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("story.txt", board["idea"] + "\n\n" + board["story"] + "\n")
        for i in range(len(board["scenes"])):
            path = f"{root}/boards/{boardid}/{i + 1}.jpg"
            if os.path.exists(path):
                z.write(path, f"scene{i + 1}.jpg")
    return buf.getvalue()


def deleteboard(boardid, userid):
    if getboard(boardid, userid) is None:
        return False
    write("delete from boards where id = ? and userid = ?", (boardid, userid))
    shutil.rmtree(f"{root}/boards/{boardid}", ignore_errors=True)
    return True
