import json
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from fluxfile import Engine, compatible_targets
from extended_formats import media_command

class ExtendedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = Engine()

    def test_jsonl_roundtrip(self):
        src = self.root / 'rows.jsonl'
        src.write_text('{"name":"a","value":1}\n{"name":"b","value":2}\n')
        mid = self.root / 'rows.xlsx'
        out = self.root / 'result.jsonl'
        self.engine.convert(src, mid)
        self.engine.convert(mid, out)
        self.assertEqual([json.loads(s) for s in out.read_text().splitlines()], [{'name':'a','value':1},{'name':'b','value':2}])

    def test_subtitle_roundtrip(self):
        src = self.root / 'captions.srt'
        src.write_text('1\n00:00:01,100 --> 00:00:02,200\nhello\n')
        mid = self.root / 'captions.vtt'
        out = self.root / 'result.srt'
        self.engine.convert(src, mid)
        self.engine.convert(mid, out)
        self.assertIn('00:00:01,100 --> 00:00:02,200\nhello', out.read_text())

    def test_archives_preserve_files_and_empty_directories(self):
        src = self.root / 'files.zip'
        with zipfile.ZipFile(src, 'w') as z:
            z.writestr('folder/a.txt', 'hello')
            z.writestr('empty/', '')
        for fmt in ['tar','tgz','tbz2','txz']:
            mid = self.root / ('files.' + fmt)
            out = self.root / ('roundtrip-' + fmt + '.zip')
            self.engine.convert(src, mid)
            self.engine.convert(mid, out)
            with zipfile.ZipFile(out) as z:
                self.assertEqual(z.read('folder/a.txt'), b'hello')
                self.assertIn('empty/', z.namelist())

    def test_archive_refuses_windows_unsafe_paths_and_aliases(self):
        source = self.root / "unsafe.zip"
        output = self.root / "safe.tar"
        output.write_bytes(b"existing output")
        for names, reason in (
            (["aux.txt"], "Unsafe archive member path"),
            (["folder /a.txt"], "Unsafe archive member path"),
            (["folder/data.txt", "./folder//data.txt"], "duplicate paths"),
            (["DATA.txt", "data.txt"], "duplicate paths"),
            (["Folder", "folder/child.txt"], "used as a parent"),
        ):
            with self.subTest(names=names):
                with zipfile.ZipFile(source, "w") as archive:
                    for name in names:
                        archive.writestr(name, "example")
                with self.assertRaisesRegex(ValueError, reason):
                    self.engine.convert(source, output)
                self.assertEqual(output.read_bytes(), b"existing output")

    def test_archive_refuses_zip_special_files(self):
        source = self.root / "special.zip"
        output = self.root / "safe.tar"
        with zipfile.ZipFile(source, "w") as archive:
            entry = zipfile.ZipInfo("pipe")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFIFO | 0o644) << 16
            archive.writestr(entry, b"")
        with self.assertRaisesRegex(ValueError, "special files"):
            self.engine.convert(source, output)
        self.assertFalse(output.exists())

    def test_tar_root_and_dot_prefix_repack_with_portable_names(self):
        source = self.root / "original.tar"
        output = self.root / "repacked.zip"
        with tarfile.open(source, "w") as archive:
            root = tarfile.TarInfo(".")
            root.type = tarfile.DIRTYPE
            archive.addfile(root)
            archive.addfile(tarfile.TarInfo("./folder//data.txt"))
        self.engine.convert(source, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ["folder/data.txt"])

    def test_compound_archive_suffix(self):
        src = self.root / 'files.tar.gz'
        with tarfile.open(src, 'w:gz') as archive:
            import io
            info = tarfile.TarInfo('readme.txt')
            info.size = 5
            archive.addfile(info, io.BytesIO(b'hello'))
        out = self.root / 'files.zip'
        self.engine.convert(src, out)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(archive.read('readme.txt'), b'hello')

    def test_icon_and_image_outputs(self):
        from PIL import Image
        src = self.root / 'image.png'
        Image.new('RGB', (64,64), 'red').save(src)
        for fmt in ['ico', 'ppm', 'tga']:
            out = self.root / ('image.' + fmt)
            self.engine.convert(src, out)
            with Image.open(out) as image:
                self.assertEqual(image.size, (64,64))

    def test_unsafe_archive_does_not_replace_output(self):
        src = self.root / 'unsafe.zip'
        with zipfile.ZipFile(src, 'w') as z: z.writestr('../escape', 'bad')
        out = self.root / 'keep.tar'
        out.write_bytes(b'original')
        with self.assertRaises(ValueError): self.engine.convert(src, out)
        self.assertEqual(out.read_bytes(), b'original')

    def test_pdf_pages_preserved_and_single_image_loss_refused(self):
        import pymupdf
        from PIL import Image
        src = self.root / 'pages.pdf'
        with pymupdf.open() as doc:
            doc.new_page().insert_text((30,30),'first')
            doc.new_page().insert_text((30,30),'second')
            doc.save(src)
        out = self.root / 'pages.tiff'
        self.engine.convert(src, out)
        with Image.open(out) as image: self.assertEqual(image.n_frames, 2)
        with self.assertRaisesRegex(RuntimeError, 'Multi-page'): self.engine.convert(src, self.root/'pages.png')
        self.engine.convert(src, self.root/'pages.html')
        self.assertIn('second', (self.root/'pages.html').read_text())

    def test_animation_preserved_and_loss_refused(self):
        from PIL import Image
        src = self.root/'animated.gif'
        frames = [Image.new('RGB',(32,32),color) for color in ['red','blue']]
        frames[0].save(src,save_all=True,append_images=frames[1:],duration=120,loop=0)
        out = self.root/'animated.webp'
        self.engine.convert(src,out)
        with Image.open(out) as im: self.assertEqual(im.n_frames,2)
        with self.assertRaisesRegex(RuntimeError,'Multi-frame'): self.engine.convert(src,self.root/'animated.jpg')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg unavailable')
    def test_real_audio_and_video_conversion(self):
        src = self.root/'tone.wav'
        with wave.open(str(src),'wb') as w:
            w.setparams((1,2,44100,0,'NONE','not compressed'))
            w.writeframes(b'\0\0'*44100)
        for fmt in ['mp3','flac','ogg','opus','m4a','aac','aiff']:
            out = self.root/('audio.'+fmt)
            self.engine.convert(src,out)
            self.assertGreater(out.stat().st_size,0)
        for fmt in ("au", "caf", "mka"):
            with self.subTest(audio_format=fmt):
                encoded = self.root / f"tone.{fmt}"
                decoded = self.root / f"decoded-{fmt}.wav"
                self.assertEqual(self.engine.convert(src, encoded), "ffmpeg")
                self.assertEqual(self.engine.convert(encoded, decoded), "ffmpeg")
                with wave.open(str(decoded), "rb") as audio:
                    self.assertEqual(audio.getnframes(), 44100)
                    self.assertEqual(audio.readframes(44100), b"\0\0" * 44100)

        video = self.root/'source.mp4'
        subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','color=c=blue:s=32x32:d=1','-i',str(src),'-shortest','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
        transport_stream = self.root / "camera.m2ts"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(video), "-c", "copy",
             "-f", "mpegts", str(transport_stream)],
            check=True,
        )
        self.assertEqual(self.engine.convert(transport_stream, self.root / "camera.mp4"), "ffmpeg")

        for fmt in ['mkv','mov','avi','webm','gif','mp3']:
            out = self.root/('video.'+fmt)
            self.engine.convert(video,out)
            self.assertGreater(out.stat().st_size,0)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools unavailable")
    def test_media_preflight_preserves_output_and_allows_audio_extraction(self):
        video = self.root / "silent.mp4"
        mixed = self.root / "with-audio.mp4"
        output = self.root / "result.mp3"
        subprocess.run([
            "ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=s=32x32:d=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
        ], check=True)
        subprocess.run([
            "ffmpeg", "-loglevel", "error", "-i", str(video),
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "copy", "-c:a", "aac", str(mixed),
        ], check=True)
        output.write_bytes(b"existing output")
        with self.assertRaisesRegex(RuntimeError, "No audio stream"):
            self.engine.convert(video, output)
        self.assertEqual(output.read_bytes(), b"existing output")

        self.engine._media_encoders = set()
        with self.assertRaisesRegex(RuntimeError, "missing required encoder.*libmp3lame"):
            self.engine.convert(mixed, output)
        self.assertEqual(output.read_bytes(), b"existing output")

        self.engine._media_encoders = None
        self.assertEqual(self.engine.convert(mixed, output), "ffmpeg")
        pcm = subprocess.check_output([
            "ffmpeg", "-loglevel", "error", "-i", str(output), "-f", "s16le", "-",
        ])
        self.assertTrue(any(pcm))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools unavailable")
    def test_media_does_not_follow_http_playlist_references(self):
        playlist = self.root / "playlist.m3u8"
        playlist.write_text(
            "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n"
            "http://127.0.0.1:9/segment.ts\n#EXT-X-ENDLIST\n",
            encoding="utf-8",
        )
        output = self.root / "audio.mp3"
        with self.assertRaisesRegex(RuntimeError, "not on whitelist"):
            self.engine._preflight_media(playlist, "mp3", None)
        with self.assertRaisesRegex(RuntimeError, "not on whitelist"):
            self.engine._run(media_command(self.engine.ffmpeg, playlist, output))
        self.assertFalse(output.exists())

    def test_svg_local_render_and_external_reference_rejected(self):
        if not self.engine.capabilities()['cairosvg']: self.skipTest('CairoSVG unavailable')
        src=self.root/'shape.svg'
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="blue"/></svg>')
        for fmt in ['png','pdf']: self.engine.convert(src,self.root/('shape.'+fmt))
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/passwd"/></svg>')
        with self.assertRaisesRegex(ValueError,'External'): self.engine.convert(src,self.root/'bad.png')

if __name__ == '__main__': unittest.main()
