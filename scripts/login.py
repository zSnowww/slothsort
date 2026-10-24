import os
from pathlib import Path

from dotenv import load_dotenv
from telethon.sync import TelegramClient


def main() -> None:
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = Path(os.getenv("TELEGRAM_SESSION", ".data/slothsort"))
    if not api_id.isdigit() or not api_hash:
        raise SystemExit("Completa TELEGRAM_API_ID y TELEGRAM_API_HASH en .env primero.")

    session.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    print("Telegram pedirá tu teléfono, el código recibido y, si corresponde, tu contraseña 2FA.")
    with TelegramClient(str(session), int(api_id), api_hash) as client:
        me = client.get_me()
        print(f"Sesión lista para: {me.first_name or me.username or me.id}")

    session_file = session.with_suffix(".session")
    if session_file.exists():
        session_file.chmod(0o600)


if __name__ == "__main__":
    main()
