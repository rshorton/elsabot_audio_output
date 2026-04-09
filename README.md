# Elsabot Audio Output Processor

This package implements a ROS2 node that implements Elsabot-specific audio output processing which includes these features:
* Text-to-speech output generation using local or cloud-based (Microsoft Speech services) TTS services (see below).  
* Audio file playback
* Foreground and background streams to allow mixing of audio files with TTS output
* Publishing to the /head/speaking topic for triggering the Head node to indicate speaking using the face LEDs
* Publishing to the /audio_output/* topics for indicating status
* Translation of emojis in the TTS input to robot actions including:
  * Face smile level based on emoji face types
  * (Future) Head movements

These services are implemented by this node:
* play_tts_service - used to convert and play TTS text
* play_audio_service - used to play an audio file (from file or specified base64 data)
* cancel_audio_service - used to cancel TTS or audio playback.  A specific TTS/audio playback can be cancelled or all playing/queued.
* pause_audio_service - used to pause TTS or audio playback
* resume_audio_service - used to resume TTS or audio playback

The following can be specified when issuing a request to play TTS or audio:
* Output stream - foreground/background
* Request ID - used to identify the playback instance.  This ID can be specified to the cancel_audio_service to cancel a specific playback instance.

The TTS provider is selected and configured using environment variables:
  * For local TTS (defaults if no env vars specified):

```
 export TTS_PROVIDER_TYPE=local
 export TTS_LOCAL_URL='http://localhost:5000'
 export TTS_LOCAL_TIMEOUT=10
```
  * For Microsoft cloud-based:
```
 export TTS_PROVIDER_TYPE=ms_cognitive_speech
 export MS_COGNTIVE_SUB_KEY=<subscription key>
 export MS_COGNTIVE_SUB_REGION=<region>
```

For local TTS, the current implementation of this node expects a Piper TTS server interface where a JSON request of this form is used:

```
{"text": "the text to convert to speech"}
```

The current implementation of the local TTS processor is implemented using a Docker container (for Nvidia Jetson) that hosts the Piper TTS package.  See the jetson_support repo for the docker file and script run_stt_tts.py used to start that container.  You can specify the input device and host/port via arguments.
          

