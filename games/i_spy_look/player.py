import copy
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from backends import CustomResponseModel, HumanModel, Model
from clemgame.clemgame import Player

class Teacher(Player):

    def __init__(self, backend):
        super().__init__(backend)
        self.role: str = "Teacher"

class Learner(Player):

    def __init__(self, backend):
        super().__init__(backend)
        self.role: str = "Learner"
        self.last_is_question = True

