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
    living_rooms = [f"FloorPlan{200 + i}" for i in range(1, 31)]
    bedrooms = [f"FloorPlan{300 + i}" for i in range(1, 31)]
    bathrooms = [f"FloorPlan{400 + i}" for i in range(1, 31)]

    scenes = kitchens + living_rooms + bedrooms + bathrooms

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

# Function to determine the quadrant of the object in the agent's view
def get_quadrant(object_position: Dict[str, float],
                 agent_position: Dict[str, float],
                 agent_rotation: Dict[str, float]) -> str:
    local_position = get_frame_position(object_position, agent_position, agent_rotation)

    x_rel, z_rel = local_position
    if x_rel < 0 and z_rel > 0:
        return "Top-left"
    elif x_rel > 0 and z_rel > 0:
        return "Top-right"
    elif x_rel < 0 and z_rel < 0:
        return "Bottom-left"
    else:
        return "Bottom-right"

# Function to transform object's global position to the agent's local frame
def get_frame_position(object_position: Dict[str, float], agent_position: Dict[str, float], agent_rotation: Dict[str, float]) -> np.ndarray:
    # Translate object position relative to agent
    rel_position = np.array([
        object_position['x'] - agent_position['x'],
        object_position['z'] - agent_position['z']
    ])

    # Get the agent's yaw (rotation around y-axis) and create rotation matrix
    yaw = np.deg2rad(agent_rotation['y'])  # Convert yaw to radians
    rotation_matrix = np.array([
        [np.cos(yaw), -np.sin(yaw)],
        [np.sin(yaw),  np.cos(yaw)]
    ])

    # Rotate the relative position to get the local position in the agent's view
    local_position = np.dot(rotation_matrix, rel_position)
    return local_position


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

