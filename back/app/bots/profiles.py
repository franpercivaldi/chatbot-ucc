import os, yaml

_DEFAULT = {
    "default_bot_id": "public-admisiones",
    "bots": {
        "public-admisiones": {
            "label": "Chat Admisiones (Público)",
            # Incluimos "perfiles" para habilitar la info ingresada vía JSON (datos_generales_carreras.json)
            "allowed_domains": ["general","oferta","carreras","aranceles","becas","fechas","reglamentos","faq","perfiles","palabras_clave","link_inscripcion","datos_especiales"],
            "contact": {"email": "", "phone": "", "hours": ""},
            "system_instruction": None,
        }
    }
}

def _profiles_path() -> str:
    env_path = os.environ.get("BOT_PROFILES_PATH")
    if env_path:
        return env_path

    # Prefer .yaml, pero si solo existe .yml (como en este repo), úsalo.
    yaml_path = "/app/config/bot_profiles.yaml"
    yml_path = "/app/config/bot_profiles.yml"
    if os.path.isfile(yaml_path):
        return yaml_path
    if os.path.isfile(yml_path):
        return yml_path
    return yaml_path

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
