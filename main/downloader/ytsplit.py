import os
import math
import subprocess

MAX_SIZE = 1950 * 1024 * 1024  # 1950MB

def get_video_duration(input_file):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return float(result.stdout)

def split_video(input_file, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    total_size = os.path.getsize(input_file)
    duration = get_video_duration(input_file)

    parts = math.ceil(total_size / MAX_SIZE)
    part_duration = duration / parts

    base_name = os.path.splitext(os.path.basename(input_file))[0]

    output_files = []

    for i in range(parts):
        start_time = i * part_duration
        output_file = os.path.join(
            output_dir,
            f"{base_name}_Part {str(i+1).zfill(2)}.mp4"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start_time),
            "-i", input_file,
            "-t", str(part_duration),
            "-c", "copy",
            output_file
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output_files.append(output_file)

    return output_files
