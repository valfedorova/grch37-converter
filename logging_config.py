import logging


def configure_logging(level_name: str = "INFO") -> None:
    logging.basicConfig(
        level=level_name.strip().upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
