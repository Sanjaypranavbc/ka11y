import yaml


def load_config(config_path: str = "ka11y/config/config.yml"):
    with open(config_path, "r") as file:
        _config = yaml.safe_load(file)
    return _config


config = load_config()
