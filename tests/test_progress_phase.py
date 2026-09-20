from jav_downloader.web.progress_phase import phase_from_log


def test_phase_from_clip_download():
    parsed = phase_from_log('Clip 2: downloading segments…')
    assert parsed == ('Downloading', 'Clip 2 · segments')


def test_phase_from_encoding():
    parsed = phase_from_log(
        'Encoding… H.264 CRF 28 · 480p · slow · 16 thread(s)')
    assert parsed == (
        'Encoding',
        'H.264 CRF 28 · 480p · slow · 16 thread(s)',
    )


def test_phase_strips_timestamp():
    parsed = phase_from_log('[2:15:20 PM] Found 1436 segments')
    assert parsed == ('Segments found', '1436')
