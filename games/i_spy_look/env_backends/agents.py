from ai2thor.controller import Controller
from PIL import Image
import os

"""
Pitch: X axis -> Up/Down 
Roll: Z axis -> rolling movement
Yaw: Y axis -> turning 


For look fn, we want left/right movement to control the Yaw,
and up down to controll the pitch
"""


IMAGE_OUTPUT_PATH = ""


class BaseEnvironment:
    def __init__(self, **config):
        """
        Initialize the base agent with configuration settings.
        Individual agents (e.g., AI2ThorAgent) will inherit this class
        and extend or modify behaviors specific to their environments.

        Specify all the generic functions here, it should serve as a base framework.
        """
        self.config = config
        self.controller = None  # To be initialized in the subclass

    def move(self, direction: str):
        """Generic move function, to be implemented by each subclass."""
        raise NotImplementedError("Subclasses must implement this method.")

    def look(self, direction: str):
        """Generic look function to shift the agents POV off-center."""
        raise NotImplementedError("Subclasses must implement this method.")

    def turn(self, direction: str):
        """Generic turn function to adjust agent's orientation."""
        raise NotImplementedError("Subclasses must implement this method.")

    def interact(self):
        """Generic look function to adjust agent's orientation."""
        raise NotImplementedError("Subclasses must implement this method.")

    def reset_controller(self, **kwargs):
        """Reset the environment controller to initial conditions."""
        if self.controller:
            self.controller.reset(**kwargs)
        else:
            print("Controller not initialized.")

    def get_controller_settings(self):
        """Retrieve current controller settings, if available."""
        if self.controller:
            return self.controller.__dict__
        else:
            return "Controller not initialized."

    def save_frame(self):
        """Take the screenshot of the current frame"""
        raise NotImplementedError("Subclasses must implement this method.")



"""
Base functionality currently works, however, it probably needs further configuration
1) No feedback when a limit is reached -> either movement up/down or hitting an object.
    - We need this to be able to prompt the LLM that the action is not possible.
2) Storing and loading images.

"""

class AI2ThorEnvironment(BaseEnvironment):
    def __init__(self, **config):
        super().__init__(**config)
        self.controller = Controller(**config)
        self.event = None

    def move(self, direction: str):
        """Translate the universal move command into AI2Thor actions."""
        if direction.lower() == "forward":
            self.event = self.controller.step("MoveAhead")
        elif direction.lower() == "backward":
            self.event = self.controller.step("MoveBack")
        elif direction.lower() == "left":
            self.event =   self.controller.step("MoveLeft")
        elif direction.lower() == "right":
            self.event = self.controller.step("MoveRight")
        else:
            raise ValueError("Invalid direction. Use 'forward', 'backward', 'left', or 'right'.")

        # self.event = self.controller.step(action="Done")
        valid, error = self.check_validity()
        if valid:
            self.event = self.controller.step(action="Done")
        else:
            raise ValueError(f"Error encountered: {error}")


    # doesn't work. It has a delay when turning the camera. Goes in the opposite direction first.
    def look(self, direction: str):
        """Rotate the agent by a specific angle."""
        print(direction)
        if direction.lower()=="up":
            self.event =  self.controller.step(
                action="LookUp",
                degrees=30
            )

        elif direction.lower()=="down":
            self.event =  self.controller.step(
                action="LookDown",
                degrees=30
            )

        elif direction.lower()=="left":
            self.event = self.controller.step(
                action="RotateLeft",
                degrees=30
            )

        elif direction.lower()=="right":
            self.event =  self.controller.step(
                action="RotateRight",
                degrees=30
            )
        else:
            raise ValueError("Invalid direction. Use 'up', 'down', 'left', or 'right'.")


        valid, error = self.check_validity()
        if valid:
            self.event = self.controller.step(action="Done")
        else:
            raise ValueError(f"Error encountered: {error}")

    def turn(self, direction: str):
        """turn the agent to a specific side."""
        if direction.lower()=="left":
            self.event =  self.controller.step(
                action="RotateLeft",
                degrees=90
            )

        elif direction.lower()=="right":
            self.event = self.controller.step(
                action="RotateRight",
                degrees=90
            )

        elif direction.lower()=="behind":
            self.event =  self.controller.step(
                action="RotateLeft",
                degrees=180
            )
        else:
            raise ValueError("Invalid direction. Use 'behind', 'left', or 'right'.")


        valid, error = self.check_validity()
        if valid:
            self.event = self.controller.step(action="Done")
        else:
            raise ValueError(f"Error encountered: {error}")

    def teleport(self, **positions):

        self.event = self.controller.step(action="Teleport", **positions)
        valid, error = self.check_validity()

        if valid:
            self.event = self.controller.step(action="Done")
        else:
            raise ValueError(f"Error encountered: {error}")

    def check_validity(self) -> tuple[bool, None | str]:

        metadata = self.get_metadata()
        if not metadata['lastActionSuccess']:
            return False, metadata['errorMessage']

        return True, None

    def save_frame(self, name, path ):
        """
        Save the last frame so that it can be given to the model(s).
        """
        img = self.controller.last_event.frame
        img = Image.fromarray(img, 'RGB')
        full_path = os.path.join(path, name)


        # Ensure the output directory exists
        os.makedirs(path, exist_ok=True)
        img = img.resize((250, 150), Image.Resampling.LANCZOS)
        img.save(full_path)
        return full_path

    def get_available_positions(self):

        positions = self.controller.step(action="GetReachablePositions").metadata["actionReturn"]
        return positions


    def get_metadata(self):
        """returns metadata"""

        return self.event.metadata

    def get_object_in_2d(self, object_id):
        frame_coords = self.controller.last_event.instance_detections2D[object_id]
        return frame_coords