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

class AudioQueue:
    def __init__(self):
        self.queue = queue.Queue()
        self.cur_item = None
        self.cur_audio_type = None
        self.cur_req_id = None
        self.cur_item_offset = 0

        self.cancel_list = []
        self.cancel_list_lock = threading.Lock()

    def put(self, data, audio_type, req_id):
        self.queue.put((data, audio_type, req_id))

    def get(self, req_size):
        out_size = 0
        data = None
        audio_type = None
        try:
            while(True):
                if self.cur_item == None:
                    self.cur_item, self.cur_audio_type, self.cur_req_id = self.queue.get_nowait()
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
        new_list = []
        with self.cancel_list_lock:
            for id, remaining_cks in self.cancel_list:
                if req_id == id:
                    drop = True
                    print(f"drop {req_id}  remaining {remaining_cks}")
                if remaining_cks > 1:
                    new_list.append((id, remaining_cks - 1))
            self.cancel_list = new_list                    
        return drop            

    def cancel(self, req_id):
        with self.cancel_list_lock:
            self.cancel_list.append((req_id, self.queue.qsize()))

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
            print("Changing sample rate")
            num_samples = int(len(processed) * self.rate / source_rate)
            processed = np.interp(
                np.linspace(0, len(processed), num_samples),
                np.arange(len(processed)),
                processed
            ).astype(np.float32)

        # Convert to Stereo
        if source_channels == 1:
            print("Changing num channels")
            processed = np.column_stack((processed, processed))
        elif source_channels == 2 and processed.ndim == 1:
            print("Reshape channels")
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
