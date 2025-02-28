import json
import random
import os
import sys
import re
from pathlib import Path
from select import select

from ai2thor.controller import Controller
from typing import Dict, List, Any
from dataset_utils import *

sys.path.append(str(Path(__file__).parent.parent.parent))
from clemgame.clemgame import GameInstanceGenerator

# IMG_PATH = '/Users/dicaristic/PycharmProjects/playpen_im/clembench/games/i_spy_interactive/resources/images/images_v2'
# METADATA = '/Users/dicaristic/PycharmProjects/playpen_im/clembench/games/i_spy_interactive/resources/metadata/metadata_v2.json'
# TEACHER_TEMP = 'resources/prompts/teacher.template'
# LEARNER_TEMP = 'resources/prompts/learner.template'
# MISTAKE_TEMP = 'resources/prompts/learner_mistake.template'
# MOVE_ERR_TEMP = 'resources/prompts/move_err.template'


# TEMPLATES = {
#     'static' : {
#         'TEACHER_TEMP' : '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/static/teacher.template',
#         'LEARNER_TEMP' : '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/static/learner.template',
#         'MISTAKE_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look'
#                         '/learner_mistake.template',
#         'MOVE_ERR_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look/move_err.template',
#     },
#     'look': {
#         'TEACHER_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look/teacher.template',
#         'LEARNER_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look/learner.template',
#         'MISTAKE_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look/learner_mistake.template',
#         'MOVE_ERR_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look/move_err.template',
#     },
#     'interactive': {
#         'TEACHER_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/interactive/teacher.template',
#         'LEARNER_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/interactive/learner.template',
#         'MISTAKE_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look/learner_mistake.template',
#         'MOVE_ERR_TEMP': '/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_final/resources/prompts/look/move_err.template',
#     }
#
# }

from clemgame.clemgame import GameInstanceGenerator

# Define the base path relative to this file's location
BASE_PATH = Path(__file__).parent.parent.parent

VARIANT = 'cot_on'

TEMPLATES = {
    'static' : {
        'TEACHER_TEMP' : str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/static/teacher.template'),
        'LEARNER_TEMP' : str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/static/learner.template'),
        'MISTAKE_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/learner_mistake.template'),
        'MOVE_ERR_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/move_err.template'),
    },
    'look': {
        'TEACHER_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/teacher.template'),
        'LEARNER_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/learner.template'),
        'MISTAKE_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/learner_mistake.template'),
        'MOVE_ERR_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/move_err.template'),
    },
    'interactive': {
        'TEACHER_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/interactive/teacher.template'),
        'LEARNER_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/interactive/learner.template'),
        'MISTAKE_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/learner_mistake.template'),
        'MOVE_ERR_TEMP': str(BASE_PATH / f'games/i_spy_final/resources/prompts/{VARIANT}/look/move_err.template'),
    }
}


GAME_NAME = 'i_spy_final'
NUM_INSTANCES = 12
SEED = 58
MIN_GUESS_TURN = 5
K = 15


POSITION_INDEX_LIST = [0, 1, 2, 3, 4, 5]
ROTATION_VALUE_LIST = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
HORIZON_VALUE_LIST = [-30, 0, 30, 60]

# OBJECT TYPES
OBJECT_EXCLUSION_LIST = ['Bathtub', 'Blinds', 'Bed', 'BathtubBasin', 'Cabinet', 'CoffeeTable', 'CounterTop',
                         'Curtains', 'Desk','DiningTable', 'Dresser','EggCracked', 'Floor','Fridge','LettuceSliced',
                         'Mirror', 'PotatoSliced', 'ShelvingUnit', 'ShowerCurtain', 'ShowerDoor', 'ShowerGlass',
                         'Sofa', 'TargetCircle', 'TomatoSliced', 'Window']

GAME_MODES = ['static', 'look', 'interactive']
# GAME_MODES = ['look']
def split_camel_case(word):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', word)

def split_words_only_if_camel_case(word_list):
    return [split_camel_case(word) if re.match(r'^[a-z]+[A-Z]|[A-Z][a-z]+[A-Z]', word) else word for word in word_list]



def get_scenes() -> list[str]:
    kitchens = [f"FloorPlan{i}" for i in range(1, 31)]
    living_rooms = [f"FloorPlan{200 + i}" for i in range(1, 31)]
    bedrooms = [f"FloorPlan{300 + i}" for i in range(1, 31)]
    bathrooms = [f"FloorPlan{400 + i}" for i in range(1, 31)]

    # Exclude FloorPlan8 from kitchens
    kitchens = [scene for scene in kitchens if scene != 'FloorPlan8']

    # Select 3 random examples from each room type
    selected_kitchens = random.sample(kitchens, 3)
    selected_living_rooms = random.sample(living_rooms, 3)
    selected_bedrooms = random.sample(bedrooms, 3)
    selected_bathrooms = random.sample(bathrooms, 3)

    # Combine all selected scenes
    scenes = selected_kitchens + selected_living_rooms + selected_bedrooms + selected_bathrooms

    return scenes


