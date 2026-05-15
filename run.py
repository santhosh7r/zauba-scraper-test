"""
run.py — legacy entry point.
The scraper is now driven entirely by bot.py; this just forwards to it.
"""
from bot import main

if __name__ == "__main__":
    main()
