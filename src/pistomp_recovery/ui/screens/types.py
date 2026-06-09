from typing import Callable

ACTIONS_KEY = str

Actions = dict[ACTIONS_KEY, Callable[[], None]]
