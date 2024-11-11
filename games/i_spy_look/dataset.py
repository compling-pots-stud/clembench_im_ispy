from dataset_utils import *
import random
import os
import json
from PIL import Image
import time

DOWNSIZED_IMAGE_OUTPUT_PATH = "resources/images/images_v2_downsized"
IMAGE_OUTPUT_PATH = "resources/images/images_v2"
METADATA_OUTPUT_PATH = "resources/metadata"
METADATA_FILENAME = "metadata_v2.json"

SEED = 21
SAMPLE_SIZE = 10


# Controller setup params
STARTING_SCENE = None
GRID_SIZE = 0.25
SNAP_TO_GRID = True

WIDTH = 800
HEIGHT = 600
FOV = 110


# add randomization with controller.step(action="RandomizeMaterials")
# if necessary, can generate more data and explore material recognition.
# TBD in the future
# think about resampling if a scene cannot be completed

def build_dataset():
    random.seed(SEED)
    all_scenes = get_scenes()
    controller_meta = {
                    'random_seed' : SEED,
                    'sample_size': SAMPLE_SIZE,
                    'min_obj_in_frame': MIN_OBJ_IN_FRAME,
                    'starting_scene' : STARTING_SCENE,
                    'grid_size' : GRID_SIZE,
                    'snap_to_grid' : SNAP_TO_GRID,
                    'width' : WIDTH,
                    'height' : HEIGHT,
                    'fov' : FOV
    }

    metadata = dict()
    metadata['controller_meta'] = controller_meta
    metadata['scene_meta'] = dict()
    print(metadata)
    # initialize controller with one scene
    # define parameters that can be changed upon initialization
    start_scene = STARTING_SCENE if STARTING_SCENE else all_scenes[0]
    all_scenes.remove('FloorPlan8')
    controller = Controller(
                            agentMode="default",
                            visibilityDistance=5,
                            scene=start_scene,
                            # step sizes
                            gridSize=GRID_SIZE,
                            snapToGrid=SNAP_TO_GRID,

                            # image modalities
                            renderDepthImage=True,
                            renderClassImage=True,
                            renderObjectImage=True,
                            renderInstanceSegmentation=True,
                            # camera properties
                            width=WIDTH,
                            height=HEIGHT,
                            fieldOfView=FOV
    )
    if STARTING_SCENE:
        all_scenes.remove(STARTING_SCENE)
        all_scenes.insert(0, STARTING_SCENE)
    for scene in all_scenes:
        print(f'Stating scene: {scene}')
        if scene != start_scene:
            controller.reset(scene = scene) # change to new scene
        objects = controller.last_event.metadata['objects']
        selected_objects = random.sample(objects, SAMPLE_SIZE) # select frames centered arround each object.

        for inx, obj in enumerate(selected_objects):
            controller.step(action="RandomizeMaterials")
            print(obj['objectType'])
            iteration = 0
            while True:
                time.sleep(1)
                status = get_object_in_frame(controller, obj, iteration)
                if not status: # if we ran out of iterations, continue to next object
                    print(f"No frames for {obj['objectType']}")
                    break

                if frame_accepted(controller):
                    visible_objects = get_visible(controller)
                    name = f'{scene}_{inx}.png'
                    # add 2d xy coordinates of each object to metadata
                    try:
                        visible_objects = get_2d(controller, visible_objects)
                    except:
                        print("Error, no 2d for objects")
                        iteration += 1
                        continue
                    save_image(controller, name)

                    #add to metadata
                    metadata['scene_meta'][name] = {
                                    'visible_objects': visible_objects,
                                    'agent_position' : controller.last_event.metadata['agent']['position'],
                                    'agent_rotation' : controller.last_event.metadata['agent']['rotation'],
                                        }
                    break
                else:
                    iteration +=1
                    continue
        print(f'{scene} complete!' )
    print('All scenes done, saving metadata.')
    save_metadata(metadata)



def frame_accepted(controller: Controller) -> bool:
    # we want to make sure that more than N items are visible in each scene.
    # It defeats the purpose if there is only a single item visible.

    visible: list = get_visible(controller)
    print(f'visible: {len(visible)}')
    if len(visible) >= MIN_OBJ_IN_FRAME:
        return True
    else:
        return False


def get_visible(controller: Controller) -> list[dict[str, Any]]:
    obj_in_scene = controller.last_event.metadata['objects']
    visible = [obj for obj in obj_in_scene if obj['visible'] == True]
    return visible


def save_image(controller: Controller, name: str):
    image = controller.last_event.frame
    img = Image.fromarray(image, 'RGB')
    full_path = os.path.join(IMAGE_OUTPUT_PATH, name)

    # Ensure the output directory exists
    os.makedirs(IMAGE_OUTPUT_PATH, exist_ok=True)
    img.save(full_path)


def save_metadata(metadata: Dict[str, Any]):
    os.makedirs(METADATA_OUTPUT_PATH, exist_ok=True)
    json_filepath = os.path.join(METADATA_OUTPUT_PATH, METADATA_FILENAME)
    with open(json_filepath, 'w') as json_file:
        json.dump(metadata, json_file, indent=4)

    print(f"Metadata saved to {json_filepath}")

def show_image(controller):
    image = controller.last_event.frame
    img = Image.fromarray(image, 'RGB')
    img.show()




def resize_and_save_images(input_folder: str, output_folder: str, size: tuple[int, int]):
    """
    Resizes images from input_folder and saves them to output_folder.
    :param input_folder: Path to the folder containing the original images.
    :param output_folder: Path to the folder where resized images will be saved.
    :param size: Tuple (width, height) specifying the new size for the images.
    """
    os.makedirs(output_folder, exist_ok=True)

    for img_name in os.listdir(input_folder):
        img_path = os.path.join(input_folder, img_name)

        with Image.open(img_path) as img:
            img_resized = img.resize(size, Image.LANCZOS)
            save_path = os.path.join(output_folder, img_name)
            img_resized.save(save_path)
            print(f"Saved resized image to {save_path}")

def get_2d(controller, visible):
    for object in visible:
        obj_id = object['objectId']
        frame_coords = controller.last_event.instance_detections2D[obj_id]
        object['frame_coords'] = frame_coords


    return visible


if __name__ == "__main__":
    build_dataset()
    # see which size fits better
    # resize_and_save_images(IMAGE_OUTPUT_PATH, DOWNSIZED_IMAGE_OUTPUT_PATH, (120, 100))
