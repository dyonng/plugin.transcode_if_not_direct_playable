#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    plugins.plugin.transcode_if_not_direct_playable.py

    Written by:               dyonng

    Copyright:
        Copyright (C) 2026 dyonng

        This program is free software: you can redistribute it and/or modify
        it under the terms of the GNU General Public License as published by
        the Free Software Foundation, either version 3 of the License, or
        (at your option) any later version.

        This program is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU General Public License for more details.

        You should have received a copy of the GNU General Public License
        along with this program.  If not, see <https://www.gnu.org/licenses/>.

    Queues a file for transcoding ONLY when its video is not directly
    playable on modern clients (Shield TV, Google TV, desktop browsers):

      - containers that clients won't direct play (AVI, WMV, FLV, ...)
      - legacy video codecs (MPEG-4 Part 2, MPEG-1/2, VC-1, AV1, ...)
      - H.264 that is not 8-bit 4:2:0 (Hi10P and friends - no hardware
        decoder exists for these)

    Deliberately leaves alone anything that direct plays:

      - HEVC (including Main 10 / HDR - always skipped)
      - 8-bit H.264 (yuv420p)
      - VP9 (hardware-decoded on all modern clients)

    Place this plugin FIRST in the library File Test flow, ahead of the
    Transcode Video Files plugin. Unmanic stops at the first definitive
    answer, so files answered False here never reach the transcoder.

"""

import json
import os
import subprocess

from unmanic.libs.unplugins.settings import PluginSettings


class Settings(PluginSettings):
    settings = {
        "transcode_codecs":   "mpeg4,msmpeg4,msmpeg4v2,msmpeg4v3,mpeg1video,mpeg2video,vc1,vp8,theora,av1",
        "process_containers": "avi,wmv,flv,ogm,ts,m2ts,mov",
        "transcode_non_8bit_h264": True,
        "process_hevc":            False,
    }

    form_settings = {
        "transcode_codecs": {
            "label":       "Video codecs to transcode (comma separated)",
            "input_type":  "textbox",
            "description": "Files whose video codec is in this list are queued. HEVC is never queued unless 'Process HEVC' is enabled below.",
        },
        "process_containers": {
            "label":       "Containers to always process (comma separated, no dots)",
            "input_type":  "textbox",
            "description": "Files in these containers are queued regardless of codec (e.g. AVI never direct plays).",
        },
        "transcode_non_8bit_h264": {
            "label":       "Transcode non-8-bit H.264 (Hi10P etc.)",
            "input_type":  "checkbox",
            "description": "H.264 with anything other than yuv420p has no hardware decoder. Uncheck to leave it alone.",
        },
        "process_hevc": {
            "label":       "Process HEVC as well (NOT recommended)",
            "input_type":  "checkbox",
            "description": "HEVC Main 10 direct plays on modern clients. Only enable if a client cannot play it.",
        },
    }


def _ffprobe(path):
    """Probe the file. Returns parsed ffprobe JSON dict, or None."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_name,codec_type,pix_fmt,width,height:stream_disposition=attached_pic",
             "-show_entries", "format=format_name,duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=120)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except Exception:
        return None


def _setting_list(settings, key):
    return [v.strip().lower() for v in
            str(settings.get_setting(key) or "").split(",") if v.strip()]


def on_library_management_file_test(data, file_metadata=None):
    """
    Runner function - enables additional actions during the library management file tests.

    :param data:
    :return:
    """
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    abspath = data.get('path')
    if not abspath or not os.path.isfile(abspath):
        return

    def skip(reason):
        data['add_file_to_pending_tasks'] = False
        data['issues'].append({
            'id':      'Transcode If Not Direct Playable',
            'message': "File '{}' is direct playable ({}). Skipping.".format(abspath, reason),
        })

    def needs_work(reason):
        # Definitive True: Unmanic stops here and queues the file.
        # (No issues entry: issues are only meaningful when declining.)
        data['add_file_to_pending_tasks'] = True

    # 1. Container check - these never direct play, regardless of codec
    ext = os.path.splitext(abspath)[1].lower().lstrip(".")
    if ext in _setting_list(settings, 'process_containers'):
        needs_work("container .{} is not direct playable".format(ext))
        return data

    # 2. Probe streams
    probe = _ffprobe(abspath)
    if not probe or not probe.get('streams'):
        # Cannot determine - decline rather than risk queueing something
        # that has nothing to fix (e.g. audio-only files).
        skip("probe failed or unreadable")
        return data

    # Cover art (mjpeg/png/bmp) common in music files is not real video
    COVER_ART_CODECS = {'mjpeg', 'png', 'bmp', 'gif', 'webp'}
    video_streams = [
        s for s in probe.get('streams', [])
        if s.get('codec_type') == 'video'
        and int(s.get('disposition', {}).get('attached_pic', 0) or 0) != 1
        and str(s.get('codec_name', '') or '').lower() not in COVER_ART_CODECS
    ]
    if not video_streams:
        # Audio-only file, or only embedded cover art. Nothing to fix.
        skip("audio-only / no real video stream")
        return data

    stream = video_streams[0]
    codec = str(stream.get('codec_name', '') or '').lower()
    pix_fmt = str(stream.get('pix_fmt', '') or '').lower()

    # 3. Legacy / software-only codecs always need work
    if codec in _setting_list(settings, 'transcode_codecs'):
        needs_work("video codec '{}' is not direct playable".format(codec or 'unknown'))
        return data

    # 4. H.264 is only direct playable in 8-bit 4:2:0
    if codec == 'h264':
        if pix_fmt and pix_fmt != 'yuv420p':
            if settings.get_setting('transcode_non_8bit_h264'):
                needs_work("H.264 with pixel format '{}' has no hardware decoder".format(pix_fmt))
                return data
        skip("8-bit H.264 direct plays")
        return data

    # 5. HEVC direct plays on modern clients - leave it alone
    if codec in ('hevc', 'h265'):
        if settings.get_setting('process_hevc'):
            needs_work("HEVC processing explicitly enabled")
        else:
            skip("HEVC direct plays")
        return data

    # 6. VP9 is hardware-decoded everywhere modern - leave it alone
    if codec == 'vp9':
        skip("VP9 direct plays")
        return data

    # 7. Anything unrecognised: assume it needs work rather than
    #    silently leaving an unplayable file in the library
    needs_work("unknown video codec '{}'".format(codec or 'missing'))
    return data
