
import ollama

def one_shot(system: str, context: str, prompt: str, model: str = "gemma3n:e4b", seed: int = None) -> str:
    """
    Generates structured prose using a local Ollama model.
    Combines a system directive, contextual setup, and user prompt.
    
    Args:
        system: System message/directive for the model
        context: Contextual information for the generation
        prompt: User prompt/request
        model: Ollama model name to use
        seed: Random seed for deterministic generation (optional)
    """

    print(f"system: {system}")
    print(f"context: {context}")
    print(f"prompt: {prompt}")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": context},
        {"role": "user", "content": prompt}
    ]
    
    # Build options dict with seed if provided
    options = {}
    if seed is not None:
        options["seed"] = seed
    
    try:
        response = ollama.chat(model=model, messages=messages, options=options)
        print(f"Response from model {model}: {response['message']['content']}")
        return response['message']['content']
    except Exception as e:
        print(f"Error during one_shot: {e}")
        return ""

