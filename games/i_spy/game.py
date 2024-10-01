import copy
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from clembench.backends import CustomResponseModel, HumanModel, Model
from player import Teacher, Learner

GAME_NAME: str = "i_spy"

class Game:
    """
    Handles the Game state
    """
    pass
