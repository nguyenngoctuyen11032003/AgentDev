import shutil
import sys
from pathlib import Path
import ast
import subprocess
import tempfile
from agentdev.utils.code_execution import require_unsafe_code_execution

def _get_class_names(py_file: str) -> list[str]:
    file_path = Path(py_file)
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

def render_manim(
    script_path: str,
    quality: str = "h",
    preview: bool = True,
) -> Path:
    require_unsafe_code_execution("render_manim")
    # Render into a folder of its own: the old code deleted <cwd>/media, which can be the user's own folder.
    output_dir = Path(tempfile.mkdtemp(prefix="manim-media-"))
    script_path = Path(script_path).resolve()
    if not script_path.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
        raise FileNotFoundError(script_path, " does not exist.")
    scene_name = _get_class_names(str(script_path))[0]
    cmd = [
        sys.executable, "-m", "manim",
        f"-pq{quality}",
    ]

    if preview:
        cmd.insert(3, "-p")

    cmd.extend(["--media_dir", str(output_dir), str(script_path), scene_name])

    print("Running:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        print("Manim rendering failed:")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        error_info = f"Error rendering {scene_name} from {script_path}: {e.stderr}"
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError(error_info)

    # Final video only: skip the partial_movie_files that manim keeps next to it
    video_file = None
    for mp4_file in output_dir.rglob("*.mp4"):
        if mp4_file.name == f"{scene_name}.mp4" and "partial_movie_files" not in mp4_file.parts:
            video_file = mp4_file
            break
    if video_file is None:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError(f"Manim finished but produced no {scene_name}.mp4")

    target_path = script_path.parent / video_file.name
    print(f"Copying video to {target_path}")
    shutil.copy2(video_file, target_path)
    shutil.rmtree(output_dir, ignore_errors=True)
    return target_path

def concat_videos(video_paths: list[Path]) -> Path:
    if not video_paths:
        raise ValueError("No video files to concatenate")

    video_paths = [Path(p).resolve() for p in video_paths]
    output_path = video_paths[0].parent / "combined_video.mp4"

    # utf-8 (accented folder names); a quote in a path must be escaped for ffmpeg's concat list
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in video_paths:
            escaped = p.as_posix().replace("'", "'\\''")  # ffmpeg concat quoting: ' -> '\''
            f.write(f"file '{escaped}'\n")
        list_file = f.name

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True)
    finally:
        Path(list_file).unlink(missing_ok=True)
    return output_path