class IspyFinalInstanceGenerator(GameInstanceGenerator):
    def __init__(self, game_name):
        super().__init__(game_name)
        self.game_name = game_name


    def on_generate(self):
        random.seed(SEED)


        scenes = get_scenes()

        for game_mode in GAME_MODES:
            # load prompts
            init_teacher_prompt = self.load_template(TEMPLATES[game_mode]['TEACHER_TEMP'])
            init_learner_prompt = self.load_template(TEMPLATES[game_mode]['LEARNER_TEMP'])
            init_mistake_prompt = self.load_template(TEMPLATES[game_mode]['MISTAKE_TEMP'])
            init_move_err_prompt = self.load_template(TEMPLATES[game_mode]['MOVE_ERR_TEMP'])

            experiment = self.add_experiment(f'{game_mode}')
            experiment['teacher_prompt'] = init_teacher_prompt
            experiment['learner_prompt'] = init_learner_prompt
            experiment['learner_mistake_prompt'] = init_mistake_prompt
            experiment['move_error_prompt'] = init_move_err_prompt


            game_id = 0
            for i in range(NUM_INSTANCES):
                if i == 0:
                    controller = Controller(
                        agentMode="default",
                        visibilityDistance=8,
                        scene=scenes[0],
                        # step sizes
                        gridSize=0.5,
                        snapToGrid=True,

                        # image modalities
                        renderDepthImage=True,
                        renderClassImage=True,
                        renderObjectImage=True,
                        renderInstanceSegmentation=True,
                        # camera properties
                        width=800,
                        height=600,
                        fieldOfView=90,
                    )

                else:
                    controller.reset(scene=scenes[i])  # change to new scene
                    # controller.step(action="RandomizeMaterials") # used to randomize materials so that scenes look different.
                print(f'current scene: {scenes[i]}')
                # available_positions: list[Dict[str, float]] = controller.step(action="GetReachablePositions").metadata[
                #     "actionReturn"]
                #
                # starting_position = self.random_select_obj(available_positions)[0]

                instance = self.add_game_instance(experiment, game_id)
                objects = self.get_objects(controller)

                # Apply camelCase splitting
                # select only objects with no duplicates

                # EG IS IN THE FRIDGE.
                #  IF ITEM IS NOT VISIBLE AFTER 10 ATTEMPTS, CONTINUE WITH NEXT ITEM.

                selected_objects = self.random_select_obj(objects)

                for k in range(K):
                    selected_object = selected_objects[k]
                    sel_object_type = selected_object['objectType']
                    if sel_object_type in OBJECT_EXCLUSION_LIST:
                        continue

                    unique = self.obj_is_unique(sel_object_type, objects)
                    if unique:

                        # default values used in the static game mode.
                        selected_object_name = split_words_only_if_camel_case([selected_object['objectType']])[0]
                        agent_position, agent_rotation = get_object_in_frame(controller, selected_object)
                        agent_horizon = 0
                        if agent_position:
                            break
                        else:
                            continue

                if game_mode =='look':
                    agent_rotation['y'] = self.random_select_obj(ROTATION_VALUE_LIST, 1)[0]  # left/right rotation
                    agent_horizon = self.random_select_obj(HORIZON_VALUE_LIST, 1)[0]  # up/down position

                if game_mode =='interactive':
                    available_positions: list[Dict[str, float]] = controller.step(action="GetReachablePositions").metadata[
                        "actionReturn"]

                    agent_position = self.random_select_obj(available_positions, 1)[0]
                    agent_rotation['y'] = self.random_select_obj(ROTATION_VALUE_LIST, 1)[0]  # left/right rotation
                    agent_horizon = self.random_select_obj(HORIZON_VALUE_LIST, 1)[0]  # up/down position


                instance['scene'] = scenes[i]
                instance['selected_object'] = selected_object_name
                instance['selected_object_id'] = selected_object['objectId']
                instance['starting_position'] = agent_position
                instance['starting_rotation'] = agent_rotation
                instance['starting_horizon'] = agent_horizon
                instance['min_guess_turn'] = MIN_GUESS_TURN

                game_id += 1

            controller.stop()
    def get_objects(self, controller: Controller) -> list[dict[str, Any]]:
        obj_in_scene = controller.last_event.metadata['objects']
        objects = [obj for obj in obj_in_scene]
        return objects

    def random_select_images(self, some_list: list[str]):
        samples = random.sample(some_list, NUM_INSTANCES)
        return samples

    def random_select_obj(self, objects: list, n = K):
        return random.sample(objects, n)

    def obj_is_unique(self, selected_object_type: str, objects: list):
        # selected object type and all available objects
        # we want the selected object to be unique
        unique_counter = 0

        for object in objects:
            if object['objectType'] == selected_object_type:
                unique_counter += 1
            if unique_counter > 1:
                return False

        return True



if __name__ == "__main__":
    IspyFinalInstanceGenerator(GAME_NAME).generate()
