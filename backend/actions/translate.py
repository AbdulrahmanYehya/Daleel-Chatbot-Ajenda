def translate_text(model_call, text, target='ar'):
    prompt = f"Translate the following text to {target}.\nText:\n{text}"
    return model_call(prompt, max_tokens=500)
