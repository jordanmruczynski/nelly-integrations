"""CLI: python -m integrations.tuya_vacuum {list|status <id>|functions <id>|dock <id>|locate <id>}"""
from integrations.tuya_vacuum.device import _cli

if __name__ == "__main__":
    _cli()
