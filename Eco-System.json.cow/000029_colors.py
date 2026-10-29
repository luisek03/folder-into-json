#!/usr/bin/env python3
"""ANSI-Farben für eco-update. Kein externer Dependency."""

import os
import sys


if sys.platform == "win32":
    os.system("color")


class Color:
    def __init__(self, no_color=False):
        self.no_color = no_color
        if no_color:
            self.FG_BLACK = ''
            self.FG_RED = ''
            self.FG_GREEN = ''
            self.FG_YELLOW = ''
            self.FG_BLUE = ''
            self.FG_PURPLE = ''
            self.FG_CYAN = ''
            self.FG_WHITE = ''
            self.BG_BLACK = ''
            self.BG_RED = ''
            self.BG_GREEN = ''
            self.BG_YELLOW = ''
            self.BG_BLUE = ''
            self.BG_PURPLE = ''
            self.BG_CYAN = ''
            self.BG_WHITE = ''
            self.RESET = ''
        else:
            self.FG_BLACK = '\033[30m'
            self.FG_RED = '\033[31m'
            self.FG_GREEN = '\033[32m'
            self.FG_YELLOW = '\033[33m'
            self.FG_BLUE = '\033[34m'
            self.FG_PURPLE = '\033[35m'
            self.FG_CYAN = '\033[36m'
            self.FG_WHITE = '\033[37m'
            self.BG_BLACK = '\033[40m'
            self.BG_RED = '\033[41m'
            self.BG_GREEN = '\033[42m'
            self.BG_YELLOW = '\033[43m'
            self.BG_BLUE = '\033[44m'
            self.BG_PURPLE = '\033[45m'
            self.BG_CYAN = '\033[46m'
            self.BG_WHITE = '\033[47m'
            self.RESET = '\033[0m'

    def black(self, text, bg=''):
        return f"{bg}{self.FG_BLACK}{text}{self.RESET}"

    def red(self, text, bg=''):
        return f"{bg}{self.FG_RED}{text}{self.RESET}"

    def green(self, text, bg=''):
        return f"{bg}{self.FG_GREEN}{text}{self.RESET}"

    def yellow(self, text, bg=''):
        return f"{bg}{self.FG_YELLOW}{text}{self.RESET}"

    def blue(self, text, bg=''):
        return f"{bg}{self.FG_BLUE}{text}{self.RESET}"

    def purple(self, text, bg=''):
        return f"{bg}{self.FG_PURPLE}{text}{self.RESET}"

    def cyan(self, text, bg=''):
        return f"{bg}{self.FG_CYAN}{text}{self.RESET}"

    def white(self, text, bg=''):
        return f"{bg}{self.FG_WHITE}{text}{self.RESET}"
