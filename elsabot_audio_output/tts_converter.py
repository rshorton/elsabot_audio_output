import threading
import queue
import requests

from .tts_provider_factory import create_tts_provider

class TTSConverter():
  def __init__(self, logger, audio_output):
      self.logger = logger
      self.audio_output = audio_output
      self.queue = queue.Queue()
      self.tts_provider = create_tts_provider(logger)

      self.run = True

      self.worker_thread = threading.Thread(target=self._worker, daemon=True)
      self.worker_thread.start()

  def __del__(self):
      self.run = False
      self.queue.join()

  def convert(self, text, req_id):
      self.queue.put((text, req_id))
      return "queued"

  def _worker(self):
      while self.run:
          # Blocks until an item is available in the queue
          text, req_id = self.queue.get()
          
          audio, sample_rate = self.tts_provider.convert(text, req_id)
          if audio is None:
              self.logger.error(f'TTS conversion failed, req_id={req_id}')
          else:
              self.logger.info(f'TTS conversion completed, req_id={req_id}')
              self.audio_output.add_to_queue('fg', audio, source_rate=sample_rate)

