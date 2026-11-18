from pathlib import Path
import shutil
import tempfile
import unittest
from pivoki_studio import media

@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"ffmpeg and ffprobe required")
class LocalVideo(unittest.TestCase):
    def test_silent_vp9_becomes_h264_and_mask_ends_at_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/"input.mp4"
            media.invoke(["ffmpeg","-v","error","-f","lavfi","-i","color=white:s=128x96:r=10:d=2",
                          "-c:v","libvpx-vp9","-an",str(source)])
            result=root/"mac.mp4"
            media.encode(source,result,mode="quicktime")
            streams=media.inspect(result)
            self.assertEqual(streams[0]["codec_name"],"h264")
            self.assertIsNone(streams[1])
            masked=root/"mask.mp4"
            media.encode(source,masked,mode="mask",start=0.5,end=1.3,
                         points=[(.2,.25),(.8,.25),(.8,.75),(.2,.75)],angle=45)
            def brightness(t):
                frame=media.invoke(["ffmpeg","-v","error","-ss",str(t),"-i",str(masked),"-frames:v","1",
                                    "-vf","crop=2:2:64:48","-f","rawvideo","-pix_fmt","rgb24","-"])
                return frame[0]
            self.assertGreater(brightness(0.3),230)
            self.assertLess(brightness(0.7),25)
            self.assertGreater(brightness(1.3),230)
            compare=root/"comparison.mp4"
            media.comparison(result,compare,0.2,1)
            self.assertGreater(media.inspect(compare)[0]["width"],800)
