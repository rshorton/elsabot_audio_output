import threading
import queue 
import requests
from enum import Enum
import regex
import emoji

from .audio_output import AudioType
from .tts_provider_factory import create_tts_provider
from .actions import create_actions_from_emoji, create_random_head_movement_action

class QueueItemType(Enum):
    CancelMarker = 1
    TTSReq = 2
    Action = 3

class QueueItem:
    def __init__(self, type):
        self.type = type

class QueueItemTTSReq:
    def __init__(self, text, req_id):
        QueueItem.__init__(self, QueueItemType.TTSReq)
        self.text = text
        self.req_id = req_id

class QueueItemCancelMarker:
    def __init__(self, marker_id):
        QueueItem.__init__(self, QueueItemType.CancelMarker)
        self.marker_id = marker_id

class QueueItemAction:
    def __init__(self, action, req_id):
        QueueItem.__init__(self, QueueItemType.Action)
        self.action = action
        self.req_id = req_id

class TTSConverter():
    def __init__(self, logger, audio_output):
        self.logger = logger
        self.audio_output = audio_output

        self.queue = queue.Queue()
        self.tts_provider = create_tts_provider(logger)

        # Fix - create common object that can be shared with audoi_output queue
        # for handling cancellation
        self.cancel_list = []
        self.cancel_list_lock = threading.Lock()
        self.cancel_marker_id = 0

        self.processing = False

        self.run = True

        self.worker_thread = threading.Thread(target=self._worker, daemon=False)
        self.worker_thread.start()

    def __del__(self):
        self.run = False
        self.worker_thread.join()

    # Translate emojis into robot face/head actions for conveying emotion
    def split_and_interpret_emojis(self, input_text, req_id):
        # \X matches a "Unicode grapheme cluster" (e.g., a complex emoji)
        # This keeps emojis with modifiers (like 👨‍👩‍👧‍👦) together.
        tokens = regex.findall(r'\X', input_text)

        punctuation_list = '?.,!'
        current_text = ""
        ch_cnt = 0
        
        for token in tokens:
            if emoji.is_emoji(token):
                actions = create_actions_from_emoji(token)
                if len(actions) > 0:
                    # If we have accumulated text prior to this emoji, then push it to the queue before
                    # the action (ignore whitespace in the text)
                    if current_text.strip():
                        self.logger.debug(f"text before emoji: {current_text}")
                        self.queue.put(QueueItemTTSReq(current_text, req_id))
                        current_text = ""

                    for action in actions:
                        self.queue.put(QueueItemAction(action, req_id))
            else:
                ch_cnt += 1
                if token in punctuation_list or ch_cnt >= 50:
                    action = create_random_head_movement_action()
                    print(f"req_id {req_id}")
                    self.queue.put(QueueItemAction(action, req_id))
                    ch_cnt = 0

                current_text += token
                
        # Add any remaining text at the end (ignore whitespace)
        if current_text.strip():
            self.logger.debug(f"remaining: {current_text}")
            self.queue.put(QueueItemTTSReq(current_text, req_id))

    def convert(self, text, req_id):
        self.logger.info(f"convert: {text}")
        self.split_and_interpret_emojis(text, req_id)
        return "queued"

    def cancel(self, req_id):
        # Do actual dropping during the read path.  Add id to the list of
        # items to cancel.  Use a marker entry in the data queue to know
        # when to retire this cancel request.
        with self.cancel_list_lock:
            self.cancel_marker_id += 1
            self.cancel_list.append((req_id, self.cancel_marker_id))
            self.queue.put(QueueItemCancelMarker(self.cancel_marker_id))            

    def should_drop(self, req_id):
        drop = False
        with self.cancel_list_lock:
            for id, _ in self.cancel_list:
                #print(f'TTSConverter, checking cancel item: req_id: {req_id} id: {id}')
                if id == "all" or req_id == id:
                    drop = True
                    #print(f"TTSConverter, dropping {req_id}")
                    break
            return drop            

    def is_processing(self):
        return self.queue.qsize() > 0 or self.processing

    def retire_cancel_request(self, marker_id_to_retire):
        with self.cancel_list_lock:
            new_list = []
            for req_id, marker_id in self.cancel_list:
                if marker_id != marker_id_to_retire:
                    new_list.append((req_id, marker_id))
            self.cancel_list = new_list

    def _worker(self):
        while self.run:
            self.processing = False

            # Blocks until an item is available in the queue
            item = self.queue.get()
            
            self.queue.task_done()
            if item.type == QueueItemType.CancelMarker:
                self.retire_cancel_request(item.marker_id)
                continue

            elif item.type == QueueItemType.Action:
                # Add action and associate with a period of silence (can be very short)
                self.audio_output.add_silence_to_queue('fg', AudioType.TTS, item.action.get_silence_duration(), item.req_id, item.action)
                self.logger.debug(f'TTSConverter added action to playback queue, req_id={item.req_id}')
                continue
            
            self.logger.debug(f"worker next job: type: {item.type}, text: {item.text}")                

            text = item.text
            req_id = item.req_id

            self.processing = True

            if self.should_drop(req_id):
                self.logger.info(f'TTSConverter dropped, req_id={req_id}')
                continue
          
            audio, sample_rate = self.tts_provider.convert(text, req_id)
            if audio is None:
                self.logger.error(f'TTSConverter failed, text= {text}, req_id={req_id}')
            else:
                self.logger.debug(f'TTSConverter completed, req_id={req_id}')
                if self.should_drop(req_id):
                    self.logger.debug(f'TTSConverter canceled, req_id={req_id}')
                    continue

                self.audio_output.add_to_queue('fg', audio, sample_rate, AudioType.TTS, req_id, None)
                self.logger.debug(f'TTSConverter added to playback queue, req_id={req_id}')
