from piper import PiperVoice
import pyaudio # Assuming you are using pyaudio for playback

# Load the model
voice = PiperVoice.load("en_US-lessac-medium.onnx")
text_to_speak = "Hello! I am now speaking to you in real time..."

# Setup PyAudio stream (Piper outputs 16-bit mono PCM, typically at 16000Hz or 22050Hz)
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=voice.config.sample_rate, 
                output=True)

print("Playing text...")
# This will now correctly stream the raw bytes
for audio_bytes in voice.synthesize_stream_raw(text_to_speak):
    stream.write(audio_bytes)

stream.stop_stream()
stream.close()
p.terminate()