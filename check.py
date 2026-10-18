# quick test without the website just the idea and text amd image generation 
import sys
from story import loadllm
from scenes import writestory, getscenes
from images import loadimager, drawscene

idea = sys.argv[1] if len(sys.argv) > 1 else "a lost robot finds a garden"
tok, model = loadllm()
story = writestory(tok, model, idea, "easy")
print(story)
data = getscenes(tok, model, story, 3)
print(data)
pipe = loadimager()
for i, scene in enumerate(data["scenes"]):
    drawscene(pipe, data["character"], scene, "storybook", 42).save(f"check{i + 1}.jpg")
print("saved check1.jpg, check2.jpg, check3.jpg")
