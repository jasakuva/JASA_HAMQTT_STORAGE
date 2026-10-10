import logging

from ..db import ApplicationLog, SessionLocal


def record_log(level, source, event, message, *, context=None, connection_id=None):
    """Persist a diagnostic event without allowing logging failures to affect workers."""
    try:
        with SessionLocal() as session:
            session.add(ApplicationLog(
                level=str(level).upper()[:20],
                source=str(source)[:150],
                event=str(event)[:100],
                message=str(message)[:4000],
                context=context or {},
                connection_id=connection_id,
            ))
            session.commit()
    except Exception:
        logging.getLogger(__name__).exception("Could not persist application log")