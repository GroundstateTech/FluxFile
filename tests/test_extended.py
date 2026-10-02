import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from fluxfile import Engine, compatible_targets

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
        video = self.root/'source.mp4'
        subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','color=c=blue:s=32x32:d=1','-i',str(src),'-shortest','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
        for fmt in ['mkv','mov','avi','webm','gif','mp3']:
            out = self.root/('video.'+fmt)
            self.engine.convert(video,out)
            self.assertGreater(out.stat().st_size,0)

    def test_svg_local_render_and_external_reference_rejected(self):
        if not self.engine.capabilities()['cairosvg']: self.skipTest('CairoSVG unavailable')
        src=self.root/'shape.svg'
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="blue"/></svg>')
        for fmt in ['png','pdf']: self.engine.convert(src,self.root/('shape.'+fmt))
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/passwd"/></svg>')
        with self.assertRaisesRegex(ValueError,'External'): self.engine.convert(src,self.root/'bad.png')

if __name__ == '__main__': unittest.main()
