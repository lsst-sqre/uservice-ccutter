"""Module for getting the version of the app.

Used by `make image` (`python -m uservice_ccutter.version`).
"""

from . import __version__


def main():
    print('{}'.format(__version__))


if __name__ == '__main__':
    main()
