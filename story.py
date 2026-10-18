import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

modelname = "mistralai/Mistral-Nemo-Instruct-2407"


def loadllm():
    # 4-bit, same setup as the quantization notebook
    cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
    tok = AutoTokenizer.from_pretrained(modelname)
    model = AutoModelForCausalLM.from_pretrained(
        modelname, quantization_config=cfg, device_map="auto"
    )
    return tok, model


def ask(tok, model, prompt, maxtokens=600, temp=0.7):
    msgs = [{"role": "user", "content": prompt}]
    # return_dict gives the attention mask too, so there is no warning
    enc = tok.apply_chat_template(
        msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(model.device)
    out = model.generate(
        **enc,
        max_new_tokens=maxtokens,
        do_sample=True,
        temperature=temp,
        top_p=0.95,
        pad_token_id=tok.eos_token_id,
    )
    # keep only the new tokens, not the prompt
    return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
