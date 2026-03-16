import os
import io
import numpy as np
import soundfile as sf
import azure.cognitiveservices.speech as speechsdk

from .tts_provider import TTSProvider

class TTSProviderMicrosoft(TTSProvider):
    def __init__(self, logger):
        TTSProvider.__init__(self, logger, 'ms_cognitive_speech')

        key = os.getenv('MS_COGNTIVE_SUB_KEY') 
        region = os.getenv('MS_COGNTIVE_SUB_REGION')
        voice = os.getenv('MS_VOICE_NAME', 'en-US-JennyNeural')

        self.sample_rate = 44100  
        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Raw44100Hz16BitMonoPcm)
        speech_config.speech_synthesis_voice_name = voice

        self.speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

    def request_tts(self, text):
        result = self.speech_synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            audio_data = result.audio_data
            self.logger.debug(f'TTS conversion okay, len {len(audio_data)}')

            audio_data = np.frombuffer(result.audio_data, dtype=np.int16)

            tts_io_buf = io.BytesIO()
            tts_io_buf.name = 'tts.wav'
            sf.write(tts_io_buf, audio_data, self.sample_rate)
            return tts_io_buf

        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            error_msg = cancellation_details.error_details if cancellation_details.reason == speechsdk.CancellationReason.Error else None
            self.logger.error(f'TTS canceled: {cancellation_details.reason}, error: {error_msg}')

        return None
