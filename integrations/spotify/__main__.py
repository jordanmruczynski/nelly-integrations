"""CLI: python -m integrations.spotify {status|play|pause|next|prev|vol}"""
import sys

from integrations.spotify.service import _cli

if __name__ == "__main__":
    sys.exit(_cli())
