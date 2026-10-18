# Imagineo

Imagineo is a small web site that turns one sentence into a short story with a picture for every scene. You type an idea like "a lost robot finds a garden", pick an art style and a reading level, and a few minutes later you get a story written in simple words, split into scenes, with one illustration per scene.

I built it as my final project in the internship. The idea came from teachers who need easy reading material with pictures, for example for students who find reading hard. Writing a simple story, simplifying the words and finding a picture for each part takes a lot of time, so I wanted to see if two AI models could do most of that work together. It is a learning project. I have not tested it with real students, so I make no claims about how well it works for them.

## What it does

You create an account, log in, and write your idea. You choose one of six art styles (storybook, cartoon, anime, watercolor, comic, cinematic), one of two reading levels (easy is about 100 words with very short sentences, medium is about 150 words), and between 3 and 6 scenes. Imagineo writes the story, splits it into scenes, draws a picture for each one, and saves everything in your account. Later you can open it again, print it, download it as a zip, or delete it.

There is also an "easy-to-read text" switch at the top of the page. It makes the letters bigger, adds more space between letters and words, and uses a friendlier font.

## How it works

Everything is a chain of steps where the output of one step becomes the input of the next:

1. The language model writes a short children's story from the idea and the chosen reading level.
2. The same model reads that story and answers with JSON only: a short description of the main character, and a list of scenes, each with the text of the scene and a description of the picture.
3. The code finds the JSON in the answer, checks that it has the right shape, and asks again (up to 3 times) if it does not.
4. The image model draws one picture per scene. The prompt is the character description, plus the scene description, plus the art style. I use the same seed for every scene to help the main character look similar from picture to picture.
5. The story, the scenes and the pictures are saved in a SQLite database and in jpg files, and the website shows them.

For the story and the scenes I use Mistral-Nemo-Instruct-2407, loaded in 4-bit so it fits on a free Kaggle T4 GPU next to the image model. For the pictures I use Stable Diffusion XL in fp16 with a fixed VAE (so the pictures do not come out black) and CPU offload (only the part that is working sits on the GPU). 

## What I used from the internship

The project builds on the notebooks we got during the internship. I used the same language model (Mistral-Nemo), the LangChain PromptTemplate for the prompts, the idea of chaining steps one after another, the idea of asking the model for structured JSON and parsing it, 4-bit quantization, and the FastAPI plus ngrok pattern for sharing a model running on Kaggle.

I did not copy those notebooks as they were. In the notebooks the chain is made with LLMChain, and here I wrote the chain as normal Python functions so I could show progress and handle errors between the steps. The notebooks use StructuredOutputParser and a regex for json fences, and here I wrote my own small parser with a check and retries. The generate function in the notebooks sends the raw prompt and returns the prompt together with the answer, and mine uses the model's chat template and returns only the new text. The 4-bit setup is simpler than the one in the fine-tuning notebook, and I use float16 because the T4 has no native bfloat16. The sampling values (top_p 0.95, temperature 0.7) come from the notebooks.

Everything else (the image generation, the database, the login system, the job queue and the whole website) I added myself.

## The files

The Python files are in the main folder and the website is in a folder called web.

```
imagineo/
  server.py
  engine.py
  db.py
  story.py
  scenes.py
  images.py
  options.py
  check.py
  notebook.ipynb
  .gitignore
  web/
    index.html
    style.css
    app.js
    config.js
```

story.py loads the language model in 4-bit and has one function, ask(), that every language model step uses. It puts the prompt in the chat format, generates the answer with temperature and top_p sampling, and returns only the new text.

scenes.py has the two prompts and the two language model steps. writestory() turns the idea into a story. getscenes() turns the story into the character description and the scenes. The same file has findjson(), which takes the JSON out of the answer, and checkscenes(), which makes sure every scene has text and an image description. getscenes() uses a low temperature and tries up to 3 times.

images.py loads Stable Diffusion XL and has drawscene(), which builds the prompt and draws one picture. The model name, the picture size and the number of steps can be changed with environment variables.

options.py keeps all the choices in one place: the six art style prompts, the two reading levels, the minimum and maximum number of scenes, and the negative prompt that tells the image model to avoid bad faces, text, watermarks and unsafe content. The server, the models and the website all read from it, so they always agree.

engine.py runs the jobs. When the server starts, a background thread loads the models once, then takes jobs from a queue one at a time, because there is only one GPU. It writes down what step it is on ("drawing picture 2 of 4") so the page can show it. It also checks the rules: the models must be ready, a user can only have one job at a time, and no more than 10 jobs can wait. This file also has a fake mode (see below) that makes colored placeholder pictures instead of using the models.

db.py is everything about accounts and storage, using SQLite. It has three tables: users, sessions and boards. Passwords are hashed with PBKDF2 and a random salt, session tokens are stored only as hashes, and sessions last 7 days. It also saves the pictures, makes a small cover image for each storyboard, builds the zip file and deletes storyboards. Every function that reads a storyboard checks the user id, so nobody can open another person's storyboard.

