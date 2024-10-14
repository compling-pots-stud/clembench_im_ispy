import json
import random
import os
import sys
import re
from pathlib import Path
from select import select
from navigation import get_quadrant

sys.path.append(str(Path(__file__).parent.parent.parent))
from clemgame.clemgame import GameInstanceGenerator

IMG_PATH = '/Users/dicaristic/PycharmProjects/playpen_im/clembench/games/i_spy/resources/images/images_v2'
METADATA = '/Users/dicaristic/PycharmProjects/playpen_im/clembench/games/i_spy/resources/metadata/metadata_v2.json'
TEACHER_TEMP = 'resources/prompts/teacher.template'
LEARNER_TEMP = 'resources/prompts/learner.template'
GAME_NAME = 'i_spy'
NUM_INSTANCES = 5
SEED = 58
MIN_GUESS_TURN = 5

def split_camel_case(word):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', word)

def split_words_only_if_camel_case(word_list):
    return [split_camel_case(word) if re.match(r'^[a-z]+[A-Z]|[A-Z][a-z]+[A-Z]', word) else word for word in word_list]

class IspyInstanceGenerator(GameInstanceGenerator):
    def __init__(self, game_name):
        super().__init__(game_name)
        self.game_name = game_name

    def on_generate(self):
        random.seed(SEED)

        init_teacher_prompt = self.load_template(TEACHER_TEMP)
        init_learner_prompt = self.load_template(LEARNER_TEMP)
        experiment = self.add_experiment('base')
        experiment['teacher_prompt'] = init_teacher_prompt
        experiment['learner_prompt'] = init_learner_prompt
        with open(METADATA, 'r') as f:
            img_metadata = json.load(f)
        img_list = list(img_metadata['scene_meta'].keys())
        game_id = 0
        samples = self.random_select_images(img_list)
        for sample in samples:

            img_name = sample
            visible_objects = img_metadata['scene_meta'][sample]['visible_objects']  # obj metadata
            visible_objects_val = [obj['objectType'] for obj in visible_objects]  # names of objs in frame (needs to preprocesed)
            # agent_position = img_metadata['scene_meta'][sample]['agent_position']
            # agent_rotation = img_metadata['scene_meta'][sample]['agent_rotation']
            frame_height = img_metadata['controller_meta']['height']
            frame_width = img_metadata['controller_meta']['width']


            # Apply camelCase splitting
            visible_objects_names = split_words_only_if_camel_case(visible_objects_val) # clean names of objects

            # Apply camelCase splitting
            selected_object: dict[str, any] = self.random_select_obj(visible_objects)
            selected_object_name: str = split_words_only_if_camel_case([selected_object['objectType']])[0]

            # closest and farthest (x,y) distance from top left corner (0,0)
            selected_object_position: list[int] = selected_object["frame_coords"] # position of object in 2d canvas
            quadrant: str = get_quadrant(selected_object_position, frame_width, frame_height) # get quadrant

            instance = self.add_game_instance(experiment, game_id)
            instance['image'] = os.path.join(IMG_PATH, img_name)
            instance['selected_object'] = selected_object_name
            instance['object_quadrant'] = quadrant
            # instance['object_position'] = selected_object_position
            instance['visible_objects'] = visible_objects_names
            # instance['agent_position']  = agent_position
            # instance['agent_rotation']  = agent_rotation
            instance['min_guess_turn'] = MIN_GUESS_TURN
            game_id += 1

    def random_select_images(self, img_list: list[str]):
        samples = random.sample(img_list, NUM_INSTANCES)
        return samples

    def random_select_obj(self, visible_objects: list[dict[str, any]]):
        return random.sample(visible_objects, 1)[0]


if __name__ == "__main__":
    IspyInstanceGenerator(GAME_NAME).generate()
