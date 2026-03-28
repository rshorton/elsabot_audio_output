import os
import io
import json
import requests

from .tts_provider import TTSProvider

class TTSProviderHTTPPiper(TTSProvider):
    def __init__(self, logger):
        TTSProvider.__init__(self, logger, 'local_piper')
      
        self.tts_url = os.getenv('TTS_PIPER_URL', 'http://localhost:5000') 
        self.tts_timeout = os.getenv('TTS_PIPER_TIMEOUT', 10)
  
    def request_tts(self, text):
        req_data = {"text": text}

        try:
            self.logger.debug(f"TTS Piper making request: {req_data}")
            response = requests.post(self.tts_url, json=req_data, timeout=self.tts_timeout)
            self.logger.debug(f"TTS Piper response status: {response.status_code}, size {len(response.content)}")
            if response.status_code == 200:
                tts_io_buf = io.BytesIO()
                tts_io_buf.name = 'tts.wav'
                tts_io_buf.write(response.content)
                return tts_io_buf

        except requests.exceptions.ConnectTimeout:
            self.logger.error(f'TTS Piper conversion failed, connection timed out')

        except requests.exceptions.ReadTimeout:
            self.logger.error(f'TTS Piper conversion failed, read timed out')

        except Exception as e:
            self.logger.error(f'TTS Piper conversion failed, ex: {e}')

        return None
