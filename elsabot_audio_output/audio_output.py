import pyaudio
import numpy as np
import queue
import time

class AudioQueue:
    def __init__(self):
        self.queue = queue.Queue()
        self.cur_item = None
        self.cur_item_offset = 0

    def put(self, data):
        self.queue.put(data)

    def get(self, req_size):
        out_size = 0
        data = None
        try:
            if self.cur_item == None:
                self.cur_item = self.queue.get_nowait()
                self.cur_item_offset = 0;

            avail = len(self.cur_item) - self.cur_item_offset
            out_size = avail if avail < req_size else req_size

            data = self.cur_item[self.cur_item_offset : self.cur_item_offset + out_size]

            self.cur_item_offset += out_size
            if len(self.cur_item) - self.cur_item_offset <= 0:
              self.cur_item = None

        except queue.Empty:
            pass
        return out_size, data

class AudioOutput:
    def __init__(self, device_name=None, rate=44100):
        self.device_name = device_name
        self.rate = rate
        self.channels = 2
        self.format = pyaudio.paFloat32
        
        # Two independent input queues.  One for TTS audio, the other for other audio such as from wav files.
        self.queue_fg = AudioQueue()
        self.queue_bg = AudioQueue()
        
        self.p = pyaudio.PyAudio()
        self.stream = None

    def _get_chunk_from_queue(self, q, bytes_needed):
        """Helper to pull and aggregate specific byte length from a queue."""
        data = bytearray()

        needed = bytes_needed
        while len(data) < needed:
            size, chunk = q.get(needed)

            if size > 0:
                data.extend(chunk)
                needed -= size
            else:
              break

        if len(data) < bytes_needed:
            # Fill remaining needed space with silence
            data.extend(b'\x00' * (bytes_needed - len(data)))

        return bytes(data[:bytes_needed])

    def _callback(self, in_data, frame_count, time_info, status):
        # Calculate bytes for: frames * 2 channels * 4 bytes (float32)
        bytes_needed = frame_count * self.channels * 4
        
        # Pull data from both queues
        raw_a = self._get_chunk_from_queue(self.queue_fg, bytes_needed)
        raw_b = self._get_chunk_from_queue(self.queue_bg, bytes_needed)

        # Convert raw bytes back to numpy arrays for mixing
        arr_a = np.frombuffer(raw_a, dtype=np.float32)
        arr_b = np.frombuffer(raw_b, dtype=np.float32)

        # Mix: Sum the signals. 
        # Note: 0.5 gain prevents clipping if both signals are at max volume.
        mixed = (arr_a * 0.5) + (arr_b * 0.5)

        return (mixed.tobytes(), pyaudio.paContinue)

    def add_to_queue(self, q_name, audio_data, source_rate, source_channels=1):
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

        target_q.put(processed.tobytes())

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

