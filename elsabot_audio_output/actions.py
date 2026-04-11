from queue import Queue, Empty
from enum import Enum
import emoji

import rclpy

from robot_head_interfaces.msg import Smile, HeadTilt
from std_msgs.msg import Bool, String

class ActionCategory(Enum):
    Smile = 0
    HeadMovement = 1

class SmileActionType(Enum):
    NoChange = 0
    BigSmile = 1
    NormalSmile = 2
    SmallSmile = 3
    NoSmile = 4

class HeadMovementActionType(Enum):
    NoChange = 0
    Normal = 1
    TiltForward = 2
    TiltLeft = 3

class Action:
    def __init__(self, action_category, silence_duration, action_duration):
        self.action_category = action_category
        self.silence_duration = silence_duration
        self.action_duration = action_duration

    def get_silence_duration(self):
        return self.silence_duration

    def get_action_duration(self):
        return self.action_duration        

    def get_action_category(self):
        return self.action_category

class SmileAction(Action):
    def __init__(self, action_type, silence_duration, action_duration):
        Action.__init__(self, ActionCategory.Smile, silence_duration, action_duration)
        self.action_type = action_type

class HeadMovementAction(Action):
    def __init__(self, action_type, silence_duration, action_duration):
        Action.__init__(self, ActionCategory.HeadMovement, silence_duration, action_duration)
        self.action_type = action_type

def create_actions_from_emoji(emoji):
    big_smile_if_emoji = "😀😃😄😁😆😅🤣😂😉🥰😍🤩😘😗☺️🤗🤑😝🤪😜😛😋🥲😙😚🥳"        
    normal_smile_if_emoji = "🙂🙂🙃🫠😊😇"
    small_smile_if_emoji = "🫡😐️😑"
    no_smile_if_emoji = "🤐🤨😌🤥😮‍💨😒😏😶‍🌫️🫥😶😔😪🤤😴😷🤒🤕🤢🤮🤧🤓😎😵‍💫😵🥴😕🫤😟🙁☹️😦😧😨😰😥😢😭😱😠😡😤🥱😫😩😓😞😣😖"        
    tilt_head_down_if_emoji = "🙃🤥😦😧😨😰😥😢😭😫😩😓😞😣😖🤦🤦‍♂️🤦‍♀️"        
    tilt_head_left_if_emoji = "🤔🤨😕🫤"        

    #interpretation = emoji.demojize(token)
    #self.logger.info(f"{token} ({interpretation})")

    actions = []

    silence_duration = 2000
    action_duration = 1500

    if emoji in big_smile_if_emoji:
        actions.append(SmileAction(SmileActionType.BigSmile, silence_duration, action_duration))
    elif emoji in normal_smile_if_emoji:
        actions.append(SmileAction(SmileActionType.NormalSmile, silence_duration, action_duration))
    elif emoji in small_smile_if_emoji:
        actions.append(SmileAction(SmileActionType.SmallSmile, silence_duration, action_duration))
    elif emoji in no_smile_if_emoji:
        actions.append(SmileAction(SmileActionType.NoSmile, silence_duration, action_duration))

    if emoji in tilt_head_down_if_emoji:
        actions.append(HeadMovementAction(HeadMovementActionType.TiltForward, silence_duration, action_duration))
    elif emoji in tilt_head_left_if_emoji:
        actions.append(HeadMovementAction(HeadMovementActionType.TiltLeft, silence_duration, action_duration))

    return actions

class SmileActionExecutor:
    def __init__(self, logger, node):
        self.publisher_head_smile = node.create_publisher(Smile, '/head/smile', 10)
        self.logger = logger
        self.queue = Queue()    

    # This is likely called during from the audio sample request loop.  As such
    # do minimal processing and avoid delaying the current thread
    def pre_process(self, action):
        self.queue.put(action)

    def complete_pending(self):
        while(True):
            try:
                action = self.queue.get_nowait()
                msg = Smile()
                msg.level = 1
                if action.action_type == SmileActionType.NoChange:
                    return
                elif action.action_type == SmileActionType.NoSmile: 
                    msg.level = 0
                elif action.action_type == SmileActionType.SmallSmile: 
                    msg.level = 1
                elif action.action_type == SmileActionType.NormalSmile: 
                    msg.level = 3
                elif action.action_type == SmileActionType.BigSmile: 
                    msg.level = 5

                msg.mode = "smile"
                msg.duration_ms = action.get_action_duration()
                msg.use_as_default = False
                self.publisher_head_smile.publish(msg)

            except Empty:
                break

class HeadMovementExecutor():
    def __init__(self, logger, node):
        return

    # This is likely called during from the audio sample request loop.  As such
    # do minimal processing and avoid delaying the current thread
    def pre_process(self, action):
        return

    def complete_pending(self):
        return

def create_action_executors(logger, node):
    executors = {}
    executors[ActionCategory.Smile] = SmileActionExecutor(logger, node)
    executors[ActionCategory.HeadMovement] = HeadMovementExecutor(logger, node)
    return executors