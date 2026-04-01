import json
import logging
from datetime import datetime
from pathlib import Path

AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "logs" / "audit.log"

class AuditLogger:
    def __init__(self, log_path: Path = AUDIT_LOG_PATH):
        self.log_path = log_path
        self.logger = logging.getLogger("audit")
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log(self, who: str, what: str, context: dict = None, result: str = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "who": who,
            "what": what,
            "context": context or {},
            "result": result,
        }
        self.logger.info(json.dumps(entry, ensure_ascii=False))

# Singleton
_audit_logger = AuditLogger()

def audit_log(who: str, what: str, context: dict = None, result: str = None):
    """Logga un evento di audit strutturato."""
    _audit_logger.log(who, what, context, result)
