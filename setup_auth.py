#!/usr/bin/env python3
"""Ejecuta este script UNA SOLA VEZ para configurar las credenciales de Lunia."""
import os
import sys
import getpass
import secrets
import bcrypt
import pyotp
import qrcode

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


def set_env_value(key: str, value: str):
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                lines[i] = f'{key}="{value}"\n'
                found = True
                break
    if not found:
        lines.append(f'{key}="{value}"\n')
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main():
    print("\n╔════════════════════════════════╗")
    print("║   Configuración de acceso Lunia  ║")
    print("╚════════════════════════════════╝\n")

    # Username
    username = input("Nombre de usuario: ").strip()
    if not username:
        print("[ERROR] El nombre de usuario no puede estar vacío.")
        sys.exit(1)

    # Password
    while True:
        password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
        if len(password) < 12:
            print("[ERROR] La contraseña debe tener al menos 12 caracteres.")
            continue
        confirm = getpass.getpass("Confirma la contraseña: ")
        if password != confirm:
            print("[ERROR] Las contraseñas no coinciden. Intenta de nuevo.\n")
            continue
        break

    # Hash password
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    # TOTP secret
    totp_secret = pyotp.random_base32()

    # JWT secret key
    jwt_secret = secrets.token_hex(64)

    # Save to .env
    set_env_value("SECRET_KEY", jwt_secret)
    set_env_value("AUTH_USERNAME", username)
    set_env_value("AUTH_PASSWORD_HASH", hashed)
    set_env_value("TOTP_SECRET", totp_secret)

    print("\n✓ Credenciales guardadas en .env")

    # Generate QR code for Google Authenticator
    totp = pyotp.TOTP(totp_secret)
    uri = totp.provisioning_uri(name=username, issuer_name="Lunia")

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(uri)
    qr.make(fit=True)

    qr_path = os.path.join(os.path.dirname(__file__), "lunia_2fa_qr.png")
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_path)

    print(f"✓ Código QR guardado en: lunia_2fa_qr.png")
    print("\n┌─ IMPORTANTE ──────────────────────────────────────────────┐")
    print("│  1. Abre Google Authenticator en tu celular               │")
    print("│  2. Escanea el archivo lunia_2fa_qr.png                   │")
    print("│  3. Borra el archivo QR después de escanearlo             │")
    print("│  4. Nunca compartas el archivo .env                       │")
    print("└───────────────────────────────────────────────────────────┘")
    print("\n¡Listo! Ahora puedes iniciar Lunia con python main.py\n")


if __name__ == "__main__":
    main()
