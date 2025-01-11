import json
from os import environ
from games.i_spy_interactive.env_backends.agents import AI2ThorEnvironment  # Import your specific agent classes
from typing import Dict, List, Any
import numpy as np
from pathlib import Path

BASE_PATH = Path(__file__).parent.parent.parent

CONFIG_PATH = str(BASE_PATH/'i_spy_final/env_backends/configs/environments.json')
# CONFIG_PATH = ("/Users/dicaristic/PycharmProjects/clembench_im/games/i_spy_look/env_backends/configs"
#                "/environments.json")

MOVE_DIRECTIONS = {
    "forward" : True,
    "backward": True,
    "left" : True,
    "right" : True,
}

LOOK_DIRECTIONS = {
    "left": True,
    "right": True,
    "up": True,
    "down": True,
}

TURN_DIRECTIONS = {
    "left": True,
    "right": True,
    "behind": True,
}

FOV = 90 # replace this to be dynamic
# remove all magic numbers from all files.

def load_config(environment_name):
    with open(CONFIG_PATH, "r") as config_file:
        config_data = json.load(config_file)
    return config_data.get(environment_name, {})

def get_object_center(frame_coordinates: list[int]) -> tuple[float, float]:

    x_mean = float(np.mean([frame_coordinates[0], frame_coordinates[2]]))
    y_mean = float(np.mean([frame_coordinates[1], frame_coordinates[3]]))

    return x_mean, y_mean

def get_quadrant(frame_coordinates: list[int], frame_width: int, frame_height: int) -> str:

    # get object center

    x_mean, y_mean = get_object_center(frame_coordinates)

    # split into 9 sub_cells
    # top left corne is (0,0)
    x_thresholds = [frame_width/3, 2*frame_width/3]
    y_thresholds = [2*frame_height/3, frame_height/3]


    # Determine horizontal position
    if x_mean < x_thresholds[0]:
        horizontal = "Left"
    elif x_mean > x_thresholds[1]:
        horizontal = "Right"
    else:
        horizontal = "Center"

    # Determine vertical position
    if y_mean > y_thresholds[0]:
        vertical = "Bottom"
    elif y_mean < y_thresholds[1]:
        vertical = "Top"
    else:
        vertical = "Middle"

    return f"{vertical}-{horizontal}"

class Agent:
    def __init__(self, environment: str):
        self.environment = environment
        self.config = load_config(environment)
        self.agent = self.set_up(self.config)
        self.error = None


    def set_up(self, config: dict):
        if self.environment == "AI2THOR":
            return AI2ThorEnvironment(**config)
        raise ValueError(f"Unsupported environment: {self.environment}")

    def move(self, direction: str):
        if hasattr(self.agent, 'move'):
            if MOVE_DIRECTIONS.get(direction.lower()):
                try:
                    self.agent.move(direction.lower())
                    self.error = None
                except Exception as e:
                    self.error = str(e)
                    print(f"Error while moving: {e}")
            else:
                self.error = f"Unsupported Move Direction: {direction}"
                print(self.error)
        else:
            raise NotImplementedError("Move method not implemented for this agent.")

    def look(self, direction: str):
        if hasattr(self.agent, 'look'):
            if LOOK_DIRECTIONS.get(direction.lower()):
                try:
                    self.agent.look(direction.lower())
                    self.error = None
                except Exception as e:
                    self.error = str(e)
                    print(f"Error while looking: {e}")
            else:
                self.error = f"Unsupported Look Direction: {direction}"
                print(self.error)
        else:
            raise NotImplementedError("Look method not implemented for this agent.")

    def turn(self, direction: str):
        if hasattr(self.agent, 'turn'):
            if TURN_DIRECTIONS.get(direction.lower()):
                try:
                    self.agent.turn(direction.lower())
                    self.error = None
                except Exception as e:
                    self.error = str(e)
                    print(f"Error while turning: {e}")
            else:
                self.error = f"Unsupported Turn Direction: {direction}"
                print(self.error)
        else:
            raise NotImplementedError("Turn method not implemented for this agent.")

    def teleport(self, position: dict, rotation: dict = None, horizon: int = None):
        try:
            self.agent.teleport(position, rotation, horizon)
            self.error = None

        except ValueError as e:
            self.error = str(e)  # Store the error message
            print(f"Error while turning: {e}")  # Optional: Print the error

    def get_rotation(self,
            object_position: Dict[str, float],
            agent_position: Dict[str, float],
    ) -> float:
        """
        Returns the angle relative to the agent's position.
        The angle measured from the perspective of Z = 1
        Assumes that the agent is facing forward (Z direction).
        To obtain angle between the Agent's POV and Object's POV,
        we must subtract Agent's Y rotation from theta obtained here.

        Since theta is [0,180], if the object is to the left of the agent,
        we need to subtract Theta from 360 - This gives us values in the range [180-360].

        """
        delta_x = object_position['x'] - agent_position['x']
        delta_z = object_position['z'] - agent_position['z']

        AB = np.sqrt(delta_x ** 2 + delta_z ** 2)
        AC = 1  # Since point C is directly in front along Z-axis, the distance is 1 unit
        BC = np.sqrt(delta_x ** 2 + (delta_z - 1) ** 2)

        # Apply the Law of Cosines to calculate theta
        cos_theta = (AB ** 2 + AC ** 2 - BC ** 2) / (2 * AB * AC)
        theta = np.degrees(np.arccos(cos_theta))

        if object_position['x'] > agent_position['x']:
            return theta
        else:

            return 360-theta

    def rotation_to_direction(self,
                              object_position: Dict[str, float],
                              agent_position: Dict[str, float],
                              agent_rotation: Dict[str, float]
                              ):

        theta = self.get_rotation(object_position, agent_position)

        agent_y = agent_rotation['y']
        rotation = theta - agent_y
        rotation = (theta - agent_y + 360) % 360  # Normalize to [0, 360)

        print(f'rotation: {rotation}')

        # potentially account for cases when object is in POV (i.e. ahead).
        # if y is larger than theta, object is to the left of the agent.


        half_fov = FOV / 2
        if -half_fov <= rotation <= half_fov or 360 - half_fov <= rotation <= 360:
            return 'up or down'

        # Determine left or right direction if outside FOV
        if rotation < 180:
            return 'right'
        else:
            return 'left'


    def screenshot(self, name, path):

        img = self.agent.save_frame(name, path)
        return img

    def get_objects(self, visible: bool):
        meta = self.get_metadata()

        # only visible objects
        if visible:
            objects = [obj for obj in meta['objects'] if obj['visible'] == True]
        else:
            objects = [obj for obj in meta['objects']]

        return objects

    def get_available_positions(self):

        available_positions: list[Dict[str, float]] = self.agent.get_available_positions()
        return available_positions

    def get_error(self):
        return self.error

    def get_metadata(self):
        return self.agent.get_metadata()

    def print_errors(self):
        """Optional method to print all logged errors."""
        print(self.error)

    def reset(self, **kwargs):
        self.agent.reset_controller(**kwargs)

    def get_object_position(self, object_id):
        position: list | None = self.agent.get_object_in_2d(object_id)

        return position
