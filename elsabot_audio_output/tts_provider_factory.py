import os

from .tts_provider_local import TTSProviderLocal
from .tts_provider_ms import TTSProviderMicrosoft

def create_tts_provider(logger):
    provider_type = os.getenv('TTS_PROVIDER_TYPE', 'local')
    if provider_type == 'local':
      return TTSProviderLocal(logger)
    elif provider_type == 'ms_cognitive_speech':
      return TTSProviderMicrosoft(logger)
    else:
      raise ValueError("Invalid TTS_PROVIDER_TYPE env value specified") 
