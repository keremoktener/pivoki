"""Offline ffmpeg operations for local files. Subprocess arguments are passed directly."""
from pathlib import Path
import json
import math
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw

from .files import tool


def invoke(args):
    result = subprocess.run(args, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        error = result.stderr.decode("utf-8","replace").strip().splitlines()
        raise ValueError(error[-1] if error else "Medya işlemi tamamlanamadı.")
    return result.stdout


def inspect(path):
    info = json.loads(invoke([tool("ffprobe"),"-v","error","-show_format","-show_streams","-of","json",str(path)]))
    streams = info.get("streams", [])
    video = next((s for s in streams if s["codec_type"] == "video" and not s.get("disposition",{}).get("attached_pic")),None)
    if not video:
        raise ValueError("Okunabilir video akışı bulunamadı.")
    audio = next((s for s in streams if s["codec_type"] == "audio"),None)
    return video, audio, float(info["format"].get("duration",0))


def mask_layer(size, points, angle):
    width, height = size
    if not points or len(set(points)) < 3 or any(not 0<=n<=1 for point in points for n in point):
        raise ValueError("Maske için 0–1 aralığında en az üç farklı nokta girin.")
    vertices = [(x*width,y*height) for x,y in points]
    if angle:
        cx=sum(x for x,y in vertices)/len(vertices)
        cy=sum(y for x,y in vertices)/len(vertices)
        r=math.radians(angle)
        vertices=[(cx+(x-cx)*math.cos(r)-(y-cy)*math.sin(r),
                   cy+(x-cx)*math.sin(r)+(y-cy)*math.cos(r)) for x,y in vertices]
    mask = Image.new("RGBA",size)
    ImageDraw.Draw(mask).polygon(vertices,fill="black")
    return mask


def encode(source, target, *, mode, mb=10, start=0, end=None, points=None, angle=0):
    v,a,duration = inspect(source)
    if duration <= 0:
        raise ValueError("Video süresi okunamadı.")
    audio_rate = 96000
    args = [tool("ffmpeg"),"-v","error","-nostdin","-y"]
    if mode == "sample":
        if not 0 <= start < duration:
            raise ValueError("Sahne zamanı video süresinin içinde olmalı.")
        args += ["-ss",str(start)]
    args += ["-i",str(source)]
    streams = ["-map",f"0:{v['index']}"]
    if a:
        streams += ["-map",f"0:{a['index']}"]
    output = []
    if mode in {"target","sample"}:
        rate = int(mb*1_000_000*8*0.97/duration) - (audio_rate if a else 0)
        if rate < 16000:
            raise ValueError("Hedef boyut bu süre ve ses için çok küçük.")
        if mode == "sample":
            output += ["-t",str(min(3,duration-start))]
        output += ["-c:v","libx264","-b:v",str(rate),"-maxrate",str(rate*2),"-bufsize",str(rate*4)]
    elif mode == "quicktime":
        copy = v.get("codec_name") == "h264" and v.get("pix_fmt") in {"yuv420p","yuvj420p"}
        output += ["-c:v","copy" if copy else "libx264"]
    elif mode == "mask":
        if end is None or not 0 <= start < end <= duration:
            raise ValueError("Maskenin zaman aralığını kontrol edin.")
        width,height = v["width"], v["height"]
        if any(abs(int(s.get("rotation",0))) % 180 == 90 for s in v.get("side_data_list",[])):
            width,height = height,width
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp,"mask.png")
            mask = mask_layer((width,height), points, angle)
            mask.save(overlay)
            args += ["-i",str(overlay),"-filter_complex",
                     f"[0:{v['index']}][1:v]overlay=enable='gte(t,{start})*lt(t,{end})'[masked]",
                     "-map","[masked]"]
            if a:
                args += ["-map",f"0:{a['index']}"]
            invoke(args+["-c:v","libx264","-c:a","aac","-movflags","+faststart",str(target)])
            inspect(target)
            return
    else:
        raise ValueError("Bilinmeyen medya işlemi.")
    if "copy" not in output:
        output += ["-vf","pad=ceil(iw/2)*2:ceil(ih/2)*2","-pix_fmt","yuv420p"]
    if a:
        output += ["-c:a","copy"] if mode == "quicktime" and a["codec_name"]=="aac" else ["-c:a","aac","-b:a",str(audio_rate)]
    invoke(args+streams+output+["-movflags","+faststart",str(target)])
    new_video,new_audio,_ = inspect(target)
    if new_video["codec_name"]!="h264" or bool(a)!=bool(new_audio) or (new_audio and new_audio["codec_name"]!="aac"):
        raise ValueError("MP4 akışları doğrulanamadı.")


def comparison(source, target, start, mb):
    with tempfile.TemporaryDirectory() as tmp:
        sample = Path(tmp,"sample.mp4")
        encode(source,sample,mode="sample",start=start,mb=mb)
        invoke([tool("ffmpeg"),"-v","error","-nostdin","-y","-ss",str(start),"-i",str(source),
                "-i",str(sample),"-filter_complex",
                "[0:v]scale=-2:360,setsar=1[a];[1:v]scale=-2:360,setsar=1[b];[a][b]hstack=shortest=1[out]",
                "-map","[out]","-t","3","-an","-c:v","libx264","-pix_fmt","yuv420p",str(target)])
