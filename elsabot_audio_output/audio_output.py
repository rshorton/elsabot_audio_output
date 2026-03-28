import pyaudio
import numpy as np
import queue
import threading
import time
from enum import Enum

# class syntax
class AudioType(Enum):
    TTS = 1
    File = 2

class QueueItemType(Enum):
    CancelMarker = 1
    Data = 2

class QueueItem:
    def __init__(self, type):
        self.type = type

class QueueItemData:
    def __init__(self, data, audio_type, req_id):
        QueueItem.__init__(self, QueueItemType.Data)
        self.data = data
        self.audio_type = audio_type
        self.req_id = req_id

class QueueItemCancelMarker:
    def __init__(self, marker_id):
        QueueItem.__init__(self, QueueItemType.CancelMarker)
        self.marker_id = marker_id

class AudioQueue:
    def __init__(self):
        self.queue = queue.Queue()
        self.cur_item = None
        self.cur_audio_type = None
        self.cur_req_id = None
        self.cur_item_offset = 0

        self.cancel_list = []
        self.cancel_list_lock = threading.Lock()
        self.cancel_marker_id = 0

    def put(self, data, audio_type, req_id):
        self.queue.put(QueueItemData(data, audio_type, req_id))

    def get(self, req_size):
        out_size = 0
        data = None
        audio_type = None
        try:
            while(True):
                if self.cur_item == None:
                    item = self.queue.get_nowait()
                    self.queue.task_done()

                    if item.type == QueueItemType.CancelMarker:
                        self.retire_cancel_request(item.marker_id)
                        continue

                    self.cur_item = item.data
                    self.cur_audio_type = item.audio_type
                    self.cur_req_id = item.req_id
                    self.cur_item_offset = 0

                if self.should_drop(self.cur_req_id):
                    # Probably should decay last sample to zero here to avoid a pop
                    self.cur_item = None
                    continue

                avail = len(self.cur_item) - self.cur_item_offset
                out_size = avail if avail < req_size else req_size

                data = self.cur_item[self.cur_item_offset : self.cur_item_offset + out_size]

                self.cur_item_offset += out_size
                if len(self.cur_item) - self.cur_item_offset <= 0:
                    self.cur_item = None
                audio_type = self.cur_audio_type
                break

        except queue.Empty:
            pass
        return out_size, data, audio_type

    def should_drop(self, req_id):
        drop = False
        with self.cancel_list_lock:
            for id, _ in self.cancel_list:
                #print(f'checking cancel item: req_id: {req_id} id: {id}')
                if id == "all" or req_id == id:
                    drop = True
                    #print(f"dropping {req_id}")
                    break
        return drop            

    def cancel(self, req_id):
        # Do actual dropping during the read path.  Add id to the list of
        # items to cancel.  Use a marker entry in the data queue to know
        # when to retire this cancel request.
        with self.cancel_list_lock:
            self.cancel_marker_id += 1
            self.cancel_list.append((req_id, self.cancel_marker_id))
            self.queue.put(QueueItemCancelMarker(self.cancel_marker_id))            

    def retire_cancel_request(self, marker_id_to_retire):
        with self.cancel_list_lock:
            new_list = []
            for req_id, marker_id in self.cancel_list:
                if marker_id != marker_id_to_retire:
                    new_list.append((req_id, marker_id))
            self.cancel_list = new_list

class AudioOutput:
    def __init__(self, device_name=None, rate=44100):
        self.device_name = device_name
        self.rate = rate
        self.channels = 2
        self.format = pyaudio.paFloat32
        
        # Two independent input queues.  One for TTS audio, the other for other audio such as from wav files.
        self.queue_fg = AudioQueue()
        self.queue_bg = AudioQueue()
        
        self.paused = False
        self.p = pyaudio.PyAudio()
        self.stream = None

        self.fg_audio_type = None
        self.bg_audio_type = None

    def _get_chunk_from_queue(self, q, bytes_needed):
        audio_type = None
        data = bytearray()

        needed = bytes_needed
        while len(data) < needed:
            size, chunk, audio_type = q.get(needed)

            if size > 0:
                data.extend(chunk)
                needed -= size
            else:
              break

        if len(data) < bytes_needed:
            # Fill remaining needed space with silence
            data.extend(b'\x00' * (bytes_needed - len(data)))

        return (bytes(data[:bytes_needed]), audio_type)

    def _callback(self, in_data, frame_count, time_info, status):

        if False:
            if status & pyaudio.paOutputUnderflow:
                print('underflow')
            if status & pyaudio.paOutputOverflow:
                print('overflow')
            if status & pyaudio.paPrimingOutput:
                print('priming')

        # Calculate bytes for: frames * 2 channels * 4 bytes (float32)
        bytes_needed = frame_count * self.channels * 4
        
        # Pull data from both queues
        if self.paused:
            data = bytearray(bytes_needed)
            arr = np.frombuffer(data, dtype=np.float32)
            self.fg_audio_type = None
            self.bg_audio_type = None
            return (arr.tobytes(), pyaudio.paContinue)
        else:
            raw_a, self.fg_audio_type = self._get_chunk_from_queue(self.queue_fg, bytes_needed)
            raw_b, self.bg_audio_type = self._get_chunk_from_queue(self.queue_bg, bytes_needed)

        # Convert raw bytes back to numpy arrays for mixing
        arr_a = np.frombuffer(raw_a, dtype=np.float32)
        arr_b = np.frombuffer(raw_b, dtype=np.float32)

        # Mix: Sum the signals. 
        # Note: 0.5 gain prevents clipping if both signals are at max volume.
        mixed = (arr_a * 0.5) + (arr_b * 0.5)

        return (mixed.tobytes(), pyaudio.paContinue)

    def add_to_queue(self, q_name, audio_data, source_rate, audio_type, req_id, source_channels=1):
        target_q = self.queue_fg if q_name.lower() == 'fg' else self.queue_bg
        
        processed = np.array(audio_data, dtype=np.float32)

        # Resample
        if source_rate != self.rate:
            num_samples = int(len(processed) * self.rate / source_rate)

            original_len = len(processed)

            # 1. Define the 'old' and 'new' x-coordinates (indices)
            # Use - 1 to ensure the new points fit exactly within the old range
            old_indices = np.arange(original_len)
            new_indices = np.linspace(0, original_len - 1, num_samples)

            # 2. Apply interpolation across the first axis (rows)
            # This processes each column independently
            resampled = np.apply_along_axis(
                lambda col: np.interp(new_indices, old_indices, col),
                axis=0,
                arr=processed
            )
            processed = resampled.astype(np.float32)

        # Convert to Stereo
        if source_channels == 1:
            processed = np.column_stack((processed, processed))
        elif source_channels == 2 and processed.ndim == 1:
            processed = processed.reshape(-1, 2)

        target_q.put(processed.tobytes(), audio_type, req_id)

    def cancel(self, req_id):
        self.queue_fg.cancel(req_id)
        self.queue_bg.cancel(req_id)

    def start(self):

        info = self.p.get_default_output_device_info()
        print(f'def audio dev info: {info}')

        output_device_index = None
        if self.device_name is not None:
            for i in range(self.p.get_device_count()):
                info = self.p.get_device_info_by_index(i)
                if self.device_name in info['name'] and info['maxOutputChannels'] > 0:
                    output_device_index = info['index']
                    break

        self.stream = self.p.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            output=True,
            output_device_index=output_device_index,
            stream_callback=self._callback
        )

    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def get_audio_type(self):
        return {'fg': self.fg_audio_type, 'bg': self.bg_audio_type}
