import sys
import logging
from logging import ERROR
from pathlib import Path
from typing import Tuple, Dict, List
import re

from importlib_metadata import pass_none

sys.path.append(str(Path(__file__).parent.parent.parent))
from backends import Model
from clemgame import get_logger
from clemgame.clemgame import GameBenchmark, GameMaster, DialogueGameMaster, Player
from games.i_spy_look.player import Teacher, Learner
from clembench.games.i_spy_look.env_backends.navigation import Agent, get_quadrant
import json
import os

IMAGE_OUTPUT_PATH = 'resources/images'
METADATA_OUTPUT_PATH='resources/metadata'
MAX_TURNS = 7
MAX_REPROMPTS = 2
GAME_NAME = 'i_spy_look'
TURN_TEMPLATE = "resources/prompts/turn.template"
logger = get_logger(__name__)

MOVEMENT_KEYS  = ["MOVE", "LOOK", "TURN"]

ERROR_CODEBOOK = {
    1:'The starting letter was not correct, therefore you cannot call the game SUCCESS. Please re-evaluate your '
      'answer.',
    2: 'The guessed location was incorrect, therefore you cannot call the game SUCCESS Please re-evaluate your '
      'answer.',
    3: 'The guessed location was incorrect since the object is not visible in this frame, therefore you cannot call '
       'the game SUCCESS. Please re-evaluate your answer.',
    4: 'You must use the ANSWER tag to provide an answer. Please try again.',
    5: 'You are not allowed to mention the name of the object in your answers. Please try again.',
    6: 'You are not allowed to make a GUESS and a QUESTION at the same time! Please try again.',
    7: 'You did not ask a QUESTION. Please try again.',
    8: 'You are not allowed to make a GUESS yet. Please ask a question.',
    9: 'You need to provide a LOCATION with your GUESS! Please try again.',
    10: 'You are not allowed to move when making a GUESS. Please try again.',
    11: 'You can only make one move each turn. Please try again.',
    12: 'This move is not possible due to the following reason: $REASON$ \nPlease try again!',
}


"""
TODO: 
1) Every turn check the location of the object relative to the POV (use get_rotation). √
2) Tell the teacher where the object is and whether the agent should turn that way. √

"""


"""
Learner plays first 

"""

