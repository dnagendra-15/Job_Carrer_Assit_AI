import os

MODEL_CONFIG = {
    "jd_parser": {
        "provider": "google",
        "model": "gemini-2.5-flash",
        "temperature": 0.1
    },
    "gap_analyzer": {
        "provider": "google",
        "model": "gemini-2.5-pro",
        "temperature": 0.2
    },
    "question_generator": {
        "provider": "google",
        "model": "gemini-2.5-flash",
        "temperature": 0.4
    },
    "resume_writer": {
        "provider": "google",
        "model": "gemini-2.5-pro",
        "temperature": 0.3
    },
    "cover_letter_writer": {
        "provider": "google",
        "model": "gemini-2.5-pro",
        "temperature": 0.5
    },
    "fit_scorer": {
        "provider": "google",
        "model": "gemini-2.5-flash",
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
