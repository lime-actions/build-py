from ._api import package as package
from ._limecli import get_main
# ======================================================================
_main = get_main(__name__, function = package) # type: ignore[arg-type]
# ----------------------------------------------------------------------
def main(args: list[str] | None = None) -> int:
    if args is None:
        from sys import argv
        args = argv[1:]

    return _main(args)
