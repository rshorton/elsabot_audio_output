import os
import io
from pathlib import Path
import hashlib
import soundfile as sf

class TTSProvider:
    def __init__(self, logger, name):
        self.logger = logger
        self.name = name
        self.cache_enabled = os.getenv('TTS_CACHE_ENABLED', False)
        self.cache_dir = Path(os.getenv('TTS_CACHE_DIR', './speech_wav_cache/'))
        if self.cache_enabled:
            os.makedirs(self.cache_dir, exist_ok=True)

    def get_cache_fname(self, text):
        m = hashlib.md5()
        m.update(text.encode('utf-8'))
        md5_sum = m.hexdigest()
        fname = md5_sum + '_tts.wav'
        path = self.cache_dir / fname
        print(f"get_cache_name: {path}")
        return path

    def cache_put(self, text, audio, sample_rate):
        fpath = self.get_cache_fname(text)
        sf.write(fpath, audio, sample_rate)

    def cache_get(self, fpath):
        try:
            return sf.read(fpath)
        except Exception as e:
            self.logger.debug(f'Cached TTS not avail: {fpath}, {e}')
            pass
        return None, None

    def convert(self, text, req_id):
        self.logger.debug(f'TTSProvider convert, text: {text}')

        audio = None
        if self.cache_enabled:
            fpath = self.get_cache_fname(text)
            audio, sample_rate = self.cache_get(fpath)    

        if audio is None:
            # Perform the text to speech conversion.
            # An io buf is used to return an object that can be
            # read using soundfile.  Since the provider may receive
            # a wav file from the actual TTS service, the provider
            # will not always know the sample rate without processing
            # the wav file.  As such, the provider saves what it gets
            # to a file in memory, and then lets soundfile read that
            # here to get the audio sample and the sample rate.
            tts_io_buf = self.request_tts(text)
            if tts_io_buf is None:
                return None, None
            self.logger.debug(f'TTSProvider convert, using converted text')
            tts_io_buf.seek(0)
            audio, sample_rate = sf.read(tts_io_buf)

            if self.cache_enabled:
                self.cache_put(text, audio, sample_rate)
        else:
            self.logger.debug(f'TTSProvider convert, using cached text')

        return audio, sample_rate





