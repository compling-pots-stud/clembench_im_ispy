from typing import Dict, Any, Optional, List, Tuple
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

    """
    AI2Thor uses right hand alignment:
    1) Z is forward
    2) X is right.

    The rotation that we get is the angle from the
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
        return -theta


    # change angle using controller.step(action="Teleport", rotation=dict(x=0, y=theta, z =0))


def get_object_in_frame(
        controller: Controller,
        object: Dict[str, Any],
        position_index: int = 0
    ) -> Optional[Tuple[Dict, Dict]]:


    """
    Adjusted for the Look-mode instance generator.
    Finds the closest positions, and returns the one matching the index we provide.
    Rotation -> given the position, rotation such that the object is in frame
    """



    # iteration refers to the iterations in the while loop when building a dataset.
    # if closest doesn't work, we select the next closest.
    available_positions: list[Dict[str, float]] = controller.step(action="GetReachablePositions").metadata["actionReturn"]
    if position_index >= len(available_positions):
        return None

    closest_positions: list[Dict[str, float]] = get_closest_positions(object["position"], available_positions)
    print(f'iteration: {position_index}')
    event = controller.step(action="Teleport", **closest_positions[position_index])  # move to the closest position to the object
    agent_position = event.metadata['agent']['position']  # get agent position

    angle: float = get_rotation(object["position"], agent_position)  # get rotation angle
    rotation = dict(x=0, y=angle,z=0)
    controller.step(action="Teleport", rotation=dict(x=0, y=angle, z=0))  # rotate

    return closest_positions[position_index], rotation

