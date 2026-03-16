import os

from .tts_provider_http_piper import TTSProviderHTTPPiper
from .tts_provider_ms import TTSProviderMicrosoft

def create_tts_provider(logger):
    #provider_type = os.getenv('TTS_PROVIDER_TYPE', 'local_piper')
    provider_type = os.getenv('TTS_PROVIDER_TYPE', 'ms_cognitive_speech')
    if provider_type == 'local_piper':
      return TTSProviderHTTPPiper(logger)
    elif provider_type == 'ms_cognitive_speech':
      return TTSProviderMicrosoft(logger)
    else:
      raise ValueError("Invalid TTS_PROVIDER_TYPE env value specified") 
