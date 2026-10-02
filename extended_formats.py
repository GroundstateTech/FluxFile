"""Additional local conversion engines shared by the desktop planner."""
from pathlib import Path
import re

AUDIO = {'mp3', 'wav', 'flac', 'ogg', 'opus', 'm4a', 'aac', 'aiff', 'wma'}
VIDEO = {'mp4', 'mkv', 'mov', 'avi', 'webm', 'mpeg', 'mpg', 'm4v', 'wmv', 'flv', 'ts'}
MEDIA_TARGETS = ['mp4', 'mkv', 'mov', 'avi', 'webm', 'gif']
AUDIO_TARGETS = ['mp3', 'wav', 'flac', 'ogg', 'opus', 'm4a', 'aac', 'aiff']
EXTRA_IMAGES = {'ico', 'icns', 'ppm', 'pgm', 'pbm', 'tga', 'avif', 'dds'}
IMAGE_OUTPUTS = ['ico', 'icns', 'ppm', 'tga', 'avif']


def media_command(ffmpeg, source, output):
    target = output.suffix.lower().lstrip('.')
    command = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source)]
    if target in AUDIO_TARGETS:
        command += ['-map', '0:a:0', '-vn']
        codecs = {'mp3': 'libmp3lame', 'wav': 'pcm_s16le', 'flac': 'flac',
                  'ogg': 'libvorbis', 'opus': 'libopus', 'm4a': 'aac', 'aac': 'aac', 'aiff': 'pcm_s16be'}
        command += ['-c:a', codecs[target]]
    elif target == 'gif':
        command += ['-map', '0:v:0', '-vf', 'fps=12,scale=640:-1:flags=lanczos', '-an']
    else:
        command += ['-map', '0:v:0', '-map', '0:a:0?', '-sn']
        command += (['-c:v', 'libvpx-vp9', '-c:a', 'libopus'] if target == 'webm'
                    else ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac'])
        # H.264 needs even dimensions; preserve aspect ratio with padding.
        if target != 'webm':
            command += ['-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2']
        if target in {'mp4', 'mov'}:
            command += ['-movflags', '+faststart']
    return command + [str(output)]


def convert_subtitles(source: Path, output: Path):
    text = source.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    if source.suffix.lower() == '.srt':
        blocks = []
        for block in re.split(r'\n\s*\n', text.strip()):
            lines = block.splitlines()
            if lines and lines[0].strip().isdigit():
                lines.pop(0)
            if not lines or '-->' not in lines[0]:
                raise ValueError('Invalid SRT cue')
            lines[0] = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', lines[0])
            blocks.append('\n'.join(lines))
        output.write_text('WEBVTT\n\n' + '\n\n'.join(blocks) + '\n', encoding='utf-8')
    else:
        if not text.startswith('WEBVTT'):
            raise ValueError('Invalid WebVTT header')
        cues = []
        for block in re.split(r'\n\s*\n', text.strip())[1:]:
            lines = block.splitlines()
            if not lines or lines[0].startswith(('NOTE', 'STYLE', 'REGION')):
                continue
            timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
            if timing is None:
                continue
            raw = lines[timing].split('-->')
            def stamp(value):
                value = value.strip().split()[0]
                if value.count(':') == 1:
                    value = '00:' + value
                if not re.fullmatch(r'\d{2,}:\d{2}:\d{2}\.\d{3}', value):
                    raise ValueError('Unsupported WebVTT timestamp')
                return value.replace('.', ',')
            cues.append(f'{len(cues)+1}\n{stamp(raw[0])} --> {stamp(raw[1])}\n' + '\n'.join(lines[timing+1:]))
        if not cues:
            raise ValueError('No subtitle cues found')
        output.write_text('\n\n'.join(cues) + '\n', encoding='utf-8')

ARCHIVES = {'zip', 'tar', 'tgz', 'tbz2', 'txz'}

def repack_archive(source: Path, output: Path):
    """Repack regular files without extracting paths, links, or devices to disk."""
    import contextlib
    import tarfile
    import zipfile
    limit = 512 * 1024 * 1024
    total = 0
    names = set()
    with contextlib.ExitStack() as stack:
        if source.suffix.lower() == '.zip':
            reader = stack.enter_context(zipfile.ZipFile(source))
            items = reader.infolist()
            import stat
            if any(stat.S_ISLNK(m.external_attr >> 16) for m in items):
                raise ValueError("Archive contains links; repacking refused")
            members = [(m.filename, m.file_size, m.is_dir(), m) for m in items]
            opener = reader.open
        else:
            reader = stack.enter_context(tarfile.open(source))
            items = reader.getmembers()
            if any(not (m.isfile() or m.isdir()) for m in items):
                raise ValueError('Archive contains links or special files; repacking refused')
            members = [(m.name, m.size, m.isdir(), m) for m in items]
            opener = reader.extractfile
        if len(members) > 10000:
            raise ValueError('Archive exceeds 10,000 entries')
        for name, size, directory, member in members:
            path = name.replace('\\', '/')
            if path.startswith('/') or ':' in path or '..' in path.split('/'):
                raise ValueError('Unsafe archive member path')
            if path in names:
                raise ValueError('Archive contains duplicate paths')
            names.add(path)
            total += size
        if total > limit:
            raise ValueError('Archive exceeds 512 MiB expanded size')
        if output.suffix == '.zip':
            writer = stack.enter_context(zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED))
        else:
            mode = {'.tar': 'w', '.tgz': 'w:gz', '.tbz2': 'w:bz2', '.txz': 'w:xz'}[output.suffix]
            writer = stack.enter_context(tarfile.open(output, mode))
        for name, size, directory, member in members:
            name = name.replace('\\', '/')
            if directory:
                if isinstance(writer, zipfile.ZipFile):
                    writer.writestr(name.rstrip('/') + '/', b'')
                else:
                    info = tarfile.TarInfo(name)
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    writer.addfile(info)
                continue
            with opener(member) as data:
                if isinstance(writer, zipfile.ZipFile):
                    with writer.open(name, 'w') as target:
                        import shutil
                        shutil.copyfileobj(data, target)
                else:
                    info = tarfile.TarInfo(name)
                    info.size = size
                    info.mode = 0o644
                    writer.addfile(info, data)


def render_svg(source, output):
    import cairosvg
    from defusedxml import ElementTree
    text = source.read_text(encoding='utf-8-sig')
    root = ElementTree.fromstring(text)
    # Keep rendering local: reject file/network references and CSS imports.
    if re.search(r'@import', text, re.I):
        raise ValueError('External SVG stylesheet imports are unsupported')
    for node in root.iter():
        for key, value in node.attrib.items():
            if key.split('}')[-1] in {'href', 'src'} and not value.startswith('#'):
                raise ValueError('External SVG resources are unsupported; embed shapes directly')
    for match in re.finditer(r'url\((.*?)\)', text, re.I | re.S):
        if not match.group(1).strip(' \t\r\n\"\'').startswith('#'):
            raise ValueError('External SVG resources are unsupported')
    converter = cairosvg.svg2png if output.suffix == '.png' else cairosvg.svg2pdf
    converter(bytestring=text.encode('utf-8'), write_to=str(output), unsafe=False)