class ISpyLookGameMaster(DialogueGameMaster):
    """
    Controls the gameplay, game loop, etc.
    """
    # fixed
    env_agent = None

    def __init__(self, experiment: Dict, player_backends: List[Model]):
        super().__init__(GAME_NAME, experiment, player_backends)
        """
        Figure out which prompts are needed and which should be initialized here
        """

        self.experiment = experiment["name"]
        self.teacher_prompt = experiment["teacher_prompt"]
        self.learner_prompt = experiment["learner_prompt"]
        self.learner_mistake_prompt = experiment["learner_mistake_prompt"]
        self.learner_move_error_prompt = experiment["move_error_prompt"]

        self.teacher_model = player_backends[0]
        self.learner_model = player_backends[1]
        self.move_error = None

        if ISpyLookGameMaster.env_agent is None:
            ISpyLookGameMaster.env_agent = Agent("AI2THOR")
            logger.info("Environment agent initialized")

    def _on_setup(self, **game_instance):
        self.game_instance: dict = game_instance
        self.instance_id = game_instance['game_id']
        self.scene = game_instance["scene"]

        self.selected_object: str = game_instance["selected_object"]
        self.selected_object_id: str = game_instance["selected_object_id"]
        self.object_location = None

        self.min_guess_turn: int = game_instance["min_guess_turn"]
        self.starting_position: dict = game_instance["starting_position"]
        self.starting_rotation: dict = game_instance["starting_rotation"]
        self.starting_horizon: int = game_instance["starting_horizon"]

        self.metadata = {}
        self.experiment_name = f"{self.teacher_model}--{self.learner_model}"
        self.folder_name = f"episode_{self.instance_id}"



        # adapt teacher prompt
        self.teacher_prompt = self.teacher_prompt.replace("$OBJECT$", self.selected_object)

        # template to define turn
        self.turn_template = self.load_template(TURN_TEMPLATE)

        # create player in player.py
        self.learner: Player = Learner(self.learner_model)
        self.teacher: Player = Teacher(self.teacher_model)


        # learner plays first
        self.add_player(self.learner)
        self.add_player(self.teacher)

        self.n_turns: int = 0

        # initialize environment in the correct position
        self.env_agent.reset(scene=self.scene)
        self.env_agent.teleport(position=self.starting_position,
                                rotation=self.starting_rotation,
                                horizon=self.starting_horizon)


        self.current_image = [self._save_frame()]

        self.correct_guess: bool = False # was the guess correct
        self.invalid_response: bool = False # is the response invalid -> used for reprompt
        self.max_turns: int = MAX_TURNS # max allowed turns
        self.can_guess: bool = False # is learner allowed to guess
        self.task_msg: str | None = None # task definition, starting letter of the object
        self.last_guess: str | None = None # what was the learners last guess
        self.last_guess_location: str | None = None # last guess item location
        # was there movement on the previous turn? If yes, take a new screenshot and add it to the stranscript.
        self.movement_on_last: bool = False
        self.error_code: int | None = None
        self.reprompt_counter = 0

        # for reprompting - store the last uttered piece to add to assistant history.
        self.last_utterance = None
    def _on_before_game(self):
        """
        Initialized before game start.
        """

        # add initial prompt and image to learner and teacher
        self.task_msg = self._build_task_message()
        self.add_user_message(self.learner, self.learner_prompt + "\n" + self.task_msg, self.current_image)  # prompt + task

        logger.info("Added Prompt Learner")
        # self.add_user_message(self.teacher, self.teacher_prompt, self.scene)
        # logger.info("Added Prompt Teacher")

        self.next_player = self.teacher #teacher plays second


    def _on_after_game(self):
        """
        Runs after the game has been completed.
        """

        self._store_instance_metadata()

    def _on_before_turn(self, turn_idx):
        """
        Runs before the start of each turn.
        """

        self.n_turns+=1

        self._get_object_location() # get the location of the object (we need to tell the teacher if it's in frame).
        # self._add_teacher_object_location_prompt() # add the information to the teacher's prompt - moved to AFTER
        # PLAYER RESPONSE

        self._add_learner_turn_prompt() # tell learner turn number
        self._check_guess_allowed() # is the guess allowed?
        self._enable_learner_guess() # if guess is allowed, add prompt to learner

    def _on_after_turn(self, turn_idx: int):
        pass

    def _does_game_proceed(self) -> bool:
        """
        Checks whether the game should proceed.
        """

        if self.correct_guess:
            self.log_to_self("win", 'end game')
            return False


        if self.n_turns >= self.max_turns:
            self.log_to_self("max turns reached", "abort game")
            return False


        if self.reprompt_counter > MAX_REPROMPTS:

            if self.invalid_response:
                self.log_to_self("max reprompts reached", "abort game")
                self.log_to_self("invalid format", "abort game")
                return False


        return True

    def _validate_player_response(self, player: Player, utterance: str) -> bool:
        """
        Checks the validity of teacher/learner responses.
        """

        print(f"Player: {player.role}")
        self.last_utterance = utterance # save it for later
        response = self._parse_response(utterance)
        response_keys = list(response.keys())
        if player.role == "Teacher":
            if not self.validate_teacher(response, response_keys):
                return False

        if player.role == "Learner":
            if not self.validate_learner(response, response_keys):
                return False

        # reset the counter and all incorrect move indicators.
        # double check if we need this.
        self.reprompt_counter=0
        self.invalid_response = False
        self.error_code = None
        self.move_error = None
        self.log_to_self("valid format", "continue")
        return True

    def validate_learner(self, response, response_keys):
        if response.get("GUESS") and response.get("QUESTION"):
            self.error_code = 6
            self.invalid_response = True
            print(response)
            print('Not allowed to make a guess and question')
            return False

        if not response.get("GUESS") and not response.get("QUESTION"):
            self.error_code = 7
            self.invalid_response = True
            print(response)
            print('Must make either a guess or a question')
            return False

        if response.get("GUESS"):
            if not self.can_guess:
                self.error_code = 8
                self.invalid_response = True
                print(response)
                print('Not allowed to make a guess')
                return False

            if not response.get("LOCATION"):
                self.error_code = 9
                self.invalid_response = True
                print(response)
                print('Incomplete Guess - Location missing')
                return False

            for movement_key in MOVEMENT_KEYS:
                if response.get(movement_key):
                    self.error_code = 10
                    self.invalid_response = True
                    print(response)
                    print('Movement not allowed on guess')
                    return False

            self.learner.last_is_question = False
            self.last_guess = response["GUESS"].lower()
            self.last_guess_location = response["LOCATION"].lower()
            self._validate_learner_guess()  # provides information to teacher
            # TODO fix so that the location is obtained live

        if response.get("QUESTION"):
            if not self.has_only_one_movement_key(response_keys):
                self.error_code = 11
                self.invalid_response = True
                print(response)
                print('Only one move allowed per turn')
                return False

            self.learner.last_is_question = True
            self.make_and_validate_move(response, response_keys)

            if self.move_error:
                self.error_code = 12
                self.invalid_response = True

                return False


        self.current_image = [self._save_frame()] # take screenshot every turn
        return True

    def has_only_one_movement_key(self, response_keys):
        # Count the number of movement keys in the dictionary
        count = sum(1 for key in MOVEMENT_KEYS if key in response_keys)
        return count == 1

    def validate_teacher(self, response, response_keys):
        # let the teacher evaluate if the Learner guess is correct. TODO: Come up with a better approach.
        if "SUCCESS" in response_keys:
            # maybe we can get a scoring mechasnism out of this?
            # How often does the teacher make a mistake when evaluating the item?
            # Find out why?
            #Answer not correct if they don't start with the same letter
            if self.last_guess[0] != self.selected_object.lower()[0]:
                self.error_code = 1
                self.invalid_response = True
                return False
            # verify that the object is in the correct location
            # potentially remove this, probably not needed for gameflow. Can be useful for teacher eval.
            # currently this gate should be checked under learner.
            if self.object_location:
                if  self.object_location.lower() not in self.last_guess_location.lower():
                    self.error_code = 2
                    print(response)
                    print('Correct guess, but incorrect location')
                    self.invalid_response = True
                    return False
            else:
                self.error_code = 3
                print(response)
                print('object not in frame')
                self.invalid_response = True
                return False

            self.correct_guess = True
            self.log_to_self("object correctly guessed", "continue")
            print('Correct guess')
            return True
        # if the learner's last response was a question, teacher must provide answer
        if self.learner.last_is_question is True:
            if not "ANSWER" in response_keys:
                print(response)
                print('Answer tag missing')
                self.error_code = 4
                self.invalid_response = True
                return False
            # teacher not allowed to name the object in the response
            if self.selected_object.lower() in response['ANSWER'].lower():
                self.error_code = 5
                print('Teacher mentioned the object name')
                print(response)
                self.invalid_response = True
                return False

        # check if it's needed - the idea is to once we have an invalid response, if the next reprompt is fine,
        # return to False
        return True

    def make_and_validate_move(self, response, response_keys):
        """
        Validate moves here and move the scenes.
        """
        if 'LOOK' in response_keys:
            self.env_agent.look(response['LOOK'])
            self.move_error = self.env_agent.error
        if 'TURN' in response_keys:
            self.env_agent.turn(response['TURN'])
            self.move_error = self.env_agent.error
        if 'MOVE' in response_keys:
            self.env_agent.move(response['MOVE'])
            self.move_error = self.env_agent.error


    # if the game still proceeds and there is an invalid response, reprompt.
    def _should_reprompt(self, player: Player):
        """
        Re-prompting Logic - When should we reprompt?
        """
        while self._does_game_proceed():
            if self.invalid_response:
                return True
            else:
                return False

        return False

    def _on_before_reprompt(self, player: Player):
        """
        Hook

        Change the prompt to reprompt the player on e.g. an invalid response.
        Add the new prompt to the players message via self.add_user_message(player, new_prompt)

        :param player: that produced the invalid response
        """

        # increment the reprompt counter
        self.reprompt_counter += 1

        # add assistant message -> LLM Makes a mistake, we add that sentence to history, then we correct them.
        # maybe not the best way to reprompt. Try with the standard approach as well.
        self.add_assistant_message(player, self.last_utterance)
        # add message based on the code
        # two cases - non move and move error. Move errors require info about object in front of them as well.

        if self.move_error:
            self.add_user_message(player, ERROR_CODEBOOK[self.error_code].replace("$REASON$", self.move_error))

        elif self.invalid_response:
            self.add_user_message(player, ERROR_CODEBOOK[self.error_code])


    def _after_add_player_response(self, player: Player, utterance: str):
        """
        Adds messages to the other players' history (not current player).
        Added step to tell the teacher where the object is actually located.
        Updates the next player.
        """


        if self.n_turns == 1 and self.next_player == self.teacher:

            print(self.selected_object)
            self.add_user_message(self.teacher, self.teacher_prompt, self.current_image)
            logger.info("Added Prompt Teacher")
            # this adds the task message as if it came from the teacher.
            self.add_assistant_message(self.teacher, self.task_msg)

        print(self.n_turns)
        print(self.current_image)

        logger.info(f"adding image")
        self.add_user_message(self.next_player, utterance= utterance, image=self.current_image)
        logger.info(f"done adding image")

        print(utterance)
        logger.info(f"done print utterance")

        if self.next_player == self.teacher:
            self._add_teacher_object_location_prompt()

        if self.next_player == self.teacher and not self.learner.last_is_question:
             self._validate_learner_guess()

        # Update -> change who is playing after the next player (i.e. the current player comes after the next).
        self.next_player = self.teacher if player == self.teacher else self.learner
        logger.info(f"done after add player")




    # use this to validate the guess before it is given to the teacher.
    # Prevent teacher from calling success before the answer is correct.
    # give prompt to teacher how to respond
    # e.g. If item is correctly guessed, but location is wrong
    # or item doesn't start with the correct letter.
    def _validate_learner_guess(self):
        self._get_object_location()

        # was the initial letter of the obj correctly guessed
        if self.last_guess[0] != self.selected_object.lower()[0]:
            print('Initial letter missed')
            self.messages_by_names[self.teacher.descriptor][-1]["content"] = \
                (self.messages_by_names[self.teacher.descriptor][-1]["content"]
                 + "\n"
                 + self.learner_mistake_prompt.replace("$MISTAKE$",
                                                              "The initial letter of the guessed item was not correct")
                 + "\n")

            # give the prompt to teacher to say that the initial letter was missed

        # if object is not correct, no need to validate location
        # was the location guessed correctly

        elif not self.object_location:
            # object is not visible/ in frame
            print('Object location set to none - not in frame')

            self.messages_by_names[self.teacher.descriptor][-1]["content"] = \
                (self.messages_by_names[self.teacher.descriptor][-1]["content"]
                 + "\n"
                 + self.learner_mistake_prompt.replace("$MISTAKE$",
                                                              f"The object is not visible in this frame, "
                                                              f"therefore the location is incorrect. To see the "
                                                              f"object, turn the camera to the {self.rotate_to}" 
                                                              " If the learner guessed the item correctly, "
                                                              "tell them that the location was incorrect and that the object is currently not visible in the frame."
                                                              " Otherwise, the entire guess is incorrect.")
                 + "\n")


        elif self.object_location and self.object_location.lower() not in self.last_guess_location.lower():
            print('Object actually missed')

            # prompt to say that the item location was not guessed accordingly
            self.messages_by_names[self.teacher.descriptor][-1]["content"] = \
                (self.messages_by_names[self.teacher.descriptor][-1]["content"]
                 + "\n"
                 + self.learner_mistake_prompt.replace("$MISTAKE$",
                                                              "The guessed location of the item was not correct."
                                                              " If the learner guessed the item correctly, tell them that the location was incorrect."
                                                              " Otherwise, the entire guess is incorrect.")
                 + "\n")


    def _parse_response(self, utterance: str) -> Dict[str, str]:
        pattern = r'(GUESS|LOCATION|ANSWER|QUESTION|TASK|SUCCESS|LOOK|MOVE|TURN):\s*(.*?)(?=\n{2,}|(?=\n[A-Z]+:)|$)'
        return {key: value.strip() for key, value in re.findall(pattern, utterance)}

    def _get_object_location(self):
        """
        If object is in the frame:
            - Get object Location.
        If not:
            - Tell the learner + teacher where to look (left, right).
        """
        current_object_meta = self.metadata[self.n_turns-1]['metadata']['objects']
        for object in current_object_meta:
            if object['objectId'] == self.selected_object_id:
                if object['visible']:
                    print(f"Object state is {object['visible']} - set to True")
                    object_position = self.env_agent.get_object_position(self.selected_object_id)
                    location = get_quadrant(object_position, frame_width=800, frame_height=600)
                    self.object_location = location.lower()
                    self.rotate_to = None
                else:
                    """
                    If object is not visible (i.e. in the frame), 
                    We should calculate the rotation to the object.
                    Then tell the teacher to instruct the learner where to look. (e.g. left, right).
                    """
                    print(f"Object state is {object['visible']} - set to None")

                    self.rotate_to = self.env_agent.rotation_to_direction(
                                                        object['position'],
                                                        self.metadata[self.n_turns-1]['metadata']['agent']['position'],
                                                        self.metadata[self.n_turns - 1]['metadata']['agent']['rotation']
                                                        )
                    self.object_location = None

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

    def _add_teacher_object_location_prompt(self):
        """
        Prompts the teacher with information whether the object is visible or not. If not visible, tells the teacher
        where the object is.
        """

        if self.object_location:
            message = f"The object is in the frame! It is located in {self.object_location}"
        else:
            print(f'Told the teacher to rotate to: {self.rotate_to}')
            message = (f"The object is not present in this scene. To see it, the camera needs to turn "
                       f"{self.rotate_to}. Tell the learner to look in that direction.")

        self.messages_by_names[self.teacher.descriptor][-1]["content"] =\
                (self.messages_by_names[self.teacher.descriptor][-1]["content"]
                 + "\n" + message)

    def _on_parse_response(self, player: Player, utterance: str) -> Tuple[str, bool]:
        # potentially return without prefixes.
        # msg = f"Current turn: {self.n_turns}"
        # utterance = msg + utterance
        return utterance, True


    # from matchit
    # messages passed in between LLMs with user roles.
    def add_message(self, player: Player, utterance: str, role: str, image = None):
        """
        TODO -> ADAPT THIS
        """

        if image is None:
            message = {"role": role, "content": utterance}
        else:
            message = {"role": role, "content": utterance, "image": image}
        history = self.messages_by_names[player.descriptor]
        history.append(message)

    def add_user_message(self, player: Player, utterance: str, image = None):
        self.add_message(player, utterance, role="user", image=image)

    def _build_task_message(self):
        """
        TODO -> ADAPT THIS
        """


        first_letter = self.selected_object.lower()[0]
        task_msg = f"Task: I imagine something starting with a letter [{first_letter}]."

        return task_msg

    def _save_frame(self):
        """
        Takes the screenshot of the current scene. Adds the image and meta to matadata file.
        Image stored at:

        resources/images/{model1}--{model2}/experiment_n/image_episodeNumber_turnNumber.png

        returns: string
        """


        img_name = f"image_{self.instance_id}_{self.n_turns}.png"
        img_path = os.path.join(IMAGE_OUTPUT_PATH, self.experiment_name, self.folder_name)
        image: str = self.env_agent.screenshot(img_name, img_path)

        self._add_to_metadata(self.n_turns, image)
        return image

    def _add_to_metadata(self, turn: int, image: str):
        """
        Adds image and scene information to the metadata dictionary.

        """
        meta = {'image' : image,
                'metadata': self.env_agent.get_metadata()}

        self.metadata[turn] = meta

    def _store_instance_metadata(self):
        """
        Saves the metadata for the instance.
        Metadata contains information:
            for each turn
                image name.
                complete scene metadata.


        stored inside:
            resources/metadata/{model1}--{model2}/experiment_n/scene_metadata.json
        """

        try:
            full_path = os.path.join(
                METADATA_OUTPUT_PATH,
                self.experiment_name,
                self.folder_name
            )

            os.makedirs(full_path, exist_ok=True)
            file_path = os.path.join(full_path, 'scene_metadata.json')

            with open(file_path, 'w') as json_file:
                json.dump(self.metadata, json_file, indent=4)

            print(f"Metadata successfully saved to {file_path}")
            return file_path

        except IOError as e:
            print(f"Error writing metadata file: {e}")
            return None

        except TypeError as e:
            print(f"Error converting metadata to JSON: {e}")
            return None


class ISpyInteractiveBenchmark(GameBenchmark):
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

        return ISpyLookGameMaster(experiment, player_backends)


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
