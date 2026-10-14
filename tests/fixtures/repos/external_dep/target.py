import requests
import yaml


def fetch() -> str:
    return yaml.dump({"v": requests.get("x").status_code})
