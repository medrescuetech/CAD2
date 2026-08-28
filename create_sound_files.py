import os
import wave
import struct
import math

def create_silent_wav(filename, duration=0.5, sample_rate=44100):
    """Create a silent WAV file with the specified duration."""
    # Ensure the sounds directory exists
    os.makedirs('static/sounds', exist_ok=True)
    
    # Create a silent audio buffer
    n_frames = int(sample_rate * duration)
    silent = [0] * n_frames
    
    # Write the WAV file
    with wave.open(f'static/sounds/{filename}', 'w') as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)   # 2 bytes per sample (16-bit)
        wf.setframerate(sample_rate)
        
        # Convert to bytes and write
        for sample in silent:
            data = struct.pack('<h', int(sample * 32767.0))
            wf.writeframesraw(data)

# Create all required sound files
sound_files = [
    'incident_notification.mp3',
    'unit_notification.mp3',
    'system_notification.mp3',
    'notification.mp3',
    'alarm.mp3'
]

for sound_file in sound_files:
    print(f'Creating {sound_file}...')
    create_silent_wav(sound_file)

print('\nAll sound files created successfully in static/sounds/')
