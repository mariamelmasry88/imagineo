import json
import re
from langchain_core.prompts import PromptTemplate
from story import ask
from options import levels

storyprompt = PromptTemplate.from_template(
    "Write a short story based on this idea: {idea}\n"
    "Length and wording: {size}\n"
    "The story must be friendly and suitable for children. "
    "Keep it simple, with a clear beginning, middle and end. "
    "Write only the story, no title."
)

sceneprompt = PromptTemplate.from_template(
    "Split the story below into {count} scenes.\n\n"
    "Story:\n{story}\n\n"
    "Reply ONLY with JSON in this exact shape, nothing before or after it:\n"
    '{{"character": "age, hair, clothes and face of the main character, in English, under 25 words",\n'
    ' "scenes": [{{"text": "1-2 short sentences of the story for this scene",\n'
    '              "image": "what is happening and where, in English, under 30 words, '
    'and say it is a medium shot or close-up so the face is clearly visible"}}]}}\n'
)


def writestory(tok, model, idea, level="easy"):
    prompt = storyprompt.format(idea=idea, size=levels[level])
    return ask(tok, model, prompt, maxtokens=400)


def findjson(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no json found")
    return m.group(0)


def checkscenes(data):
    # make sure i really got a list of dicts with text and image, not just a string
    if not isinstance(data.get("character"), str):
        raise ValueError("character is missing")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) == 0:
        raise ValueError("scenes is missing")
    for s in scenes:
        if not isinstance(s, dict) or not s.get("text") or not s.get("image"):
            raise ValueError("a scene is missing text or image")
    return data


def getscenes(tok, model, story, count=4, tries=3):
    prompt = sceneprompt.format(story=story, count=count)
    for i in range(tries):
        raw = ask(tok, model, prompt, maxtokens=800, temp=0.3)
        try:
            return checkscenes(json.loads(findjson(raw)))
        except Exception as e:
            print("try", i + 1, "failed:", e)
    raise RuntimeError("could not get valid scenes json")
