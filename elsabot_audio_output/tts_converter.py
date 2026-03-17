import threading
import queue
import requests

from .audio_output import AudioType
from .tts_provider_factory import create_tts_provider

class TTSConverter():
  def __init__(self, logger, audio_output):
      self.logger = logger
      self.audio_output = audio_output

      self.queue = queue.Queue()
      self.tts_provider = create_tts_provider(logger)

      self.cancel_list = []
      self.cancel_list_lock = threading.Lock()

      self.processing = False

      self.run = True

      self.worker_thread = threading.Thread(target=self._worker, daemon=True)
      self.worker_thread.start()

  def __del__(self):
      self.run = False
      self.worker_thread.join()

  def convert(self, text, req_id):
      self.queue.put((text, req_id))
      return "queued"

  def cancel(self, req_id):
      with self.cancel_list_lock:
          self.cancel_list.append((req_id, self.queue.qsize()))

  def is_processing(self):
      return self.queue.qsize() > 0 or self.processing

  def should_drop(self, req_id):
      drop = False
      new_list = []
      with self.cancel_list_lock:
          for id, remaining_cks in self.cancel_list:
              if req_id == id:
                  drop = True
              self.logger.info(f'TTS conversion, should_drop, drop={drop}, remaining_cks={remaining_cks}')
              if remaining_cks > 1:
                  new_list.append((id, remaining_cks - 1))
          self.cancel_list = new_list                    
      return drop            

  def _worker(self):
      while self.run:
          self.processing = False

          # Blocks until an item is available in the queue
          text, req_id = self.queue.get()
          self.processing = True

          if self.should_drop(req_id):
              self.logger.info(f'TTS conversion dropped, req_id={req_id}')
              continue
          
          audio, sample_rate = self.tts_provider.convert(text, req_id)
          if audio is None:
              self.logger.error(f'TTS conversion failed, req_id={req_id}')
          else:
              self.logger.info(f'TTS conversion completed, req_id={req_id}')
              if self.should_drop(req_id):
                  self.logger.info(f'TTS conversion canceled, req_id={req_id}')
                  continue

              self.audio_output.add_to_queue('fg', audio, sample_rate, AudioType.TTS, req_id)
