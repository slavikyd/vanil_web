import uuid


def get_or_create_session_id(session: dict) -> str:
    session_id = session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
    return session_id
