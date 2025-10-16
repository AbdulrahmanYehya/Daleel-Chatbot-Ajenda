def summarize_text(model_call, text, lang='en'):
    prompt = f"Summarize the following text. Language: {lang}.\nText:\n{text}"
    return model_call(prompt, max_tokens=500)
