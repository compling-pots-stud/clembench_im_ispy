import sys
import logging
from pathlib import Path
from typing import Tuple, Dict, List
import re

sys.path.append(str(Path(__file__).parent.parent.parent))
from backends import Model
from clemgame import get_logger
from clemgame.clemgame import GameBenchmark, GameMaster, DialogueGameMaster, Player
from games.i_spy.player import Teacher, Learner

MAX_TURNS = 10
GAME_NAME = 'i_spy'
TURN_TEMPLATE = "resources/prompts/turn.template"
logger = get_logger(__name__)

# think about decision turn like in matchit -> force LLM to ask several questions before actually making a guess.
# think about re-prompting and re-attempts after mistaken guess.
# do we need to provide both LLMs with a list of objects?
# do we need to verify the location of the object?
# do we need to ask the LLM for explanation?


# minimum 5 turns of guessing
# after on 5th turn, Model can take a guess.
# each subsequent turn, model needs to ask another question.
#
class ISpyGameMaster(DialogueGameMaster):
    """
    Controls the gameplay, game loop, etc.
    """
    def __init__(self, experiment: Dict, player_backends: List[Model]):
        super().__init__(GAME_NAME, experiment, player_backends)

        self.experiment = experiment["name"]
        self.teacher_prompt = experiment["teacher_prompt"]
        self.learner_prompt = experiment["learner_prompt"]
        self.learner_mistake_prompt = experiment["learner_mistake_prompt"]
        self.teacher_model = player_backends[0]
        self.learner_model = player_backends[1]

    def _on_setup(self, **game_instance):
        self.game_instance: dict = game_instance
        self.scene: list[str]= [game_instance["image"]]
        self.selected_object: str = game_instance["selected_object"]
        self.object_location: str = game_instance["object_quadrant"]
        self.visible_objects: set[str] = set(game_instance["visible_objects"])
        self.min_guess_turn: int = game_instance["min_guess_turn"]

        self.teacher_prompt = self.teacher_prompt.replace("$OBJECT$", self.selected_object)
        self.teacher_prompt = self.teacher_prompt.replace("$OBJECT_LOCATION$", self.object_location)
        self.learner_prompt = self.learner_prompt.replace("$MIN_GUESS_TURN$", str(self.min_guess_turn))

        # template to define turn
        self.turn_template = self.load_template(TURN_TEMPLATE)

        # create player in player.py
        self.learner: Player = Learner(self.learner_model)
        self.teacher: Player = Teacher(self.teacher_model)

        # learner plays first
        self.add_player(self.learner)
        self.add_player(self.teacher)

        self.n_turns: int = 0

        self.correct_guess: bool = False # was the guess correct
        self.invalid_response: bool = False # is the response invalid -> used for reprompt
        self.max_turns: int = MAX_TURNS # max allowed turns
        self.can_guess: bool = False # is learner allowed to guess
        self.task_msg: str | None = None # task definition, starting letter of the object
        self.last_guess: str | None = None # what was the learners last guess
        self.last_guess_location: str | None = None # last guess item location

    def _on_before_game(self):

        # add initial prompt and image to learner and teacher
        self.task_msg = self._build_task_message()
        self.add_user_message(self.learner, self.learner_prompt + "\n" + self.task_msg, self.scene)  # prompt + task

        logger.info("Added Prompt Learner")
        # self.add_user_message(self.teacher, self.teacher_prompt, self.scene)
        # logger.info("Added Prompt Teacher")

        self.next_player = self.teacher #teacher plays second


    def _on_after_game(self):
        pass

    def _on_before_turn(self, turn_idx: int):
        self.n_turns+=1
        self._add_learner_turn_prompt() # tell learner turn number
        self._check_guess_allowed() # is the guess allowed?
        self._enable_learner_guess() # if guess is allowed, add prompt to learner


    def _on_after_turn(self, turn_idx: int):
        pass

    def _does_game_proceed(self) -> bool:
        if self.invalid_response:
            self.log_to_self("invalid format", "abort game")
            return False

        if self.current_turn >= self.max_turns:
            self.log_to_self("max turns reached", str(self.max_turns))
            return False

        if self.correct_guess:
            return False
        return True

    def _validate_player_response(self, player: Player, utterance: str) -> bool:
        # make sure that the response contains the Answer or I SPY Phrase
        # Make sure that after the question by learner, answer is ANSWER:
        # for learner role, differentiate between QUESTION and GUESS.
        # GUESS needs to come with LOCATION to tell us where the object is.
        # use _parse to get parsed outputs and find these answers inside.
        # we also need to make sure that the teacher doesn't use the keyword inside the answer.
        print(f"Player: {player.role}")
        # get player response
        response = self._parse_response(utterance)
        response_keys = list(response.keys())


        if player.role == "Teacher":
            # let the teacher evaluate if the Learner guess is correct. TODO: Come up with a better approach.
            if "SUCCESS" in response_keys:
                # maybe we can get a scoring mechasnism out of this?
                # How often does the teacher make a mistake when evaluating the item?
                # Find out why?

                #Answer not correct if they don't start with the same letter
                if self.last_guess[0] != self.selected_object.lower()[0]:
                    print('1')
                    self.invalid_response = True
                    return False

                # verify that the object is in the correct location
                # potentially remove this, probably not needed for gameflow. Can be useful for teacher eval.
                # currently this gate should be checked under learner.
                if  self.object_location.lower() not in self.last_guess_location.lower():
                    print('2')
                    self.invalid_response = True
                    return False

                self.correct_guess = True
                self.log_to_self("object correctly guessed", "continue")
                print('3')
                return True

            # if the learner's last response was a question, teacher must provide answer
            if self.learner.last_is_question is True:
                if not "ANSWER" in response_keys:
                    print('4')
                    self.invalid_response = True
                    return False

                # teacher not allowed to name the object in the response
                if self.selected_object.lower() in response['ANSWER'].lower():
                    print('5')
                    self.invalid_response = True
                    return False

        # figure sth to validate response to GUESS
        # probably won't work, needs change
        if player.role == "Learner":

            # not allowed to guess this turn.
            if not self.can_guess and "GUESS" in response_keys:
                # not allowed to guess yet
                self.invalid_response = True
                print('7')

                return False

            # Location not provided
            if self.can_guess and "GUESS" in response_keys:
                if not "LOCATION" in response_keys:
                    self.invalid_response = True
                    print('8')

                    return False

            # else:
            # if guess hasn't been made, and no QUESTION tag either
            if not "QUESTION" in response_keys and not "GUESS" in response_keys:
                self.invalid_response = True
                print('9')

                return False

            # can't guess and make a question.
            if "QUESTION" in response_keys and "GUESS" in response_keys:
                self.invalid_response = True
                print('10')
                return False

            # also needs to check LOCATION is proper. If not, then some other verification method.
            # check if learner has guessed correctly
            # TODO: learner shouldn't make two guesses in a row.
            if "QUESTION" in response_keys:
                self.learner.last_is_question = True
            else:
                self.learner.last_is_question = False

            if "GUESS" in response_keys and "LOCATION" in response_keys:
                self.last_guess = response["GUESS"].lower()
                self.last_guess_location = response["LOCATION"].lower()
                self._validate_learner_guess() # provides information to teacher


                # # if validation is done by teacher, do we need this?
                # if self.selected_object.lower() == self.last_guess:
                #     if self.object_location.lower() not in self.last_guess_location.lower():
                #         self.invalid_response = True
                #         return False
                #
                #     self.correct_guess = True
                #     self.log_to_self("object correctly guessed", "continue")
                #     return True

        self.log_to_self("valid format", "continue")
        return True


    def _after_add_player_response(self, player: Player, utterance: str):
            # EXPLANATION:
            # Each player has their own message history. In their message history, they are assistant
            # The other player is user.
            # Their own history is logged by default.
            # This step adds the message to the other player's history.
            # They are added as a message coming in from User.
            if self.n_turns == 1 and self.next_player == self.teacher:
                print(self.selected_object)
                self.add_user_message(self.teacher, self.teacher_prompt, self.scene)
                logger.info("Added Prompt Teacher")
                # this adds the task message as if it came from the teacher.
                self.add_assistant_message(self.teacher, self.task_msg)

            # print(self.messages_by_names[player.descriptor])

            # print(f"pre: {self.next_player}")
            self.add_user_message(self.next_player, utterance = utterance)
            # print('added')
            print(utterance)
            # change which player is next

            # check whether the guess made by the learner was incorrect
            # only do so if the last attempt was a guess.

            if self.next_player == self.teacher and not self.learner.last_is_question:
                 self._validate_learner_guess()

            # Update -> change who is playing after the next player (i.e. the current player comes after the next).
            self.next_player = self.teacher if player == self.teacher else self.learner
            # print(f"post: {self.next_player}")

    def _parse_response(self, utterance: str):

        pattern = r'(GUESS|LOCATION|ANSWER|QUESTION|TASK|SUCCESS): (.+?)(?=\n[A-Z]|$)'
        # Find all matches in the text
        matches = re.findall(pattern, utterance)
        # Convert matches to a dictionary
        parsed_output = {key: value.strip() for key, value in matches}

        # Print the parsed output
        return parsed_output



    # use this to validate the guess before it is given to the teacher.
    # Prevent teacher from calling success before the answer is correct.
    # give prompt to teacher how to respond
    # e.g. If item is correctly guessed, but location is wrong
    # or item doesn't start with the correct letter.
    def _validate_learner_guess(self):
        # was the initial letter of the obj correctly guessed
        if self.last_guess[0] != self.selected_object.lower()[0]:
            self.messages_by_names[self.teacher.descriptor][-1]["content"] = \
                (self.messages_by_names[self.teacher.descriptor][-1]["content"]
                 + "\n"
                 + self.learner_mistake_prompt.replace("$MISTAKE$",
                                                              "The initial letter of the guessed item was not correct")
                 + "\n")

            # give the prompt to teacher to say that the initial letter was missed

        # if object is not correct, no need to validate location
        # was the location guessed correctly
        elif self.object_location.lower() not in self.last_guess_location.lower():
            # prompt to say that the item location was not guessed accordingly
            self.messages_by_names[self.teacher.descriptor][-1]["content"] = \
                (self.messages_by_names[self.teacher.descriptor][-1]["content"]
                 + "\n"
                 + self.learner_mistake_prompt.replace("$MISTAKE$",
                                                              "The guessed location of the item was not correct."
                                                              " If the learner guessed the item correctly, tell them that the location was incorrect."
                                                              " Otherwise, the entire guess is incorrect.")
                 + "\n")

    def _check_guess_allowed(self):
        if self.n_turns >= self.min_guess_turn and self.learner.last_is_question:
            self.can_guess = True
        else:
            self.can_guess = False

    def _enable_learner_guess(self):
        if self.can_guess:  #and self.learner.last_is_question:
            self.messages_by_names[self.learner.descriptor][-1]["content"] = \
                (self.messages_by_names[self.learner.descriptor][-1]["content"]
                 + "\n" + "You are allowed to make a guess now." + "\n")

    def _add_learner_turn_prompt(self):
        self.messages_by_names[self.learner.descriptor][-1]["content"] =\
            (self.messages_by_names[self.learner.descriptor][-1]["content"]
             + "\n" + self.turn_template.replace("$TURN_NUMBER$", str(self.n_turns)))


    def _on_parse_response(self, player: Player, utterance: str) -> Tuple[str, bool]:
        # potentially return without prefixes.
        # msg = f"Current turn: {self.n_turns}"
        # utterance = msg + utterance
        return utterance, True





    # from matchit
    # messages passed in between LLMs with user roles.
    def add_message(self, player: Player, utterance: str, role: str, image = None):
        if image is None:
            message = {"role": role, "content": utterance}
        else:
            message = {"role": role, "content": utterance, "image": image}
        history = self.messages_by_names[player.descriptor]
        history.append(message)

    def add_user_message(self, player: Player, utterance: str, image = None):
        self.add_message(player, utterance, role="user", image= image)


    def _build_task_message(self):
        first_letter = self.selected_object.lower()[0]
        task_msg = f"Task: I imagine something starting with a letter [{first_letter}]."

        return task_msg


class ISpyBenchmark(GameBenchmark):
    def __init__(self):
        super().__init__(GAME_NAME)

    def is_single_player(self):
        return False

    def get_description(self):
        return "A simple game in which learner has to succesfully identify the object imagined by the teacher."

    def create_game_master(self,
                           experiment: Dict,
                           player_backends: List[Model]
                           ) -> GameMaster:

        return ISpyGameMaster(experiment, player_backends)


if __name__ == "__main__":

    # comment out to run with cli
    from clemgame import benchmark
    from scripts.cli import read_model_specs

    # model_specs: list[str] = ["gpt-4o-2024-08-06", "gpt-4o-2024-08-06"]
    model_specs: list[str] = ["gpt-4o-2024-08-06", "gpt-4o-mini"]

    # model_specs: list[str] = ["llava-v1.5-7b-4096-preview", "llava-v1.5-7b-4096-preview"]

    gen_args: dict[str: str] = {"temperature": 0.0, "max_tokens": 800}

    benchmark.run(
        game_name=GAME_NAME,
        model_specs=read_model_specs(model_specs),
        gen_args=gen_args,
    )
