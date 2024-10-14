from typing import Dict, List, Any
import numpy as np
from ai2thor.controller import Controller

VIS_THRESHOLD = 3

# think about taking multiple positions for each item we select.
# also think about randomizing the angle with which we view the item.
# we don't always want it centralized
# also change object rotation WHEN POSSIBLE


def get_scenes() -> list[str]:
    kitchens = [f"FloorPlan{i}" for i in range(1, 31)]
    # living_rooms = [f"FloorPlan{200 + i}" for i in range(1, 31)]
    # bedrooms = [f"FloorPlan{300 + i}" for i in range(1, 31)]
    # bathrooms = [f"FloorPlan{400 + i}" for i in range(1, 31)]

    # scenes = kitchens + living_rooms + bedrooms + bathrooms
    scenes = kitchens

    return scenes


# Define a function to get the 10 closest positions between the agent and the object
def get_closest_positions(
        object_position: Dict[str, float],
        reachable_positions: List[Dict[str, float]],
) -> List[Dict[str, float]]:
    # Sort the positions by their distance to the object
    sorted_positions = sorted(
        reachable_positions,
        key=lambda pos: (pos['x'] - object_position['x']) ** 2 + (pos['z'] - object_position['z']) ** 2
    )

    # Return the top n closest positions
    return sorted_positions


# finds the rotation value such that object is in frame
def get_rotation(
        object_position: Dict[str, float],
        agent_position: Dict[str, float],
    ) -> float:


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
        return -theta


    # change angle using controller.step(action="Teleport", rotation=dict(x=0, y=theta, z =0))

# does not work, fix it
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

def get_object_center(frame_coordinates: list[int]) -> tuple[float, float]:

    x_mean = float(np.mean([frame_coordinates[0], frame_coordinates[2]]))
    y_mean = float(np.mean([frame_coordinates[1], frame_coordinates[3]]))

    return x_mean, y_mean

def get_object_in_frame(
        controller: Controller,
        object: Dict[str, Any],
        iteration: int = 0
    ) -> bool | None:
    # iteration refers to the iterations in the while loop when building a dataset.
    # if closest doesn't work, we select the next closest.
    available_positions: list[Dict[str, float]] = controller.step(action="GetReachablePositions").metadata["actionReturn"]
    if iteration >= len(available_positions):
        return None

    closest_positions: list[Dict[str, float]] = get_closest_positions(object["position"], available_positions)
    print(f'iteration: {iteration}')
    event = controller.step(action="Teleport", **closest_positions[iteration])  # move to the closest position to the object
    agent_position = event.metadata['agent']['position']  # get agent position

    angle: float = get_rotation(object["position"], agent_position)  # get rotation angle
    controller.step(action="Teleport", rotation=dict(x=0, y=angle, z=0))  # rotate

    return True

