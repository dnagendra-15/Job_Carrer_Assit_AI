
import os
MODEL_CONFIG = {


    # GEMINI: Reads the long Job Description text
    "jd_parser": {
        "provider": "google",
        "model": "gemini-3.1-flash-lite",
        "temperature": 0.1
    },
    
    # OPENAI: Analyzes the heavy resume text and guarantees perfect JSON output
    "gap_analyzer": {
        "provider": "google",
        "model": "gemini-3.5-flash",
        "temperature": 0.2
    },
    
    # GROQ: Generates the chat questions blazing fast (Llama 3.1 8B)
    "question_generator": {
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
        "temperature": 0.4
    },
    
    # GROQ: Does the heavy, professional writing (Llama 3.3 70B)
    "resume_writer": {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3
    },
    
    "cover_letter_writer": {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.5
    },
    
    # OPENAI: Evaluates the final result and returns a safe JSON score
    "fit_scorer": {
        "provider": "google",
        "model": "gemini-3.5-flash",
        "temperature": 0.1
    }
}

def get_llm(node_name: str):
    cfg = MODEL_CONFIG.get(node_name, MODEL_CONFIG["gap_analyzer"])
    provider = cfg["provider"]
    model = cfg["model"]
    temp = cfg.get("temperature", 0.3)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=temp,
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, api_key=os.getenv("GROQ_API_KEY"), temperature=temp)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=os.getenv("OPENAI_API_KEY"), temperature=temp)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=os.getenv("ANTHROPIC_API_KEY"), temperature=temp)
    else:
        raise ValueError(f"Unknown provider '{provider}'. Use: google, groq, openai, or anthropic")
