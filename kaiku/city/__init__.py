"""Kaiku /city: Turku as NGSI-LD Store entities in Orion-LD (see docs/city.md)."""


def startup() -> dict:
    from .router import startup as _s
    return _s()


def reset() -> dict:
    from . import seed
    return seed.seed(force=True)
