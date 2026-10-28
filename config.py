# config.py - single source of truth for every bot setting.
# Priority: Render/OS environment variable > env.txt / .env > default below.
import os  #linew os gives access to environment variables and file paths

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  #linew folder that holds this file, so env files load from any cwd


def _load_env_files():  #linew copies KEY=VALUE lines from env.txt/.env into os.environ
    for name in ("env.txt", ".env"):  #linew env.txt first, then optional .env
        path = os.path.join(BASE_DIR, name)  #linew absolute path of the env file
        if not os.path.exists(path):  #linew skip silently if the file is missing
            continue
        with open(path, "r", encoding="utf-8") as f:  #linew read the file as UTF-8 text
            for line in f:  #linew go through the file line by line
                line = line.strip()  #linew remove spaces and newline characters
                if not line or line.startswith("#") or "=" not in line:  #linew ignore blanks, comments and bad lines
                    continue
                key, value = line.split("=", 1)  #linew split only at the first "=" so values may contain "="
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))  #linew setdefault means Render variables are never overwritten


_load_env_files()  #linew run once at import time, before any setting is read


def env_str(key, default=""):  #linew read a text setting
    v = os.environ.get(key)  #linew raw value from the environment
    return default if v is None or v.strip() == "" else v.strip()  #linew empty counts as "not set"


def env_int(key, default=0):  #linew read a whole-number setting
    try:
        return int(env_str(key, str(default)))  #linew convert the text to int
    except ValueError:  #linew bad value such as "abc"
        return default  #linew fall back instead of crashing the bot


def env_bool(key, default=False):  #linew read a true/false setting
    return env_str(key, str(default)).lower() in ("true", "1", "yes", "on")  #linew accepts true/1/yes/on


def env_list(key):  #linew read a comma separated list
    return [x.strip() for x in env_str(key).split(",") if x.strip()]  #linew split on commas and drop empty items


def env_int_list(key):  #linew read a comma separated list of numbers (admin IDs)
    out = []
    for x in env_list(key):
        try:
            out.append(int(x))  #linew keep only valid integers
        except ValueError:
            pass  #linew ignore anything that is not a number
    return out


# Auto-add local standalone binary directories to PATH
for _p in [
    os.path.join(BASE_DIR, "bin"),
    os.path.join(BASE_DIR, "calibre-bin"),
    os.path.join(BASE_DIR, "calibre-bin", "calibre"),
    os.path.expanduser("~/calibre-bin"),
    os.path.expanduser("~/calibre-bin/calibre"),
    os.path.expanduser("~/.local/bin"),
    "/opt/render/project/src/bin",
    "/opt/render/project/src/calibre-bin",
    "/opt/render/project/src/calibre-bin/calibre",
]:
    if os.path.exists(_p) and _p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_p}:{os.environ.get('PATH', '')}"

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
