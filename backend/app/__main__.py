"""Запуск сервера командой `python -m app` (параметры — из .env)."""
import uvicorn

from .config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, log_level=s.log_level.lower(), reload=s.app_env == "dev")
