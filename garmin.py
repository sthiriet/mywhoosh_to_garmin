# garmin.py

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


@dataclass
class GarminActivity:
    activity_id: int
    name: str = ""
    start_time: str = ""
    start_time_gmt: str = ""
    distance: float = 0.0
    duration: float = 0.0
    sport_type: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "GarminActivity":
        return cls(
            activity_id=data.get("activityId", 0),
            name=data.get("activityName", ""),
            start_time=data.get("startTimeLocal", ""),
            start_time_gmt=data.get("startTimeGMT", data.get("startTimeGmt", "")),
            distance=data.get("distance", 0.0),
            duration=data.get("duration", 0.0),
            sport_type=data.get("activityType", {}).get("typeKey", ""),
        )

    def formatted_date(self) -> str:
        if self.start_time:
            try:
                dt = datetime.strptime(self.start_time, "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%a %d %b %Y %H:%M")
            except ValueError:
                pass
        return ""

    def formatted_duration(self) -> str:
        if self.duration <= 0:
            return ""
        h = int(self.duration // 3600)
        m = int((self.duration % 3600) // 60)
        s = int(self.duration % 60)
        if h == 0:
            return f"{m}m{s}s"
        return f"{h}h{m:02d}m{s:02d}s"

    def formatted_distance(self) -> str:
        if self.distance > 0:
            return f"{self.distance / 1000:.1f} km"
        return ""

    def utc_timestamp(self) -> float:
        """Retourne l'heure de début normalisée en UTC."""
        value = self.start_time_gmt or self.start_time
        if not value:
            return 0.0
        try:
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).timestamp()
        except ValueError:
            return 0.0

    def distance_km(self) -> float:
        return self.distance / 1000 if self.distance > 0 else 0.0


class GarminClient:
    """Client Garmin Connect."""

    def __init__(self, token_dir: Optional[str] = None):
        self._token_dir = str(Path(token_dir or "~/.garminconnect").expanduser())
        self._client: Optional[Garmin] = None
        self._migrate_legacy_cache()

    def _migrate_legacy_cache(self) -> None:
        base_dir = Path(self._token_dir)
        legacy_dir = base_dir / "garmin-tokens"
        if not legacy_dir.is_dir():
            return

        base_dir.mkdir(parents=True, exist_ok=True)
        for name in ("oauth1_token.json", "oauth2_token.json"):
            legacy_file = legacy_dir / name
            destination = base_dir / name
            if legacy_file.is_file() and not destination.exists():
                legacy_file.replace(destination)

    def _cache_exists(self) -> bool:
        cache_dir = Path(self._token_dir)
        return (
            (cache_dir / "oauth1_token.json").is_file()
            and (cache_dir / "oauth2_token.json").is_file()
        )

    def _save_tokens(self) -> None:
        if self._client is None:
            return
        cache_dir = Path(self._token_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._client.garth.dump(str(cache_dir))
        for token_file in (
            cache_dir / "oauth1_token.json",
            cache_dir / "oauth2_token.json",
        ):
            if token_file.exists():
                token_file.chmod(0o600)

    def resume(self) -> bool:
        """Restaure une session depuis les tokens sauvegardés."""
        if not self._cache_exists():
            return False
        try:
            self._client = Garmin()
            self._client.login(self._token_dir)
            self._save_tokens()
            return True
        except GarminConnectTooManyRequestsError:
            raise
        except (GarminConnectAuthenticationError, GarminConnectConnectionError, FileNotFoundError):
            return False

    def login(self, email: str, password: str) -> None:
        """Authentifie avec email/mot de passe (arguments positionnels)."""
        self._client = Garmin(email, password)
        self._client.login()
        self._save_tokens()

    @property
    def is_authenticated(self) -> bool:
        return self._client is not None

    def get_activities(self, start: int = 0, limit: int = 50) -> list[GarminActivity]:
        """Récupère les activités Garmin (paginé)."""
        if not self._client:
            raise RuntimeError("not authenticated")
        raw = self._client.get_activities(start=start, limit=limit)
        self._save_tokens()
        return [GarminActivity.from_dict(a) for a in raw]

    def get_recent_activities(self, days: int) -> list[GarminActivity]:
        """Retourne les activités des N derniers jours."""
        all_acts: list[GarminActivity] = []
        start = 0
        limit = 50
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

        while True:
            batch = self.get_activities(start=start, limit=limit)
            if not batch:
                break
            for act in batch:
                act_timestamp = act.utc_timestamp()
                if act_timestamp > 0 and act_timestamp < cutoff:
                    return all_acts
                all_acts.append(act)
            if len(batch) < limit:
                break
            start += limit

        return all_acts

    def upload_activity(self, fit_path: str) -> dict:
        """Upload un fichier FIT vers Garmin Connect (chemin de fichier)."""
        if not self._client:
            raise RuntimeError("not authenticated")
        result = self._client.upload_activity(fit_path)
        self._save_tokens()
        return result