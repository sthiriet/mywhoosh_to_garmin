# mywhoosh.py

import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import requests

LOGIN_URL = "https://services.mywhoosh.com/http-service/api/login"
ACTIVITIES_BASE = "https://service14.mywhoosh.com/v2/"

# Fonction de debug (remplaçable)
_debug_fn = print


def set_debug_fn(fn):
    """Remplace la fonction de log debug (ex: pour rediriger vers une GUI)."""
    global _debug_fn
    _debug_fn = fn


@dataclass
class Activity:
    id: str = ""
    name: str = ""
    date: float = 0.0
    activity_file_id: str = ""
    distance: float = 0.0
    ride_duration: str = ""
    avg_power: float = 0.0
    avg_hr: float = 0.0
    elevation: float = 0.0
    watt_per_kg: float = 0.0
    route_name: str = ""
    sport_type: str = ""
    start_datetime: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Activity":
        return cls(
            id=data.get("id", ""),
            name=data.get("title", ""),
            date=data.get("date", 0.0),
            activity_file_id=data.get("activityFileId", ""),
            distance=data.get("distance", 0.0),
            ride_duration=data.get("rideDuration", ""),
            avg_power=data.get("watt", 0.0),
            avg_hr=data.get("heartrate", 0.0),
            elevation=data.get("elevation", 0.0),
            watt_per_kg=data.get("wattPerKg", 0.0),
            route_name=data.get("routeName", ""),
            sport_type=data.get("sportType", ""),
            start_datetime=data.get("startDatetime", ""),
        )

    def formatted_date(self) -> str:
        """Retourne la date de l'activité en format lisible."""
        if self.start_datetime:
            try:
                # Format: "2024-01-15T10:30:00.000Z"
                value = self.start_datetime.strip()
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone().strftime("%a %d %b %Y %H:%M")
            except ValueError:
                pass
        if self.date:
            dt = datetime.fromtimestamp(self.date)
            return dt.strftime("%a %d %b %Y %H:%M")
        return ""

    def formatted_duration(self) -> str:
        """Retourne la durée en format lisible (ex: '1h31m54s')."""
        if not self.ride_duration:
            return ""
        parts = self.ride_duration.split(".")[0].split(":")
        if len(parts) == 3:
            h, m, s = parts
            if h == "00":
                return f"{m}m{s}s"
            h = h.lstrip("0") or "0"
            return f"{h}h{m}m{s}s"
        return self.ride_duration

    def formatted_distance(self) -> str:
        """Retourne la distance en km avec 1 décimale."""
        if self.distance > 0:
            return f"{self.distance:.1f} km"
        return ""

    def display_name(self) -> str:
        return self.name if self.name else "Activity"

    def date_unix(self) -> int:
        value = int(self.date)
        if value > 10_000_000_000:
            value //= 1000
        return value

    def utc_timestamp(self) -> float:
        """Retourne l'heure de début normalisée en UTC."""
        if self.start_datetime:
            try:
                value = self.start_datetime.strip()
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).timestamp()
            except ValueError:
                pass
        return float(self.date_unix()) if self.date else 0.0


class Client:
    """Client pour l'API MyWhoosh (authentification + téléchargement d'activités)."""

    def __init__(self, token_dir: Optional[str] = None):
        self._token: str = ""
        self._whoosh_id: str = ""
        self._token_dir = token_dir
        self._session = requests.Session()
        self._timeout = 30

    def resume(self) -> bool:
        """Restaure une session depuis le cache disque. Retourne True si réussi."""
        if not self._token_dir:
            return False
        token_path = Path(self._token_dir) / "mywhoosh_token.json"
        if not token_path.exists():
            return False
        try:
            data = json.loads(token_path.read_text())
            if not data.get("access_token"):
                return False
            self._token = data["access_token"]
            self._whoosh_id = data.get("whoosh_id", "")
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def _save_token(self):
        """Sauvegarde le token sur disque."""
        if not self._token_dir:
            return
        dir_path = Path(self._token_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        data = {"access_token": self._token, "whoosh_id": self._whoosh_id}
        token_path = dir_path / "mywhoosh_token.json"
        token_path.write_text(json.dumps(data, indent=2))
        token_path.chmod(0o600)

    def login(self, email: str, password: str) -> None:
        """Authentifie l'utilisateur avec email et mot de passe."""
        payload = {
            "Username": email,
            "Password": password,
            "Platform": "Android",
            "Action": 1001,
            "CorrelationId": str(uuid.uuid4()),
            "DeviceId": str(uuid.uuid4()),
            "Authorization": "",
        }

        resp = self._session.post(LOGIN_URL, json=payload, timeout=self._timeout)

        if resp.status_code >= 400:
            raise ConnectionError(
                f"login failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        result = resp.json()

        if not result.get("Success"):
            msg = result.get("Message", "unknown error")
            raise PermissionError(f"login failed: {msg}")

        access_token = result.get("AccessToken", "")
        if not access_token:
            raise PermissionError("login failed: no access token in response")

        self._token = access_token
        self._whoosh_id = result.get("WhooshId", "")
        self._save_token()

    @property
    def is_authenticated(self) -> bool:
        return bool(self._token)

    def get_activities(self) -> list[Activity]:
        """Récupère toutes les activités (paginé, du plus récent au plus ancien)."""
        if not self._token:
            raise RuntimeError("not authenticated — login first")

        url = ACTIVITIES_BASE + "rider/profile/activities"
        all_activities: list[Activity] = []
        page = 1

        while True:
            payload = {"sortDate": "DESC", "page": page}
            headers = {"Authorization": f"Bearer {self._token}"}

            resp = self._session.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )

            if resp.status_code >= 400:
                raise ConnectionError(
                    f"fetch activities failed (HTTP {resp.status_code}): {resp.text[:300]}"
                )

            data = resp.json()
            results = data.get("data", {}).get("results", [])
            total_pages = data.get("data", {}).get("totalPages", 1)

            for raw in results:
                all_activities.append(Activity.from_dict(raw))

            if page >= total_pages:
                break
            page += 1

        return all_activities

    def get_recent_activities(self, days: int) -> list[Activity]:
        """Retourne les activités des N derniers jours."""
        all_acts = self.get_activities()
        cutoff = time.time() - (days * 86400)
        recent = []
        for act in all_acts:
            if act.date_unix() >= cutoff:
                recent.append(act)
            else:
                break  # Triées en DESC, on peut s'arrêter
        return recent

    def download_fit_file(self, activity_file_id: str) -> bytes:
        """Télécharge le fichier FIT d'une activité et retourne les octets bruts."""
        if not self._token:
            raise RuntimeError("not authenticated — login first")

        url = ACTIVITIES_BASE + "rider/profile/download-activity-file"
        payload = {"fileId": activity_file_id}
        headers = {"Authorization": f"Bearer {self._token}"}

        resp = self._session.post(
            url, json=payload, headers=headers, timeout=self._timeout
        )

        if resp.status_code >= 400:
            raise ConnectionError(
                f"download failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        result = resp.json()
        download_url = result.get("data", "")

        if not download_url:
            raise ValueError("no download URL in response")

        # Téléchargement du FIT depuis le lien S3 pré-signé
        fit_resp = self._session.get(download_url, timeout=self._timeout)

        if fit_resp.status_code >= 400:
            raise ConnectionError(f"FIT download failed (HTTP {fit_resp.status_code})")

        return fit_resp.content