server.py is the FastAPI app that connects everything. It checks what the website sends (for example the idea must be between 3 and 300 characters), limits wrong login attempts to 5 per 10 minutes, checks the login token on every private request, and has all the endpoints. At the end it serves the web folder as the website.

web/index.html is the structure of the page: the login and signup forms, the form where you write the idea, the progress card, the list of saved storyboards and the page that shows one storyboard.

web/style.css is the dark theme and the layout, the easy-to-read mode, a layout for phones, and the print styles that print only the storyboard in black on white.

web/app.js is all the behavior of the page, written in plain JavaScript. It talks to the API with the login token, handles login and signup, builds the style and level choices from the server, sends the generate request and then asks the server for progress every 2 seconds, and shows the finished storyboard, the saved list, the zip download and the delete button. All text is put on the page with textContent and never with innerHTML, so nothing a user types or the model writes can run as code.

web/config.js is a leftover from when the website was a separate site from the server. Now the Python server serves the page itself, so it is not needed anymore.

check.py is a quick test without the website. It runs the whole chain from the command line for one idea and saves three pictures (check1.jpg, check2.jpg, check3.jpg), which is useful to look at the faces before starting the server.

notebook.ipynb is the Kaggle notebook that runs the project. It installs the packages, clones this repo, logs in to Hugging Face, optionally runs check.py, starts the server and ngrok to give a public link, shows the server log, and at the end zips the data folder so accounts and storyboards are not lost.

.gitignore keeps local files out of git. The data folder holds the accounts and pictures, so it should never be pushed.

## Running it on Kaggle

You need a Kaggle account, a Hugging Face account with a token, and a free ngrok authtoken.

1. Push this repo to GitHub.
2. Make a Kaggle notebook from notebook.ipynb.
3. In the settings choose the GPU T4 accelerator and turn the internet on.
4. Add two secrets to the notebook: hf (your Hugging Face token) and ngrok (your ngrok authtoken).
5. Accept the terms of mistralai/Mistral-Nemo-Instruct-2407 on Hugging Face.
6. Put your own repo link in the repo line of the clone cell.
7. Run the cells one at a time. The server cell prints a public link. Open it, and a banner on the page tells you when the models have finished loading, which takes a few minutes.
8. Before you stop the session, run the last cell. Kaggle deletes everything when the session ends, and that cell saves the accounts and storyboards in data.zip so you can download it.

## Trying it without a GPU

Fake mode skips the models and makes placeholder pictures, so you can test the website, the accounts and the database on a normal laptop.

```
pip install fastapi "uvicorn[standard]" pillow
fake=1 python -m uvicorn server:app --port 8000
```

On Windows PowerShell, run `$env:fake="1"` first and then the uvicorn command. Then open http://localhost:8000.

These environment variables change the settings: fake (set to 1 for fake mode), datadir (where the database and pictures are saved, default data), imgmodel (the image model), imgsize (default 1024), imgsteps (default 28) and origins (allowed websites for the API, default all).

## The API

These are the endpoints. All of them except status, options, signup and login need the login token in an Authorization: Bearer header.

```
GET    /api/status
GET    /api/options
POST   /api/signup
POST   /api/login
POST   /api/logout
GET    /api/me
POST   /api/generate
GET    /api/jobs/{id}
GET    /api/boards
GET    /api/boards/{id}
GET    /api/boards/{id}/image/{n}
GET    /api/boards/{id}/cover
GET    /api/boards/{id}/zip
DELETE /api/boards/{id}
```

## Known problems

The faces are not guaranteed to match between scenes. Using the same character description and the same seed helps, but Stable Diffusion does not really remember a character.

The language model can make mistakes. Sometimes it gives broken JSON (the retries handle most of that), and the story may not be exactly at the reading level you chose, so a teacher should always read the story before using it.

There is one GPU, so only one storyboard is made at a time and the others wait in the queue. The queue and the login attempt limits are kept in memory, so they reset when the server restarts. Kaggle sessions are temporary, so download data.zip before the session ends. The safety filtering is basic: the story prompt asks for child-friendly content and the image negative prompt blocks unsafe results, but there is no separate moderation model.

## Ideas for the future

I would like to fine-tune the story model with LoRA on simple children's stories to control the reading level better, and use RAG over a school word list so the stories reuse the words students are learning. A readability score next to each story would help too, together with better character consistency (for example with IP-Adapter), PDF export, editing a scene's text or redrawing a single picture, and moving from Kaggle and ngrok to a permanent host.

## Built with

Kaggle, ngrok, Python, FastAPI, SQLite, PyTorch, Hugging Face Transformers, bitsandbytes, Diffusers, LangChain (core), plain HTML, CSS and JavaScript


## Author

Made by Mariam Ashraf as an internship project. Thank you to Tips Hindawi for the guidance.
