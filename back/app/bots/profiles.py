import os, yaml

_DEFAULT = {
    "default_bot_id": "public-admisiones",
    "bots": {
        "public-admisiones": {
            "label": "Chat Admisiones (Público)",
            "allowed_domains": ["general","oferta","carreras","aranceles","becas","fechas","reglamentos","faq"],
            "contact": {"email": "", "phone": "", "hours": ""},
            "system_instruction": None,
        }
    }
}

def _profiles_path() -> str:
    return os.environ.get("BOT_PROFILES_PATH", "/app/config/bot_profiles.yaml")

def load_profiles() -> dict:
    path = _profiles_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        # sane defaults
        if "bots" not in cfg or not isinstance(cfg["bots"], dict):
            return _DEFAULT
        if "default_bot_id" not in cfg:
            cfg["default_bot_id"] = list(cfg["bots"].keys())[0]
        return cfg
    except Exception:
        return _DEFAULT

def get_profile(bot_id: str | None) -> tuple[str, dict]:
    cfg = load_profiles()
    default_id = cfg.get("default_bot_id")
    bots = cfg.get("bots", {})
    bot_id = bot_id or default_id
    profile = bots.get(bot_id) or bots.get(default_id) or list(bots.values())[0]
    return bot_id, profile
