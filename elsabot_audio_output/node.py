import rclpy
from rclpy.node import Node

from elsabot_audio_output_interfaces.srv import PlayTTS, PlayAudioFile, CancelAudio, PauseAudio, ResumeAudio
from elsabot_audio_output_interfaces.msg import StreamType
from std_msgs.msg import Bool, String

from .audio_output import AudioOutput, AudioType
from .actions import create_action_executors

from .tts_converter import TTSConverter

import os
import io
import base64
from queue import Queue, Empty
import numpy as np
import soundfile as sf
from threading import Timer

class ElsabotAudioOutput(Node):
    def __init__(self):
        super().__init__('elsabot_audio_output')

        self.declare_parameter('audio_device_name', 'ReSpeaker')
        audio_device_name = self.get_parameter('audio_device_name').get_parameter_value().string_value

        self.tts_srv = self.create_service(PlayTTS, 'play_tts', self.tts_service_callback)
        self.audio_srv = self.create_service(PlayAudioFile, 'play_audio', self.audio_service_callback)
        self.cancel_srv = self.create_service(CancelAudio, 'cancel_audio', self.cancel_service_callback)
        self.pause_srv = self.create_service(PauseAudio, 'pause_audio', self.pause_service_callback)
        self.resume_srv = self.create_service(ResumeAudio, 'resume_audio', self.resume_service_callback)

        self.publisher_head_speaking = self.create_publisher(Bool, '/head/speaking', 10)
        self.publisher_fg_status = self.create_publisher(String, '/audio_output/status/fg', 10)
        self.publisher_bg_status = self.create_publisher(String, '/audio_output/status/bg', 10)
        self.publisher_tts_status = self.create_publisher(String, '/audio_output/status/tts', 10)

        self.audio_output = AudioOutput(self.get_logger(), self.action_cb, audio_device_name)
        self.audio_output.start()

        self.action_executors = create_action_executors(self.get_logger(), self)

        self.tts = TTSConverter(self.get_logger(), self.audio_output)

        self.set_status_timer()

    def __del__(self):
        self.audio_output.stop()

    def set_status_timer(self):
        self.timer = Timer(0.1, self.report_status)
        self.timer.start()

    def publish_channel_status(self, status, pub):
        msg = String()
        if status == AudioType.TTS:
            msg.data = 'tts'
        elif status == AudioType.File:
            msg.data = 'file'
        else:
            msg.data = 'none'                
        pub.publish(msg)

    def publish_tts_status(self, status):
        msg = String()
        if status["fg"] == AudioType.TTS or \
           status["bg"] == AudioType.TTS or \
           self.tts.is_processing():
            msg.data = "active"
        else:
            msg.data = "inactive"
        self.publisher_tts_status.publish(msg)

    def report_status(self):
        status = self.audio_output.get_audio_type()

        self.publish_channel_status(status["fg"], self.publisher_fg_status)
        self.publish_channel_status(status["bg"], self.publisher_bg_status)

        self.publish_tts_status(status)

        # Legacy support for Head node
        msg = Bool()
        msg.data = status["fg"]["type"] == AudioType.TTS
        self.publisher_head_speaking.publish(msg)

        # Fix - trigger calling these by an event instead of timer based
        for _, executor in self.action_executors.items():
            executor.complete_pending()

        self.set_status_timer()

    def action_cb(self, action):
        if action is None:
            return
        # This should queue up the processing to avoid holding up the calling thread
        self.action_executors[action.get_action_category()].pre_process(action)

    def pause_service_callback(self, request, response):
        if request.stream_type.stream_type == StreamType.STREAM_TYPE_FG:
            self.audio_output.pause_fg()
            strm = 'fg'
        elif request.stream_type.stream_type == StreamType.STREAM_TYPE_BG:
            self.audio_output.pause_bg()
            strm = 'bg'
        else:
            self.get_logger().error(f'Pause: invalid stream type {request.stream_type}')                
            response.result = "failed"
            return response

        self.get_logger().info(f'Pause: {strm}')
        response.result = "success"
        return response

    def resume_service_callback(self, request, response):
        if request.stream_type.stream_type == StreamType.STREAM_TYPE_FG:
            self.audio_output.resume_fg()
            strm = 'fg'
        elif request.stream_type.stream_type == StreamType.STREAM_TYPE_BG:
            self.audio_output.resume_bg()
            strm = 'bg'
        else:
            self.get_logger().error(f'Resume: invalid stream type {request.stream_type}')                
            response.result = "failed"
            return response

        self.get_logger().info(f'Resume: {strm}')
        response.result = "success"
        return response

    def cancel_service_callback(self, request, response):
        self.tts.cancel(request.req_id);
        self.audio_output.cancel(request.req_id);

        response.result = "success"
        self.get_logger().info(f'Cancel request: req_id={request.req_id}. Returning: {response.result}')
        return response

    def tts_service_callback(self, request, response):
        response.result = self.tts.convert(request.tts_req.text, request.req_id)
        self.get_logger().info(f'TTS request: text={request.tts_req.text}, '\
                               f'req_id={request.req_id}. Returning: {response.result}')
        return response

    def audio_service_callback(self, request, response):
        self.get_logger().info(f'Incoming Audio request: file_path={request.audio_req.file_path}, '\
                               f'stream_type={request.stream_type.stream_type}, req_id={request.req_id}')

        stream_type = "bg"
        if request.stream_type.stream_type == StreamType.STREAM_TYPE_FG:
            stream_type = "fg"

        if len(request.audio_req.file_path) > 0:
            try:
                data, samplerate = sf.read(request.audio_req.file_path)

            except Exception as ex:
                response.result = "file not found: " + request.audio_req.file_path + ", " + str(ex)
                return response
        else:
            try:
                encoded_bytes_from_string = request.audio_req.base64_audio.encode('utf-8')
                decoded_bytes = base64.b64decode(encoded_bytes_from_string, validate=True)
                audio_file = io.BytesIO(decoded_bytes)
                data, samplerate = sf.read(audio_file)

            except Exception as ex:
                response.result = "Invalid base64 audio, " + str(ex)
                return response

        self.audio_output.add_to_queue(stream_type, data, samplerate, AudioType.File, request.req_id,
                                       None, source_channels=data.ndim)
        response.result = "success"
        return response

def main(args=None):
    rclpy.init(args=args)
    server_node = ElsabotAudioOutput()

    rclpy.spin(server_node)
    server_node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()