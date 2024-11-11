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

IMG_PATH = '/Users/dicaristic/PycharmProjects/playpen_im/clembench/games/i_spy_interactive/resources/images/images_v2'
METADATA = '/Users/dicaristic/PycharmProjects/playpen_im/clembench/games/i_spy_interactive/resources/metadata/metadata_v2.json'
TEACHER_TEMP = 'resources/prompts/teacher.template'
LEARNER_TEMP = 'resources/prompts/learner.template'
MISTAKE_TEMP = 'resources/prompts/learner_mistake.template'
MOVE_ERR_TEMP = 'resources/prompts/move_err.template'


GAME_NAME = 'i_spy_look'
NUM_INSTANCES = 5
SEED = 58
MIN_GUESS_TURN = 5
K = 5


POSITION_INDEX_LIST = [0, 1, 2, 3, 4, 5]
ROTATION_VALUE_LIST = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
HORIZON_VALUE_LIST = [-30, 0, 30, 60]



def split_camel_case(word):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', word)

def split_words_only_if_camel_case(word_list):
    return [split_camel_case(word) if re.match(r'^[a-z]+[A-Z]|[A-Z][a-z]+[A-Z]', word) else word for word in word_list]

def get_scenes() -> list[str]:
    # kitchens = [f"FloorPlan{i}" for i in range(1, 31)]
    # living_rooms = [f"FloorPlan{200 + i}" for i in range(1, 31)]
    # bedrooms = [f"FloorPlan{300 + i}" for i in range(1, 31)]
    # bathrooms = [f"FloorPlan{400 + i}" for i in range(1, 31)]

    # scenes = kitchens + living_rooms + bedrooms + bathrooms
    scenes = ["FloorPlan1", "FloorPlan201","FloorPlan301","FloorPlan401","FloorPlan21","FloorPlan211","FloorPlan311"]

    return scenes


class IspyLookInstanceGenerator(GameInstanceGenerator):
    def __init__(self, game_name):
        super().__init__(game_name)
        self.game_name = game_name


    def on_generate(self):
        random.seed(SEED)


        scenes = get_scenes()


        # load prompts
        init_teacher_prompt = self.load_template(TEACHER_TEMP)
        init_learner_prompt = self.load_template(LEARNER_TEMP)
        init_mistake_prompt = self.load_template(MISTAKE_TEMP)
        init_move_err_prompt = self.load_template(MOVE_ERR_TEMP)
        experiment = self.add_experiment('look')
        experiment['teacher_prompt'] = init_teacher_prompt
        experiment['learner_prompt'] = init_learner_prompt
        experiment['learner_mistake_prompt'] = init_mistake_prompt
        experiment['move_error_prompt'] = init_move_err_prompt


        game_id = 0
        for i in range(NUM_INSTANCES):
            if i == 0:
                controller = Controller(
                    agentMode="default",
                    visibilityDistance=20,
                    scene=scenes[0],
                    # step sizes
                    gridSize=0.5,
                    snapToGrid=True,

                    # image modalities
                    renderDepthImage=False,
                    renderClassImage=False,
                    renderObjectImage=False,
                    renderInstanceSegmentation=True,
                    # camera properties
                    width=800,
                    height=600,
                    fieldOfView=90
                )
            else:
                controller.reset(scene=scenes[i])  # change to new scene
                # controller.step(action="RandomizeMaterials") # used to randomize materials so that scenes look different.

            # available_positions: list[Dict[str, float]] = controller.step(action="GetReachablePositions").metadata[
            #     "actionReturn"]
            #
            # starting_position = self.random_select_obj(available_positions)[0]

            instance = self.add_game_instance(experiment, game_id)
            objects = self.get_objects(controller)

            # Apply camelCase splitting
            # select only objects with no duplicates
            selected_objects = self.random_select_obj(objects)

            for k in range(K):
                selected_object = selected_objects[k]
                sel_object_type = selected_object['objectType']
                unique = self.obj_is_unique(sel_object_type, objects)

                if unique:
                    break

            selected_object_name = split_words_only_if_camel_case([selected_object['objectType']])[0]

            position_index = self.random_select_obj(POSITION_INDEX_LIST, 1)[0]
            agent_position, agent_rotation = get_object_in_frame(controller, selected_object, position_index)
            agent_rotation['y'] = self.random_select_obj(ROTATION_VALUE_LIST, 1)[0] # left/right rotation
            agent_horizon = self.random_select_obj(HORIZON_VALUE_LIST, 1)[0] # up/down position


            instance['scene'] = scenes[i]
            instance['selected_object'] = selected_object_name
            instance['selected_object_id'] = selected_object['objectId']
            instance['starting_position'] = agent_position
            instance['starting_rotation'] = agent_rotation
            instance['starting_horizon'] = agent_horizon
            instance['min_guess_turn'] = MIN_GUESS_TURN
            game_id += 1

    def get_objects(self, controller: Controller) -> list[dict[str, Any]]:
        obj_in_scene = controller.last_event.metadata['objects']
        visible = [obj for obj in obj_in_scene]
        return visible

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
    IspyLookInstanceGenerator(GAME_NAME).generate()
