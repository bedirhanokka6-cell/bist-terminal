import os
import firebase_admin
from firebase_admin import credentials, messaging


def _firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL", "").strip()
    private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").strip().replace("\\n", "\n")

    if not project_id or not client_email or not private_key:
        raise RuntimeError(
            "Firebase Admin ayarları eksik. FIREBASE_PROJECT_ID, "
            "FIREBASE_CLIENT_EMAIL ve FIREBASE_PRIVATE_KEY gerekli."
        )

    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": project_id,
        "private_key": private_key,
        "client_email": client_email,
        "token_uri": "https://oauth2.googleapis.com/token",
    })
    return firebase_admin.initialize_app(cred)


def send_push(tokens, title, body, data=None):
    _firebase_app()

    success_count = 0
    invalid_tokens = []
    errors = []

    for token in list(dict.fromkeys(tokens)):
        try:
            message = messaging.Message(
                token=token,
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data={str(k): str(v) for k, v in (data or {}).items()},
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        title=title,
                        body=body,
                        icon="/icon-192.png",
                    ),
                    fcm_options=messaging.WebpushFCMOptions(
                        link="https://bist-terminal-sable.vercel.app/"
                    ),
                ),
            )
            messaging.send(message)
            success_count += 1
        except Exception as exc:
            msg = str(exc)
            errors.append(msg)
            low = msg.lower()
            if (
                "registration-token-not-registered" in low
                or "not found" in low
                or "unregistered" in low
                or "invalid argument" in low
            ):
                invalid_tokens.append(token)

    return {
        "success_count": success_count,
        "invalid_tokens": invalid_tokens,
        "errors": errors[:5],
    }
