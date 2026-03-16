import rclpy
from rclpy.node import Node
from elsabot_audio_output_interfaces.srv import PlayTTS, PlayAudioFile
from elsabot_audio_output_interfaces.msg import StreamType

from .audio_output import AudioOutput
from .tts_converter import TTSConverter

import os
import numpy as np
import soundfile as sf

class AudioOutputServerNode(Node):
    def __init__(self):
        super().__init__('audio_output_server_node')

        self.tts_srv = self.create_service(PlayTTS, 'tts_service', self.tts_service_callback)
        self.audio_srv = self.create_service(PlayAudioFile, 'audio_service', self.audio_service_callback)

        self.audio_output = AudioOutput()
        self.audio_output.start()

        self.tts = TTSConverter(self.get_logger(), self.audio_output)

    def __del__(self):
        self.audio_output.stop()

    def tts_service_callback(self, request, response):
        response.result = self.tts.convert(request.tts_req.text, request.req_id)
        self.get_logger().info(f'TTS request: text={request.tts_req.text}, req_id={request.req_id}. Returning: {response.result}')
        return response

    def audio_service_callback(self, request, response):
        self.get_logger().info(f'Incoming Audio request: file_path={request.audio_req.file_path}, stream_type={request.stream_type}, req_id={request.req_id}')

        stream_type = "bg"
        if request.stream_type == StreamType.STREAM_TYPE_FG:
            stream_type = "fg"
        try:
            data, samplerate = sf.read(request.audio_req.file_path)
        except Exception as ex:
            response.result = "file not found: " + request.audio_req.file_path + ", " + ex

        self.audio_output.add_to_queue(stream_type, data, source_rate=samplerate)
        response.result = "ok"

        return response

def main(args=None):
    rclpy.init(args=args)
    server_node = AudioOutputServerNode()

    rclpy.spin(server_node)
    server_node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()