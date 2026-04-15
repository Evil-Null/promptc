"""Entry point for python -m interceptor."""

from dotenv import load_dotenv

load_dotenv()

from interceptor.cli import main

main()
