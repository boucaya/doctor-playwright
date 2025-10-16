from dotenv import load_dotenv
import os

load_dotenv()

from src.checker import send_notification


def main():
    # send a short test email using credentials in .env
    subject = "[doctor-playwright] Test email"
    body = "Este es un correo de prueba enviado por el script doctor-playwright. Si lo recibes, la configuración SMTP funciona."
    send_notification(f"{subject}\n\n{body}")
    print("Intenté enviar el correo. Revisa tu bandeja de entrada y spam.")


if __name__ == "__main__":
    main()
