# main.py

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from mywhoosh import Client as MyWhooshClient
from garmin import GarminClient
from fitchanger import patch_fit_device

CONFIG_PATH = Path.cwd() / "config.json"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Crée {CONFIG_PATH}")
    config = json.loads(CONFIG_PATH.read_text())

    required_values = {
        "manufacturer_id": 0xFFFF,
        "product_id": 0xFFFF,
        "serial_number": 0xFFFFFFFF,
    }
    for key, maximum in required_values.items():
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"La configuration '{key}' doit être un entier.")
        if value < 0 or value > maximum:
            raise ValueError(
                f"La configuration '{key}' doit être comprise entre 0 et {maximum}."
            )
    return config


def main():
    config = load_config()
    token_dir = config.get("token_dir", str(CONFIG_PATH.parent))
    manufacturer_id = config["manufacturer_id"]
    product_id = config["product_id"]
    serial_number = config["serial_number"]

    # MyWhoosh
    mw = MyWhooshClient(token_dir=token_dir)
    if not mw.resume():
        mw.login(config["mywhoosh_email"], config["mywhoosh_password"])

    # Garmin
    gc = GarminClient(token_dir=token_dir)
    if not gc.resume():
        garmin_email = config.get("garmin_email")
        garmin_password = config.get("garmin_password")
        if not isinstance(garmin_email, str) or not isinstance(garmin_password, str):
            raise ValueError("La configuration Garmin doit contenir un email et un mot de passe.")
        gc.login(garmin_email, garmin_password)

    # Récupère les activités MyWhoosh récentes
    activities = mw.get_recent_activities(days=7)

    garmin_acts = gc.get_recent_activities(days=7)
    garmin_by_time = [
        (act.utc_timestamp(), act.distance_km())
        for act in garmin_acts
        if act.utc_timestamp() > 0
    ]


    for act in activities:
        if act.utc_timestamp() > 0:
            # Vérifie si l'activité est déjà présente sur Garmin
            mw_timestamp = act.utc_timestamp()
            mw_distance = act.distance if act.distance > 0 else 0.0
            already_present = mw_timestamp > 0 and any(
                abs(mw_timestamp - garmin_timestamp) <= 300
                and abs(mw_distance - garmin_distance) <= 0.5
                for garmin_timestamp, garmin_distance in garmin_by_time
            )
            if already_present:
                print(f"MyWhoosh activity {act.display_name()} is already present on Garmin")
                continue
            else:
                print(f"Uploading MyWhoosh activity {act.display_name()} to Garmin")
            # Télécharge puis crée les fichiers temporaires nécessaires au patch FIT.
            fit_data = mw.download_fit_file(activity_file_id=act.activity_file_id)
            with TemporaryDirectory() as temp_dir:
                input_fit = Path(temp_dir) / f"{act.activity_file_id}.fit"
                output_fit = input_fit.with_name(f"{act.activity_file_id}_modifiee.fit")
                input_fit.write_bytes(fit_data)

                patch_fit_device(
                    str(input_fit),
                    str(output_fit),
                    manufacturer_id=manufacturer_id,
                    product_id=product_id,
                    serial_number=serial_number,
                )
                # Upload le fichier FIT modifié vers Garmin
                gc.upload_activity(fit_path=str(output_fit))


if __name__ == "__main__":
    main()