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

        voice = "en-US-JennyNeural"
        style = "chat"
        rate = "-15"
        pitch = "21"
        contour = "(0%, +0%) (100%, +0%)"

        ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">'
                    f'<voice name="{voice}">'
                        f'<mstts:express-as style="{style}">'
                            f'<prosody rate="{rate}%" pitch="{pitch}%" contour="{contour}">'
                                f'{text}'
                            f'</prosody>'
                        f'</mstts:express-as>'
                    f'</voice>'
                f'</speak>')

        result = self.speech_synthesizer.speak_ssml_async(ssml).get()

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
